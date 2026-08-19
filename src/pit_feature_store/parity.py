from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from numbers import Real
from pathlib import Path

import duckdb

from .catalog import CATALOG_PATH, FeatureCatalog, load_catalog
from .online_engine import (
    RedisClient,
    compute_features,
    event_time_to_epoch,
)
from .warehouse import DATABASE_PATH


MIN_SAMPLE_SIZE = 50
DEFAULT_SAMPLE_SIZE = 50
DEFAULT_REL_TOL = 1e-9
DEFAULT_ABS_TOL = 1e-9
SAMPLE_SEED = 42


@dataclass(frozen=True)
class OfflineFeatureSample:
    label_id: int | str
    uid: str
    cutoff_ts: datetime
    feature_values: dict[str, object]


@dataclass(frozen=True)
class ParityMismatch:
    label_id: int | str
    uid: str
    cutoff_ts: datetime
    feature_name: str
    offline_value: object
    online_value: object
    reason: str


@dataclass(frozen=True)
class ParityResult:
    sample_count: int
    feature_names: tuple[str, ...]
    comparison_count: int
    mismatches: tuple[ParityMismatch, ...]

    @property
    def mismatch_count(self) -> int:
        return len(self.mismatches)


def normalize_missing(value: object) -> object | None:
    """Normalize DuckDB NULL, Python None and numeric NaN to None."""

    if value is None:
        return None
    try:
        if math.isnan(value):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    return value


def feature_values_equal(
    offline_value: object,
    online_value: object,
    *,
    rel_tol: float = DEFAULT_REL_TOL,
    abs_tol: float = DEFAULT_ABS_TOL,
) -> bool:
    """Compare one offline/online value with PIT parity semantics."""

    normalized_offline = normalize_missing(offline_value)
    normalized_online = normalize_missing(online_value)
    if normalized_offline is None or normalized_online is None:
        return normalized_offline is None and normalized_online is None

    if (
        isinstance(normalized_offline, Real)
        and not isinstance(normalized_offline, bool)
        and isinstance(normalized_online, Real)
        and not isinstance(normalized_online, bool)
    ):
        return math.isclose(
            float(normalized_offline),
            float(normalized_online),
            rel_tol=rel_tol,
            abs_tol=abs_tol,
        )
    return normalized_offline == normalized_online


def _validate_options(
    sample_size: int,
    rel_tol: float,
    abs_tol: float,
) -> None:
    if isinstance(sample_size, bool) or sample_size < MIN_SAMPLE_SIZE:
        raise ValueError(
            f"sample_size must be at least {MIN_SAMPLE_SIZE}."
        )
    for name, value in (("rel_tol", rel_tol), ("abs_tol", abs_tol)):
        if (
            isinstance(value, bool)
            or not math.isfinite(float(value))
            or value < 0
        ):
            raise ValueError(f"{name} must be a finite non-negative number.")


def _load_offline_samples(
    connection: duckdb.DuckDBPyConnection,
    catalog: FeatureCatalog,
    sample_size: int,
) -> list[OfflineFeatureSample]:
    feature_names = [feature.name for feature in catalog.features]
    eligible_count = connection.execute(
        "SELECT COUNT(*) FROM pit_features WHERE uid IS NOT NULL"
    ).fetchone()[0]
    if eligible_count < sample_size:
        raise ValueError(
            "Not enough offline rows with a non-missing uid for parity: "
            f"required {sample_size}, found {eligible_count}."
        )

    selected_columns = ", ".join(
        ["label_id", "uid", "cutoff_ts", *feature_names]
    )
    rows = connection.execute(
        f"""
        SELECT {selected_columns}
        FROM (
            SELECT {selected_columns}
            FROM pit_features
            WHERE uid IS NOT NULL
        ) AS eligible
        USING SAMPLE reservoir({sample_size} ROWS) REPEATABLE({SAMPLE_SEED})
        ORDER BY cutoff_ts, label_id
        """
    ).fetchall()

    return [
        OfflineFeatureSample(
            label_id=row[0],
            uid=row[1],
            cutoff_ts=row[2],
            feature_values=dict(zip(feature_names, row[3:], strict=True)),
        )
        for row in rows
    ]


def _mismatch_reason(
    offline_value: object,
    online_value: object,
) -> str:
    offline_missing = normalize_missing(offline_value) is None
    online_missing = normalize_missing(online_value) is None
    if offline_missing != online_missing:
        return "one_side_missing"
    return "values_differ"


def run_parity(
    redis_client: RedisClient,
    *,
    database_path: Path = DATABASE_PATH,
    catalog_path: Path = CATALOG_PATH,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    rel_tol: float = DEFAULT_REL_TOL,
    abs_tol: float = DEFAULT_ABS_TOL,
) -> ParityResult:
    """Compare sampled offline features with online values at identical cutoffs."""

    _validate_options(sample_size, rel_tol, abs_tol)
    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy warehouse: {database_path.resolve()}"
        )

    catalog = load_catalog(Path(catalog_path))
    feature_names = tuple(feature.name for feature in catalog.features)
    connection = duckdb.connect(database_path.as_posix(), read_only=True)
    try:
        samples = _load_offline_samples(
            connection,
            catalog,
            sample_size,
        )
    finally:
        connection.close()

    mismatches: list[ParityMismatch] = []
    for sample in samples:
        online_values = compute_features(
            redis_client,
            sample.uid,
            event_time_to_epoch(sample.cutoff_ts),
            catalog=catalog,
        )
        for feature_name in feature_names:
            offline_value = sample.feature_values[feature_name]
            if feature_name not in online_values:
                mismatches.append(
                    ParityMismatch(
                        label_id=sample.label_id,
                        uid=sample.uid,
                        cutoff_ts=sample.cutoff_ts,
                        feature_name=feature_name,
                        offline_value=offline_value,
                        online_value=None,
                        reason="online_feature_missing",
                    )
                )
                continue

            online_value = online_values[feature_name]
            if not feature_values_equal(
                offline_value,
                online_value,
                rel_tol=rel_tol,
                abs_tol=abs_tol,
            ):
                mismatches.append(
                    ParityMismatch(
                        label_id=sample.label_id,
                        uid=sample.uid,
                        cutoff_ts=sample.cutoff_ts,
                        feature_name=feature_name,
                        offline_value=offline_value,
                        online_value=online_value,
                        reason=_mismatch_reason(
                            offline_value,
                            online_value,
                        ),
                    )
                )

    return ParityResult(
        sample_count=len(samples),
        feature_names=feature_names,
        comparison_count=len(samples) * len(feature_names),
        mismatches=tuple(mismatches),
    )
