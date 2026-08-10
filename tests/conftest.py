from collections.abc import Iterator

import duckdb
import pytest


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
