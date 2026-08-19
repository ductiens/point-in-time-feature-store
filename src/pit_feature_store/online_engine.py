from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Protocol

import duckdb

from .catalog import CATALOG_PATH, FeatureCatalog, FeatureDefinition, load_catalog
from .warehouse import DATABASE_PATH


EVENTS_KEY_PREFIX = "events:"
VIRTUAL_CLOCK_KEY = "sys:virtual_now_epoch"
SECONDS_PER_HOUR = 60 * 60
DELETE_BATCH_SIZE = 1_000
FETCH_BATCH_SIZE = 10_000

FeatureValue = int | float | None
FeatureValues = dict[str, FeatureValue]
TransactionId = int | str
EventTime = datetime | int | float | str


class RedisClient(Protocol):
    """Subset of the synchronous Redis API used by the online engine."""

    def zadd(
        self,
        name: str,
        mapping: Mapping[str, float],
    ) -> int | float: ...

    def zrangebyscore(
        self,
        name: str,
        min: int | float | str,
        max: int | float | str,
        *,
        withscores: bool = False,
    ) -> list[Any]: ...

    def scan_iter(
        self,
        match: str | None = None,
        count: int | None = None,
    ) -> Iterator[bytes | str]: ...

    def delete(self, *names: bytes | str) -> int: ...

    def set(self, name: str, value: str) -> object: ...

    def get(self, name: str) -> bytes | str | None: ...


@dataclass(frozen=True)
class OnlineEvent:
    transaction_id: TransactionId
    uid: str | None
    event_ts: EventTime
    amount: float


@dataclass(frozen=True)
class ReplayResult:
    total_rows: int
    ingested_events: int
    last_event_epoch: float | None


ReplayInput = OnlineEvent | Mapping[str, object] | Sequence[object]
FeatureObserver = Callable[[OnlineEvent, FeatureValues], None]


def events_key(uid: str) -> str:
    if not isinstance(uid, str) or not uid:
        raise ValueError("uid must be a non-empty string.")
    return f"{EVENTS_KEY_PREFIX}{uid}"


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name} must be a finite number."
        ) from error
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number.")
    return number


def event_time_to_epoch(value: EventTime) -> float:
    """Convert the dataset's naive timestamps to UTC epoch seconds."""

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError(
                "event_ts must be an ISO datetime or epoch seconds."
            ) from error

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return _finite_number(value.timestamp(), "event_ts")

    return _finite_number(value, "event_ts")


def _epoch_text(value: int | float) -> str:
    epoch = _finite_number(value, "epoch")
    if epoch.is_integer():
        return str(int(epoch))
    return format(epoch, ".17g")


def _transaction_id(value: object) -> TransactionId:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("transaction_id must be an integer or string.")
    if isinstance(value, str) and not value:
        raise ValueError("transaction_id must not be empty.")
    return value


def _event_member(transaction_id: TransactionId, amount: float) -> str:
    return json.dumps(
        {
            "amount": amount,
            "transaction_id": transaction_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _decode_member(member: bytes | str) -> dict[str, object]:
    if isinstance(member, bytes):
        member = member.decode("utf-8")
    if not isinstance(member, str):
        raise ValueError("Redis event member must be bytes or string.")
    try:
        payload = json.loads(member)
    except json.JSONDecodeError as error:
        raise ValueError("Redis event member is not valid JSON.") from error
    if not isinstance(payload, dict):
        raise ValueError("Redis event member must contain a JSON object.")
    if "transaction_id" not in payload or "amount" not in payload:
        raise ValueError(
            "Redis event member must contain transaction_id and amount."
        )
    _transaction_id(payload["transaction_id"])
    payload["amount"] = _finite_number(payload["amount"], "amount")
    return payload


def ingest_event(
    redis_client: RedisClient,
    uid: str,
    transaction_id: TransactionId,
    amount: int | float,
    event_epoch: int | float,
) -> None:
    """Store one raw transaction in the entity's Redis ZSET."""

    key = events_key(uid)
    validated_transaction_id = _transaction_id(transaction_id)
    validated_amount = _finite_number(amount, "amount")
    validated_epoch = _finite_number(event_epoch, "event_epoch")
    member = _event_member(validated_transaction_id, validated_amount)
    redis_client.zadd(key, {member: validated_epoch})


def _default_feature_value(feature: FeatureDefinition) -> FeatureValue:
    if feature.aggregation == "sum":
        return float(feature.default_value or 0)
    if feature.aggregation == "count":
        return int(feature.default_value or 0)
    return feature.default_value


def _compute_feature(
    feature: FeatureDefinition,
    events: list[tuple[dict[str, object], float]],
    cutoff_epoch: float,
) -> FeatureValue:
    lower_epoch = cutoff_epoch - feature.window_hours * SECONDS_PER_HOUR
    window_events = [
        (payload, score)
        for payload, score in events
        if score >= lower_epoch
    ]
    if not window_events:
        return _default_feature_value(feature)

    if feature.aggregation == "sum":
        return float(
            sum(float(payload["amount"]) for payload, _ in window_events)
        )
    if feature.aggregation == "count":
        return len(window_events)
    if feature.aggregation == "time_since_last":
        last_event_epoch = max(score for _, score in window_events)
        return float(cutoff_epoch - last_event_epoch)
    raise ValueError(f"Unsupported aggregation: {feature.aggregation}")


def compute_features(
    redis_client: RedisClient,
    uid: str,
    cutoff_epoch: int | float,
    *,
    catalog_path: Path = CATALOG_PATH,
    catalog: FeatureCatalog | None = None,
) -> FeatureValues:
    """Compute catalog features from raw events in ``[lower, cutoff)``."""

    key = events_key(uid)
    validated_cutoff = _finite_number(cutoff_epoch, "cutoff_epoch")
    active_catalog = (
        catalog
        if catalog is not None
        else load_catalog(Path(catalog_path))
    )
    max_lower_epoch = (
        validated_cutoff
        - active_catalog.max_lookback_hours * SECONDS_PER_HOUR
    )
    raw_events = redis_client.zrangebyscore(
        key,
        max_lower_epoch,
        f"({_epoch_text(validated_cutoff)}",
        withscores=True,
    )
    decoded_events = [
        (_decode_member(member), _finite_number(score, "event score"))
        for member, score in raw_events
    ]
    return {
        feature.name: _compute_feature(
            feature,
            decoded_events,
            validated_cutoff,
        )
        for feature in active_catalog.features
    }


def set_virtual_now_epoch(
    redis_client: RedisClient,
    event_epoch: int | float,
) -> None:
    redis_client.set(VIRTUAL_CLOCK_KEY, _epoch_text(event_epoch))


def get_virtual_now_epoch(redis_client: RedisClient) -> float | None:
    raw_value = redis_client.get(VIRTUAL_CLOCK_KEY)
    if raw_value is None:
        return None
    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8")
    return _finite_number(raw_value, VIRTUAL_CLOCK_KEY)


def clear_online_state(redis_client: RedisClient) -> int:
    """Delete only project-owned event keys and the virtual clock."""

    deleted = 0
    batch: list[bytes | str] = []
    for key in redis_client.scan_iter(
        match=f"{EVENTS_KEY_PREFIX}*",
        count=DELETE_BATCH_SIZE,
    ):
        batch.append(key)
        if len(batch) >= DELETE_BATCH_SIZE:
            deleted += int(redis_client.delete(*batch))
            batch.clear()
    if batch:
        deleted += int(redis_client.delete(*batch))
    deleted += int(redis_client.delete(VIRTUAL_CLOCK_KEY))
    return deleted


def _coerce_event(value: ReplayInput) -> OnlineEvent:
    if isinstance(value, OnlineEvent):
        return value
    if isinstance(value, Mapping):
        try:
            return OnlineEvent(
                transaction_id=_transaction_id(value["transaction_id"]),
                uid=value["uid"],  # type: ignore[arg-type]
                event_ts=value["event_ts"],  # type: ignore[arg-type]
                amount=_finite_number(value["amount"], "amount"),
            )
        except KeyError as error:
            raise ValueError(
                "Replay mapping must contain transaction_id, uid, "
                "event_ts and amount."
            ) from error
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        if len(value) != 4:
            raise ValueError(
                "Replay tuple must contain transaction_id, uid, "
                "event_ts and amount."
            )
        return OnlineEvent(
            transaction_id=_transaction_id(value[0]),
            uid=value[1],  # type: ignore[arg-type]
            event_ts=value[2],  # type: ignore[arg-type]
            amount=_finite_number(value[3], "amount"),
        )
    raise ValueError("Unsupported replay event value.")


def replay_transactions(
    redis_client: RedisClient,
    transactions: Iterable[ReplayInput],
    *,
    catalog_path: Path = CATALOG_PATH,
    on_features: FeatureObserver | None = None,
) -> ReplayResult:
    """Replay chronologically ordered events into a clean online store."""

    catalog = load_catalog(Path(catalog_path))
    clear_online_state(redis_client)

    total_rows = 0
    ingested_events = 0
    previous_epoch: float | None = None
    last_event_epoch: float | None = None

    for raw_event in transactions:
        event = _coerce_event(raw_event)
        event_epoch = event_time_to_epoch(event.event_ts)
        if previous_epoch is not None and event_epoch < previous_epoch:
            raise ValueError(
                "Replay transactions must be ordered by event_ts."
            )

        total_rows += 1
        if event.uid is not None:
            features = compute_features(
                redis_client,
                event.uid,
                event_epoch,
                catalog=catalog,
            )
            if on_features is not None:
                on_features(event, features)
            ingest_event(
                redis_client,
                event.uid,
                event.transaction_id,
                event.amount,
                event_epoch,
            )
            ingested_events += 1

        set_virtual_now_epoch(redis_client, event_epoch)
        previous_epoch = event_epoch
        last_event_epoch = event_epoch

    return ReplayResult(
        total_rows=total_rows,
        ingested_events=ingested_events,
        last_event_epoch=last_event_epoch,
    )


def replay_warehouse(
    redis_client: RedisClient,
    *,
    database_path: Path = DATABASE_PATH,
    catalog_path: Path = CATALOG_PATH,
    on_features: FeatureObserver | None = None,
) -> ReplayResult:
    """Replay warehouse transactions ordered by event time and ID."""

    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy warehouse: {database_path.resolve()}"
        )

    connection = duckdb.connect(database_path.as_posix(), read_only=True)
    try:
        cursor = connection.execute(
            """
            SELECT transaction_id, uid, event_ts, amount
            FROM transactions
            ORDER BY event_ts, transaction_id
            """
        )

        def transactions() -> Iterator[OnlineEvent]:
            while rows := cursor.fetchmany(FETCH_BATCH_SIZE):
                for transaction_id, uid, event_ts, amount in rows:
                    yield OnlineEvent(
                        transaction_id=transaction_id,
                        uid=uid,
                        event_ts=event_ts,
                        amount=amount,
                    )

        return replay_transactions(
            redis_client,
            transactions(),
            catalog_path=catalog_path,
            on_features=on_features,
        )
    finally:
        connection.close()
