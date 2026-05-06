"""Observability compatibility reports for cache/offload metric surfaces."""

from __future__ import annotations

import fnmatch
import json
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from inferguard.collect_metrics.normalize import LMCACHE_LOCKED_METRICS, VLLM_LOCKED_METRICS
from inferguard.metrics_core import LabeledSample, parse_labeled_prometheus_text

SCHEMA_VERSION = "inferguard-observability-compat/v1"


@dataclass(frozen=True)
class MetricFamilySpec:
    surface: str
    family: str
    patterns: tuple[str, ...]
    required_when: str = "always"


LMCACHE_COMPAT_REGISTRY: tuple[MetricFamilySpec, ...] = (
    MetricFamilySpec("lmcache_embedded", "legacy_lookup", ("lmcache:lookup_*", "lmcache_lookup_*")),
    MetricFamilySpec("lmcache_embedded", "legacy_retrieve", ("lmcache:retrieve_*", "lmcache_retrieve_*")),
    MetricFamilySpec("lmcache_embedded", "legacy_local_cpu", ("lmcache:local_cpu_*", "lmcache_local_cpu_*")),
    MetricFamilySpec("lmcache_embedded", "legacy_tier_usage", ("lmcache:tier_usage*", "lmcache_tier_usage*")),
    MetricFamilySpec("lmcache_mp", "storage_manager", ("lmcache_mp_sm_*",)),
    MetricFamilySpec("lmcache_mp", "lookup_tokens", ("lmcache_mp_lookup_*_tokens_total",)),
    MetricFamilySpec("lmcache_mp", "l1_counters", ("lmcache_mp_l1_*_keys_total",)),
    MetricFamilySpec("lmcache_mp", "l1_memory", ("lmcache_mp_l1_memory_usage_bytes",)),
    MetricFamilySpec("lmcache_mp", "l1_lifecycle", ("lmcache_mp_l1_chunk_*_seconds*",)),
    MetricFamilySpec("lmcache_mp", "l0_lifecycle", ("lmcache_mp_l0_block_*_seconds*",)),
    MetricFamilySpec("lmcache_mp", "real_reuse", ("lmcache_mp_real_reuse_gap_*",)),
    MetricFamilySpec("lmcache_mp", "l2_counters", ("lmcache_mp_l2_*",), required_when="l2_configured"),
    MetricFamilySpec(
        "lmcache_mp", "l0_l1_throughput", ("lmcache_mp_l0_l1_*_throughput_gbs*",)
    ),
    MetricFamilySpec("lmcache_mp", "engine_counters", ("lmcache_mp_num_chunks_loaded_total",)),
    MetricFamilySpec(
        "lmcache_mp",
        "gauges",
        (
            "lmcache_mp_active_prefetch_jobs",
            "lmcache_mp_num_inflight_l2_*",
            "lmcache_mp_inflight_load_memory_usage_bytes",
        ),
    ),
    MetricFamilySpec("lmcache_mp", "event_bus", ("lmcache_mp_event_bus_*",)),
)

VLLM_COMPAT_REGISTRY: tuple[MetricFamilySpec, ...] = (
    MetricFamilySpec("vllm_prefix_cache", "local_prefix", ("vllm:prefix_cache_*",)),
    MetricFamilySpec("vllm_prefix_cache", "external_prefix", ("vllm:external_prefix_cache_*",)),
    MetricFamilySpec("vllm_prefix_cache", "prompt_tokens_by_source", ("vllm:prompt_tokens_by_source*",)),
    MetricFamilySpec("vllm_prefix_cache", "prompt_tokens_cached", ("vllm:prompt_tokens_cached*",)),
    MetricFamilySpec("vllm_simple_cpu_offload", "kv_offload_transfer", ("vllm:kv_offload_*",)),
    MetricFamilySpec("vllm_simple_cpu_offload", "simple_cpu_pool", ("vllm:simple_cpu_offload_*",)),
)

COMPAT_REGISTRY: tuple[MetricFamilySpec, ...] = LMCACHE_COMPAT_REGISTRY + VLLM_COMPAT_REGISTRY


def build_compat_report(
    *,
    engine_text: str = "",
    lmcache_text: str = "",
    engine_source: str = "",
    lmcache_source: str = "",
) -> dict[str, Any]:
    """Return a compatibility report for observed vLLM/LMCache metrics."""

    samples = _tag_samples(engine_text, "engine") + _tag_samples(lmcache_text, "lmcache")
    observed_names = {sample.name for sample in samples}
    observed_lmcache_mp = any(name.startswith("lmcache_mp_") for name in observed_names)
    observed_lmcache_embedded = any(
        (name.startswith("lmcache:") or name.startswith("lmcache_"))
        and not name.startswith("lmcache_mp_")
        for name in observed_names
    )
    families = [_family_row(spec, samples) for spec in COMPAT_REGISTRY]
    return {
        "schema_version": SCHEMA_VERSION,
        "engine_source": engine_source,
        "lmcache_source": lmcache_source,
        "observed": {
            "lmcache_mp": observed_lmcache_mp,
            "lmcache_embedded": observed_lmcache_embedded,
            "vllm": any(name.startswith("vllm:") for name in observed_names),
            "total_series": len(observed_names),
            "populated_nonzero_series": len(
                {sample.name for sample in samples if sample.value != 0.0}
            ),
        },
        "surfaces": _surface_rows(families),
        "families": families,
        "locked_metrics": {
            "vllm": list(VLLM_LOCKED_METRICS),
            "lmcache": list(LMCACHE_LOCKED_METRICS),
        },
    }


def build_compat_report_from_paths(
    *,
    engine_metrics_file: Path | None = None,
    lmcache_metrics_file: Path | None = None,
) -> dict[str, Any]:
    return build_compat_report(
        engine_text=engine_metrics_file.read_text(encoding="utf-8")
        if engine_metrics_file is not None
        else "",
        lmcache_text=lmcache_metrics_file.read_text(encoding="utf-8")
        if lmcache_metrics_file is not None
        else "",
        engine_source=str(engine_metrics_file or ""),
        lmcache_source=str(lmcache_metrics_file or ""),
    )


def build_compat_report_from_urls(
    *,
    engine_metrics_url: str | None = None,
    lmcache_metrics_url: str | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    return build_compat_report(
        engine_text=_read_url(engine_metrics_url, timeout_seconds) if engine_metrics_url else "",
        lmcache_text=_read_url(lmcache_metrics_url, timeout_seconds) if lmcache_metrics_url else "",
        engine_source=engine_metrics_url or "",
        lmcache_source=lmcache_metrics_url or "",
    )


def write_compat_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _tag_samples(text: str, source: str) -> list[LabeledSample]:
    tagged: list[LabeledSample] = []
    for sample in parse_labeled_prometheus_text(text):
        labels = dict(sample.labels)
        labels["_inferguard_source"] = source
        tagged.append(LabeledSample(name=sample.name, value=sample.value, labels=labels))
    return tagged


def _family_row(spec: MetricFamilySpec, samples: list[LabeledSample]) -> dict[str, Any]:
    matches = [
        sample
        for sample in samples
        if any(fnmatch.fnmatchcase(sample.name, pattern) for pattern in spec.patterns)
    ]
    matched_names = sorted({sample.name for sample in matches})
    nonzero_names = sorted({sample.name for sample in matches if sample.value != 0.0})
    status = "missing"
    if matched_names and nonzero_names:
        status = "populated"
    elif matched_names:
        status = "zero"
    return {
        **asdict(spec),
        "status": status,
        "series_count": len(matched_names),
        "populated_series_count": len(nonzero_names),
        "matched_metrics": matched_names,
    }


def _surface_rows(families: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for family in families:
        surface = str(family["surface"])
        row = rows.setdefault(
            surface,
            {"family_count": 0, "populated": 0, "zero": 0, "missing": 0, "status": "missing"},
        )
        row["family_count"] += 1
        row[str(family["status"])] += 1
    for row in rows.values():
        if row["populated"]:
            row["status"] = "partial" if row["missing"] or row["zero"] else "complete"
        elif row["zero"]:
            row["status"] = "zero"
    return rows


def _read_url(url: str, timeout_seconds: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


__all__ = [
    "COMPAT_REGISTRY",
    "SCHEMA_VERSION",
    "build_compat_report",
    "build_compat_report_from_paths",
    "build_compat_report_from_urls",
    "write_compat_report",
]
