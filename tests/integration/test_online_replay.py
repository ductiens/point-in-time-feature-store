from datetime import datetime, timezone
from pathlib import Path

import duckdb
import fakeredis
import pytest

from pit_feature_store.online_engine import (
    OnlineEvent,
    ingest_event,
    replay_warehouse,
)


def create_replay_warehouse(database_path: Path) -> None:
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
        connection.executemany(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?)",
            [
                (3, "entity-a", "2017-12-01 00:01:00", 30.0, 0),
                (2, "entity-a", "2017-12-01 00:00:00", 20.0, 0),
                (4, None, "2017-12-01 00:00:30", 999.0, 0),
                (1, "entity-a", "2017-12-01 00:00:00", 10.0, 0),
            ],
        )
    finally:
        connection.close()


def test_replay_warehouse_orders_rows_and_preserves_pit_semantics(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "warehouse.duckdb"
    create_replay_warehouse(database_path)
    redis_client = fakeredis.FakeRedis()
    redis_client.set("unrelated:key", "keep-me")
    observed: list[tuple[int | str, dict[str, int | float | None]]] = []

    def observe(
        event: OnlineEvent,
        features: dict[str, int | float | None],
    ) -> None:
        observed.append((event.transaction_id, features))

    result = replay_warehouse(
        redis_client,
        database_path=database_path,
        on_features=observe,
    )

    assert [transaction_id for transaction_id, _ in observed] == [1, 2, 3]
    assert observed[0][1]["count_txn_24h"] == 0
    assert observed[1][1]["count_txn_24h"] == 0
    assert observed[2][1] == {
        "sum_amt_24h": 30.0,
        "count_txn_24h": 2,
        "sum_amt_7d": 30.0,
        "time_since_last_txn_sec": 60.0,
    }
    assert result.total_rows == 4
    assert result.ingested_events == 3
    assert result.last_event_epoch == datetime(
        2017,
        12,
        1,
        0,
        1,
        tzinfo=timezone.utc,
    ).timestamp()
    assert redis_client.get("sys:virtual_now_epoch") == b"1512086460"
    assert redis_client.get("unrelated:key") == b"keep-me"


def test_missing_warehouse_does_not_clear_existing_online_state(
    tmp_path: Path,
) -> None:
    redis_client = fakeredis.FakeRedis()
    ingest_event(redis_client, "entity-a", 1, 10.0, 1_700_000_000)

    with pytest.raises(FileNotFoundError, match="warehouse"):
        replay_warehouse(
            redis_client,
            database_path=tmp_path / "missing.duckdb",
        )

    assert redis_client.zcard("events:entity-a") == 1
