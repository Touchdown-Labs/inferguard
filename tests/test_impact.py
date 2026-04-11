"""Tests for demo/impact.py — operational impact computation."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

# Make demo/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "demo"))

from impact import OperationalImpact, compute_impact  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _healthy(ts: float, kv: float = 0.40, ttft: float = 0.10,
             queue: int = 0, preemptions: int = 0,
             proof_level: str | None = None) -> dict:
    r: dict = {
        "status": "healthy",
        "metrics": {
            "timestamp": ts,
            "engine": "vllm",
            "kv_cache_usage": kv,
            "ttft_avg_seconds": ttft,
            "requests_waiting": queue,
            "preemptions_total": preemptions,
        },
    }
    if proof_level is not None:
        r["proof_level"] = proof_level
    return r


def _anomaly(ts: float, kv: float = 0.92, ttft: float = 0.50,
             queue: int = 12, preemptions: int = 5,
             proof_level: str | None = None) -> dict:
    r: dict = {
        "status": "anomaly_detected",
        "metrics": {
            "timestamp": ts,
            "engine": "vllm",
            "kv_cache_usage": kv,
            "ttft_avg_seconds": ttft,
            "requests_waiting": queue,
            "preemptions_total": preemptions,
        },
        "anomaly": {"severity": "critical", "reasons": ["KV cache high"]},
    }
    if proof_level is not None:
        r["proof_level"] = proof_level
    return r


def _error(ts: float) -> dict:
    return {"status": "error", "error": "connection refused"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestComputeImpactEmpty:
    def test_no_reports(self):
        impact = compute_impact([])
        assert impact.cycles_monitored == 0
        assert impact.incidents_detected == 0
        assert impact.label == "No data yet."

    def test_as_dict_round_trip(self):
        impact = compute_impact([])
        d = impact.as_dict()
        assert isinstance(d, dict)
        assert d["cycles_monitored"] == 0
        assert d["proof_level"] == "unknown"


class TestComputeImpactHealthy:
    def test_all_healthy_no_incidents(self):
        t = time.time()
        reports = [_healthy(t), _healthy(t + 10), _healthy(t + 20)]
        impact = compute_impact(reports)
        assert impact.cycles_monitored == 3
        assert impact.incidents_detected == 0
        assert impact.kv_headroom_recovered_pct is None
        assert impact.ttft_improvement_pct is None
        assert "no incidents" in impact.label.lower()

    def test_proof_level_extracted_from_reports(self):
        t = time.time()
        reports = [_healthy(t, proof_level="live"), _healthy(t + 10)]
        impact = compute_impact(reports)
        assert impact.proof_level == "live"


class TestComputeImpactSingleAnomaly:
    def test_single_anomaly_no_followup(self):
        """One anomaly with no subsequent data → pending label."""
        t = time.time()
        reports = [_anomaly(t)]
        impact = compute_impact(reports)
        assert impact.incidents_detected == 1
        assert impact.kv_headroom_recovered_pct is None
        assert "Awaiting" in impact.label

    def test_anomaly_as_first_report_no_detection_latency(self):
        """No healthy report before anomaly → detection latency is None."""
        t = time.time()
        reports = [_anomaly(t)]
        impact = compute_impact(reports)
        assert impact.detection_latency_s is None


class TestComputeImpactRecovery:
    def test_kv_headroom_recovered(self):
        t = time.time()
        reports = [
            _healthy(t, kv=0.40),
            _anomaly(t + 30, kv=0.92),
            _healthy(t + 60, kv=0.50),
        ]
        impact = compute_impact(reports)
        # 0.92 - 0.50 = 0.42 → 42%
        assert impact.kv_headroom_recovered_pct == 42.0

    def test_ttft_improvement(self):
        t = time.time()
        reports = [
            _healthy(t, ttft=0.10),
            _anomaly(t + 30, ttft=0.50),
            _healthy(t + 60, ttft=0.12),
        ]
        impact = compute_impact(reports)
        # (0.50 - 0.12) / 0.50 * 100 = 76%
        assert impact.ttft_improvement_pct == 76.0

    def test_ttft_degradation(self):
        t = time.time()
        reports = [
            _healthy(t, ttft=0.10),
            _anomaly(t + 30, ttft=0.20),
            _healthy(t + 60, ttft=0.30),
        ]
        impact = compute_impact(reports)
        # (0.20 - 0.30) / 0.20 * 100 = -50% → negative means degraded
        assert impact.ttft_improvement_pct is not None
        assert impact.ttft_improvement_pct < 0

    def test_queue_depth_reduction(self):
        t = time.time()
        reports = [
            _healthy(t),
            _anomaly(t + 30, queue=15),
            _healthy(t + 60, queue=2),
        ]
        impact = compute_impact(reports)
        assert impact.queue_depth_reduction == 13

    def test_preemptions_avoided(self):
        t = time.time()
        reports = [
            _healthy(t, preemptions=0),
            _anomaly(t + 30, preemptions=10),
            _healthy(t + 60, preemptions=10),  # no growth
        ]
        impact = compute_impact(reports)
        assert impact.preemptions_avoided == 0  # no growth = 0 avoided

    def test_preemptions_still_growing(self):
        """If preemptions are still growing, preemptions_avoided is None."""
        t = time.time()
        reports = [
            _healthy(t, preemptions=0),
            _anomaly(t + 30, preemptions=10),
            _healthy(t + 60, preemptions=20),  # still growing
        ]
        impact = compute_impact(reports)
        assert impact.preemptions_avoided is None

    def test_detection_latency(self):
        t = time.time()
        reports = [
            _healthy(t),
            _healthy(t + 10),
            _anomaly(t + 40),
        ]
        impact = compute_impact(reports)
        # Last healthy before anomaly is at t+10, anomaly at t+40 → 30s
        assert impact.detection_latency_s == 30.0

    def test_full_recovery_label_contains_all_deltas(self):
        t = time.time()
        reports = [
            _healthy(t, kv=0.40, ttft=0.10, queue=0, preemptions=0),
            _anomaly(t + 30, kv=0.92, ttft=0.50, queue=12, preemptions=5),
            _healthy(t + 60, kv=0.50, ttft=0.12, queue=1, preemptions=5),
        ]
        impact = compute_impact(reports)
        assert "KV" in impact.label
        assert "TTFT" in impact.label
        assert "Queue" in impact.label
        assert "Detected" in impact.label


class TestComputeImpactEdgeCases:
    def test_error_reports_ignored_for_metrics(self):
        t = time.time()
        reports = [_healthy(t), _error(t + 10), _healthy(t + 20)]
        impact = compute_impact(reports)
        assert impact.incidents_detected == 0

    def test_missing_metrics_fields_handled(self):
        """Reports with sparse metrics should not crash."""
        reports = [
            {"status": "healthy", "metrics": {"timestamp": time.time()}},
            {"status": "anomaly_detected", "metrics": {"timestamp": time.time() + 30, "kv_cache_usage": 0.9},
             "anomaly": {"severity": "warning", "reasons": ["test"]}},
            {"status": "healthy", "metrics": {"timestamp": time.time() + 60}},
        ]
        impact = compute_impact(reports)
        assert impact.incidents_detected == 1
        # KV headroom can be computed (0.9 vs missing → None for latest_kv)
        # but should not raise

    def test_proof_level_defaults_to_unknown(self):
        t = time.time()
        reports = [_healthy(t)]
        impact = compute_impact(reports)
        assert impact.proof_level == "unknown"

    def test_proof_level_from_mock(self):
        t = time.time()
        reports = [_healthy(t, proof_level="mock"), _anomaly(t + 30, proof_level="mock")]
        impact = compute_impact(reports)
        assert impact.proof_level == "mock"

    def test_small_kv_delta_not_reported(self):
        """Deltas <= 1% are noise and should not be reported."""
        t = time.time()
        reports = [
            _healthy(t),
            _anomaly(t + 30, kv=0.50),
            _healthy(t + 60, kv=0.495),
        ]
        impact = compute_impact(reports)
        assert impact.kv_headroom_recovered_pct is None

    def test_small_ttft_delta_not_reported(self):
        """TTFT changes < 1% are noise."""
        t = time.time()
        reports = [
            _healthy(t),
            _anomaly(t + 30, ttft=1.00),
            _healthy(t + 60, ttft=0.995),
        ]
        impact = compute_impact(reports)
        assert impact.ttft_improvement_pct is None


class TestOperationalImpactDataclass:
    def test_defaults(self):
        impact = OperationalImpact()
        assert impact.kv_headroom_recovered_pct is None
        assert impact.cycles_monitored == 0
        assert impact.proof_level == "unknown"
        assert impact.label == "No data yet."

    def test_as_dict_keys(self):
        impact = OperationalImpact(cycles_monitored=5, proof_level="mock")
        d = impact.as_dict()
        expected_keys = {
            "kv_headroom_recovered_pct", "ttft_improvement_pct",
            "queue_depth_reduction", "preemptions_avoided",
            "detection_latency_s", "cycles_monitored",
            "incidents_detected", "proof_level", "label",
        }
        assert set(d.keys()) == expected_keys
        assert d["cycles_monitored"] == 5
        assert d["proof_level"] == "mock"
