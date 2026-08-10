from pathlib import Path

import duckdb
import pandas as pd
import pandas.testing as pdt

from pit_feature_store.catalog import CATALOG_PATH, load_catalog
from pit_feature_store.offline_engine import build_offline_features


BASE_TS = pd.Timestamp("2020-01-10 12:00:00")
EXPECTED_OBJECT_COLUMNS = {
    "label_spine": ["label_id", "uid", "cutoff_ts", "label"],
    "feature_events": ["uid", "feature_ts", "amount", "event_id"],
    "feature_cumsum": [
        "uid",
        "feature_ts",
        "amount",
        "event_id",
        "cumulative_amount",
        "cumulative_count",
    ],
    "pit_features": [
        "label_id",
        "uid",
        "cutoff_ts",
        "label",
        "sum_amt_24h",
        "count_txn_24h",
        "sum_amt_7d",
        "time_since_last_txn_sec",
    ],
}


def create_connection(rows: list[tuple]) -> duckdb.DuckDBPyConnection:
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
    build_offline_features(connection, CATALOG_PATH)
    return connection


def pandas_expected(rows: list[tuple]) -> pd.DataFrame:
    source = pd.DataFrame(
        rows,
        columns=["label_id", "uid", "cutoff_ts", "amount", "label"],
    )
    source["cutoff_ts"] = pd.to_datetime(source["cutoff_ts"])
    output: list[dict] = []

    for row in source.itertuples(index=False):
        history = source[
            source["uid"].notna()
            & (source["uid"] == row.uid)
            & (source["cutoff_ts"] < row.cutoff_ts)
        ]
        history_24h = history[
            history["cutoff_ts"] >= row.cutoff_ts - pd.Timedelta(hours=24)
        ]
        history_7d = history[
            history["cutoff_ts"] >= row.cutoff_ts - pd.Timedelta(hours=168)
        ]
        history_720h = history[
            history["cutoff_ts"] >= row.cutoff_ts - pd.Timedelta(hours=720)
        ]
        last_ts = (
            history_720h["cutoff_ts"].max()
            if not history_720h.empty
            else pd.NaT
        )
        output.append(
            {
                "label_id": row.label_id,
                "uid": row.uid,
                "cutoff_ts": row.cutoff_ts,
                "label": row.label,
                "sum_amt_24h": float(history_24h["amount"].sum()),
                "count_txn_24h": len(history_24h),
                "sum_amt_7d": float(history_7d["amount"].sum()),
                "time_since_last_txn_sec": (
                    float((row.cutoff_ts - last_ts).total_seconds())
                    if pd.notna(last_ts)
                    else float("nan")
                ),
            }
        )

    return pd.DataFrame(output).sort_values("label_id").reset_index(drop=True)


def test_offline_objects_have_separated_responsibilities() -> None:
    connection = create_connection(
        [(1, "entity-a", BASE_TS, 10.0, 0)]
    )
    try:
        for object_name, expected_columns in EXPECTED_OBJECT_COLUMNS.items():
            actual_columns = [
                row[0]
                for row in connection.sql(
                    f"DESCRIBE {object_name}"
                ).fetchall()
            ]
            assert actual_columns == expected_columns

        object_types = dict(
            connection.sql(
                """
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_name IN (
                    'label_spine',
                    'feature_events',
                    'feature_cumsum',
                    'pit_features'
                )
                """
            ).fetchall()
        )
        assert object_types == {
            "label_spine": "VIEW",
            "feature_events": "VIEW",
            "feature_cumsum": "VIEW",
            "pit_features": "BASE TABLE",
        }
    finally:
        connection.close()


def test_duckdb_features_match_manual_pandas_calculation() -> None:
    rows = [
        (1, "entity-a", BASE_TS - pd.Timedelta(hours=30), 5.0, 0),
        (2, "entity-a", BASE_TS - pd.Timedelta(hours=2), 10.0, 0),
        (3, "entity-a", BASE_TS - pd.Timedelta(hours=2), 20.0, 1),
        (4, "entity-b", BASE_TS - pd.Timedelta(hours=1), 100.0, 0),
        (5, "entity-a", BASE_TS, 40.0, 1),
        (6, "entity-b", BASE_TS, 200.0, 0),
        (7, None, BASE_TS, 300.0, 0),
    ]
    connection = create_connection(rows)
    try:
        actual = connection.sql(
            "SELECT * FROM pit_features ORDER BY label_id"
        ).df()
    finally:
        connection.close()

    expected = pandas_expected(rows)
    actual["cutoff_ts"] = pd.to_datetime(actual["cutoff_ts"])
    actual["label"] = actual["label"].astype("uint8")
    actual["count_txn_24h"] = actual["count_txn_24h"].astype("int64")
    pdt.assert_frame_equal(
        actual,
        expected,
        check_dtype=False,
        check_exact=False,
        rtol=1e-12,
    )


def test_pipeline_is_safe_to_run_again() -> None:
    connection = create_connection(
        [
            (1, "entity-a", BASE_TS - pd.Timedelta(hours=1), 10.0, 0),
            (2, "entity-a", BASE_TS, 20.0, 1),
        ]
    )
    try:
        first = connection.sql(
            "SELECT * FROM pit_features ORDER BY label_id"
        ).df()
        build_offline_features(connection, CATALOG_PATH)
        second = connection.sql(
            "SELECT * FROM pit_features ORDER BY label_id"
        ).df()
    finally:
        connection.close()

    pdt.assert_frame_equal(first, second)


def test_catalog_drives_output_feature_names(tmp_path: Path) -> None:
    catalog_path = tmp_path / "feature_catalog.yaml"
    catalog_path.write_text(
        """
version: "test"
features:
  - name: custom_sum_2h
    description: Test sum
    entity: uid
    aggregation: sum
    source_column: amount
    window_hours: 2
    event_time: event_ts
    version: "test"
    default_value: 0
""",
        encoding="utf-8",
    )
    assert load_catalog(catalog_path).features[0].name == "custom_sum_2h"

    connection = duckdb.connect()
    connection.execute(
        """
        CREATE TABLE transactions AS
        SELECT
            1::BIGINT AS transaction_id,
            'entity-a'::VARCHAR AS uid,
            TIMESTAMP '2020-01-01' AS event_ts,
            10.0::DOUBLE AS amount,
            0::UTINYINT AS label
        """
    )
    try:
        build_offline_features(connection, catalog_path)
        columns = [
            row[0]
            for row in connection.sql("DESCRIBE pit_features").fetchall()
        ]
    finally:
        connection.close()

    assert columns == [
        "label_id",
        "uid",
        "cutoff_ts",
        "label",
        "custom_sum_2h",
    ]
