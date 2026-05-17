"""CacheBlend serde metric normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from inferguard.metrics_core import parse_labeled_prometheus_text

_ENCODE_SUM = {
    "lmcache_blend_serde_encode_duration_seconds_sum",
    "lmcache_blend.serde_encode_duration_seconds_sum",
}
_ENCODE_COUNT = {
    "lmcache_blend_serde_encode_duration_seconds_count",
    "lmcache_blend.serde_encode_duration_seconds_count",
}
_DECODE_SUM = {
    "lmcache_blend_serde_decode_duration_seconds_sum",
    "lmcache_blend.serde_decode_duration_seconds_sum",
}
_DECODE_COUNT = {
    "lmcache_blend_serde_decode_duration_seconds_count",
    "lmcache_blend.serde_decode_duration_seconds_count",
}
_BYTES_IN = {
    "lmcache_blend_serde_bytes_in_total",
    "lmcache_blend.serde_bytes_in",
}
_BYTES_OUT = {
    "lmcache_blend_serde_bytes_out_total",
    "lmcache_blend.serde_bytes_out",
}
_FAILURES = {
    "lmcache_blend_serde_failures_total",
    "lmcache_blend.serde_failures",
}


@dataclass(frozen=True)
class CacheBlendSerdeSummary:
    """Normalized CacheBlend serde counters, histograms, and ratios."""

    present: bool
    bytes_in_by_serde: dict[str, float]
    bytes_out_by_serde: dict[str, float]
    compression_ratio_by_serde: dict[str, float | None]
    failures_by_serde_direction: dict[tuple[str, str], float]
    total_failures: float
    encode_avg_seconds_by_serde: dict[str, float]
    decode_avg_seconds_by_serde: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "present": self.present,
            "bytes_in_by_serde": self.bytes_in_by_serde,
            "bytes_out_by_serde": self.bytes_out_by_serde,
            "compression_ratio_by_serde": self.compression_ratio_by_serde,
            "failures_by_serde_direction": {
                f"{serde_type}:{direction}": value
                for (serde_type, direction), value in self.failures_by_serde_direction.items()
            },
            "total_failures": self.total_failures,
            "encode_avg_seconds_by_serde": self.encode_avg_seconds_by_serde,
            "decode_avg_seconds_by_serde": self.decode_avg_seconds_by_serde,
        }


def analyze_cacheblend_serde_metrics(text: str) -> CacheBlendSerdeSummary:
    """Parse CacheBlend serde metrics and compute compression ratios."""
    bytes_in: dict[str, float] = {}
    bytes_out: dict[str, float] = {}
    failures: dict[tuple[str, str], float] = {}
    encode_sum: dict[str, float] = {}
    encode_count: dict[str, float] = {}
    decode_sum: dict[str, float] = {}
    decode_count: dict[str, float] = {}

    present = False
    for sample in parse_labeled_prometheus_text(text):
        name = sample.name
        serde_type = sample.labels.get("serde_type", "unknown")
        if name in _BYTES_IN:
            present = True
            bytes_in[serde_type] = bytes_in.get(serde_type, 0.0) + sample.value
        elif name in _BYTES_OUT:
            present = True
            bytes_out[serde_type] = bytes_out.get(serde_type, 0.0) + sample.value
        elif name in _FAILURES:
            present = True
            direction = sample.labels.get("direction", "unknown")
            key = (serde_type, direction)
            failures[key] = failures.get(key, 0.0) + sample.value
        elif name in _ENCODE_SUM:
            present = True
            encode_sum[serde_type] = encode_sum.get(serde_type, 0.0) + sample.value
        elif name in _ENCODE_COUNT:
            present = True
            encode_count[serde_type] = encode_count.get(serde_type, 0.0) + sample.value
        elif name in _DECODE_SUM:
            present = True
            decode_sum[serde_type] = decode_sum.get(serde_type, 0.0) + sample.value
        elif name in _DECODE_COUNT:
            present = True
            decode_count[serde_type] = decode_count.get(serde_type, 0.0) + sample.value

    serde_types = sorted(set(bytes_in) | set(bytes_out))
    return CacheBlendSerdeSummary(
        present=present,
        bytes_in_by_serde=bytes_in,
        bytes_out_by_serde=bytes_out,
        compression_ratio_by_serde={
            serde_type: _safe_ratio(bytes_out.get(serde_type), bytes_in.get(serde_type))
            for serde_type in serde_types
        },
        failures_by_serde_direction=failures,
        total_failures=sum(failures.values()),
        encode_avg_seconds_by_serde=_histogram_avgs(encode_sum, encode_count),
        decode_avg_seconds_by_serde=_histogram_avgs(decode_sum, decode_count),
    )


def _histogram_avgs(sums: dict[str, float], counts: dict[str, float]) -> dict[str, float]:
    return {
        serde_type: total / counts[serde_type]
        for serde_type, total in sums.items()
        if counts.get(serde_type, 0) > 0
    }


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


__all__ = ["CacheBlendSerdeSummary", "analyze_cacheblend_serde_metrics"]
