from pathlib import Path

import duckdb
import pandas as pd
import pandas.testing as pdt

from pit_feature_store.backfill import run_backfill


def _read_main_pit_features(database_path: Path) -> pd.DataFrame:
    connection = duckdb.connect(database_path.as_posix(), read_only=True)
    try:
        return connection.sql(
            """
            SELECT *
            FROM pit_features
            ORDER BY cutoff_ts, label_id
            """
        ).df()
    finally:
        connection.close()


def test_backfill_matches_full_pipeline_and_preserves_main_pit_table(
    backfill_warehouse_path: Path,
    tmp_path: Path,
) -> None:
    main_before = _read_main_pit_features(backfill_warehouse_path)
    expected = main_before[
        (main_before["cutoff_ts"] >= pd.Timestamp("2020-01-31"))
        & (main_before["cutoff_ts"] < pd.Timestamp("2020-02-02"))
    ].reset_index(drop=True)

    result = run_backfill(
        "2020-01-31",
        "2020-02-01",
        database_path=backfill_warehouse_path,
        output_root=tmp_path / "offline_store" / "backfill",
        log_path=tmp_path / "logs" / "backfill_log.jsonl",
    )
    actual = pd.read_parquet(result.output_path)
    main_after = _read_main_pit_features(backfill_warehouse_path)

    pdt.assert_frame_equal(actual, expected, check_dtype=False)
    pdt.assert_frame_equal(main_after, main_before)
    assert actual["label_id"].tolist() == [4, 5, 6, 7, 8, 9]
