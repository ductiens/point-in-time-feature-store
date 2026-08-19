from datetime import datetime
from pathlib import Path

import fakeredis
import pytest

from pit_feature_store.parity import (
    ParityMismatch,
    ParityResult,
    feature_values_equal,
    normalize_missing,
    run_parity,
)
from scripts.run_parity import print_result


def test_missing_values_are_normalized_before_comparison() -> None:
    assert normalize_missing(None) is None
    assert normalize_missing(float("nan")) is None
    assert feature_values_equal(None, float("nan"))
    assert feature_values_equal(float("nan"), None)
    assert not feature_values_equal(None, 0)
    assert not feature_values_equal(float("nan"), 0.0)


def test_numeric_values_use_small_float_tolerance() -> None:
    assert feature_values_equal(10.0, 10.0 + 1e-10)
    assert not feature_values_equal(10.0, 10.01)


def test_parity_rejects_fewer_than_fifty_samples() -> None:
    with pytest.raises(ValueError, match="at least 50"):
        run_parity(
            fakeredis.FakeRedis(),
            database_path=Path("does-not-need-to-exist.duckdb"),
            sample_size=49,
        )


def test_cli_report_prints_mismatch_context_and_returns_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    mismatch = ParityMismatch(
        label_id=7,
        uid="entity-a",
        cutoff_ts=datetime(2020, 1, 2, 3, 4, 5),
        feature_name="sum_amt_24h",
        offline_value=10.0,
        online_value=11.0,
        reason="values_differ",
    )
    result = ParityResult(
        sample_count=50,
        feature_names=("sum_amt_24h",),
        comparison_count=50,
        mismatches=(mismatch,),
    )

    exit_code = print_result(result)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "mismatches=1" in output
    assert "label_id=7" in output
    assert "uid='entity-a'" in output
    assert "cutoff_ts=2020-01-02T03:04:05" in output
    assert "feature=sum_amt_24h" in output
    assert "offline=10.0" in output
    assert "online=11.0" in output
    assert "reason=values_differ" in output
