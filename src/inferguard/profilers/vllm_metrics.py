"""vLLM Prometheus text ingestion for profiler bridge reports."""

from __future__ import annotations

import re
from collections.abc import Iterable

from inferguard.profilers.schema import RequestMetrics

_SAMPLE_RE = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+(?P<value>[-+0-9.eE]+)\s*$")


def parse_prometheus_samples(text: str) -> dict[str, float]:
    samples: dict[str, float] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _SAMPLE_RE.match(stripped)
        if not match:
            continue
        try:
            samples[match.group("name")] = float(match.group("value"))
        except ValueError:
            continue
    return samples


def parse_vllm_prometheus(text: str) -> RequestMetrics:
    samples = parse_prometheus_samples(text)
    return RequestMetrics(
        source="vllm_prometheus",
        ttft_seconds=_first(samples, ("vllm:time_to_first_token_seconds_sum", "vllm_time_to_first_token_seconds_sum")),
        itl_seconds=_first(samples, ("vllm:inter_token_latency_seconds_sum", "vllm_inter_token_latency_seconds_sum")),
        latency_seconds=_first(samples, ("vllm:e2e_request_latency_seconds_sum", "vllm_e2e_request_latency_seconds_sum")),
        tokens_per_second=_first(samples, ("vllm:generation_tokens_total", "vllm_generation_tokens_total")),
        requests_per_second=_first(samples, ("vllm:request_success_total", "vllm_request_success_total")),
        queue_depth=_first(samples, ("vllm:num_requests_waiting", "vllm_num_requests_waiting")),
        raw_metrics=samples,
    )


def _first(samples: dict[str, float], names: Iterable[str]) -> float | None:
    for name in names:
        if name in samples:
            return samples[name]
    return None
