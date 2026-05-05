"""Normalized LMCache/TensorMesh metrics schema and Prometheus normalization.

The aliases in this module are intentionally permissive because LMCache metric
names have varied across public examples and integration layers. Parsed fields
are evidence only when the source metric is present in live Prometheus output;
unknown LMCache-prefixed metric names are retained in ``raw_metrics_extra`` for
audit/debugging instead of being discarded.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from inferguard.metrics_core import LabeledSample, parse_labeled_prometheus_text


@dataclass(frozen=True)
class LmcacheMetrics:
    """Normalized LMCache metric snapshot.

    ``None`` means the metric was not present. Boolean fields are parsed from
    numeric gauges or mode labels when available, not inferred from workload
    shape.
    """

    lmcache_enabled: bool | None = None
    lmcache_hit_count: int | None = None
    lmcache_miss_count: int | None = None
    lmcache_hit_rate: float | None = None
    lmcache_eviction_count: int | None = None
    lmcache_save_count: int | None = None
    lmcache_retrieve_count: int | None = None
    lmcache_tier_hbm_bytes: int | None = None
    lmcache_tier_cpu_bytes: int | None = None
    lmcache_tier_disk_bytes: int | None = None
    lmcache_tier_remote_bytes: int | None = None
    lmcache_offload_bytes_total: int | None = None
    lmcache_retrieve_latency_ms_p50: float | None = None
    lmcache_retrieve_latency_ms_p95: float | None = None
    lmcache_retrieve_latency_ms_p99: float | None = None
    lmcache_nixl_transfer_bytes: int | None = None
    lmcache_nixl_transfer_latency_ms: float | None = None
    lmcache_cacheblend_enabled: bool | None = None
    lmcache_cachegen_enabled: bool | None = None
    lmcache_mp_mode_enabled: bool | None = None
    lmcache_connector_type: str | None = None
    lmcache_cache_salt_enabled: bool | None = None
    # Backward-compatible v0.5 provisional fields retained for existing adapter callers.
    lmcache_remote_bytes_sent: int | None = None
    lmcache_remote_bytes_received: int | None = None
    lmcache_queue_depth: int | None = None
    raw_metrics_extra: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


NORMALIZED_LMCACHE_FIELDS: tuple[str, ...] = tuple(
    field for field in LmcacheMetrics.__dataclass_fields__ if field != "raw_metrics_extra"
)

# Selectors use Prometheus label matching. ``convert`` supports seconds->ms.
_ALIAS_TABLE: dict[str, tuple[dict[str, Any], ...]] = {
    "lmcache_enabled": (
        {"name": "lmcache:enabled", "type": "bool"},
        {"name": "lmcache_enabled", "type": "bool"},
        {"name": "lmcache_config_info", "label": "enabled", "type": "bool_label"},
    ),
    "lmcache_hit_count": (
        {"name": "lmcache:hit_count", "type": "int"},
        {"name": "lmcache:hit_count_total", "type": "int"},
        {"name": "lmcache_hit_count", "type": "int"},
        {"name": "lmcache_hits_total", "type": "int"},
        {"name": "lmcache_lookup_hits_total", "type": "int"},
        {"name": "lmcache_retrieve_hit_count_total", "type": "int"},
    ),
    "lmcache_miss_count": (
        {"name": "lmcache:miss_count", "type": "int"},
        {"name": "lmcache:miss_count_total", "type": "int"},
        {"name": "lmcache_miss_count", "type": "int"},
        {"name": "lmcache_misses_total", "type": "int"},
        {"name": "lmcache_lookup_misses_total", "type": "int"},
        {"name": "lmcache_retrieve_miss_count_total", "type": "int"},
    ),
    "lmcache_hit_rate": (
        {"name": "lmcache:hit_rate", "type": "float"},
        {"name": "lmcache_hit_rate", "type": "float"},
        {"name": "lmcache_cache_hit_rate", "type": "float"},
    ),
    "lmcache_eviction_count": (
        {"name": "lmcache:eviction_count", "type": "int"},
        {"name": "lmcache:eviction_count_total", "type": "int"},
        {"name": "lmcache_eviction_count", "type": "int"},
        {"name": "lmcache_evictions_total", "type": "int"},
        {"name": "lmcache_cache_evictions_total", "type": "int"},
    ),
    "lmcache_save_count": (
        {"name": "lmcache:save_count", "type": "int"},
        {"name": "lmcache:save_count_total", "type": "int"},
        {"name": "lmcache_save_count", "type": "int"},
        {"name": "lmcache_saves_total", "type": "int"},
    ),
    "lmcache_retrieve_count": (
        {"name": "lmcache:retrieve_count", "type": "int"},
        {"name": "lmcache:retrieve_count_total", "type": "int"},
        {"name": "lmcache_retrieve_count", "type": "int"},
        {"name": "lmcache_retrieves_total", "type": "int"},
    ),
    "lmcache_tier_hbm_bytes": (
        {"name": "lmcache:tier_usage_bytes", "labels": {"tier": "hbm"}, "type": "int"},
        {"name": "lmcache_tier_usage_bytes", "labels": {"tier": "hbm"}, "type": "int"},
        {"name": "lmcache_tier_hbm_bytes", "type": "int"},
        {"name": "lmcache_gpu_bytes", "type": "int"},
    ),
    "lmcache_tier_cpu_bytes": (
        {"name": "lmcache:tier_usage", "labels": {"tier": "cpu"}, "type": "int"},
        {"name": "lmcache:tier_usage_bytes", "labels": {"tier": "cpu"}, "type": "int"},
        {"name": "lmcache_tier_usage_bytes", "labels": {"tier": "cpu"}, "type": "int"},
        {"name": "lmcache_tier_cpu_bytes", "type": "int"},
        {"name": "lmcache_local_cpu_bytes", "type": "int"},
    ),
    "lmcache_tier_disk_bytes": (
        {"name": "lmcache:tier_usage", "labels": {"tier": "local_disk"}, "type": "int"},
        {"name": "lmcache:tier_usage_bytes", "labels": {"tier": "disk"}, "type": "int"},
        {"name": "lmcache:tier_usage_bytes", "labels": {"tier": "local_disk"}, "type": "int"},
        {"name": "lmcache_tier_usage_bytes", "labels": {"tier": "disk"}, "type": "int"},
        {"name": "lmcache_tier_disk_bytes", "type": "int"},
        {"name": "lmcache_tier_local_disk_bytes", "type": "int"},
    ),
    "lmcache_tier_remote_bytes": (
        {"name": "lmcache:tier_usage", "labels": {"tier": "remote"}, "type": "int"},
        {"name": "lmcache:tier_usage_bytes", "labels": {"tier": "remote"}, "type": "int"},
        {"name": "lmcache_tier_usage_bytes", "labels": {"tier": "remote"}, "type": "int"},
        {"name": "lmcache_tier_remote_bytes", "type": "int"},
        {"name": "lmcache_remote_bytes", "type": "int"},
    ),
    "lmcache_offload_bytes_total": (
        {"name": "lmcache:offload_bytes_total", "type": "int"},
        {"name": "lmcache_offload_bytes_total", "type": "int"},
        {"name": "lmcache_remote_bytes_sent_total", "type": "int"},
        {"name": "lmcache:remote_bytes_sent_total", "type": "int"},
    ),
    "lmcache_retrieve_latency_ms_p50": (
        {"name": "lmcache_retrieve_latency_ms", "labels": {"quantile": "0.5"}, "type": "float"},
        {"name": "lmcache_retrieve_latency_ms", "labels": {"quantile": "0.50"}, "type": "float"},
        {"name": "lmcache:retrieve_latency_ms", "labels": {"quantile": "0.5"}, "type": "float"},
        {
            "name": "lmcache_retrieve_latency_seconds",
            "labels": {"quantile": "0.5"},
            "type": "float",
            "convert": "seconds_to_ms",
        },
    ),
    "lmcache_retrieve_latency_ms_p95": (
        {"name": "lmcache_retrieve_latency_ms", "labels": {"quantile": "0.95"}, "type": "float"},
        {"name": "lmcache:retrieve_latency_ms", "labels": {"quantile": "0.95"}, "type": "float"},
        {
            "name": "lmcache_retrieve_latency_seconds",
            "labels": {"quantile": "0.95"},
            "type": "float",
            "convert": "seconds_to_ms",
        },
    ),
    "lmcache_retrieve_latency_ms_p99": (
        {"name": "lmcache_retrieve_latency_ms", "labels": {"quantile": "0.99"}, "type": "float"},
        {"name": "lmcache:retrieve_latency_ms", "labels": {"quantile": "0.99"}, "type": "float"},
        {
            "name": "lmcache_retrieve_latency_seconds",
            "labels": {"quantile": "0.99"},
            "type": "float",
            "convert": "seconds_to_ms",
        },
    ),
    "lmcache_nixl_transfer_bytes": (
        {"name": "lmcache:nixl_transfer_bytes", "type": "int"},
        {"name": "lmcache_nixl_transfer_bytes", "type": "int"},
        {"name": "lmcache_nixl_transfer_bytes_total", "type": "int"},
    ),
    "lmcache_nixl_transfer_latency_ms": (
        {"name": "lmcache:nixl_transfer_latency_ms", "type": "float"},
        {"name": "lmcache_nixl_transfer_latency_ms", "type": "float"},
        {
            "name": "lmcache_nixl_transfer_latency_seconds",
            "type": "float",
            "convert": "seconds_to_ms",
        },
    ),
    "lmcache_remote_bytes_sent": (
        {"name": "lmcache:remote_bytes_sent_total", "type": "int"},
        {"name": "lmcache_remote_bytes_sent_total", "type": "int"},
    ),
    "lmcache_remote_bytes_received": (
        {"name": "lmcache:remote_bytes_received_total", "type": "int"},
        {"name": "lmcache_remote_bytes_received_total", "type": "int"},
    ),
    "lmcache_queue_depth": (
        {"name": "lmcache:queue_depth", "type": "int"},
        {"name": "lmcache_queue_depth", "type": "int"},
    ),
    "lmcache_cacheblend_enabled": (
        {"name": "lmcache:cacheblend_enabled", "type": "bool"},
        {"name": "lmcache_cacheblend_enabled", "type": "bool"},
        {"name": "lmcache_config_info", "label": "cacheblend", "type": "bool_label"},
    ),
    "lmcache_cachegen_enabled": (
        {"name": "lmcache:cachegen_enabled", "type": "bool"},
        {"name": "lmcache_cachegen_enabled", "type": "bool"},
        {"name": "lmcache_config_info", "label": "cachegen", "type": "bool_label"},
    ),
    "lmcache_mp_mode_enabled": (
        {"name": "lmcache:mp_mode_enabled", "type": "bool"},
        {"name": "lmcache_mp_mode_enabled", "type": "bool"},
        {"name": "lmcache_config_info", "label": "mp_mode", "type": "bool_label"},
    ),
    "lmcache_connector_type": (
        {"name": "lmcache_config_info", "label": "connector", "type": "str_label"},
        {"name": "lmcache:connector_info", "label": "connector", "type": "str_label"},
        {"name": "lmcache_connector_info", "label": "connector", "type": "str_label"},
        {"name": "lmcache_nixl_transfer_bytes_total", "const": "nixl", "type": "str_const"},
    ),
    "lmcache_cache_salt_enabled": (
        {"name": "lmcache:cache_salt_enabled", "type": "bool"},
        {"name": "lmcache_cache_salt_enabled", "type": "bool"},
        {"name": "lmcache_config_info", "label": "cache_salt", "type": "bool_label"},
    ),
}


def parse_lmcache_prometheus(text: str) -> LmcacheMetrics:
    """Normalize LMCache-ish Prometheus exposition text."""
    samples = parse_labeled_prometheus_text(text)
    values: dict[str, Any] = {}
    matched_names: set[str] = set()
    for field_name, aliases in _ALIAS_TABLE.items():
        value, names = _first_alias(samples, aliases)
        if value is not None:
            values[field_name] = value
            matched_names.update(names)
    if values.get("lmcache_hit_rate") is None:
        hit = values.get("lmcache_hit_count")
        miss = values.get("lmcache_miss_count")
        if isinstance(hit, int) and isinstance(miss, int) and hit + miss > 0:
            values["lmcache_hit_rate"] = hit / (hit + miss)
    values["raw_metrics_extra"] = _raw_extra(samples, matched_names)
    return LmcacheMetrics(**values)


def _first_alias(
    samples: list[LabeledSample], aliases: tuple[dict[str, Any], ...]
) -> tuple[Any | None, set[str]]:
    seen: set[str] = set()
    for alias in aliases:
        for sample in samples:
            if sample.name != alias["name"]:
                continue
            if not _labels_match(sample, alias.get("labels") or {}):
                continue
            value = _coerce(sample, alias)
            if value is not None:
                seen.add(sample.name)
                return value, seen
    return None, seen


def _labels_match(sample: LabeledSample, expected: dict[str, str]) -> bool:
    return all(sample.labels.get(key) == value for key, value in expected.items())


def _coerce(sample: LabeledSample, alias: dict[str, Any]) -> Any | None:
    alias_type = alias.get("type")
    value = sample.value
    if alias.get("convert") == "seconds_to_ms":
        value *= 1000.0
    if alias_type == "int":
        return int(value)
    if alias_type == "float":
        return float(value)
    if alias_type == "bool":
        return bool(value)
    if alias_type == "bool_label":
        raw = sample.labels.get(str(alias.get("label")), "")
        return _truthy_label(raw) if raw else None
    if alias_type == "str_label":
        raw = sample.labels.get(str(alias.get("label")), "")
        return raw.lower() if raw else None
    if alias_type == "str_const":
        return alias.get("const")
    return None


def _truthy_label(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled", "enable"}


def _raw_extra(samples: list[LabeledSample], matched_names: set[str]) -> dict[str, float]:
    extras: dict[str, float] = {}
    for sample in samples:
        if not (sample.name.startswith("lmcache") or sample.name.startswith("lm_cache")):
            continue
        if sample.name in matched_names:
            continue
        extras[sample.name] = sample.value
    return extras


__all__ = ["LmcacheMetrics", "NORMALIZED_LMCACHE_FIELDS", "parse_lmcache_prometheus"]
