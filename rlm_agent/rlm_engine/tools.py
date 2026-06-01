"""Zero-LLM-token diagnostic tools for RLM REPL environments."""

from __future__ import annotations

from typing import Any


def calculate_kv_slope(snapshots: list[dict[str, Any]]) -> float:
    """Run linear regression on KV cache usage snapshot window to get slope/sec.
    
    y = mx + c
    m = (n*sum(xy) - sum(x)*sum(y)) / (n*sum(x^2) - (sum(x))^2)
    """
    if not snapshots or len(snapshots) < 2:
        return 0.0
    
    n = len(snapshots)
    x = [float(s.get("timestamp") or i) for i, s in enumerate(snapshots)]
    y = [float(s.get("kv_cache_usage") or 0.0) for s in snapshots]
    
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)
    
    denominator = (n * sum_x2 - sum_x * sum_x)
    if abs(denominator) < 1e-6:
        # Fallback to simple finite difference if timestamps are identical
        return (y[-1] - y[0]) / max(x[-1] - x[0], 1.0)
        
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return float(round(slope, 4))


def match_prior_incident(anomaly_type: str) -> dict[str, Any]:
    """Simulate semantic lookup for prior incidents and return the best compaction setting."""
    # Pre-calculated from Touchdown's L5 Upstash vector learning rows
    priors = {
        "kv_saturation": {
            "id": "inc-042",
            "failure_mode": "kv_saturation",
            "resolution": "recommend_compaction",
            "remediation_parameters": {"threshold_t": 1.0, "target_ratio": 0.68}
        },
        "ttft_cliff": {
            "id": "inc-089",
            "failure_mode": "ttft_cliff",
            "resolution": "recommend_compaction",
            "remediation_parameters": {"threshold_t": 2.0, "target_ratio": 0.55}
        }
    }
    return priors.get(anomaly_type, {
        "id": "inc-generic",
        "failure_mode": "unknown",
        "resolution": "recommend_compaction",
        "remediation_parameters": {"threshold_t": 1.0, "target_ratio": 0.75}
    })


def slice_redis_logs(events: list[dict[str, Any]], start: int = 0, end: int = -1) -> list[dict[str, Any]]:
    """Programmatically partition redis tails to reduce LLM prompt token bloat."""
    if not events:
        return []
    if end == -1 or end >= len(events):
        return events[start:]
    return events[start:end]
