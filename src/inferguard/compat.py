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
    expect_mode: str = "auto",
    l2_configured: bool = False,
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
    families = [
        _family_row(spec, samples, detected_mode=detected_mode, l2_configured=l2_configured)
        for spec in COMPAT_REGISTRY
    ]
    upstream_questions = _upstream_questions(families, samples)
    failures = _failures(families, detected_mode=detected_mode, expect_mode=expect_mode)
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
    )


def build_compat_report_from_urls(
    *,
    engine_metrics_url: str | None = None,
    lmcache_metrics_url: str | None = None,
    timeout_seconds: float = 10.0,
    expect_mode: str = "auto",
    l2_configured: bool = False,
) -> dict[str, Any]:
    return build_compat_report(
        engine_text=_read_url(engine_metrics_url, timeout_seconds) if engine_metrics_url else "",
        lmcache_text=_read_url(lmcache_metrics_url, timeout_seconds) if lmcache_metrics_url else "",
        engine_source=engine_metrics_url or "",
        lmcache_source=lmcache_metrics_url or "",
        expect_mode=expect_mode,
        l2_configured=l2_configured,
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
) -> dict[str, Any]:
    matches = [
        sample
        for sample in samples
        if any(fnmatch.fnmatchcase(sample.name, pattern) for pattern in spec.patterns)
    ]
    matched_names = sorted({sample.name for sample in matches})
    nonzero_names = sorted({sample.name for sample in matches if sample.value != 0.0})
    applicable = _is_applicable(spec, detected_mode=detected_mode, l2_configured=l2_configured)
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


def _is_applicable(spec: MetricFamilySpec, *, detected_mode: str, l2_configured: bool) -> bool:
    if spec.surface == "lmcache_mp" and detected_mode not in {"mp", "mixed"}:
        return False
    if spec.surface == "lmcache_embedded" and detected_mode not in {"embedded", "mixed"}:
        return False
    if spec.required_when == "l2_configured":
        return l2_configured
    return True


def _failures(
    families: list[dict[str, Any]], *, detected_mode: str, expect_mode: str
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
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
    families: list[dict[str, Any]], samples: list[LabeledSample]
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
