from datetime import datetime, timedelta
from pathlib import Path

import fakeredis
import pytest

from pit_feature_store.online_engine import (
    OnlineEvent,
    clear_online_state,
    compute_features,
    ingest_event,
    replay_transactions,
)


VIRTUAL_CLOCK_KEY = "sys:virtual_now_epoch"


def make_redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


def test_ingest_event_stores_raw_event_in_uid_zset() -> None:
    redis_client = make_redis()

    ingest_event(
        redis_client,
        "entity-a",
        987654321,
        12.5,
        1_700_000_000,
    )

    stored = redis_client.zrange(
        "events:entity-a",
        0,
        -1,
        withscores=True,
    )
    assert len(stored) == 1
    member, score = stored[0]
    member_text = member.decode("utf-8")
    assert "987654321" in member_text
    assert "12.5" in member_text
    assert score == 1_700_000_000


def test_compute_features_returns_catalog_defaults_without_history() -> None:
    actual = compute_features(
        make_redis(),
        "new-entity",
        1_700_000_000,
    )

    assert actual == {
        "sum_amt_24h": 0,
        "count_txn_24h": 0,
        "sum_amt_7d": 0,
        "time_since_last_txn_sec": None,
    }


def test_compute_features_uses_closed_lower_and_open_upper_boundaries() -> None:
    redis_client = make_redis()
    cutoff = 1_700_000_000

    events = [
        (1, 1.0, cutoff - 720 * 3600),
        (2, 2.0, cutoff - 168 * 3600),
        (3, 3.0, cutoff - 24 * 3600),
        (4, 4.0, cutoff - 1),
        (5, 100.0, cutoff),
        (6, 200.0, cutoff + 1),
    ]
    for transaction_id, amount, event_epoch in events:
        ingest_event(
            redis_client,
            "entity-a",
            transaction_id,
            amount,
            event_epoch,
        )
    ingest_event(redis_client, "entity-b", 7, 999.0, cutoff - 1)

    assert compute_features(redis_client, "entity-a", cutoff) == {
        "sum_amt_24h": 7.0,
        "count_txn_24h": 2,
        "sum_amt_7d": 9.0,
        "time_since_last_txn_sec": 1.0,
    }


def test_time_since_last_includes_720h_boundary_and_excludes_older_event() -> None:
    redis_client = make_redis()
    cutoff = 1_700_000_000
    ingest_event(
        redis_client,
        "at-boundary",
        1,
        10.0,
        cutoff - 720 * 3600,
    )
    ingest_event(
        redis_client,
        "outside-boundary",
        2,
        10.0,
        cutoff - 720 * 3600 - 1,
    )

    at_boundary = compute_features(redis_client, "at-boundary", cutoff)
    outside_boundary = compute_features(
        redis_client,
        "outside-boundary",
        cutoff,
    )

    assert at_boundary["time_since_last_txn_sec"] == 720 * 3600
    assert outside_boundary["time_since_last_txn_sec"] is None


def test_events_with_same_timestamp_are_counted_separately() -> None:
    redis_client = make_redis()
    cutoff = 1_700_000_000
    ingest_event(redis_client, "entity-a", 1, 10.0, cutoff - 60)
    ingest_event(redis_client, "entity-a", 2, 20.0, cutoff - 60)

    actual = compute_features(redis_client, "entity-a", cutoff)

    assert actual["sum_amt_24h"] == 30.0
    assert actual["count_txn_24h"] == 2
    assert actual["time_since_last_txn_sec"] == 60.0


def test_compute_features_is_driven_by_the_supplied_catalog(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "feature_catalog.yaml"
    catalog_path.write_text(
        """
version: "test"
features:
  - name: spend_2h
    description: Amount in the previous two hours.
    entity: uid
    aggregation: sum
    source_column: amount
    window_hours: 2
    event_time: event_ts
    version: "test"
    default_value: 0
  - name: transactions_2h
    description: Transactions in the previous two hours.
    entity: uid
    aggregation: count
    source_column: transaction_id
    window_hours: 2
    event_time: event_ts
    version: "test"
    default_value: 0
  - name: last_seen_3h
    description: Seconds since the last transaction in three hours.
    entity: uid
    aggregation: time_since_last
    source_column: event_ts
    window_hours: 3
    event_time: event_ts
    version: "test"
    default_value: null
""".strip(),
        encoding="utf-8",
    )
    redis_client = make_redis()
    cutoff = 1_700_000_000
    ingest_event(redis_client, "entity-a", 1, 8.5, cutoff - 3600)

    actual = compute_features(
        redis_client,
        "entity-a",
        cutoff,
        catalog_path=catalog_path,
    )

    assert actual == {
        "spend_2h": 8.5,
        "transactions_2h": 1,
        "last_seen_3h": 3600.0,
    }


def test_clear_online_state_preserves_unrelated_redis_keys() -> None:
    redis_client = make_redis()
    ingest_event(redis_client, "entity-a", 1, 10.0, 1_700_000_000)
    ingest_event(redis_client, "entity-b", 2, 20.0, 1_700_000_001)
    redis_client.set(VIRTUAL_CLOCK_KEY, 1_700_000_001)
    redis_client.set("unrelated:key", "keep-me")

    clear_online_state(redis_client)

    assert list(redis_client.scan_iter(match="events:*")) == []
    assert redis_client.get(VIRTUAL_CLOCK_KEY) is None
    assert redis_client.get("unrelated:key") == b"keep-me"


def test_replay_is_deterministic_computes_before_ingest_and_advances_clock() -> None:
    redis_client = make_redis()
    base_ts = datetime(2017, 12, 1, 0, 0, 0)
    events = [
        OnlineEvent(1, "entity-a", base_ts, 10.0),
        OnlineEvent(2, None, base_ts + timedelta(seconds=30), 999.0),
        OnlineEvent(3, "entity-a", base_ts + timedelta(seconds=60), 20.0),
    ]
    redis_client.set("unrelated:key", "keep-me")
    redis_client.zadd("events:stale", {"stale-event": 1})
    zset_sizes_seen_by_callback: list[int] = []

    def observe_before_ingest(event: OnlineEvent, features: dict) -> None:
        zset_sizes_seen_by_callback.append(
            redis_client.zcard(f"events:{event.uid}")
        )

    first_result = replay_transactions(
        redis_client,
        events,
        on_features=observe_before_ingest,
    )
    first_state = redis_client.zrange(
        "events:entity-a",
        0,
        -1,
        withscores=True,
    )

    second_result = replay_transactions(redis_client, events)
    second_state = redis_client.zrange(
        "events:entity-a",
        0,
        -1,
        withscores=True,
    )

    assert zset_sizes_seen_by_callback == [0, 1]
    assert first_result.total_rows == 3
    assert first_result.ingested_events == 2
    assert first_result.last_event_epoch == 1_512_086_460
    assert second_result == first_result
    assert second_state == first_state
    assert redis_client.get(VIRTUAL_CLOCK_KEY) == b"1512086460"
    assert not redis_client.exists("events:stale")
    assert redis_client.get("unrelated:key") == b"keep-me"


def test_replay_rejects_events_out_of_time_order() -> None:
    redis_client = make_redis()
    base_ts = datetime(2020, 1, 1, 0, 0, 0)

    with pytest.raises(ValueError, match="order|timestamp|nondecreasing"):
        replay_transactions(
            redis_client,
            [
                OnlineEvent(2, "entity-a", base_ts, 20.0),
                OnlineEvent(
                    1,
                    "entity-a",
                    base_ts - timedelta(seconds=1),
                    10.0,
                ),
            ],
        )
