from pathlib import Path

import pandas as pd
import pytest

from pit_feature_store.entity_selection import run_entity_selection


def write_source(tmp_path: Path, frame: pd.DataFrame) -> Path:
    source_path = tmp_path / "transactions.csv"
    frame.to_csv(source_path, index=False)
    return source_path


def test_run_entity_selection_calculates_from_raw_and_writes_report(
    tmp_path: Path,
) -> None:
    source_path = write_source(
        tmp_path,
        pd.DataFrame(
            {
                "card1": [1, 1, 1, 1, 2, 2],
                "card2": [10, 10, 10, 10, 20, 20],
                "card5": [100, 100, 100, 100, 200, 200],
                "addr1": [1000, 1000, 1000, 1000, 2000, 2000],
                "D1": [1, 2, 3, 4, 5, 6],
            }
        ),
    )
    output_path = tmp_path / "reports" / "entity_candidates.csv"

    results = run_entity_selection(source_path, output_path)

    assert output_path.exists()
    assert len(results) == 4
    assert results.loc[results["selected"], "candidate"].tolist() == [
        "card1_card2_addr1"
    ]
    fragmented = results.loc[
        results["candidate"] == "card1_card2_addr1_D1"
    ].iloc[0]
    assert fragmented["repeat_entity_pct"] == 0.0
    assert fragmented["median_txn_per_entity"] == 1.0

    exported = pd.read_csv(output_path)
    pd.testing.assert_frame_equal(
        exported.drop(columns="selection_reason"),
        results.drop(columns="selection_reason"),
        check_dtype=False,
    )
    assert exported.loc[
        exported["selected"], "selection_reason"
    ].str.strip().ne("").all()
    assert exported.loc[
        ~exported["selected"], "selection_reason"
    ].isna().all()


def test_run_entity_selection_rejects_missing_candidate_columns(
    tmp_path: Path,
) -> None:
    source_path = write_source(
        tmp_path,
        pd.DataFrame({"card1": [1], "addr1": [1000]}),
    )

    with pytest.raises(
        ValueError,
        match="Dataset thiếu các cột đánh giá entity",
    ):
        run_entity_selection(source_path, tmp_path / "report.csv")
