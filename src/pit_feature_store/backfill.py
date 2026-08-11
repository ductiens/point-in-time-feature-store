"""Deterministic, point-in-time correct historical feature backfill."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

import duckdb

from .catalog import CATALOG_PATH, FeatureCatalog, load_catalog
from .offline_engine import build_offline_features
from .warehouse import DATABASE_PATH


BACKFILL_ROOT = Path("artifacts/offline_store/backfill")
BACKFILL_LOG_PATH = Path("artifacts/logs/backfill_log.jsonl")
CATALOG_FINGERPRINT_LENGTH = 16


@dataclass(frozen=True)
class BackfillResult:
    output_path: Path
    catalog_snapshot_path: Path
    log_path: Path
    version: str
    catalog_fingerprint: str
    start_date: date
    end_date: date
    lookback_hours: int
    row_count: int


def parse_backfill_date(value: str | date, field_name: str) -> date:
    if isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a date, not a datetime.")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must use YYYY-MM-DD format.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            f"{field_name} must use YYYY-MM-DD format: {value!r}."
        ) from error
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format: {value!r}.")
    return parsed


def catalog_fingerprint(catalog: FeatureCatalog) -> str:
    canonical_catalog = json.dumps(
        catalog.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(canonical_catalog).hexdigest()[:CATALOG_FINGERPRINT_LENGTH]


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _timestamp_sql(value: datetime) -> str:
    return f"TIMESTAMP {_sql_string(value.isoformat(sep=' '))}"


def _append_log(log_path: Path, record: dict[str, object]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        log_file.write("\n")


def run_backfill(
    start_date: str | date,
    end_date: str | date,
    *,
    database_path: Path = DATABASE_PATH,
    catalog_path: Path = CATALOG_PATH,
    output_root: Path = BACKFILL_ROOT,
    log_path: Path = BACKFILL_LOG_PATH,
) -> BackfillResult:
    """Build PIT features for an inclusive calendar-date range.

    The source cohort includes exactly the catalog lookback before ``start_date``.
    All intermediate feature objects live in an in-memory DuckDB connection and
    are declared TEMP, while the warehouse is attached read-only.
    """

    parsed_start = parse_backfill_date(start_date, "start_date")
    parsed_end = parse_backfill_date(end_date, "end_date")
    if parsed_start > parsed_end:
        raise ValueError("start_date must be on or before end_date.")

    database_path = Path(database_path)
    catalog_path = Path(catalog_path)
    output_root = Path(output_root)
    log_path = Path(log_path)
    if not database_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy warehouse: {database_path.resolve()}"
        )
    if not catalog_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy feature catalog: {catalog_path.resolve()}"
        )

    catalog = load_catalog(catalog_path)
    fingerprint = catalog_fingerprint(catalog)
    version = f"{catalog.version}-{fingerprint}"
    date_partition = f"{parsed_start.isoformat()}_{parsed_end.isoformat()}"
    output_directory = (
        output_root / f"version={version}" / date_partition
    )
    output_path = output_directory / "features.parquet"
    catalog_snapshot_path = output_directory / "catalog_snapshot.yaml"

    start_ts = datetime.combine(parsed_start, time.min)
    end_exclusive_ts = datetime.combine(
        parsed_end + timedelta(days=1),
        time.min,
    )
    lookback_start_ts = start_ts - timedelta(
        hours=catalog.max_lookback_hours
    )
    started_at = datetime.now(timezone.utc).isoformat()
    temporary_parquet: Path | None = None
    temporary_snapshot: Path | None = None

    try:
        output_directory.mkdir(parents=True, exist_ok=True)
        temporary_parquet = output_directory / (
            f".features-{uuid4().hex}.tmp.parquet"
        )
        temporary_snapshot = output_directory / (
            f".catalog-{uuid4().hex}.tmp.yaml"
        )

        connection = duckdb.connect()
        try:
            warehouse_sql = _sql_string(database_path.resolve().as_posix())
            connection.execute(
                f"ATTACH {warehouse_sql} AS source_warehouse (READ_ONLY)"
            )
            connection.execute(
                f"""
                CREATE OR REPLACE TEMP VIEW backfill_transactions AS
                SELECT transaction_id, uid, event_ts, amount, label
                FROM source_warehouse.transactions
                WHERE event_ts >= {_timestamp_sql(lookback_start_ts)}
                  AND event_ts < {_timestamp_sql(end_exclusive_ts)}
                """
            )
            build_offline_features(
                connection,
                catalog_path,
                source_relation="backfill_transactions",
                temporary=True,
            )
            connection.execute(
                f"""
                CREATE OR REPLACE TEMP TABLE backfill_features AS
                SELECT *
                FROM pit_features
                WHERE cutoff_ts >= {_timestamp_sql(start_ts)}
                  AND cutoff_ts < {_timestamp_sql(end_exclusive_ts)}
                ORDER BY cutoff_ts, label_id
                """
            )
            row_count = int(
                connection.sql(
                    "SELECT COUNT(*) FROM backfill_features"
                ).fetchone()[0]
            )
            connection.execute(
                f"""
                COPY backfill_features
                TO {_sql_string(temporary_parquet.as_posix())}
                (FORMAT PARQUET)
                """
            )
        finally:
            connection.close()

        shutil.copyfile(catalog_path, temporary_snapshot)
        os.replace(temporary_snapshot, catalog_snapshot_path)
        temporary_snapshot = None
        os.replace(temporary_parquet, output_path)
        temporary_parquet = None

        _append_log(
            log_path,
            {
                "catalog_fingerprint": fingerprint,
                "catalog_snapshot_path": catalog_snapshot_path.as_posix(),
                "catalog_version": catalog.version,
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "database_path": database_path.as_posix(),
                "end_date": parsed_end.isoformat(),
                "lookback_hours": catalog.max_lookback_hours,
                "output_path": output_path.as_posix(),
                "row_count": row_count,
                "start_date": parsed_start.isoformat(),
                "started_at_utc": started_at,
                "status": "success",
                "version": version,
            },
        )
    except Exception as error:
        _append_log(
            log_path,
            {
                "catalog_fingerprint": fingerprint,
                "catalog_version": catalog.version,
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "end_date": parsed_end.isoformat(),
                "error": f"{type(error).__name__}: {error}",
                "start_date": parsed_start.isoformat(),
                "started_at_utc": started_at,
                "status": "failed",
                "version": version,
            },
        )
        raise
    finally:
        for temporary_path in (temporary_parquet, temporary_snapshot):
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    return BackfillResult(
        output_path=output_path,
        catalog_snapshot_path=catalog_snapshot_path,
        log_path=log_path,
        version=version,
        catalog_fingerprint=fingerprint,
        start_date=parsed_start,
        end_date=parsed_end,
        lookback_hours=catalog.max_lookback_hours,
        row_count=row_count,
    )
