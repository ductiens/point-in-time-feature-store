from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from pit_feature_store.catalog import CATALOG_PATH
from pit_feature_store.offline_engine import build_offline_features


@pytest.fixture
def small_transactions_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    """Provide a small in-memory transaction warehouse for unit tests."""
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
        [
            (1, "entity-a", "2020-01-01 00:00:00", 10.0, 0),
            (2, "entity-a", "2020-01-01 01:00:00", 20.0, 1),
            (3, "entity-b", "2020-01-01 02:00:00", 30.0, 0),
        ],
    )
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def backfill_warehouse_path(tmp_path: Path) -> Path:
    """Create a small warehouse with a persistent full-pipeline reference."""
    database_path = tmp_path / "warehouse.duckdb"
    connection = duckdb.connect(database_path.as_posix())
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
        [
            (1, "entity-a", "2019-12-31 23:59:00", 1.0, 0),
            (2, "entity-a", "2020-01-01 00:00:00", 10.0, 0),
            (3, "entity-a", "2020-01-30 00:00:00", 20.0, 0),
            (4, "entity-a", "2020-01-31 00:00:00", 30.0, 1),
            (5, "entity-a", "2020-01-31 00:00:00", 5.0, 0),
            (6, "entity-a", "2020-01-31 12:00:00", 40.0, 0),
            (7, "entity-b", "2020-01-31 12:00:00", 100.0, 1),
            (8, None, "2020-02-01 00:00:00", 200.0, 0),
            (9, "entity-a", "2020-02-01 00:00:00", 50.0, 1),
            (10, "entity-a", "2020-02-02 00:00:00", 60.0, 0),
        ],
    )
    build_offline_features(connection, CATALOG_PATH)
    connection.close()
    return database_path
