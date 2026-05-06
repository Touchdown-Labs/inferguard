"""Observability compatibility reports for cache/offload metric surfaces."""

from __future__ import annotations

import fnmatch
import json
import urllib.request
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from inferguard.collect_metrics.normalize import LMCACHE_LOCKED_METRICS, VLLM_LOCKED_METRICS
from inferguard.metrics_core import LabeledSample, parse_labeled_prometheus_text

SCHEMA_VERSION = "inferguard-observability-compat/v1"


class ExpectMode(StrEnum):
    AUTO = "auto"
    MP = "mp"
    EMBEDDED = "embedded"


class FailOn(StrEnum):
    NEVER = "never"
    MODE_MISMATCH = "mode-mismatch"
    MISSING_REQUIRED = "missing-required"


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
    MetricFamilySpec(
        "lmcache_mp", "l1_lifecycle", ("lmcache_mp_l1_chunk_*_seconds*",), required_when="sampled"
    ),
    MetricFamilySpec(
        "lmcache_mp", "l0_lifecycle", ("lmcache_mp_l0_block_*_seconds*",), required_when="sampled"
    ),
    MetricFamilySpec("lmcache_mp", "real_reuse", ("lmcache_mp_real_reuse_gap_*",), required_when="sampled"),
    MetricFamilySpec("lmcache_mp", "l2_counters", ("lmcache_mp_l2_*",), required_when="l2_configured"),
    MetricFamilySpec(
        "lmcache_mp", "l0_l1_throughput", ("lmcache_mp_l0_l1_*_throughput_gbs*",), required_when="sampled"
    ),
    MetricFamilySpec("lmcache_mp", "engine_counters", ("lmcache_mp_num_chunks_loaded_total",), required_when="optional"),
    MetricFamilySpec(
        "lmcache_mp",
        "gauges",
        (
            "lmcache_mp_active_prefetch_jobs",
            "lmcache_mp_num_inflight_l2_*",
            "lmcache_mp_inflight_load_memory_usage_bytes",
        ),
        required_when="optional",
    ),
    MetricFamilySpec("lmcache_mp", "event_bus", ("lmcache_mp_event_bus_*",), required_when="optional"),
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
    expect_mode: str = "auto",
    l2_configured: bool = False,
    mp_observability: dict[str, Any] | None = None,
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
    detected_mode = _detected_mode(observed_lmcache_mp, observed_lmcache_embedded)
    mp_observability_report = _mp_observability_report(
        samples,
        observed_lmcache_mp=observed_lmcache_mp,
        explicit=mp_observability or {},
    )
    families = [
        _family_row(
            spec,
            samples,
            detected_mode=detected_mode,
            l2_configured=l2_configured,
            mp_metrics_disabled=bool(mp_observability_report["config"].get("metrics_disabled")),
        )
        for spec in COMPAT_REGISTRY
    ]
    upstream_questions = _upstream_questions(families, samples, mp_observability_report)
    failures = _failures(
        families,
        detected_mode=detected_mode,
        expect_mode=expect_mode,
        mp_observability=mp_observability_report,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "engine_source": engine_source,
        "lmcache_source": lmcache_source,
        "expect_mode": expect_mode,
        "detected_mode": detected_mode,
        "l2_configured": l2_configured,
        "failure_reasons": failures,
        "upstream_questions": upstream_questions,
        "observed": {
            "lmcache_mp": observed_lmcache_mp,
            "lmcache_embedded": observed_lmcache_embedded,
            "vllm": any(name.startswith("vllm:") for name in observed_names),
            "total_series": len(observed_names),
            "populated_nonzero_series": len(
                {sample.name for sample in samples if sample.value != 0.0}
            ),
        },
        "lmcache_mp_observability": mp_observability_report,
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
    expect_mode: str = "auto",
    l2_configured: bool = False,
    mp_observability: dict[str, Any] | None = None,
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
        expect_mode=expect_mode,
        l2_configured=l2_configured,
        mp_observability=mp_observability,
    )


def build_compat_report_from_urls(
    *,
    engine_metrics_url: str | None = None,
    lmcache_metrics_url: str | None = None,
    timeout_seconds: float = 10.0,
    expect_mode: str = "auto",
    l2_configured: bool = False,
    mp_observability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_compat_report(
        engine_text=_read_url(engine_metrics_url, timeout_seconds) if engine_metrics_url else "",
        lmcache_text=_read_url(lmcache_metrics_url, timeout_seconds) if lmcache_metrics_url else "",
        engine_source=engine_metrics_url or "",
        lmcache_source=lmcache_metrics_url or "",
        expect_mode=expect_mode,
        l2_configured=l2_configured,
        mp_observability=mp_observability,
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


def _family_row(
    spec: MetricFamilySpec,
    samples: list[LabeledSample],
    *,
    detected_mode: str,
    l2_configured: bool,
    mp_metrics_disabled: bool,
) -> dict[str, Any]:
    matches = [
        sample
        for sample in samples
        if any(fnmatch.fnmatchcase(sample.name, pattern) for pattern in spec.patterns)
    ]
    matched_names = sorted({sample.name for sample in matches})
    nonzero_names = sorted({sample.name for sample in matches if sample.value != 0.0})
    applicable = _is_applicable(
        spec,
        detected_mode=detected_mode,
        l2_configured=l2_configured,
        mp_metrics_disabled=mp_metrics_disabled,
    )
    status = "missing"
    if not applicable:
        status = "not_applicable"
    elif matched_names and nonzero_names:
        status = "populated"
    elif matched_names:
        status = "zero"
    return {
        **asdict(spec),
        "applicable": applicable,
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
            {
                "family_count": 0,
                "populated": 0,
                "zero": 0,
                "missing": 0,
                "not_applicable": 0,
                "status": "missing",
            },
        )
        row["family_count"] += 1
        row[str(family["status"])] += 1
    for row in rows.values():
        applicable_count = row["family_count"] - row["not_applicable"]
        if applicable_count == 0:
            row["status"] = "not_applicable"
        elif row["populated"]:
            row["status"] = "partial" if row["missing"] or row["zero"] else "complete"
        elif row["zero"]:
            row["status"] = "zero"
    return rows


def _detected_mode(observed_lmcache_mp: bool, observed_lmcache_embedded: bool) -> str:
    if observed_lmcache_mp and observed_lmcache_embedded:
        return "mixed"
    if observed_lmcache_mp:
        return "mp"
    if observed_lmcache_embedded:
        return "embedded"
    return "unknown"


def _is_applicable(
    spec: MetricFamilySpec,
    *,
    detected_mode: str,
    l2_configured: bool,
    mp_metrics_disabled: bool,
) -> bool:
    if spec.surface == "lmcache_mp" and mp_metrics_disabled:
        return False
    if spec.surface == "lmcache_mp" and detected_mode not in {"mp", "mixed"}:
        return False
    if spec.surface == "lmcache_embedded" and detected_mode not in {"embedded", "mixed"}:
        return False
    if spec.required_when == "l2_configured":
        return l2_configured
    return True


def _failures(
    families: list[dict[str, Any]],
    *,
    detected_mode: str,
    expect_mode: str,
    mp_observability: dict[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    mp_config = mp_observability.get("config") or {}
    if mp_config.get("observability_disabled") or mp_config.get("metrics_disabled"):
        failures.append(
            {
                "code": "lmcache_mp_observability_disabled",
                "message": "LMCache MP launch/config disables observability or metrics, so lmcache_mp_* cannot prove runtime behavior.",
            }
        )
    if expect_mode != "auto" and detected_mode != expect_mode:
        failures.append(
            {
                "code": "lmcache_mode_mismatch",
                "message": f"expected LMCache mode {expect_mode!r}, detected {detected_mode!r}",
            }
        )
    for family in families:
        if not family.get("applicable"):
            continue
        if family.get("required_when") in {"optional", "sampled"}:
            continue
        if family["surface"] == "lmcache_mp" and family["status"] == "missing":
            failures.append(
                {
                    "code": "lmcache_mp_family_missing",
                    "family": family["family"],
                    "message": f"expected LMCache MP family {family['family']!r} was missing",
                }
            )
    return failures


def _upstream_questions(
    families: list[dict[str, Any]],
    samples: list[LabeledSample],
    mp_observability: dict[str, Any],
) -> list[dict[str, Any]]:
    by_key = {(row["surface"], row["family"]): row for row in families}
    questions: list[dict[str, Any]] = []
    if (
        by_key.get(("lmcache_mp", "storage_manager"), {}).get("status") == "populated"
        and by_key.get(("lmcache_mp", "l1_counters"), {}).get("status") == "populated"
        and by_key.get(("lmcache_mp", "lookup_tokens"), {}).get("status") == "missing"
    ):
        questions.append(
            {
                "code": "lmcache_mp_lookup_counters_missing",
                "owner_question": "Should lmcache_mp_lookup_requested_tokens_total and lmcache_mp_lookup_hit_tokens_total populate for this LMCacheMPConnector workload?",
            }
        )
    if (
        by_key.get(("lmcache_mp", "storage_manager"), {}).get("status") == "populated"
        and by_key.get(("lmcache_mp", "event_bus"), {}).get("status") == "missing"
    ):
        questions.append(
            {
                "code": "lmcache_eventbus_self_metrics_missing",
                "owner_question": "Which LMCache release should expose EventBus queue depth, dropped events, drain lag, and subscriber exception metrics?",
            }
        )
    if mp_observability.get("event_bus_taildrop_risk"):
        questions.append(
            {
                "code": "lmcache_mp_eventbus_taildrop_risk",
                "owner_question": "Can LMCache expose stable EventBus queue depth, dropped events, drain lag, and subscriber exception counters for MP observability?",
            }
        )
    if mp_observability.get("sampled_histogram_sparse"):
        questions.append(
            {
                "code": "lmcache_mp_sampled_histogram_sparse",
                "owner_question": "This MP scrape has counters but sparse sampled lifecycle/throughput histograms; should this lab raise --metrics-sample-rate for validation runs?",
            }
        )
    external_queries = _sum_matching(samples, "vllm:external_prefix_cache_queries_total")
    external_hits = _sum_matching(samples, "vllm:external_prefix_cache_hits_total")
    external_transfer_tokens = _sum_matching(
        [
            sample
            for sample in samples
            if sample.labels.get("source") == "external_kv_transfer"
        ],
        "vllm:prompt_tokens_by_source_total",
    )
    if external_queries > 0 and external_hits == 0 and external_transfer_tokens == 0:
        questions.append(
            {
                "code": "vllm_external_prefix_no_hits",
                "owner_question": "Should this vLLM connector path report external prefix hits or external_kv_transfer tokens when LMCache L1 activity is present?",
            }
        )
    return questions


def _mp_observability_report(
    samples: list[LabeledSample],
    *,
    observed_lmcache_mp: bool,
    explicit: dict[str, Any],
) -> dict[str, Any]:
    config = {
        "observability_disabled": _none_to_false(explicit.get("observability_disabled")),
        "metrics_disabled": _none_to_false(explicit.get("metrics_disabled")),
        "logging_disabled": _none_to_false(explicit.get("logging_disabled")),
        "tracing_enabled": _none_to_false(explicit.get("tracing_enabled")),
        "trace_recording_enabled": _none_to_false(explicit.get("trace_recording_enabled")),
        "prometheus_port": explicit.get("prometheus_port") or 9090,
        "event_bus_queue_size": explicit.get("event_bus_queue_size") or 10000,
        "metrics_sample_rate": explicit.get("metrics_sample_rate") or 0.01,
    }
    service_instance_ids = sorted(
        {
            sample.labels["service_instance_id"]
            for sample in samples
            if sample.name == "target_info" and sample.labels.get("service_instance_id")
        }
        | {
            sample.labels["service.instance.id"]
            for sample in samples
            if sample.name == "target_info" and sample.labels.get("service.instance.id")
        }
    )
    if explicit.get("service_instance_id"):
        service_instance_ids = sorted(set(service_instance_ids) | {str(explicit["service_instance_id"])})
    cache_salts = sorted(
        {
            sample.labels.get("cache_salt", "")
            for sample in samples
            if sample.name.startswith("lmcache_mp_") and "cache_salt" in sample.labels
        }
    )
    l2_names = sorted(
        {
            sample.labels["l2_name"]
            for sample in samples
            if sample.name.startswith("lmcache_mp_") and sample.labels.get("l2_name")
        }
    )
    adapter_indices = sorted(
        {
            sample.labels["adapter_index"]
            for sample in samples
            if sample.name.startswith("lmcache_mp_") and sample.labels.get("adapter_index")
        }
    )
    event_bus_metric_names = sorted(
        {sample.name for sample in samples if sample.name.startswith("lmcache_mp_event_bus_")}
    )
    counter_names = {
        sample.name
        for sample in samples
        if sample.name.startswith("lmcache_mp_")
        and (sample.name.endswith("_total") or "_requests" in sample.name or "_keys" in sample.name)
        and sample.value != 0.0
    }
    sampled_histogram_names = {
        sample.name
        for sample in samples
        if sample.name.startswith("lmcache_mp_")
        and (
            "_l1_chunk_" in sample.name
            or "_l0_block_" in sample.name
            or "_throughput_gbs" in sample.name
            or "_real_reuse_gap_" in sample.name
        )
        and sample.value != 0.0
    }
    event_bus_taildrop_risk = (
        observed_lmcache_mp
        and bool(config["event_bus_queue_size"])
        and int(config["event_bus_queue_size"]) > 0
        and not event_bus_metric_names
    )
    sampled_histogram_sparse = (
        observed_lmcache_mp
        and bool(counter_names)
        and not sampled_histogram_names
        and float(config["metrics_sample_rate"]) <= 0.01
    )
    return {
        "config": config,
        "service_instance_ids": service_instance_ids,
        "service_instance_id_source": "target_info_or_cli" if service_instance_ids else "missing",
        "cache_salt_values": cache_salts,
        "cache_salt_cardinality": len(cache_salts),
        "cache_salt_cardinality_risk": len(cache_salts) > 100,
        "l2_names": l2_names,
        "adapter_indices": adapter_indices,
        "event_bus_metric_names": event_bus_metric_names,
        "event_bus_taildrop_risk": event_bus_taildrop_risk,
        "sampled_histogram_names": sorted(sampled_histogram_names),
        "sampled_histogram_sparse": sampled_histogram_sparse,
    }


def _none_to_false(value: Any) -> bool:
    return bool(value) if value is not None else False


def _sum_matching(samples: list[LabeledSample], pattern: str) -> float:
    return sum(sample.value for sample in samples if fnmatch.fnmatchcase(sample.name, pattern))


def _read_url(url: str, timeout_seconds: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


__all__ = [
    "COMPAT_REGISTRY",
    "ExpectMode",
    "FailOn",
    "SCHEMA_VERSION",
    "build_compat_report",
    "build_compat_report_from_paths",
    "build_compat_report_from_urls",
    "write_compat_report",
]
