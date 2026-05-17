"""CacheBlend metric normalization and derived ratios."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from inferguard.metrics_core import parse_labeled_prometheus_text

_COUNTER_ALIASES = {
    "lookup_requests": (
        "lmcache_blend_lookup_requests_total",
        "lmcache_blend.lookup_requests",
    ),
    "lookup_hit_tokens": (
        "lmcache_blend_lookup_hit_tokens_total",
        "lmcache_blend.lookup_hit_tokens",
    ),
    "lookup_requested_tokens": (
        "lmcache_blend_lookup_requested_tokens_total",
        "lmcache_blend.lookup_requested_tokens",
    ),
    "lookup_fingerprint_hits": (
        "lmcache_blend_lookup_fingerprint_hits_total",
        "lmcache_blend.lookup_fingerprint_hits",
    ),
    "lookup_storage_hits": (
        "lmcache_blend_lookup_storage_hits_total",
        "lmcache_blend.lookup_storage_hits",
    ),
    "lookup_stale_chunks": (
        "lmcache_blend_lookup_stale_chunks_total",
        "lmcache_blend.lookup_stale_chunks",
    ),
    "lookup_no_gpu_context_errors": (
        "lmcache_blend_lookup_no_gpu_context_errors_total",
        "lmcache_blend.lookup_no_gpu_context_errors",
    ),
    "retrieve_requests": (
        "lmcache_blend_retrieve_requests_total",
        "lmcache_blend.retrieve_requests",
    ),
    "retrieve_successes": (
        "lmcache_blend_retrieve_successes_total",
        "lmcache_blend.retrieve_successes",
    ),
    "retrieve_failures": (
        "lmcache_blend_retrieve_failures_total",
        "lmcache_blend.retrieve_failures",
    ),
    "retrieve_chunks": (
        "lmcache_blend_retrieve_chunks_total",
        "lmcache_blend.retrieve_chunks",
    ),
    "store_pre_computed": (
        "lmcache_blend_store_pre_computed_total",
        "lmcache_blend.store_pre_computed",
    ),
    "store_pre_computed_requests": (
        "lmcache_blend_store_pre_computed_requests_total",
        "lmcache_blend.store_pre_computed_requests",
    ),
    "store_pre_computed_chunks": (
        "lmcache_blend_store_pre_computed_chunks_total",
        "lmcache_blend.store_pre_computed_chunks",
    ),
    "store_pre_computed_failures": (
        "lmcache_blend_store_pre_computed_failures_total",
        "lmcache_blend.store_pre_computed_failures",
    ),
    "store_final": (
        "lmcache_blend_store_final_total",
        "lmcache_blend.store_final",
    ),
    "store_final_requests": (
        "lmcache_blend_store_final_requests_total",
        "lmcache_blend.store_final_requests",
    ),
    "store_final_chunks": (
        "lmcache_blend_store_final_chunks_total",
        "lmcache_blend.store_final_chunks",
    ),
    "store_final_failures": (
        "lmcache_blend_store_final_failures_total",
        "lmcache_blend.store_final_failures",
    ),
    "fingerprint_registered": (
        "lmcache_blend_fingerprint_registered_total",
        "lmcache_blend.fingerprint_registered",
    ),
    "fingerprints_registered": (
        "lmcache_blend_fingerprints_registered_total",
        "lmcache_blend.fingerprints_registered",
    ),
    "fingerprint_evicted": (
        "lmcache_blend_fingerprint_evicted_total",
        "lmcache_blend.fingerprint_evicted",
    ),
    "chunks_evicted": (
        "lmcache_blend_chunks_evicted_total",
        "lmcache_blend.chunks_evicted",
    ),
}

_ALIAS_TO_KEY = {alias: key for key, aliases in _COUNTER_ALIASES.items() for alias in aliases}


@dataclass(frozen=True)
class CacheBlendMetricsSummary:
    """Normalized CacheBlend counter surface and derived ratios."""

    present: bool
    counters: dict[str, float]
    blend_hit_rate: float | None
    stale_ratio: float | None
    fingerprint_efficiency: float | None
    eviction_rate: float | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "present": self.present,
            "counters": self.counters,
            "blend_hit_rate": self.blend_hit_rate,
            "stale_ratio": self.stale_ratio,
            "fingerprint_efficiency": self.fingerprint_efficiency,
            "eviction_rate": self.eviction_rate,
        }


def analyze_cacheblend_metrics(text: str) -> CacheBlendMetricsSummary:
    """Parse CacheBlend Prometheus counters and compute derived ratios."""
    counters: dict[str, float] = {}
    for sample in parse_labeled_prometheus_text(text):
        key = _ALIAS_TO_KEY.get(sample.name)
        if key is None:
            continue
        counters[key] = counters.get(key, 0.0) + sample.value

    return CacheBlendMetricsSummary(
        present=bool(counters),
        counters=counters,
        blend_hit_rate=_safe_ratio(
            counters.get("lookup_hit_tokens"), counters.get("lookup_requested_tokens")
        ),
        stale_ratio=_safe_ratio(
            counters.get("lookup_stale_chunks"), counters.get("lookup_fingerprint_hits")
        ),
        fingerprint_efficiency=_safe_ratio(
            counters.get("lookup_storage_hits"), counters.get("lookup_fingerprint_hits")
        ),
        eviction_rate=_eviction_rate(counters),
    )


def _eviction_rate(counters: dict[str, float]) -> float | None:
    plural = _safe_ratio(counters.get("chunks_evicted"), counters.get("fingerprints_registered"))
    if plural is not None:
        return plural
    return _safe_ratio(counters.get("fingerprint_evicted"), counters.get("fingerprint_registered"))


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


__all__ = ["CacheBlendMetricsSummary", "analyze_cacheblend_metrics"]
