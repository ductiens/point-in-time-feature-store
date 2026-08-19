from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import fakeredis
import pytest

from pit_feature_store.catalog import CATALOG_PATH
from pit_feature_store.offline_engine import build_offline_features
from pit_feature_store.online_engine import replay_warehouse
from pit_feature_store.parity import run_parity


EXPECTED_FEATURE_NAMES = (
    "sum_amt_24h",
    "count_txn_24h",
    "sum_amt_7d",
    "time_since_last_txn_sec",
)
SAMPLE_SIZE = 64


@pytest.fixture
def parity_warehouse_path(tmp_path: Path) -> Path:
    database_path = tmp_path / "parity.duckdb"
    connection = duckdb.connect(database_path.as_posix())
    try:
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
        base_ts = datetime(2017, 12, 1)
        offsets = [
            0,
            1,
            24,
            25,
            168,
            169,
            720,
            721,
            744,
            888,
            889,
            1056,
            1057,
            1440,
            1440,
            1441,
        ]
        rows = []
        transaction_id = 1
        for entity_index in range(4):
            for event_index, offset_hours in enumerate(offsets):
                rows.append(
                    (
                        transaction_id,
                        f"entity-{entity_index}",
                        base_ts
                        + timedelta(
                            hours=offset_hours,
                            minutes=entity_index,
                        ),
                        (entity_index + 1) * 10.0 + event_index / 10.0,
                        transaction_id % 2,
                    )
                )
                transaction_id += 1
        connection.executemany(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        build_offline_features(connection, CATALOG_PATH)
    finally:
        connection.close()
    return database_path


def replay_for_parity(database_path: Path) -> fakeredis.FakeRedis:
    redis_client = fakeredis.FakeRedis()
    replay_warehouse(
        redis_client,
        database_path=database_path,
        catalog_path=CATALOG_PATH,
    )
    return redis_client


def test_offline_and_online_have_zero_mismatches_for_at_least_fifty_samples(
    parity_warehouse_path: Path,
) -> None:
    redis_client = replay_for_parity(parity_warehouse_path)

    result = run_parity(
        redis_client,
        database_path=parity_warehouse_path,
        catalog_path=CATALOG_PATH,
        sample_size=SAMPLE_SIZE,
    )

    assert result.sample_count == SAMPLE_SIZE
    assert result.sample_count >= 50
    assert result.feature_names == EXPECTED_FEATURE_NAMES
    assert result.comparison_count == SAMPLE_SIZE * len(EXPECTED_FEATURE_NAMES)
    assert result.mismatch_count == 0
    assert result.mismatches == ()


def test_parity_mismatch_contains_diagnostic_context(
    parity_warehouse_path: Path,
) -> None:
    redis_client = replay_for_parity(parity_warehouse_path)
    connection = duckdb.connect(parity_warehouse_path.as_posix())
    try:
        connection.execute(
            """
            UPDATE pit_features
            SET sum_amt_24h = sum_amt_24h + 1.0
            WHERE label_id = 1
            """
        )
    finally:
        connection.close()

    result = run_parity(
        redis_client,
        database_path=parity_warehouse_path,
        catalog_path=CATALOG_PATH,
        sample_size=SAMPLE_SIZE,
    )

    assert result.mismatch_count == 1
    mismatch = result.mismatches[0]
    assert mismatch.label_id == 1
    assert mismatch.uid == "entity-0"
    assert mismatch.cutoff_ts == datetime(2017, 12, 1)
    assert mismatch.feature_name == "sum_amt_24h"
    assert mismatch.offline_value == 1.0
    assert mismatch.online_value == 0.0
    assert mismatch.reason == "values_differ"
