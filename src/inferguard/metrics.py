"""Metric snapshot extraction and anomaly detection."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

try:  # Optional future integration path; standalone mode is the default.
    from inferscope.telemetry.prometheus import ScrapeResult  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    ScrapeResult = None  # type: ignore[assignment]


@dataclass(slots=True)
class MetricSnapshot:
    timestamp: float
    engine: str
    kv_cache_usage: float = 0.0
    cpu_cache_usage: float = 0.0
    prefix_cache_hit_rate: float = 0.0
    requests_running: int = 0
    requests_waiting: int = 0
    requests_swapped: int = 0
    preemptions_total: int = 0
    ttft_avg_seconds: float | None = None
    tpot_avg_seconds: float | None = None
    error: str = ""

    @staticmethod
    async def scrape_endpoint(endpoint_url: str) -> "MetricSnapshot":
        """Fetch and parse Prometheus metrics from an inference endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{endpoint_url.rstrip('/')}/metrics")
                response.raise_for_status()
            return MetricSnapshot.from_prometheus_text(response.text)
        except Exception as exc:  # pragma: no cover - exercised through agent behavior
            return MetricSnapshot(timestamp=time.time(), engine="unknown", error=str(exc))

    @staticmethod
    def from_prometheus_text(text: str) -> "MetricSnapshot":
        metrics = _parse_prometheus_text(text)
        engine = _detect_engine(metrics)

        if engine == "vllm":
            return MetricSnapshot(
                timestamp=time.time(),
                engine="vllm",
                kv_cache_usage=metrics.get("vllm:gpu_cache_usage_perc", 0.0),
                cpu_cache_usage=metrics.get("vllm:cpu_cache_usage_perc", 0.0),
                prefix_cache_hit_rate=metrics.get("vllm:gpu_prefix_cache_hit_rate", 0.0),
                requests_running=int(metrics.get("vllm:num_requests_running", 0)),
                requests_waiting=int(metrics.get("vllm:num_requests_waiting", 0)),
                requests_swapped=int(metrics.get("vllm:num_requests_swapped", 0)),
                preemptions_total=int(metrics.get("vllm:num_preemptions_total", 0)),
                ttft_avg_seconds=_histogram_avg(metrics, "vllm:time_to_first_token_seconds"),
                tpot_avg_seconds=_histogram_avg(metrics, "vllm:time_per_output_token_seconds"),
            )

        if engine == "sglang":
            return MetricSnapshot(
                timestamp=time.time(),
                engine="sglang",
                kv_cache_usage=metrics.get("sglang:token_usage", 0.0),
                prefix_cache_hit_rate=metrics.get("sglang:cache_hit_rate", 0.0),
                requests_running=int(metrics.get("sglang:num_running_reqs", 0)),
                requests_waiting=int(metrics.get("sglang:num_queue_reqs", 0)),
                preemptions_total=int(metrics.get("sglang:num_preemptions_total", 0)),
                ttft_avg_seconds=_histogram_avg(metrics, "sglang:time_to_first_token_seconds"),
                tpot_avg_seconds=_histogram_avg(metrics, "sglang:time_per_output_token_seconds"),
            )

        return MetricSnapshot(timestamp=time.time(), engine="unknown")

    @staticmethod
    def from_scrape(scrape: "ScrapeResult") -> "MetricSnapshot":
        """Optional bridge for a verified EasyInference/Inferscope scrape type."""
        if getattr(scrape, "error", ""):
            return MetricSnapshot(
                timestamp=time.time(),
                engine=getattr(scrape, "engine", "unknown"),
                error=getattr(scrape, "error", ""),
            )
        return MetricSnapshot.from_prometheus_text(getattr(scrape, "raw_text", ""))

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "engine": self.engine,
            "kv_cache_usage": self.kv_cache_usage,
            "cpu_cache_usage": self.cpu_cache_usage,
            "prefix_cache_hit_rate": self.prefix_cache_hit_rate,
            "requests_running": self.requests_running,
            "requests_waiting": self.requests_waiting,
            "requests_swapped": self.requests_swapped,
            "preemptions_total": self.preemptions_total,
            "ttft_avg_seconds": self.ttft_avg_seconds,
            "tpot_avg_seconds": self.tpot_avg_seconds,
            "error": self.error,
        }


def _detect_engine(metrics: dict[str, float]) -> str:
    if any(name.startswith("vllm:") for name in metrics):
        return "vllm"
    if any(name.startswith("sglang:") for name in metrics):
        return "sglang"
    return "unknown"


def _parse_prometheus_text(text: str) -> dict[str, float]:
    """Parse a small subset of Prometheus exposition text into numeric values."""
    metrics: dict[str, float] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        raw_name, raw_value = parts[0], parts[-1]
        name = raw_name.split("{", 1)[0]

        try:
            metrics[name] = float(raw_value)
        except ValueError:
            continue

    return metrics


def _histogram_avg(metrics: dict[str, float], prefix: str) -> float | None:
    total = metrics.get(f"{prefix}_sum")
    count = metrics.get(f"{prefix}_count")
    if total is None or count is None or count == 0:
        return None
    return total / count


@dataclass(slots=True)
class AnomalyResult:
    is_anomaly: bool = False
    reasons: list[str] = field(default_factory=list)
    severity: str = "none"

    def as_dict(self) -> dict[str, object]:
        return {
            "is_anomaly": self.is_anomaly,
            "reasons": list(self.reasons),
            "severity": self.severity,
        }


def get_effective_kv_threshold(model_name: str, base_threshold: float = 0.85) -> float:
    lower = model_name.lower() if model_name else ""

    if "deepseek" in lower and "r1" in lower and "distill" not in lower:
        return base_threshold * 0.5
    if "qwen3.5" in lower or "qwen-3.5" in lower:
        return base_threshold * 0.7
    return base_threshold


def detect_rlm_anomalies(
    current: MetricSnapshot,
    previous: MetricSnapshot | None,
    model_name: str = "",
) -> list[str]:
    lower = model_name.lower() if model_name else ""
    is_rlm = any(keyword in lower for keyword in ("deepseek-r1", "qwen3.5", "gpt-oss", "gptoss"))
    if not is_rlm or current.error:
        return []

    reasons: list[str] = []

    if current.prefix_cache_hit_rate < 0.3 and current.requests_running > 5:
        reasons.append(
            f"RLM prefix cache thrashing: hit rate {current.prefix_cache_hit_rate:.0%} "
            f"with {current.requests_running} active requests."
        )

    if previous and not previous.error:
        kv_delta = current.kv_cache_usage - previous.kv_cache_usage
        if kv_delta > 0.15:
            reasons.append(
                f"RLM KV surge: {previous.kv_cache_usage:.0%} → {current.kv_cache_usage:.0%} in one cycle."
            )

        if current.requests_running > 0:
            preemption_delta = current.preemptions_total - previous.preemptions_total
            preemption_rate = preemption_delta / max(current.requests_running, 1)
            if preemption_delta > 0 and preemption_rate > 0.5:
                reasons.append(
                    f"RLM preemption storm: {preemption_delta} new preemptions for "
                    f"{current.requests_running} running requests (rate: {preemption_rate:.1f})."
                )

    return reasons


def detect_anomalies(
    current: MetricSnapshot,
    baseline_ttft: float | None,
    previous_preemptions: int | None = None,
    kv_threshold: float = 0.85,
    ttft_multiplier: float = 2.0,
) -> AnomalyResult:
    result = AnomalyResult()
    reasons: list[str] = []

    if current.error:
        return result

    if current.kv_cache_usage > kv_threshold:
        reasons.append(f"KV cache at {current.kv_cache_usage:.0%} (threshold: {kv_threshold:.0%})")
        result.severity = "critical" if current.kv_cache_usage > 0.95 else "warning"

    if (
        baseline_ttft is not None
        and current.ttft_avg_seconds is not None
        and current.ttft_avg_seconds > baseline_ttft * ttft_multiplier
    ):
        reasons.append(
            f"TTFT {current.ttft_avg_seconds * 1000:.0f}ms "
            f"(baseline: {baseline_ttft * 1000:.0f}ms, {ttft_multiplier}x threshold)"
        )
        result.severity = "critical"

    if current.requests_waiting > 10:
        reasons.append(f"Queue depth: {current.requests_waiting} requests waiting")
        if result.severity != "critical":
            result.severity = "warning"

    if previous_preemptions is not None:
        preemption_delta = current.preemptions_total - previous_preemptions
        if preemption_delta > 0:
            reasons.append(f"Preemptions: {preemption_delta} new since last scrape")
            result.severity = "critical"

    if current.requests_swapped > 0:
        reasons.append(f"Swap active: {current.requests_swapped} requests swapped to CPU")
        if result.severity != "critical":
            result.severity = "warning"

    if reasons:
        result.is_anomaly = True
        result.reasons = reasons

    return result

