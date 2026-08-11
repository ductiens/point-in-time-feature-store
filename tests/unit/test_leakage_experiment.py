import duckdb
import pandas as pd

from pit_feature_store.catalog import CATALOG_PATH, load_catalog
from pit_feature_store.leakage import (
    ObservationBounds,
    choose_split_timestamp,
    create_leaky_features,
    create_pit_plus_future_view,
    feature_names,
    find_observation_bounds,
    future_feature_names,
    load_feature_frame,
    prepare_experiment_frames,
    temporal_masks,
)
from pit_feature_store.offline_engine import build_offline_features


BASE_TS = pd.Timestamp("2020-01-10 12:00:00")


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


def test_prepare_experiment_frames_returns_aligned_engineering_datasets() -> None:
    event_hours = [0, 720, 800, 900, 1000, 1100, 1200, 1300, 1440, 2160]
    rows = [
        (
            index,
            "entity-a",
            BASE_TS + pd.Timedelta(hours=event_hour),
            float(index),
            index % 2,
        )
        for index, event_hour in enumerate(event_hours, start=1)
    ]
    connection = leakage_connection(rows)
    try:
        prepared = prepare_experiment_frames(
            connection,
            CATALOG_PATH,
            train_fraction=0.5,
        )
    finally:
        connection.close()

    frames = prepared["frames"]
    metadata_columns = ["label_id", "uid", "cutoff_ts", "label"]
    assert prepared["bounds"].eligible_rows == 8
    assert frames["pit"][metadata_columns].equals(
        frames["future_only"][metadata_columns]
    )
    assert frames["pit"][metadata_columns].equals(
        frames["pit_plus_future"][metadata_columns]
    )
    assert prepared["pit_columns"] == feature_names(load_catalog(CATALOG_PATH))
    assert prepared["future_columns"] == future_feature_names(
        load_catalog(CATALOG_PATH)
    )
    train_mask, test_mask = temporal_masks(frames["pit"], prepared["split_ts"])
    assert train_mask.any()
    assert test_mask.any()
