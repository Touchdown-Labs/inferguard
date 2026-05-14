"""Cross-engine observability coverage reports."""

from __future__ import annotations

import fnmatch
import json
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from inferguard.compat import build_compat_report
from inferguard.io import atomic_write_json
from inferguard.lmcache_cacheblend_boundary import read_cacheblend_boundary_evidence_jsonl
from inferguard.metrics_core import parse_labeled_prometheus_text

SCHEMA_VERSION = "inferguard-observability-coverage/v1"


@dataclass(frozen=True)
class ObservabilityFamily:
    surface: str
    family: str
    patterns: tuple[str, ...]
    required_when: str = "always"


ENGINE_REGISTRY: tuple[ObservabilityFamily, ...] = (
    ObservabilityFamily(
        "vllm",
        "request_latency",
        (
            "vllm:time_to_first_token_seconds*",
            "vllm:time_per_output_token_seconds*",
            "vllm:inter_token_latency_seconds*",
            "vllm:e2e_request_latency_seconds*",
        ),
    ),
    ObservabilityFamily(
        "vllm",
        "prefill_decode_queue",
        (
            "vllm:request_prefill_time_seconds*",
            "vllm:request_decode_time_seconds*",
            "vllm:request_queue_time_seconds*",
            "vllm:num_requests_running",
            "vllm:num_requests_waiting",
        ),
    ),
    ObservabilityFamily(
        "vllm",
        "token_throughput",
        (
            "vllm:prompt_tokens_total",
            "vllm:generation_tokens_total",
            "vllm:request_prompt_tokens*",
            "vllm:request_generation_tokens*",
            "vllm:request_success_total",
        ),
    ),
    ObservabilityFamily(
        "vllm",
        "kv_cache",
        ("vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc", "vllm:cache_config_info"),
    ),
    ObservabilityFamily(
        "vllm",
        "prefix_cache",
        ("vllm:prefix_cache_queries*", "vllm:prefix_cache_hits*"),
    ),
    ObservabilityFamily(
        "vllm",
        "external_prefix_cache",
        ("vllm:external_prefix_cache_queries*", "vllm:external_prefix_cache_hits*"),
        required_when="external_cache_configured",
    ),
    ObservabilityFamily(
        "vllm",
        "prompt_tokens_by_source",
        ("vllm:prompt_tokens_by_source*", "vllm:prompt_tokens_cached*"),
        required_when="external_cache_configured",
    ),
    ObservabilityFamily(
        "vllm",
        "cpu_offload",
        (
            "vllm:kv_offload_total_bytes*",
            "vllm:kv_offload_total_time*",
            "vllm:kv_offload_size",
            "vllm:simple_cpu_offload_*",
        ),
        required_when="cpu_offload_configured",
    ),
    ObservabilityFamily(
        "vllm",
        "kv_block_lifecycle",
        (
            "vllm:kv_block_lifetime_seconds*",
            "vllm:kv_block_idle_before_evict_seconds*",
            "vllm:kv_block_reuse_gap_seconds*",
        ),
        required_when="sampled",
    ),
    ObservabilityFamily(
        "vllm",
        "kv_transfer",
        (
            "vllm:kv_transfer_sent_bytes_total",
            "vllm:kv_transfer_recv_bytes_total",
            "vllm:kv_transfer_errors_total",
        ),
        required_when="disaggregated_or_external_cache",
    ),
    ObservabilityFamily(
        "sglang",
        "request_latency",
        (
            "sglang:time_to_first_token_seconds*",
            "sglang:time_per_output_token_seconds*",
            "sglang:e2e_request_latency_seconds*",
            "sglang:func_latency_seconds*",
        ),
    ),
    ObservabilityFamily(
        "sglang",
        "token_throughput",
        ("sglang:prompt_tokens_total", "sglang:generation_tokens_total", "sglang:gen_throughput"),
    ),
    ObservabilityFamily(
        "sglang",
        "queue",
        ("sglang:num_running_reqs", "sglang:num_queue_reqs"),
    ),
    ObservabilityFamily(
        "sglang",
        "prefix_cache",
        ("sglang:cache_hit_rate",),
    ),
    ObservabilityFamily(
        "sglang",
        "kv_cache",
        ("sglang:token_usage", "sglang:num_used_tokens"),
    ),
    ObservabilityFamily(
        "sglang",
        "kv_transfer",
        (
            "sglang:kv_transfer_sent_bytes_total",
            "sglang:kv_transfer_recv_bytes_total",
            "sglang:kv_transfer_errors_total",
        ),
        required_when="disaggregated_or_external_cache",
    ),
    ObservabilityFamily(
        "sglang",
        "flops",
        ("sglang:estimated_flops_per_gpu_total",),
        required_when="optional",
    ),
)


def build_observability_coverage_report(
    *,
    engine_text: str = "",
    lmcache_text: str = "",
    engine_source: str = "",
    lmcache_source: str = "",
    expected_engine: str = "auto",
    expect_lmcache_mode: str = "auto",
    external_cache_configured: bool = False,
    cpu_offload_configured: bool = False,
    l2_configured: bool = False,
    disaggregated_or_external_cache: bool = False,
    mp_observability: dict[str, Any] | None = None,
    lmcache_http_evidence: dict[str, Any] | None = None,
    lmcache_log_evidence: dict[str, Any] | None = None,
    lmcache_trace_evidence: dict[str, Any] | None = None,
    lmcache_otel_evidence: dict[str, Any] | None = None,
    lmcache_trace_replay_evidence: dict[str, Any] | None = None,
    lmcache_lookup_hash_evidence: dict[str, Any] | None = None,
    lmcache_cacheblend_boundary_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a single coverage report for engine and LMCache telemetry."""

    combined = "\n".join(text for text in [engine_text, lmcache_text] if text)
    samples = parse_labeled_prometheus_text(combined)
    observed_names = {sample.name for sample in samples}
    detected_engines = _detected_engines(observed_names)
    engine_families = [
        _family_row(
            family,
            samples,
            expected_engine=expected_engine,
            external_cache_configured=external_cache_configured,
            cpu_offload_configured=cpu_offload_configured,
            disaggregated_or_external_cache=disaggregated_or_external_cache,
        )
        for family in ENGINE_REGISTRY
    ]
    lmcache_report = build_compat_report(
        engine_text=engine_text,
        lmcache_text=lmcache_text,
        engine_source=engine_source,
        lmcache_source=lmcache_source,
        expect_mode=expect_lmcache_mode,
        l2_configured=l2_configured,
        mp_observability=mp_observability,
        lmcache_http_evidence=lmcache_http_evidence,
        lmcache_log_evidence=lmcache_log_evidence,
        lmcache_trace_evidence=lmcache_trace_evidence,
        lmcache_otel_evidence=lmcache_otel_evidence,
        lmcache_trace_replay_evidence=lmcache_trace_replay_evidence,
        lmcache_lookup_hash_evidence=lmcache_lookup_hash_evidence,
        lmcache_cacheblend_boundary_evidence=lmcache_cacheblend_boundary_evidence,
    )
    surfaces = _surface_rows(engine_families)
    for surface, row in lmcache_report.get("surfaces", {}).items():
        surfaces[str(surface)] = row
    gaps = _coverage_gaps(engine_families, lmcache_report)
    kv_cache_offload = _kv_cache_offload_report(samples)
    return {
        "schema_version": SCHEMA_VERSION,
        "engine_source": engine_source,
        "lmcache_source": lmcache_source,
        "expected_engine": expected_engine,
        "detected_engines": detected_engines,
        "expect_lmcache_mode": expect_lmcache_mode,
        "detected_lmcache_mode": lmcache_report.get("detected_mode"),
        "config": {
            "external_cache_configured": external_cache_configured,
            "cpu_offload_configured": cpu_offload_configured,
            "l2_configured": l2_configured,
            "disaggregated_or_external_cache": disaggregated_or_external_cache,
        },
        "observed": {
            "total_series": len(observed_names),
            "populated_nonzero_series": len({sample.name for sample in samples if sample.value != 0.0}),
        },
        "kv_cache_offload": kv_cache_offload,
        "surfaces": surfaces,
        "families": engine_families,
        "lmcache_compat": lmcache_report,
        "coverage_gaps": gaps,
    }


def build_observability_coverage_report_from_paths(
    *,
    engine_metrics_file: Path | None = None,
    lmcache_metrics_file: Path | None = None,
    lmcache_http_evidence_file: Path | None = None,
    lmcache_log_evidence_file: Path | None = None,
    lmcache_trace_evidence_file: Path | None = None,
    lmcache_otel_evidence_file: Path | None = None,
    lmcache_trace_replay_evidence_file: Path | None = None,
    lmcache_lookup_hash_evidence_file: Path | None = None,
    lmcache_cacheblend_boundary_evidence_file: Path | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return build_observability_coverage_report(
        engine_text=engine_metrics_file.read_text(encoding="utf-8")
        if engine_metrics_file is not None
        else "",
        lmcache_text=lmcache_metrics_file.read_text(encoding="utf-8")
        if lmcache_metrics_file is not None
        else "",
        engine_source=str(engine_metrics_file or ""),
        lmcache_source=str(lmcache_metrics_file or ""),
        lmcache_http_evidence=_read_json_object(lmcache_http_evidence_file),
        lmcache_log_evidence=_read_json_object(lmcache_log_evidence_file),
        lmcache_trace_evidence=_read_json_object(lmcache_trace_evidence_file),
        lmcache_otel_evidence=_read_json_object(lmcache_otel_evidence_file),
        lmcache_trace_replay_evidence=_read_json_object(lmcache_trace_replay_evidence_file),
        lmcache_lookup_hash_evidence=_read_json_object(lmcache_lookup_hash_evidence_file),
        lmcache_cacheblend_boundary_evidence=read_cacheblend_boundary_evidence_jsonl(
            lmcache_cacheblend_boundary_evidence_file
        ),
        **kwargs,
    )


def build_observability_coverage_report_from_urls(
    *,
    engine_metrics_url: str | None = None,
    lmcache_metrics_url: str | None = None,
    timeout_seconds: float = 10.0,
    lmcache_http_evidence_file: Path | None = None,
    lmcache_log_evidence_file: Path | None = None,
    lmcache_trace_evidence_file: Path | None = None,
    lmcache_otel_evidence_file: Path | None = None,
    lmcache_trace_replay_evidence_file: Path | None = None,
    lmcache_lookup_hash_evidence_file: Path | None = None,
    lmcache_cacheblend_boundary_evidence_file: Path | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return build_observability_coverage_report(
        engine_text=_read_url(engine_metrics_url, timeout_seconds) if engine_metrics_url else "",
        lmcache_text=_read_url(lmcache_metrics_url, timeout_seconds) if lmcache_metrics_url else "",
        engine_source=engine_metrics_url or "",
        lmcache_source=lmcache_metrics_url or "",
        lmcache_http_evidence=_read_json_object(lmcache_http_evidence_file),
        lmcache_log_evidence=_read_json_object(lmcache_log_evidence_file),
        lmcache_trace_evidence=_read_json_object(lmcache_trace_evidence_file),
        lmcache_otel_evidence=_read_json_object(lmcache_otel_evidence_file),
        lmcache_trace_replay_evidence=_read_json_object(lmcache_trace_replay_evidence_file),
        lmcache_lookup_hash_evidence=_read_json_object(lmcache_lookup_hash_evidence_file),
        lmcache_cacheblend_boundary_evidence=read_cacheblend_boundary_evidence_jsonl(
            lmcache_cacheblend_boundary_evidence_file
        ),
        **kwargs,
    )


def write_observability_coverage_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output, report)


def _family_row(
    family: ObservabilityFamily,
    samples: list[Any],
    *,
    expected_engine: str,
    external_cache_configured: bool,
    cpu_offload_configured: bool,
    disaggregated_or_external_cache: bool,
) -> dict[str, Any]:
    matched = [
        sample
        for sample in samples
        if any(fnmatch.fnmatchcase(sample.name, pattern) for pattern in family.patterns)
    ]
    names = sorted({sample.name for sample in matched})
    nonzero = sorted({sample.name for sample in matched if sample.value != 0.0})
    applicable = _is_applicable(
        family,
        expected_engine=expected_engine,
        external_cache_configured=external_cache_configured,
        cpu_offload_configured=cpu_offload_configured,
        disaggregated_or_external_cache=disaggregated_or_external_cache,
    )
    status = "missing"
    if not applicable:
        status = "not_applicable"
    elif names and nonzero:
        status = "populated"
    elif names:
        status = "zero"
    return {
        **asdict(family),
        "applicable": applicable,
        "status": status,
        "series_count": len(names),
        "populated_series_count": len(nonzero),
        "matched_metrics": names,
    }


def _is_applicable(
    family: ObservabilityFamily,
    *,
    expected_engine: str,
    external_cache_configured: bool,
    cpu_offload_configured: bool,
    disaggregated_or_external_cache: bool,
) -> bool:
    if expected_engine != "auto" and family.surface != expected_engine:
        return False
    if family.required_when == "external_cache_configured":
        return external_cache_configured
    if family.required_when == "cpu_offload_configured":
        return cpu_offload_configured
    if family.required_when == "disaggregated_or_external_cache":
        return disaggregated_or_external_cache or external_cache_configured
    return True


def _surface_rows(families: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for family in families:
        row = rows.setdefault(
            str(family["surface"]),
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
        applicable = row["family_count"] - row["not_applicable"]
        if applicable == 0:
            row["status"] = "not_applicable"
        elif row["missing"]:
            row["status"] = "partial" if row["populated"] or row["zero"] else "missing"
        elif row["zero"]:
            row["status"] = "zero" if not row["populated"] else "partial"
        else:
            row["status"] = "complete"
    return rows


def _kv_cache_offload_report(samples: list[Any]) -> dict[str, Any]:
    """Summarize CPU<->GPU KV movement separately from generic cache coverage."""

    vllm_gpu_to_cpu_bytes = _sum_labeled(samples, "vllm:kv_offload_total_bytes", "transfer_type", "GPU_to_CPU")
    vllm_cpu_to_gpu_bytes = _sum_labeled(samples, "vllm:kv_offload_total_bytes", "transfer_type", "CPU_to_GPU")
    vllm_gpu_to_cpu_time = _sum_labeled(samples, "vllm:kv_offload_total_time", "transfer_type", "GPU_to_CPU")
    vllm_cpu_to_gpu_time = _sum_labeled(samples, "vllm:kv_offload_total_time", "transfer_type", "CPU_to_GPU")
    vllm_gpu_to_cpu_bytes += _sum_names(samples, "vllm:kv_offload_bytes_gpu_to_cpu")
    vllm_cpu_to_gpu_bytes += _sum_names(samples, "vllm:kv_offload_bytes_cpu_to_gpu")
    vllm_gpu_to_cpu_time += _sum_names(samples, "vllm:kv_offload_time_gpu_to_cpu")
    vllm_cpu_to_gpu_time += _sum_names(samples, "vllm:kv_offload_time_cpu_to_gpu")

    lmcache_store_gbs = _hist_avg(samples, "lmcache_mp_l0_l1_store_throughput_gbs")
    lmcache_load_gbs = _hist_avg(samples, "lmcache_mp_l0_l1_load_throughput_gbs")
    lmcache_store_gbs = lmcache_store_gbs or _hist_avg(samples, "lmcache_mp.l0_l1_store_throughput_gbs")
    lmcache_load_gbs = lmcache_load_gbs or _hist_avg(samples, "lmcache_mp.l0_l1_load_throughput_gbs")

    native_present = any(
        sample.name.startswith(("vllm:kv_offload_", "vllm:simple_cpu_offload_")) for sample in samples
    )
    lmcache_present = any(
        sample.name.startswith(("lmcache_mp_l0_l1_", "lmcache_mp.l0_l1_")) for sample in samples
    )
    return {
        "schema_version": "inferguard-kv-cache-offload/v1",
        "purpose": "Profile KV cache movement between GPU memory and CPU/host memory for long-context runs.",
        "vllm_native_cpu_offload": {
            "status": "populated"
            if any(value > 0 for value in (vllm_gpu_to_cpu_bytes, vllm_cpu_to_gpu_bytes))
            else ("zero" if native_present else "missing"),
            "metric_source": "vllm /metrics",
            "interpretation": "Native vLLM CPU offload metrics; useful for offload pressure, but not proof that LMCache is serving KV.",
            "gpu_to_cpu_bytes": vllm_gpu_to_cpu_bytes,
            "cpu_to_gpu_bytes": vllm_cpu_to_gpu_bytes,
            "gpu_to_cpu_seconds": vllm_gpu_to_cpu_time,
            "cpu_to_gpu_seconds": vllm_cpu_to_gpu_time,
            "simple_cpu_offload_used_blocks": _max_names(samples, "vllm:simple_cpu_offload_used_blocks"),
            "simple_cpu_offload_usage_perc": _max_names(samples, "vllm:simple_cpu_offload_usage_perc"),
            "simple_cpu_offload_pending_loads": _max_names(samples, "vllm:simple_cpu_offload_pending_loads"),
            "simple_cpu_offload_pending_stores": _max_names(samples, "vllm:simple_cpu_offload_pending_stores"),
        },
        "lmcache_mp_l0_l1_kv_transfer": {
            "status": "populated"
            if any(value is not None and value > 0 for value in (lmcache_store_gbs, lmcache_load_gbs))
            else ("zero" if lmcache_present else "missing"),
            "metric_source": "standalone LMCache MP /metrics",
            "interpretation": "LMCache MP GPU<->CPU KV transfer throughput; this is the offload lane that proves LMCache moved KV between L0 GPU blocks and L1 CPU memory.",
            "gpu_to_cpu_store_throughput_gbs": lmcache_store_gbs,
            "cpu_to_gpu_load_throughput_gbs": lmcache_load_gbs,
        },
    }


def _sum_labeled(samples: list[Any], name: str, label: str, value: str) -> float:
    return sum(sample.value for sample in samples if sample.name == name and sample.labels.get(label) == value)


def _sum_names(samples: list[Any], *names: str) -> float:
    names_set = set(names)
    return sum(sample.value for sample in samples if sample.name in names_set)


def _max_names(samples: list[Any], *names: str) -> float | None:
    values = [sample.value for sample in samples if sample.name in set(names)]
    return max(values) if values else None


def _hist_avg(samples: list[Any], prefix: str) -> float | None:
    total = _sum_names(samples, f"{prefix}_sum")
    count = _sum_names(samples, f"{prefix}_count")
    if count <= 0:
        return None
    return total / count


def _coverage_gaps(
    engine_families: list[dict[str, Any]], lmcache_report: dict[str, Any]
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for family in engine_families:
        if family["applicable"] and family["status"] in {"missing", "zero"}:
            gaps.append(
                {
                    "surface": family["surface"],
                    "family": family["family"],
                    "status": family["status"],
                    "required_when": family["required_when"],
                }
            )
    for family in lmcache_report.get("families", []):
        if family.get("applicable") and family.get("status") in {"missing", "zero"}:
            gaps.append(
                {
                    "surface": family.get("surface"),
                    "family": family.get("family"),
                    "status": family.get("status"),
                    "required_when": family.get("required_when"),
                }
            )
    return gaps


def _detected_engines(observed_names: set[str]) -> list[str]:
    engines = []
    if any(name.startswith("vllm:") for name in observed_names):
        engines.append("vllm")
    if any(name.startswith("sglang:") for name in observed_names):
        engines.append("sglang")
    return engines


def _read_url(url: str | None, timeout_seconds: float) -> str:
    if not url:
        return ""
    with urllib.request.urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310  # nosec B310 - operator-supplied metrics URL.
        return response.read().decode("utf-8", errors="replace")


def _read_json_object(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def dumps_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True)
