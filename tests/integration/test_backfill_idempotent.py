import json
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

from pit_feature_store.backfill import run_backfill
from pit_feature_store.catalog import CATALOG_PATH


def test_backfill_is_logically_idempotent_and_writes_versioned_outputs(
    backfill_warehouse_path: Path,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "offline_store" / "backfill"
    log_path = tmp_path / "logs" / "backfill_log.jsonl"

    first_result = run_backfill(
        "2020-01-31",
        "2020-02-01",
        database_path=backfill_warehouse_path,
        output_root=output_root,
        log_path=log_path,
    )
    first_frame = pd.read_parquet(first_result.output_path)

    second_result = run_backfill(
        "2020-01-31",
        "2020-02-01",
        database_path=backfill_warehouse_path,
        output_root=output_root,
        log_path=log_path,
    )
    second_frame = pd.read_parquet(second_result.output_path)

    pdt.assert_frame_equal(first_frame, second_frame)
    assert first_result.output_path == second_result.output_path
    assert first_result.version == second_result.version
    assert first_result.catalog_fingerprint in first_result.version
    assert first_result.output_path.parent.name == "2020-01-31_2020-02-01"
    assert first_result.output_path.parent.parent.name == (
        f"version={first_result.version}"
    )
    assert first_result.lookback_hours == 720
    assert first_result.row_count == 6
    assert first_result.catalog_snapshot_path.read_bytes() == (
        CATALOG_PATH.read_bytes()
    )
    assert not list(first_result.output_path.parent.glob("*.tmp.*"))

    log_records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(log_records) == 2
    assert all(record["status"] == "success" for record in log_records)
    assert all(record["row_count"] == 6 for record in log_records)
    assert all(
        record["catalog_fingerprint"]
        == first_result.catalog_fingerprint
        for record in log_records
    )


def test_backfill_rejects_reversed_date_range(
    backfill_warehouse_path: Path,
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="start_date must be on or before end_date",
    ):
        run_backfill(
            "2020-02-01",
            "2020-01-31",
            database_path=backfill_warehouse_path,
            output_root=tmp_path / "backfill",
            log_path=tmp_path / "backfill.jsonl",
        )
