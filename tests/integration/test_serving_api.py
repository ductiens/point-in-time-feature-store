from collections.abc import Iterator

import fakeredis
import pytest
from fastapi.testclient import TestClient

from pit_feature_store.online_engine import ingest_event
from pit_feature_store.serving import create_app


FEATURE_NAMES = {
    "sum_amt_24h",
    "count_txn_24h",
    "sum_amt_7d",
    "time_since_last_txn_sec",
}
VIRTUAL_CLOCK_KEY = "sys:virtual_now_epoch"


@pytest.fixture
def redis_client() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


@pytest.fixture
def api_client(
    redis_client: fakeredis.FakeRedis,
) -> Iterator[TestClient]:
    app = create_app(redis_client=redis_client)
    with TestClient(app) as client:
        yield client


def response_features(payload: dict) -> dict:
    """Accept metadata either beside or around the catalog feature mapping."""
    if isinstance(payload.get("features"), dict):
        return payload["features"]
    return {name: payload[name] for name in FEATURE_NAMES}


def test_api_returns_503_without_cutoff_or_virtual_clock(
    api_client: TestClient,
) -> None:
    response = api_client.get("/features/entity-a")

    assert response.status_code == 503


def test_api_supports_explicit_as_of_epoch_without_virtual_clock(
    api_client: TestClient,
    redis_client: fakeredis.FakeRedis,
) -> None:
    cutoff = 1_700_000_000
    ingest_event(redis_client, "entity-a", 1, 10.0, cutoff - 3600)
    ingest_event(redis_client, "entity-a", 2, 99.0, cutoff)

    response = api_client.get(
        "/features/entity-a",
        params={"as_of_epoch": cutoff},
    )

    assert response.status_code == 200
    payload = response.json()
    features = response_features(payload)
    assert set(features) == FEATURE_NAMES
    assert features == {
        "sum_amt_24h": 10.0,
        "count_txn_24h": 1,
        "sum_amt_7d": 10.0,
        "time_since_last_txn_sec": 3600.0,
    }


def test_api_uses_virtual_clock_when_as_of_epoch_is_omitted(
    api_client: TestClient,
    redis_client: fakeredis.FakeRedis,
) -> None:
    cutoff = 1_700_000_000
    ingest_event(redis_client, "entity-a", 1, 15.0, cutoff - 60)
    redis_client.set(VIRTUAL_CLOCK_KEY, cutoff)

    response = api_client.get("/features/entity-a")

    assert response.status_code == 200
    features = response_features(response.json())
    assert features == {
        "sum_amt_24h": 15.0,
        "count_txn_24h": 1,
        "sum_amt_7d": 15.0,
        "time_since_last_txn_sec": 60.0,
    }


def test_explicit_as_of_epoch_overrides_virtual_clock(
    api_client: TestClient,
    redis_client: fakeredis.FakeRedis,
) -> None:
    earlier_cutoff = 1_700_000_000
    later_cutoff = earlier_cutoff + 3600
    ingest_event(
        redis_client,
        "entity-a",
        1,
        10.0,
        earlier_cutoff - 60,
    )
    ingest_event(
        redis_client,
        "entity-a",
        2,
        20.0,
        earlier_cutoff + 60,
    )
    redis_client.set(VIRTUAL_CLOCK_KEY, later_cutoff)

    response = api_client.get(
        "/features/entity-a",
        params={"as_of_epoch": earlier_cutoff},
    )

    assert response.status_code == 200
    features = response_features(response.json())
    assert features["sum_amt_24h"] == 10.0
    assert features["count_txn_24h"] == 1


def test_api_returns_catalog_defaults_for_unknown_entity(
    api_client: TestClient,
    redis_client: fakeredis.FakeRedis,
) -> None:
    redis_client.set(VIRTUAL_CLOCK_KEY, 1_700_000_000)

    response = api_client.get("/features/unknown-entity")

    assert response.status_code == 200
    assert response_features(response.json()) == {
        "sum_amt_24h": 0,
        "count_txn_24h": 0,
        "sum_amt_7d": 0,
        "time_since_last_txn_sec": None,
    }


@pytest.mark.parametrize("invalid_epoch", ["nan", "inf", "-inf"])
def test_api_rejects_non_finite_explicit_cutoff(
    api_client: TestClient,
    invalid_epoch: str,
) -> None:
    response = api_client.get(
        "/features/entity-a",
        params={"as_of_epoch": invalid_epoch},
    )

    assert response.status_code == 422
