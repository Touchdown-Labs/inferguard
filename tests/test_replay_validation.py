"""Tests for replay-backed validation helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from inferguard.replay_validation import (
    ReplayValidationResult,
    ReplayValidator,
)


def _result(**overrides: object) -> ReplayValidationResult:
    data = dict(
        incident_id="inc-1",
        phase="baseline",
        timestamp=1.0,
        completed_sessions=2,
        total_sessions=2,
        output_throughput_tps=100.0,
        mean_ttft_ms=1000.0,
        p99_ttft_ms=1500.0,
        mean_tpot_ms=40.0,
        cache_usage_avg=0.8,
        cache_usage_peak=0.9,
        kv_offload_observed=False,
        raw_benchmark={"aggregate_metrics": {}, "server_metrics_summary": {}},
    )
    data.update(overrides)
    return ReplayValidationResult(**data)


def test_replay_validation_result_round_trip() -> None:
    result = _result()
    payload = result.as_dict()
    assert payload["incident_id"] == "inc-1"
    assert payload["phase"] == "baseline"
    assert payload["output_throughput_tps"] == 100.0


def test_compare_improved() -> None:
    baseline = _result()
    post = _result(
        incident_id="inc-2",
        phase="post_remediation",
        output_throughput_tps=120.0,
        mean_ttft_ms=800.0,
        cache_usage_avg=0.6,
    )
    comparison = ReplayValidator.compare(baseline, post)
    assert comparison.verdict == "improved"
    assert "throughput_improved" in comparison.improvements
    assert "ttft_improved" in comparison.improvements
    assert "kv_improved" in comparison.improvements


def test_compare_regressed() -> None:
    baseline = _result()
    post = _result(
        incident_id="inc-2",
        phase="post_remediation",
        output_throughput_tps=90.0,
        mean_ttft_ms=1200.0,
        cache_usage_avg=0.9,
    )
    comparison = ReplayValidator.compare(baseline, post)
    assert comparison.verdict == "regressed"
    assert "throughput_regressed" in comparison.regressions
    assert "ttft_regressed" in comparison.regressions
    assert "kv_regressed" in comparison.regressions


def test_compare_inconclusive() -> None:
    baseline = _result()
    post = _result(
        incident_id="inc-2",
        phase="post_remediation",
        output_throughput_tps=110.0,
        mean_ttft_ms=1100.0,
        cache_usage_avg=0.8,
    )
    comparison = ReplayValidator.compare(baseline, post)
    assert comparison.verdict == "inconclusive"


@pytest.mark.asyncio
async def test_run_replay_uses_harness() -> None:
    async def fake_run_export_replay_benchmark(**_: object) -> dict[str, object]:
        return {
            "aggregate_metrics": {
                "completed_sessions": 1,
                "total_sessions": 1,
                "output_throughput_tps": 12.5,
                "mean_ttft_ms": 321.0,
                "p99_ttft_ms": 654.0,
                "mean_tpot_ms": 12.0,
            },
            "server_metrics_summary": {
                "cache_usage_avg": 0.4,
                "gpu_cache_usage_peak": 0.6,
                "kv_offload_observed": True,
            },
        }

    harness = SimpleNamespace(
        build_text_token_counter=lambda _: (lambda text: len(text.split())),
        load_replay_sessions=lambda **_: ([{"session": 1}], {"selected_sessions": 1}),
        run_export_replay_benchmark=fake_run_export_replay_benchmark,
    )
    validator = ReplayValidator("/tmp/export.json", "http://localhost:8000", "model")
    with patch.object(validator, "_load_harness", return_value=harness):
        result = await validator.run_replay("inc-1", "manual")
    assert result.completed_sessions == 1
    assert result.output_throughput_tps == 12.5
    assert result.kv_offload_observed is True


def test_run_replay_missing_extras() -> None:
    validator = ReplayValidator("/tmp/export.json", "http://localhost:8000", "model")
    with patch("builtins.__import__", side_effect=ImportError("missing")):
        with pytest.raises(RuntimeError):
            validator._load_harness()
