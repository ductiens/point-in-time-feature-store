from pathlib import Path

import pytest
from pydantic import ValidationError

from catalog import load_catalog, main


EXPECTED_FEATURES = {
    "sum_amt_24h": (
        "Tổng giá trị giao dịch của uid trong 24 giờ trước cutoff.",
        "uid",
        "sum",
        "amount",
        24,
        "event_ts",
        "1.0.0",
        0,
    ),
    "count_txn_24h": (
        "Số giao dịch của uid trong 24 giờ trước cutoff.",
        "uid",
        "count",
        "transaction_id",
        24,
        "event_ts",
        "1.0.0",
        0,
    ),
    "sum_amt_7d": (
        "Tổng giá trị giao dịch của uid trong 7 ngày trước cutoff.",
        "uid",
        "sum",
        "amount",
        168,
        "event_ts",
        "1.0.0",
        0,
    ),
    "time_since_last_txn_sec": (
        "Số giây từ giao dịch gần nhất của uid trong 720 giờ trước cutoff.",
        "uid",
        "time_since_last",
        "event_ts",
        720,
        "event_ts",
        "1.0.0",
        None,
    ),
}


def write_catalog(tmp_path: Path, content: str) -> Path:
    catalog_path = tmp_path / "feature_catalog.yaml"
    catalog_path.write_text(content, encoding="utf-8")
    return catalog_path


def test_load_catalog_contains_exact_required_features() -> None:
    catalog = load_catalog()

    actual = {
        feature.name: (
            feature.description,
            feature.entity,
            feature.aggregation,
            feature.source_column,
            feature.window_hours,
            feature.event_time,
            feature.version,
            feature.default_value,
        )
        for feature in catalog.features
    }

    assert catalog.version == "1.0.0"
    assert catalog.max_lookback_hours == 720
    assert actual == EXPECTED_FEATURES


def test_catalog_rejects_unsupported_aggregation(
    tmp_path: Path,
) -> None:
    catalog_path = write_catalog(
        tmp_path,
        """
version: "test"
features:
  - name: invalid_feature
    description: Invalid aggregation test
    entity: uid
    aggregation: average
    source_column: amount
    window_hours: 24
    event_time: event_ts
    version: "1.0.0"
    default_value: 0
""",
    )

    with pytest.raises(ValidationError):
        load_catalog(catalog_path)


@pytest.mark.parametrize("window_hours", [0, -1, 1.5])
def test_catalog_rejects_invalid_window(
    tmp_path: Path,
    window_hours: int | float,
) -> None:
    catalog_path = write_catalog(
        tmp_path,
        f"""
version: "test"
features:
  - name: invalid_window
    description: Invalid window test
    entity: uid
    aggregation: sum
    source_column: amount
    window_hours: {window_hours}
    event_time: event_ts
    version: "1.0.0"
    default_value: 0
""",
    )

    with pytest.raises(ValidationError):
        load_catalog(catalog_path)


def test_catalog_rejects_duplicate_feature_names(
    tmp_path: Path,
) -> None:
    catalog_path = write_catalog(
        tmp_path,
        """
version: "test"
features:
  - name: duplicate
    description: First duplicate
    entity: uid
    aggregation: sum
    source_column: amount
    window_hours: 24
    event_time: event_ts
    version: "1.0.0"
    default_value: 0
  - name: duplicate
    description: Second duplicate
    entity: uid
    aggregation: count
    source_column: transaction_id
    window_hours: 24
    event_time: event_ts
    version: "1.0.0"
    default_value: 0
""",
    )

    with pytest.raises(ValidationError):
        load_catalog(catalog_path)


@pytest.mark.parametrize(
    "unsafe_name",
    ["has space", "has-hyphen", "1starts_with_digit", "có_dấu"],
)
def test_catalog_rejects_unsafe_feature_names(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    catalog_path = write_catalog(
        tmp_path,
        f"""
version: "test"
features:
  - name: {unsafe_name}
    description: Unsafe name test
    entity: uid
    aggregation: sum
    source_column: amount
    window_hours: 24
    event_time: event_ts
    version: "1.0.0"
    default_value: 0
""",
    )

    with pytest.raises(ValidationError):
        load_catalog(catalog_path)


@pytest.mark.parametrize(
    ("aggregation", "source_column", "default_value"),
    [
        ("sum", "event_ts", 0),
        ("count", "transaction_id", None),
        ("time_since_last", "event_ts", 0),
    ],
)
def test_catalog_rejects_inconsistent_feature_semantics(
    tmp_path: Path,
    aggregation: str,
    source_column: str,
    default_value: int | None,
) -> None:
    catalog_path = write_catalog(
        tmp_path,
        f"""
version: "test"
features:
  - name: inconsistent_feature
    description: Inconsistent semantics test
    entity: uid
    aggregation: {aggregation}
    source_column: {source_column}
    window_hours: 24
    event_time: event_ts
    version: "1.0.0"
    default_value: {"null" if default_value is None else default_value}
""",
    )

    with pytest.raises(ValidationError):
        load_catalog(catalog_path)


def test_catalog_rejects_unsafe_version(tmp_path: Path) -> None:
    catalog_path = write_catalog(
        tmp_path,
        """
version: "invalid version"
features:
  - name: valid_feature
    description: Invalid catalog version test
    entity: uid
    aggregation: sum
    source_column: amount
    window_hours: 24
    event_time: event_ts
    version: "1.0.0"
    default_value: 0
""",
    )

    with pytest.raises(ValidationError):
        load_catalog(catalog_path)


@pytest.mark.parametrize(
    ("description", "entity", "event_time", "feature_version"),
    [
        (" ", "uid", "event_ts", "1.0.0"),
        ("Valid description", "account", "event_ts", "1.0.0"),
        ("Valid description", "uid", "created_at", "1.0.0"),
        ("Valid description", "uid", "event_ts", "invalid version"),
    ],
)
def test_catalog_rejects_invalid_feature_metadata(
    tmp_path: Path,
    description: str,
    entity: str,
    event_time: str,
    feature_version: str,
) -> None:
    catalog_path = write_catalog(
        tmp_path,
        f"""
version: "test"
features:
  - name: metadata_test
    description: "{description}"
    entity: {entity}
    aggregation: sum
    source_column: amount
    window_hours: 24
    event_time: {event_time}
    version: "{feature_version}"
    default_value: 0
""",
    )

    with pytest.raises(ValidationError):
        load_catalog(catalog_path)


def test_empty_catalog_has_clear_error(tmp_path: Path) -> None:
    catalog_path = write_catalog(tmp_path, "")

    with pytest.raises(ValueError, match="Catalog file is empty"):
        load_catalog(catalog_path)


def test_main_prints_all_features(capsys: pytest.CaptureFixture[str]) -> None:
    main()

    output = capsys.readouterr().out
    assert "catalog_version=1.0.0" in output
    assert "max_lookback_hours=720" in output
    for feature_name in EXPECTED_FEATURES:
        assert feature_name in output
