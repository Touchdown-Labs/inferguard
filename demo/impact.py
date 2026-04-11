"""Operational impact computation for InferGuard demo UI.

Computes relative operational deltas from a sequence of agent reports.
This is a presentation-layer module — it does NOT define dollar-cost
models or claim calibrated savings. All outputs are clearly labeled as
operational deltas observed during the current session.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class OperationalImpact:
    """Operational deltas observed during an InferGuard monitoring session."""

    kv_headroom_recovered_pct: float | None = None
    ttft_improvement_pct: float | None = None
    queue_depth_reduction: int | None = None
    preemptions_avoided: int | None = None
    detection_latency_s: float | None = None
    cycles_monitored: int = 0
    incidents_detected: int = 0
    proof_level: str = "unknown"
    label: str = "No data yet."

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_impact(reports: list[dict[str, Any]]) -> OperationalImpact:
    """Compute operational deltas from a sequence of agent reports.

    Compares the first anomaly snapshot to the most recent snapshot
    to derive relative improvements. If no anomaly has been detected
    or no resolution data exists, fields are None and the label says
    "pending" rather than fabricating numbers.
    """
    if not reports:
        return OperationalImpact()

    proof_level = "unknown"
    for r in reports:
        if "proof_level" in r:
            proof_level = r["proof_level"]
            break

    cycles = len(reports)
    incidents = sum(1 for r in reports if r.get("status") == "anomaly_detected")

    # Find first anomaly and most recent report with metrics
    first_anomaly: dict[str, Any] | None = None
    first_anomaly_idx: int = -1
    latest_with_metrics: dict[str, Any] | None = None

    for i, r in enumerate(reports):
        if r.get("status") == "anomaly_detected" and first_anomaly is None:
            first_anomaly = r
            first_anomaly_idx = i
        if r.get("metrics"):
            latest_with_metrics = r

    impact = OperationalImpact(
        cycles_monitored=cycles,
        incidents_detected=incidents,
        proof_level=proof_level,
    )

    if first_anomaly is None:
        impact.label = f"Healthy — {cycles} cycles monitored, no incidents."
        return impact

    if latest_with_metrics is None or latest_with_metrics is first_anomaly:
        impact.label = (
            f"Incident detected (cycle {first_anomaly_idx + 1}). "
            "Awaiting follow-up data for impact assessment."
        )
        # Still compute detection latency if we can
        impact.detection_latency_s = _detection_latency(reports, first_anomaly_idx)
        return impact

    anomaly_metrics = first_anomaly.get("metrics", {})
    latest_metrics = latest_with_metrics.get("metrics", {})

    # KV headroom recovered
    anomaly_kv = anomaly_metrics.get("kv_cache_usage")
    latest_kv = latest_metrics.get("kv_cache_usage")
    if _is_numeric(anomaly_kv) and _is_numeric(latest_kv):
        delta = float(anomaly_kv) - float(latest_kv)
        if delta > 0.01:
            impact.kv_headroom_recovered_pct = round(delta * 100, 1)

    # TTFT improvement
    anomaly_ttft = anomaly_metrics.get("ttft_avg_seconds")
    latest_ttft = latest_metrics.get("ttft_avg_seconds")
    if _is_numeric(anomaly_ttft) and _is_numeric(latest_ttft) and float(anomaly_ttft) > 0:
        pct = ((float(anomaly_ttft) - float(latest_ttft)) / float(anomaly_ttft)) * 100
        if abs(pct) > 1.0:
            impact.ttft_improvement_pct = round(pct, 1)

    # Queue depth reduction
    anomaly_queue = anomaly_metrics.get("requests_waiting", 0)
    latest_queue = latest_metrics.get("requests_waiting", 0)
    if _is_numeric(anomaly_queue) and _is_numeric(latest_queue):
        reduction = int(anomaly_queue) - int(latest_queue)
        if reduction > 0:
            impact.queue_depth_reduction = reduction

    # Preemptions avoided (delta between anomaly peak and latest)
    anomaly_preemptions = anomaly_metrics.get("preemptions_total", 0)
    latest_preemptions = latest_metrics.get("preemptions_total", 0)
    if _is_numeric(anomaly_preemptions) and _is_numeric(latest_preemptions):
        # If latest preemptions haven't grown much, that's "avoided"
        # We compare the rate of growth, not absolute numbers
        growth = int(latest_preemptions) - int(anomaly_preemptions)
        if growth <= 0:
            impact.preemptions_avoided = abs(growth)

    # Detection latency
    impact.detection_latency_s = _detection_latency(reports, first_anomaly_idx)

    # Build human-readable label
    parts: list[str] = []
    if impact.kv_headroom_recovered_pct is not None:
        parts.append(f"Recovered {impact.kv_headroom_recovered_pct:.0f}% KV headroom")
    if impact.ttft_improvement_pct is not None:
        if impact.ttft_improvement_pct > 0:
            parts.append(f"TTFT improved {impact.ttft_improvement_pct:.0f}%")
        else:
            parts.append(f"TTFT degraded {abs(impact.ttft_improvement_pct):.0f}%")
    if impact.queue_depth_reduction is not None:
        parts.append(f"Queue reduced by {impact.queue_depth_reduction}")
    if impact.preemptions_avoided is not None:
        parts.append(f"{impact.preemptions_avoided} preemptions avoided")
    if impact.detection_latency_s is not None:
        parts.append(f"Detected in {impact.detection_latency_s:.1f}s")

    if parts:
        impact.label = " · ".join(parts) + "."
    else:
        impact.label = f"{incidents} incident(s) across {cycles} cycles. Impact pending."

    return impact


def _detection_latency(
    reports: list[dict[str, Any]], anomaly_idx: int
) -> float | None:
    """Time from last healthy report to the anomaly detection."""
    if anomaly_idx <= 0:
        return None

    anomaly_ts = _report_timestamp(reports[anomaly_idx])
    if anomaly_ts is None:
        return None

    # Walk backwards to find the last healthy report before the anomaly
    for i in range(anomaly_idx - 1, -1, -1):
        if reports[i].get("status") == "healthy":
            healthy_ts = _report_timestamp(reports[i])
            if healthy_ts is not None:
                return round(anomaly_ts - healthy_ts, 1)

    return None


def _report_timestamp(report: dict[str, Any]) -> float | None:
    """Extract timestamp from a report's metrics."""
    metrics = report.get("metrics", {})
    ts = metrics.get("timestamp")
    return float(ts) if _is_numeric(ts) else None


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and value is not None
