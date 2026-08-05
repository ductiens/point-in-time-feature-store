from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from catalog import FeatureCatalog, load_catalog
from leakage_experiment import (
    ObservationBounds,
    choose_split_timestamp,
    create_leaky_features,
    create_pit_plus_future_view,
    feature_names,
    find_observation_bounds,
    future_feature_names,
    load_feature_frame,
    temporal_masks,
    train_and_evaluate,
    write_reports,
)
from offline_engine import build_offline_features


BASE_TS = pd.Timestamp("2020-01-10 12:00:00")
CATALOG_PATH = Path("feature_catalog.yaml")


def leakage_connection(rows: list[tuple]) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    connection.execute(
        """
        CREATE TABLE transactions (
            transaction_id BIGINT,
            uid VARCHAR,
            event_ts TIMESTAMP,
            amount DOUBLE,
            label UTINYINT
        )
        """
    )
    connection.executemany(
        "INSERT INTO transactions VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    catalog = load_catalog(CATALOG_PATH)
    build_offline_features(connection, CATALOG_PATH)
    create_leaky_features(connection, catalog)
    create_pit_plus_future_view(connection, catalog)
    return connection


def test_leaky_features_use_only_future_and_respect_boundaries() -> None:
    rows = [
        (1, "entity-a", BASE_TS, 10.0, 0),
        (2, "entity-a", BASE_TS, 20.0, 1),
        (3, "entity-a", BASE_TS + pd.Timedelta(hours=24), 30.0, 0),
        (4, "entity-a", BASE_TS + pd.Timedelta(hours=24, seconds=1), 40.0, 0),
        (5, "entity-a", BASE_TS + pd.Timedelta(hours=168), 50.0, 1),
        (6, "entity-a", BASE_TS + pd.Timedelta(hours=168, seconds=1), 60.0, 0),
        (7, "entity-b", BASE_TS + pd.Timedelta(hours=1), 999.0, 0),
        (8, "entity-c", BASE_TS, 1.0, 0),
        (9, "entity-c", BASE_TS + pd.Timedelta(hours=720), 2.0, 1),
        (10, "entity-d", BASE_TS, 1.0, 0),
        (11, "entity-d", BASE_TS + pd.Timedelta(hours=720, seconds=1), 2.0, 1),
        (12, None, BASE_TS, 1000.0, 0),
    ]
    connection = leakage_connection(rows)
    try:
        entity_a = connection.sql(
            """
            SELECT
                sum_amt_24h,
                count_txn_24h,
                sum_amt_7d,
                time_since_last_txn_sec
            FROM leaky_features
            WHERE label_id = 1
            """
        ).fetchone()
        entity_c_last = connection.sql(
            "SELECT time_since_last_txn_sec FROM leaky_features WHERE label_id = 8"
        ).fetchone()[0]
        entity_d_last = connection.sql(
            "SELECT time_since_last_txn_sec FROM leaky_features WHERE label_id = 10"
        ).fetchone()[0]
        null_uid = connection.sql(
            """
            SELECT sum_amt_24h, count_txn_24h, sum_amt_7d,
                   time_since_last_txn_sec
            FROM leaky_features
            WHERE label_id = 12
            """
        ).fetchone()
    finally:
        connection.close()

    assert entity_a == (30.0, 1, 120.0, 24 * 3600.0)
    assert entity_c_last == 720 * 3600.0
    assert entity_d_last is None
    assert null_uid == (0.0, 0, 0.0, None)


def test_feature_views_have_spec_and_semantic_future_names() -> None:
    connection = leakage_connection(
        [
            (1, "entity-a", BASE_TS, 10.0, 0),
            (2, "entity-a", BASE_TS + pd.Timedelta(hours=1), 20.0, 1),
        ]
    )
    catalog = load_catalog(CATALOG_PATH)
    pit_columns = feature_names(catalog)
    future_columns = future_feature_names(catalog)
    try:
        leaky_columns = [
            row[0]
            for row in connection.sql("DESCRIBE leaky_features").fetchall()
        ]
        augmented_columns = [
            row[0]
            for row in connection.sql(
                "DESCRIBE pit_plus_future_features"
            ).fetchall()
        ]
    finally:
        connection.close()

    assert leaky_columns[4:] == pit_columns
    assert augmented_columns[4:] == [*pit_columns, *future_columns]
    assert future_columns == [
        "future_sum_amt_24h",
        "future_count_txn_24h",
        "future_sum_amt_7d",
        "time_to_next_txn_sec",
    ]


def test_complete_observation_filter_includes_both_boundaries() -> None:
    rows = [
        (1, "entity-a", BASE_TS, 1.0, 0),
        (2, "entity-a", BASE_TS + pd.Timedelta(hours=719), 1.0, 0),
        (3, "entity-a", BASE_TS + pd.Timedelta(hours=720), 1.0, 1),
        (4, "entity-a", BASE_TS + pd.Timedelta(hours=1000), 1.0, 0),
        (5, "entity-a", BASE_TS + pd.Timedelta(hours=1440), 1.0, 1),
        (6, "entity-a", BASE_TS + pd.Timedelta(hours=1441), 1.0, 0),
        (7, "entity-a", BASE_TS + pd.Timedelta(hours=2160), 1.0, 0),
    ]
    connection = leakage_connection(rows)
    catalog = load_catalog(CATALOG_PATH)
    try:
        bounds = find_observation_bounds(connection, catalog)
        frame = load_feature_frame(
            connection,
            "pit_features",
            feature_names(catalog),
            bounds,
        )
    finally:
        connection.close()

    assert bounds.start == BASE_TS + pd.Timedelta(hours=720)
    assert bounds.end == BASE_TS + pd.Timedelta(hours=1440)
    assert bounds.total_rows == 7
    assert bounds.eligible_rows == 3
    assert frame["label_id"].tolist() == [3, 4, 5]


def test_temporal_split_is_after_filter_and_keeps_equal_timestamps() -> None:
    frame = pd.DataFrame(
        {
            "cutoff_ts": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-01-02",
                    "2020-01-03",
                    "2020-01-03",
                    "2020-01-04",
                    "2020-01-05",
                ]
            )
        }
    )
    bounds = ObservationBounds(
        start=pd.Timestamp("2020-01-02"),
        end=pd.Timestamp("2020-01-04"),
        total_rows=6,
        eligible_rows=4,
    )
    connection = duckdb.connect()
    connection.register("split_source", frame)
    connection.execute(
        "CREATE TABLE pit_features AS SELECT cutoff_ts FROM split_source"
    )
    try:
        split_ts = choose_split_timestamp(
            connection, bounds, train_fraction=0.5
        )
    finally:
        connection.close()

    eligible = frame[
        (frame["cutoff_ts"] >= bounds.start)
        & (frame["cutoff_ts"] <= bounds.end)
    ]
    train_mask, test_mask = temporal_masks(eligible, split_ts)
    assert split_ts == pd.Timestamp("2020-01-03")
    assert set(eligible.loc[train_mask, "cutoff_ts"]).isdisjoint(
        set(eligible.loc[test_mask, "cutoff_ts"])
    )


def model_frame(offset: float) -> pd.DataFrame:
    row_count = 100
    labels = np.arange(row_count) % 2
    return pd.DataFrame(
        {
            "cutoff_ts": pd.date_range("2020-01-01", periods=row_count, freq="h"),
            "label": labels,
            "sum_amt_24h": labels + offset,
            "count_txn_24h": np.arange(row_count) % 5,
            "sum_amt_7d": np.arange(row_count, dtype=float),
            "time_since_last_txn_sec": np.where(
                np.arange(row_count) % 7 == 0,
                np.nan,
                3600.0,
            ),
        }
    )


def model_results(catalog: FeatureCatalog) -> list[dict]:
    pit_columns = feature_names(catalog)
    semantic_future_columns = future_feature_names(catalog)
    pit = model_frame(0.0)
    future = model_frame(1.0)
    augmented = pit.copy()
    for old_name, new_name in zip(pit_columns, semantic_future_columns):
        augmented[new_name] = future[old_name]

    bounds = ObservationBounds(
        start=pit["cutoff_ts"].min(),
        end=pit["cutoff_ts"].max(),
        total_rows=len(pit),
        eligible_rows=len(pit),
    )
    split_ts = pd.Timestamp("2020-01-04 08:00:00")
    return [
        train_and_evaluate(pit, pit_columns, split_ts, "pit", bounds),
        train_and_evaluate(
            future, pit_columns, split_ts, "future_only", bounds
        ),
        train_and_evaluate(
            augmented,
            [*pit_columns, *semantic_future_columns],
            split_ts,
            "pit_plus_future",
            bounds,
        ),
    ]


def test_three_models_share_split_and_report_pr_baseline() -> None:
    catalog = load_catalog(CATALOG_PATH)
    results = model_results(catalog)

    assert [result["dataset"] for result in results] == [
        "pit",
        "future_only",
        "pit_plus_future",
    ]
    assert all(result["train_rows"] == 80 for result in results)
    assert all(result["test_rows"] == 20 for result in results)
    assert all(result["test_fraud_rate"] == 0.5 for result in results)
    assert all(0.0 <= result["roc_auc"] <= 1.0 for result in results)
    assert all(0.0 <= result["pr_auc"] <= 1.0 for result in results)
    assert all(
        result["pr_auc_lift"] == result["pr_auc"] / 0.5
        for result in results
    )


def test_reports_contain_baseline_mapping_and_both_comparisons(
    tmp_path: Path,
) -> None:
    catalog = load_catalog(CATALOG_PATH)
    results = model_results(catalog)
    metrics_path = tmp_path / "leakage_metrics.csv"
    report_path = tmp_path / "leakage_experiment.md"
    write_reports(results, catalog, metrics_path, report_path)

    metrics = pd.read_csv(metrics_path)
    report = report_path.read_text(encoding="utf-8")
    assert metrics["dataset"].tolist() == [
        "pit",
        "future_only",
        "pit_plus_future",
    ]
    assert {
        "eligible_start",
        "eligible_end",
        "test_fraud_rate",
        "pr_auc_lift",
    }.issubset(metrics.columns)
    assert "time_to_next_txn_sec" in report
    assert "baseline ngẫu nhiên" in report
    assert "Phép thử kiểm soát" in report
    assert "Phép thử theo đặc tả" in report
    assert "không giả định trước" in report
