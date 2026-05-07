"""Deterministic decision tree for PRD §4.5 bottleneck diagnosis."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from inferguard.diagnose_bottleneck.types import (
    BottleneckDiagnosis,
    ClaimStatus,
    Downgrade,
    Evidence,
    Verdict,
)
from inferguard.disagg.detect import (
    rule_kv_transfer_errors_present,
    rule_kv_transfer_stall,
    rule_prefill_decode_imbalance,
)
from inferguard.disagg.types import DisaggSnapshot, DisaggStatus, EndpointId

DEFAULT_THRESHOLDS: dict[str, float] = {
    "prefill_ttft_e2e_ratio": 0.6,
    "prefill_engine_e2e_ratio": 0.5,
    "prefill_running_low_max": 2.0,
    "decode_tpot_skew_ratio": 1.5,
    "decode_tpot_slo_floor_ms": 30.0,
    "decode_tensor_active_p95": 0.7,
    "queue_waiting_running_ratio": 1.0,
    "queue_e2e_p99_rise_ratio": 1.5,
    "kv_usage_fraction_p95": 0.85,
    "prefix_cache_expected_floor": 0.2,
    "network_nvlink_saturation_fraction": 0.8,
    "network_nvlink_bytes_p95": 1_000_000_000_000.0,
    "network_nccl_busbw_fraction": 0.6,
    "host_gpu_util_fraction": 0.5,
    "host_e2e_slo_p99_ms": 1000.0,
}

REQUIRED_INPUT_KEYS: tuple[str, ...] = (
    "requests_profile",
    "requests_summary",
    "engine_metrics_timeline",
    "gpu_metrics_timeline",
    "metrics_summary",
)

RULES_TABLE: tuple[str, ...] = (
    "model_launch_bound",
    "not_enough_evidence",
    "network_bound",
    "kv_bound",
    "queue_bound",
    "prefill_bound",
    "decode_bound",
    "host_bound",
)


@dataclass(frozen=True)
class EvidenceBundle:
    """Loaded input artifacts for one job directory."""

    job_dir: Path
    paths: dict[str, Path]
    request_summary: dict[str, Any] = field(default_factory=dict)
    request_rows: list[dict[str, Any]] = field(default_factory=list)
    metrics_summary: dict[str, Any] = field(default_factory=dict)
    engine_rows: list[dict[str, Any]] = field(default_factory=list)
    gpu_rows: list[dict[str, Any]] = field(default_factory=list)
    healthcheck: dict[str, Any] = field(default_factory=dict)
    launch_command: dict[str, Any] = field(default_factory=dict)
    operator_profile: dict[str, Any] = field(default_factory=dict)
    validation_report: dict[str, Any] = field(default_factory=dict)
    nccl_summary: dict[str, Any] = field(default_factory=dict)
    nccl_evidence_paths: list[Path] = field(default_factory=list)
    cpu_summary: dict[str, Any] = field(default_factory=dict)
    cpu_summary_path: Path | None = None
    lmcache_compat_report: dict[str, Any] = field(default_factory=dict)
    lmcache_log_evidence: dict[str, Any] = field(default_factory=dict)
    missing_required_paths: list[Path] = field(default_factory=list)
    parse_errors: dict[str, str] = field(default_factory=dict)
    rule_config: dict[str, Any] = field(default_factory=dict)

    @property
    def job_id(self) -> str:
        for source in (self.request_summary, self.operator_profile, self.launch_command):
            value = source.get("job_id")
            if value:
                return str(value)
        return self.job_dir.name


@dataclass(frozen=True)
class RuleResult:
    verdict: Verdict
    confidence: float
    claim_status: ClaimStatus | str
    primary_evidence: list[Evidence]
    secondary_evidence: list[Evidence]
    rule_fired: str
    reasoning: str
    recommended_next_probe: str
    metric_values: dict[str, Any]
    downgrades: list[Downgrade] = field(default_factory=list)


def apply_rules(bundle: EvidenceBundle) -> BottleneckDiagnosis:
    """Apply the locked §4.5 decision tree and return one diagnosis."""

    thresholds = _thresholds(bundle.rule_config)
    for checker in (
        is_model_launch_bound,
        _missing_required_inputs,
        _lmcache_missing_signal_downgrade,
        _all_metric_groups_not_proven,
        _sglang_chunked_prefill_bug_downgrade,
        _sglang_speculative_kv_bug_downgrade,
        is_network_bound,
        is_kv_bound,
        is_queue_bound,
        is_prefill_bound,
        is_decode_bound,
        is_host_bound,
    ):
        result = checker(bundle, thresholds)
        if result is not None:
            return _diagnosis(bundle, result)
    return _diagnosis(
        bundle,
        _not_enough_result(
            bundle,
            rule_fired="no_rule_fired",
            reasoning=(
                "Required artifacts were present, but no locked rule crossed its threshold. "
                "The diagnosis refuses to invent a bottleneck without discriminating evidence."
            ),
            metric_values={"rules_evaluated": list(RULES_TABLE)},
        ),
    )


def is_model_launch_bound(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> RuleResult | None:
    """Model launch failures override all metric-derived verdicts."""

    del thresholds
    healthcheck_failed = _healthcheck_failed(bundle.healthcheck)
    validation_failed = _validation_reports_launch_failure(bundle.validation_report, bundle.job_id)
    if not healthcheck_failed and not validation_failed:
        return None
    status = bundle.healthcheck.get("status")
    if status is None and bundle.healthcheck.get("ok") is False:
        status = "failed"
    failure_reason = bundle.healthcheck.get("failure_reason") or "launch_failure"
    evidence = [
        Evidence(
            metric="launch.healthcheck.status",
            value=status or "validation_launch_failure",
            source=_source(bundle, "healthcheck"),
            claim_status="measured",
        )
    ]
    if validation_failed:
        evidence.append(
            Evidence(
                metric="validation_report.launch_failure",
                value=True,
                source=_source(bundle, "validation_report"),
                claim_status="measured",
            )
        )
    return RuleResult(
        verdict=Verdict.MODEL_LAUNCH_BOUND,
        confidence=1.0,
        claim_status="measured",
        primary_evidence=evidence,
        secondary_evidence=[],
        rule_fired="model_launch_bound",
        reasoning=(
            "The launch healthcheck or validation report indicates the model did not become "
            f"healthy before diagnosis. Failure reason: {failure_reason}."
        ),
        recommended_next_probe=(
            "inferguard launch-engine "
            "--engine <vllm|sglang> --external-launch --endpoint-url <endpoint> "
            f"--output-dir {bundle.job_dir / 'launch'}"
        ),
        metric_values={
            "healthcheck_status": status,
            "failure_reason": failure_reason,
            "validation_launch_failure": validation_failed,
        },
    )


def is_prefill_bound(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> RuleResult | None:
    """High TTFT plus engine-side prefill share yields `prefill_bound`."""

    ttft_p95 = _summary_stat(bundle.request_summary, "ttft_ms", "p95")
    e2e_p95 = _summary_stat(bundle.request_summary, "e2e_latency_ms", "p95")
    engine_prefill = _group_value(bundle, "prefill", "request_prefill_time_seconds", "p95")
    engine_e2e = _engine_e2e_seconds(bundle)
    running = _group_value(bundle, "queue", "requests_running", "p95")
    if None in (ttft_p95, e2e_p95, engine_prefill, engine_e2e, running):
        return None
    if e2e_p95 <= 0 or engine_e2e <= 0:
        return None
    request_ratio = ttft_p95 / e2e_p95
    engine_ratio = engine_prefill / engine_e2e
    if request_ratio <= thresholds["prefill_ttft_e2e_ratio"]:
        return None
    if engine_ratio <= thresholds["prefill_engine_e2e_ratio"]:
        return None
    if running > thresholds["prefill_running_low_max"]:
        return None
    secondary = _prefill_decode_secondary_evidence(bundle)
    metric_values = {
        "ttft_ms.p95": ttft_p95,
        "e2e_latency_ms.p95": e2e_p95,
        "ttft_e2e_ratio": request_ratio,
        "vllm:request_prefill_time_seconds.p95": engine_prefill,
        "vllm:e2e_request_latency_seconds.p95": engine_e2e,
        "engine_prefill_e2e_ratio": engine_ratio,
        "vllm:num_requests_running": running,
    }
    return RuleResult(
        verdict=Verdict.PREFILL_BOUND,
        confidence=0.9,
        claim_status=_claim_status(bundle, "prefill", "queue"),
        primary_evidence=[
            Evidence("request.ttft_ms", _source(bundle, "requests_summary"), value_p95=ttft_p95),
            Evidence(
                "request.e2e_latency_ms", _source(bundle, "requests_summary"), value_p95=e2e_p95
            ),
            Evidence(
                "vllm:request_prefill_time_seconds",
                _source(bundle, "metrics_summary"),
                value_p95=engine_prefill,
                claim_status=_group_status(bundle, "prefill"),
            ),
            Evidence(
                "vllm:e2e_request_latency_seconds",
                _source(bundle, "engine_metrics_timeline"),
                value_p95=engine_e2e,
                claim_status=_group_status(bundle, "prefill"),
            ),
            Evidence(
                "vllm:num_requests_running",
                _source(bundle, "metrics_summary"),
                value=running,
                claim_status=_group_status(bundle, "queue"),
            ),
        ],
        secondary_evidence=secondary,
        rule_fired="prefill_bound",
        reasoning=(
            "Request TTFT dominates end-to-end latency while engine prefill time is more "
            "than half of engine E2E latency, and queue depth is low."
        ),
        recommended_next_probe=(
            "inferguard request-profile "
            "--endpoint <endpoint> --model <model> --input-jsonl <long-context-jsonl> "
            f"--output-dir {bundle.job_dir / 'request_profile_prefill_probe'} --stream --concurrency 1"
        ),
        metric_values=metric_values,
    )


def is_decode_bound(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> RuleResult | None:
    """High TPOT skew plus tensor-pipe pressure yields `decode_bound`."""

    tpot_p50 = _summary_stat(bundle.request_summary, "tpot_ms", "p50")
    tpot_p95 = _summary_stat(bundle.request_summary, "tpot_ms", "p95")
    engine_tpot = _group_value(bundle, "decode", "time_per_output_token_seconds", "p95")
    tensor_active = _group_value(bundle, "gpu_util", "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE", "p95")
    if None in (tpot_p50, tpot_p95, engine_tpot, tensor_active):
        return None
    if tpot_p50 <= 0:
        return None
    tensor_fraction = _fraction(tensor_active)
    if tpot_p95 <= tpot_p50 * thresholds["decode_tpot_skew_ratio"]:
        return None
    if engine_tpot * 1000.0 <= thresholds["decode_tpot_slo_floor_ms"]:
        return None
    if tensor_fraction <= thresholds["decode_tensor_active_p95"]:
        return None
    metric_values = {
        "tpot_ms.p50": tpot_p50,
        "tpot_ms.p95": tpot_p95,
        "tpot_skew_ratio": tpot_p95 / tpot_p50,
        "vllm:time_per_output_token_seconds.p95": engine_tpot,
        "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE.p95": tensor_active,
    }
    return RuleResult(
        verdict=Verdict.DECODE_BOUND,
        confidence=0.88,
        claim_status=_claim_status(bundle, "decode", "gpu_util"),
        primary_evidence=[
            Evidence("request.tpot_ms", _source(bundle, "requests_summary"), value_p95=tpot_p95),
            Evidence(
                "vllm:time_per_output_token_seconds",
                _source(bundle, "metrics_summary"),
                value_p95=engine_tpot,
                claim_status=_group_status(bundle, "decode"),
            ),
            Evidence(
                "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE",
                _source(bundle, "metrics_summary"),
                value_p95=tensor_active,
                claim_status=_group_status(bundle, "gpu_util"),
            ),
        ],
        secondary_evidence=_prefill_decode_secondary_evidence(bundle),
        rule_fired="decode_bound",
        reasoning=(
            "Output-token latency is skewed at p95, engine TPOT is above the SLO floor, "
            "and tensor-pipe activity is high."
        ),
        recommended_next_probe=(
            "inferguard request-profile "
            "--endpoint <endpoint> --model <model> --input-jsonl <decode-heavy-jsonl> "
            f"--output-dir {bundle.job_dir / 'request_profile_decode_probe'} --stream --concurrency 1"
        ),
        metric_values=metric_values,
    )


def is_queue_bound(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> RuleResult | None:
    """Waiting/running imbalance plus rising p99 latency yields `queue_bound`."""

    waiting = _group_value(bundle, "queue", "requests_waiting", "p95")
    running = _group_value(bundle, "queue", "requests_running", "p95")
    e2e_p99 = _summary_stat(bundle.request_summary, "e2e_latency_ms", "p99")
    if None in (waiting, running, e2e_p99):
        return None
    ratio = math.inf if running == 0 and waiting > 0 else waiting / max(running, 1.0)
    if ratio <= thresholds["queue_waiting_running_ratio"]:
        return None
    if not _e2e_p99_rising(bundle.request_summary, thresholds):
        return None
    metric_values = {
        "vllm:num_requests_waiting": waiting,
        "vllm:num_requests_running": running,
        "waiting_running_ratio": ratio,
        "e2e_latency_ms.p99": e2e_p99,
    }
    return RuleResult(
        verdict=Verdict.QUEUE_BOUND,
        confidence=0.87,
        claim_status=_claim_status(bundle, "queue"),
        primary_evidence=[
            Evidence(
                "vllm:num_requests_waiting",
                _source(bundle, "metrics_summary"),
                value=waiting,
                claim_status=_group_status(bundle, "queue"),
            ),
            Evidence(
                "vllm:num_requests_running",
                _source(bundle, "metrics_summary"),
                value=running,
                claim_status=_group_status(bundle, "queue"),
            ),
            Evidence(
                "request.e2e_latency_ms", _source(bundle, "requests_summary"), value_p95=e2e_p99
            ),
        ],
        secondary_evidence=[],
        rule_fired="queue_bound",
        reasoning=(
            "Waiting requests exceed running requests for the window and request p99 latency "
            "is rising, which points to scheduler or admission pressure."
        ),
        recommended_next_probe=(
            "inferguard request-profile "
            "--endpoint <endpoint> --model <model> --input-jsonl <load-jsonl> "
            f"--output-dir {bundle.job_dir / 'request_profile_queue_probe'} "
            "--arrival-mode poisson --rate-rps <target-rps> --concurrency <n>"
        ),
        metric_values=metric_values,
    )


def is_kv_bound(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> RuleResult | None:
    """KV usage, prefix-cache misses, LMCache pressure, or KV-transfer faults."""

    kv = _group(bundle, "kv_cache")
    prefix = _group(bundle, "prefix_cache")
    usage = _group_value(bundle, "kv_cache", "usage_fraction", "p95")
    usage_source = kv.get("usage_fraction_source")
    if usage is not None and usage > thresholds["kv_usage_fraction_p95"]:
        if not usage_source:
            return _not_enough_result(
                bundle,
                rule_fired="kv_usage_source_missing",
                reasoning=(
                    "KV usage crossed the pressure threshold, but metrics_summary did not record "
                    "which vLLM cache metric supplied usage_fraction."
                ),
                metric_values={"kv_cache.usage_fraction": usage},
                downgrades=[
                    Downgrade(
                        "kv_cache_usage",
                        "measured",
                        "not_proven",
                        "kv_usage_fraction_source_missing",
                    )
                ],
            )
        return _kv_result(
            bundle,
            confidence=0.9,
            rule_fired="kv_bound",
            reasoning="KV cache usage exceeded the locked 0.85 p95 pressure threshold.",
            metric_values={
                "kv_cache.usage_fraction": usage,
                "kv_cache.usage_fraction_source": usage_source,
            },
            primary=[
                Evidence(
                    str(usage_source),
                    _source(bundle, "metrics_summary"),
                    value_p95=usage,
                    claim_status=_group_status(bundle, "kv_cache"),
                )
            ],
        )
    prefix_hit = _number(prefix.get("hit_rate"))
    idle_before_evict = _group_value(
        bundle, "kv_cache", "kv_block_idle_before_evict_seconds", "p95"
    )
    lmcache_evict = _group_value(bundle, "lmcache", "local_cpu_evict_count", "p95")
    low_prefix = prefix_hit is not None and prefix_hit < thresholds["prefix_cache_expected_floor"]
    eviction_pressure = _trend(kv, "kv_block_idle_before_evict_seconds") == "rising"
    eviction_pressure = eviction_pressure or (
        idle_before_evict is not None and idle_before_evict > 0
    )
    eviction_pressure = eviction_pressure or (lmcache_evict is not None and lmcache_evict > 0)
    if low_prefix and eviction_pressure:
        return _kv_result(
            bundle,
            confidence=0.84,
            rule_fired="kv_bound_prefix_cache_pressure",
            reasoning=(
                "Prefix-cache hit rate is below the expected floor while eviction or LMCache "
                "pressure is present."
            ),
            metric_values={
                "prefix_cache.hit_rate": prefix_hit,
                "kv_block_idle_before_evict_seconds.p95": idle_before_evict,
                "lmcache.local_cpu_evict_count": lmcache_evict,
            },
            primary=[
                Evidence(
                    "prefix_cache.hit_rate",
                    _source(bundle, "metrics_summary"),
                    value=prefix_hit,
                    claim_status=_group_status(bundle, "prefix_cache"),
                ),
                Evidence(
                    "vllm:kv_block_idle_before_evict_seconds",
                    _source(bundle, "metrics_summary"),
                    value_p95=idle_before_evict,
                    claim_status=_group_status(bundle, "kv_cache"),
                ),
            ],
        )
    status = _disagg_status_from_summary(bundle)
    transfer_findings = [
        finding
        for finding in (
            rule_kv_transfer_errors_present(status),
            rule_kv_transfer_stall(status),
        )
        if finding is not None
    ]
    if transfer_findings:
        finding = transfer_findings[0]
        evidence = [
            Evidence(
                f"disagg.{finding.code}",
                _source(bundle, "metrics_summary"),
                value=finding.evidence,
                claim_status=_group_status(bundle, "kv_cache"),
            )
        ]
        return _kv_result(
            bundle,
            confidence=0.78,
            rule_fired=str(finding.code),
            reasoning=finding.message,
            metric_values={f"disagg.{finding.code}": finding.evidence},
            primary=evidence,
        )
    return None


def is_network_bound(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> RuleResult | None:
    """Multi-node NVLink saturation plus NCCL under-baseline yields `network_bound`."""

    if _node_count(bundle) <= 1:
        return None
    saturated, nvlink_values = _nvlink_saturated(bundle, thresholds)
    if not saturated:
        return None
    if not bundle.nccl_evidence_paths:
        return _not_enough_result(
            bundle,
            rule_fired="network_bound_missing_nccl",
            reasoning=(
                "The job is multi-node and NVLink counters look saturated, but NCCL evidence "
                "is absent, so network claims are not proven."
            ),
            metric_values=nvlink_values | {"nccl_evidence_present": False},
            downgrades=[
                Downgrade(
                    "network_bound",
                    "measured",
                    "not_proven",
                    "multi_node_network_claim_requires_nccl_evidence",
                )
            ],
        )
    busbw, expected = _nccl_busbw(bundle)
    if busbw is None or expected is None or expected <= 0:
        return _not_enough_result(
            bundle,
            rule_fired="network_bound_nccl_baseline_missing",
            reasoning="NCCL artifacts are present but do not include both measured and expected bus bandwidth.",
            metric_values=nvlink_values | {"nccl_busbw": busbw, "nccl_expected_busbw": expected},
        )
    busbw_fraction = busbw / expected
    if busbw_fraction >= thresholds["network_nccl_busbw_fraction"]:
        return None
    metric_values = nvlink_values | {
        "nccl_busbw": busbw,
        "nccl_expected_busbw": expected,
        "nccl_busbw_fraction": busbw_fraction,
    }
    return RuleResult(
        verdict=Verdict.NETWORK_BOUND,
        confidence=0.86,
        claim_status=_claim_status(bundle, "nvlink"),
        primary_evidence=[
            Evidence(
                "DCGM_FI_PROF_NVLINK_TX_BYTES",
                _source(bundle, "metrics_summary"),
                value_p95=nvlink_values.get("DCGM_FI_PROF_NVLINK_TX_BYTES.p95"),
                claim_status=_group_status(bundle, "nvlink"),
            ),
            Evidence(
                "nccl.busbw",
                str(bundle.nccl_evidence_paths[0]),
                value=busbw,
                claim_status="measured",
            ),
        ],
        secondary_evidence=[],
        rule_fired="network_bound",
        reasoning=(
            "The run is multi-node, NVLink counters are saturated, and NCCL bus bandwidth "
            "is below 60 percent of the expected baseline."
        ),
        recommended_next_probe=(
            "srun -N <nodes> -n <ranks> all_reduce_perf -b 8M -e 8G -f 2 "
            f"| tee {bundle.job_dir / 'nccl' / 'all_reduce_perf.txt'}"
        ),
        metric_values=metric_values,
    )


def is_host_bound(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> RuleResult | None:
    """Low GPU utilization plus high latency and CPU saturation yields `host_bound`."""

    gpu_util = _group_value(bundle, "gpu_util", "DCGM_FI_DEV_GPU_UTIL", "p95")
    e2e_p99 = _summary_stat(bundle.request_summary, "e2e_latency_ms", "p99")
    cpu_saturated, cpu_metric, cpu_source = _cpu_saturated(bundle)
    if gpu_util is None or e2e_p99 is None or not cpu_saturated:
        return None
    if _fraction(gpu_util) >= thresholds["host_gpu_util_fraction"]:
        return None
    if e2e_p99 <= thresholds["host_e2e_slo_p99_ms"]:
        return None
    metric_values = {
        "DCGM_FI_DEV_GPU_UTIL.p95": gpu_util,
        "e2e_latency_ms.p99": e2e_p99,
        "cpu_saturated": cpu_metric,
    }
    return RuleResult(
        verdict=Verdict.HOST_BOUND,
        confidence=0.82,
        claim_status=_claim_status(bundle, "gpu_util"),
        primary_evidence=[
            Evidence(
                "DCGM_FI_DEV_GPU_UTIL",
                _source(bundle, "metrics_summary"),
                value_p95=gpu_util,
                claim_status=_group_status(bundle, "gpu_util"),
            ),
            Evidence(
                "request.e2e_latency_ms", _source(bundle, "requests_summary"), value_p95=e2e_p99
            ),
            Evidence(
                "cpu_trace.saturated_core", cpu_source, value=cpu_metric, claim_status="measured"
            ),
        ],
        secondary_evidence=[],
        rule_fired="host_bound",
        reasoning=(
            "GPU utilization is low while request p99 exceeds the latency SLO and CPU "
            "sampling shows at least one saturated core."
        ),
        recommended_next_probe=(
            "python3 -m inferguard.bench.cpu_trace --pid <engine-pid> "
            f"--output {bundle.job_dir / 'cpu_trace' / 'summary.json'}"
        ),
        metric_values=metric_values,
    )


def _diagnosis(bundle: EvidenceBundle, result: RuleResult) -> BottleneckDiagnosis:
    evidence_paths = _evidence_paths(bundle, result)
    return BottleneckDiagnosis(
        job_id=bundle.job_id,
        verdict=result.verdict,
        confidence=max(0.0, min(1.0, result.confidence)),
        claim_status=result.claim_status,
        primary_evidence=result.primary_evidence,
        secondary_evidence=result.secondary_evidence,
        supporting_request_rows=_supporting_request_rows(bundle, result.verdict),
        rule_fired=result.rule_fired,
        reasoning=result.reasoning,
        recommended_next_probe=result.recommended_next_probe,
        downgrades=result.downgrades,
        evidence_paths=evidence_paths,
        metric_values=result.metric_values,
    )


def _missing_required_inputs(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> RuleResult | None:
    del thresholds
    if not bundle.missing_required_paths and not bundle.parse_errors:
        return None
    missing = [str(path) for path in bundle.missing_required_paths]
    metric_values: dict[str, Any] = {
        "missing_required_paths": missing,
        "parse_errors": dict(sorted(bundle.parse_errors.items())),
    }
    return _not_enough_result(
        bundle,
        rule_fired="required_input_artifacts_missing",
        reasoning=(
            "Required request-profile or metrics artifacts are missing or unreadable, "
            "so the diagnoser cannot prove an eight-class bottleneck."
        ),
        metric_values=metric_values,
    )


def _all_metric_groups_not_proven(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> RuleResult | None:
    del thresholds
    if not bundle.metrics_summary:
        return None
    groups = (
        "prefill",
        "decode",
        "queue",
        "kv_cache",
        "prefix_cache",
        "lmcache",
        "gpu_util",
        "nvlink",
    )
    statuses = [_group_status(bundle, group) for group in groups]
    if any(status != "not_proven" for status in statuses):
        return None
    return _not_enough_result(
        bundle,
        rule_fired="metrics_groups_not_proven",
        reasoning="metrics_summary marks every rule-critical group as not_proven.",
        metric_values={"group_claim_statuses": dict(zip(groups, statuses, strict=True))},
    )


def _sglang_chunked_prefill_bug_downgrade(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> RuleResult | None:
    if _engine(bundle) != "sglang":
        return None
    if "B200" not in _hardware_label(bundle).upper():
        return None
    if "fp8" not in _launch_text(bundle).lower():
        return None
    ttft_p95 = _summary_stat(bundle.request_summary, "ttft_ms", "p95")
    e2e_p95 = _summary_stat(bundle.request_summary, "e2e_latency_ms", "p95")
    if ttft_p95 is None or e2e_p95 is None or e2e_p95 <= 0:
        return None
    ratio = ttft_p95 / e2e_p95
    if ratio <= thresholds["prefill_ttft_e2e_ratio"]:
        return None
    return _not_enough_result(
        bundle,
        rule_fired="sglang_chunked_prefill_bug_downgrade",
        reasoning=(
            "SGLang on B200 with FP8 can force chunked-prefill behavior, so high TTFT "
            "alone is downgraded instead of emitted as prefill_bound."
        ),
        metric_values={
            "ttft_e2e_ratio": ratio,
            "engine": "sglang",
            "hardware": _hardware_label(bundle),
        },
        claim_status="inferred",
        downgrades=[
            Downgrade(
                "prefill_bound",
                "measured",
                "inferred",
                "sglang_chunked_prefill_bug_b200_fp8_high_ttft",
            )
        ],
    )


def _sglang_speculative_kv_bug_downgrade(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> RuleResult | None:
    del thresholds
    if _engine(bundle) != "sglang":
        return None
    hit_rate = _number(_group(bundle, "prefix_cache").get("hit_rate"))
    if hit_rate != 0:
        return None
    if "--speculative-algorithm" not in _launch_text(bundle):
        return None
    return _not_enough_result(
        bundle,
        rule_fired="sglang_speculative_cache_hit_bug_downgrade",
        reasoning=(
            "SGLang speculative decoding can report zero cache hit rate, so apparent "
            "zero-hit KV pressure is downgraded."
        ),
        metric_values={"prefix_cache.hit_rate": hit_rate, "speculative_algorithm": True},
        claim_status="inferred",
        downgrades=[
            Downgrade(
                "kv_bound",
                "measured",
                "inferred",
                "sglang_speculative_cache_hit_rate_zero_bug",
            )
        ],
    )


def _lmcache_missing_signal_downgrade(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> RuleResult | None:
    del thresholds
    report = bundle.lmcache_compat_report
    report_mode = (report or {}).get("detected_mode")
    compat_report_active = bool(report) and report_mode in {"mp", "mixed"}
    if report and not compat_report_active and not bundle.lmcache_log_evidence:
        return None
    if not report and not bundle.lmcache_log_evidence:
        return None
    findings = [
        item
        for item in ((report or {}).get("diagnostic_findings") if compat_report_active else []) or []
        if isinstance(item, Mapping)
    ]
    finding_priority = [
        "lmcache_mp_l1_failures",
        "lmcache_mp_l2_failures",
        "lmcache_mp_eventbus_loss",
        "lmcache_mp_l1_eviction_pressure",
        "lmcache_mp_low_hit_rate",
        "otel_tracing_enabled_but_no_spans",
        "lmcache_mp_trace_enabled_but_no_trace_artifact",
        "lmcache_mp_eventbus_taildrop_unobservable",
        "lmcache_mp_empty_cache_salt",
    ]
    selected_finding_code = _select_lmcache_finding_code(findings, finding_priority)
    if selected_finding_code:
        selected_finding = next(
            item for item in findings if str(item.get("code")) == selected_finding_code
        )
        selected_claim_status = (
            "measured"
            if selected_finding.get("severity") in {"critical", "warning"}
            else "inferred"
        )
        downgrades = []
        if selected_claim_status != "measured":
            downgrades.append(
                Downgrade(
                    "lmcache_mp_diagnostics",
                    "measured",
                    "inferred",
                    selected_finding_code,
                )
            )
        return _not_enough_result(
            bundle,
            rule_fired=selected_finding_code,
            reasoning=str(
                selected_finding.get("message")
                or "LMCache MP telemetry contains an actionable cache observability finding."
            ),
            metric_values={
                "lmcache_compat.detected_mode": (report or {}).get("detected_mode"),
                "lmcache_compat.detected_architecture": (
                    (report or {}).get("detected_architecture") or {}
                ),
                "lmcache_compat.diagnostic_findings": findings,
            },
            claim_status=selected_claim_status,
            downgrades=downgrades,
            evidence_source_key="lmcache_compat_report",
        )
    questions = [
        item
        for item in ((report or {}).get("upstream_questions") if compat_report_active else []) or []
        if isinstance(item, Mapping)
    ]
    codes = {str(item.get("code")) for item in questions}
    if codes:
        priority = [
            "lmcache_mp_lookup_counters_missing",
            "vllm_external_prefix_no_hits",
            "lmcache_eventbus_self_metrics_missing",
            "lmcache_mp_empty_cache_salt",
        ]
        selected = _select_lmcache_code(codes, priority) or sorted(codes)[0]
        return _not_enough_result(
            bundle,
            rule_fired=selected,
            reasoning=(
                "LMCache MP telemetry is present, but a required observability surface is "
                "missing or ambiguous. The run proves MP is wired, not that the cache "
                "economics are fully diagnosable."
            ),
            metric_values={
                "lmcache_compat.detected_mode": (report or {}).get("detected_mode"),
                "lmcache_compat.upstream_question_codes": sorted(codes),
                "lmcache_compat.surfaces": (report or {}).get("surfaces") or {},
            },
            claim_status="inferred",
            downgrades=[
                Downgrade(
                    "lmcache_mp_compatibility",
                    "measured",
                    "inferred",
                    selected,
                )
            ],
            evidence_source_key="lmcache_compat_report",
        )
    log_result = _lmcache_log_evidence_downgrade(bundle, report or {})
    if log_result is not None:
        return log_result
    return None


def _select_lmcache_finding_code(
    findings: list[Mapping[str, Any]],
    priority: list[str],
) -> str:
    codes = {str(item.get("code")) for item in findings}
    return _select_lmcache_code(codes, priority)


def _select_lmcache_code(codes: set[str], priority: list[str]) -> str:
    selected = next((code for code in priority if code in codes), "")
    if selected:
        return selected
    user_facing_prefixes = (
        "lmcache_log",
        "lmcache_cacheblend",
        "lmcache_p2p",
        "lmcache_pd",
        "lmcache_trace_replay",
        "lmcache_lookup_hash",
        "cacheblend",
        "cb.",
        "p2p",
        "pd_",
        "disaggregated_prefill",
        "trace_replay",
        "lookup_hash",
    )
    selected = next(
        (
            code
            for code in sorted(codes)
            if code.startswith(user_facing_prefixes)
            or "cacheblend" in code
            or "cache_blend" in code
            or "p2p" in code
            or "disaggregated_prefill" in code
            or "trace_replay" in code
            or "lookup_hash" in code
        ),
        "",
    )
    return selected


def _lmcache_log_evidence_downgrade(
    bundle: EvidenceBundle,
    report: Mapping[str, Any],
) -> RuleResult | None:
    log_evidence = bundle.lmcache_log_evidence
    if not log_evidence:
        return None
    event_counts = log_evidence.get("event_counts") or {}
    config = log_evidence.get("config") or {}
    code = ""
    if config.get("stale_lmcache_connector_seen"):
        code = "lmcache_log_stale_connector"
    elif (event_counts.get("pd_sender") or 0) or (event_counts.get("pd_receiver") or 0):
        code = "lmcache_log_pd_evidence_present"
    elif (event_counts.get("p2p_peer") or 0) or (event_counts.get("p2p_transfer") or 0):
        code = "lmcache_log_p2p_evidence_present"
    elif (event_counts.get("store") or 0) or (event_counts.get("retrieve") or 0):
        code = "lmcache_log_lifecycle_evidence_present"
    if not code:
        return None
    return _not_enough_result(
        bundle,
        rule_fired=code,
        reasoning=(
            "LMCache logs contain mode or lifecycle evidence, but log snippets alone "
            "do not prove cache economics. Pair this packet with Prometheus, HTTP, "
            "trace, and replay evidence before making a live coverage claim."
        ),
        metric_values={
            "lmcache_compat.detected_mode": report.get("detected_mode"),
            "lmcache_log.event_counts": event_counts,
            "lmcache_log.config": config,
            "lmcache_log.mode_candidates": log_evidence.get("mode_candidates") or [],
        },
        claim_status="inferred",
        downgrades=[
            Downgrade(
                "lmcache_log_evidence",
                "measured",
                "inferred",
                code,
            )
        ],
        evidence_source_key="lmcache_log_evidence",
    )


def _not_enough_result(
    bundle: EvidenceBundle,
    *,
    rule_fired: str,
    reasoning: str,
    metric_values: dict[str, Any],
    claim_status: ClaimStatus | str = "not_proven",
    downgrades: list[Downgrade] | None = None,
    evidence_source_key: str | None = None,
) -> RuleResult:
    source_key = evidence_source_key or (
        "metrics_summary" if bundle.paths.get("metrics_summary") else "job_dir"
    )
    evidence = [
        Evidence(
            metric="diagnose.required_evidence",
            value=metric_values,
            source=_source(bundle, source_key),
            claim_status=claim_status,
        )
    ]
    return RuleResult(
        verdict=Verdict.NOT_ENOUGH_EVIDENCE,
        confidence=0.0,
        claim_status=claim_status,
        primary_evidence=evidence,
        secondary_evidence=[],
        rule_fired=rule_fired,
        reasoning=reasoning,
        recommended_next_probe=(
            "inferguard collect-metrics "
            "--engine <engine> --engine-metrics-url <url> --dcgm-metrics-url <url> "
            f"--output-dir {bundle.job_dir / 'metrics'} --duration-seconds 120"
        ),
        metric_values=metric_values,
        downgrades=downgrades or [],
    )


def _kv_result(
    bundle: EvidenceBundle,
    *,
    confidence: float,
    rule_fired: str,
    reasoning: str,
    metric_values: dict[str, Any],
    primary: list[Evidence],
) -> RuleResult:
    return RuleResult(
        verdict=Verdict.KV_BOUND,
        confidence=confidence,
        claim_status=_claim_status(bundle, "kv_cache", "prefix_cache", "lmcache"),
        primary_evidence=primary,
        secondary_evidence=[],
        rule_fired=rule_fired,
        reasoning=reasoning,
        recommended_next_probe=(
            "inferguard collect-metrics "
            "--engine <engine> --engine-metrics-url <url> --dcgm-metrics-url <url> "
            "--lmcache-metrics-url <url-if-present> "
            f"--output-dir {bundle.job_dir / 'metrics_kv_probe'} --duration-seconds 120"
        ),
        metric_values=metric_values,
    )


def _thresholds(config: Mapping[str, Any]) -> dict[str, float]:
    thresholds = dict(DEFAULT_THRESHOLDS)
    for key, value in config.items():
        number = _number(value)
        if key in thresholds and number is not None:
            thresholds[key] = number
    return thresholds


def _source(bundle: EvidenceBundle, key: str) -> str:
    if key == "job_dir":
        return str(bundle.job_dir)
    path = bundle.paths.get(key)
    return str(path) if path is not None else str(bundle.job_dir)


def _evidence_paths(bundle: EvidenceBundle, result: RuleResult) -> list[str]:
    paths: list[str] = []
    for evidence in result.primary_evidence + result.secondary_evidence:
        if evidence.source and evidence.source not in paths:
            paths.append(evidence.source)
    for path in bundle.nccl_evidence_paths:
        text = str(path)
        if text not in paths and result.verdict == Verdict.NETWORK_BOUND:
            paths.append(text)
    return paths or [str(bundle.job_dir)]


def _supporting_request_rows(bundle: EvidenceBundle, verdict: Verdict | str) -> list[str]:
    if str(verdict) == Verdict.MODEL_LAUNCH_BOUND.value:
        return []
    rows: list[str] = []
    for row in bundle.request_rows:
        request_id = row.get("request_id")
        if request_id:
            rows.append(str(request_id))
        if len(rows) >= 5:
            break
    return rows


def _group(bundle: EvidenceBundle, name: str) -> dict[str, Any]:
    summary = bundle.metrics_summary
    nested = summary.get("groups")
    if isinstance(nested, Mapping):
        value = nested.get(name)
        if isinstance(value, Mapping):
            return dict(value)
    value = summary.get(name)
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _group_status(bundle: EvidenceBundle, name: str) -> str:
    return str(_group(bundle, name).get("claim_status") or "not_proven")


def _claim_status(bundle: EvidenceBundle, *groups: str) -> str:
    statuses = [_group_status(bundle, group) for group in groups]
    if "synthetic" in statuses:
        return "synthetic"
    if "inferred" in statuses:
        return "inferred"
    if statuses and all(status == "measured" for status in statuses):
        return "measured"
    if "measured" in statuses:
        return "inferred"
    return "not_proven"


def _group_value(
    bundle: EvidenceBundle, group_name: str, field_name: str, stat: str
) -> float | None:
    group = _group(bundle, group_name)
    return _field_value(group, field_name, stat)


def _field_value(group: Mapping[str, Any], field_name: str, stat: str) -> float | None:
    value = group.get(field_name)
    if isinstance(value, Mapping):
        return _number(value.get(stat) if value.get(stat) is not None else value.get("value"))
    number = _number(value)
    if number is not None:
        return number
    stats = group.get("stats")
    if isinstance(stats, Mapping):
        field_stats = stats.get(field_name)
        if isinstance(field_stats, Mapping):
            return _number(
                field_stats.get(stat)
                if field_stats.get(stat) is not None
                else field_stats.get("value")
            )
    return _number(group.get(f"{field_name}_{stat}"))


def _summary_stat(summary: Mapping[str, Any], group_name: str, stat: str) -> float | None:
    group = summary.get(group_name)
    if isinstance(group, Mapping):
        return _number(group.get(stat))
    return _number(summary.get(f"{group_name}.{stat}") or summary.get(f"{group_name}_{stat}"))


def _engine_e2e_seconds(bundle: EvidenceBundle) -> float | None:
    for group_name in ("prefill", "decode", "queue"):
        value = _group_value(bundle, group_name, "e2e_request_latency_seconds", "p95")
        if value is not None:
            return value
    return _timeline_metric_p95(bundle.engine_rows, "vllm:e2e_request_latency_seconds")


def _timeline_metric_p95(rows: list[dict[str, Any]], metric: str) -> float | None:
    values: list[float] = []
    for row in rows:
        for container_name in ("metrics", "normalized"):
            container = row.get(container_name)
            if not isinstance(container, Mapping):
                continue
            number = _number(container.get(metric))
            if number is not None:
                values.append(number)
        number = _number(row.get(metric))
        if number is not None:
            values.append(number)
    return _percentile(values, 0.95) if values else None


def _prefill_decode_secondary_evidence(bundle: EvidenceBundle) -> list[Evidence]:
    finding = rule_prefill_decode_imbalance(_disagg_status_from_summary(bundle))
    if finding is None:
        return []
    return [
        Evidence(
            metric=f"disagg.{finding.code}",
            value=finding.evidence,
            source=_source(bundle, "metrics_summary"),
            claim_status=_group_status(bundle, "queue"),
            note=finding.message,
        )
    ]


def _disagg_status_from_summary(bundle: EvidenceBundle) -> DisaggStatus:
    queue = _group(bundle, "queue")
    kv = _group(bundle, "kv_cache")
    engine = _engine(bundle)
    endpoint = EndpointId(url="metrics_summary", role="prefill", engine=_disagg_engine(engine))
    prefill = DisaggSnapshot(
        endpoint=endpoint,
        scraped_at=0.0,
        requests_running=_int_or_none(
            _number(queue.get("prefill_requests_running"))
            or _field_value(queue, "requests_running", "p95")
        ),
        kv_transfer_sent_bytes_total=_int_or_none(kv.get("kv_transfer_sent_bytes_total")),
        kv_transfer_errors_total=_int_or_none(kv.get("kv_transfer_errors_total")),
    )
    decode = DisaggSnapshot(
        endpoint=EndpointId(url="metrics_summary", role="decode", engine=_disagg_engine(engine)),
        scraped_at=0.0,
        requests_running=_int_or_none(
            _number(queue.get("decode_requests_running"))
            or _field_value(queue, "requests_running", "p95")
        ),
        kv_transfer_recv_bytes_total=_int_or_none(kv.get("kv_transfer_recv_bytes_total")),
        kv_transfer_errors_total=_int_or_none(kv.get("kv_transfer_errors_total")),
    )
    return DisaggStatus(prefill=prefill, decode=decode, transfer=None)


def _disagg_engine(engine: str) -> Any:
    if engine in {"vllm", "sglang", "dynamo", "lmcache", "llm-d"}:
        return engine
    if engine == "dynamo-sglang":
        return "dynamo"
    return "unknown"


def _e2e_p99_rising(summary: Mapping[str, Any], thresholds: Mapping[str, float]) -> bool:
    group = summary.get("e2e_latency_ms")
    if isinstance(group, Mapping) and group.get("trend") == "rising":
        return True
    p50 = _summary_stat(summary, "e2e_latency_ms", "p50")
    p99 = _summary_stat(summary, "e2e_latency_ms", "p99")
    if p50 is None or p99 is None or p50 <= 0:
        return False
    return p99 > p50 * thresholds["queue_e2e_p99_rise_ratio"]


def _trend(group: Mapping[str, Any], field_name: str) -> str:
    value = group.get(f"{field_name}_trend") or group.get("trend")
    if isinstance(value, str):
        return value
    trends = group.get("trends")
    if isinstance(trends, Mapping):
        trend = trends.get(field_name)
        if isinstance(trend, str):
            return trend
    return ""


def _node_count(bundle: EvidenceBundle) -> int:
    for source in (
        bundle.operator_profile,
        bundle.metrics_summary.get("labels")
        if isinstance(bundle.metrics_summary.get("labels"), Mapping)
        else {},
    ):
        if not isinstance(source, Mapping):
            continue
        for key in ("node_count", "nodes", "num_nodes", "GMI_SLURM_NODES"):
            value = source.get(key)
            number = _number(value)
            if number is not None and number >= 1:
                return int(number)
    return 1


def _nvlink_saturated(
    bundle: EvidenceBundle,
    thresholds: Mapping[str, float],
) -> tuple[bool, dict[str, Any]]:
    nvlink = _group(bundle, "nvlink")
    saturation = _number(nvlink.get("saturation_fraction"))
    tx = _group_value(bundle, "nvlink", "DCGM_FI_PROF_NVLINK_TX_BYTES", "p95")
    rx = _group_value(bundle, "nvlink", "DCGM_FI_PROF_NVLINK_RX_BYTES", "p95")
    values: dict[str, Any] = {
        "nvlink.saturation_fraction": saturation,
        "DCGM_FI_PROF_NVLINK_TX_BYTES.p95": tx,
        "DCGM_FI_PROF_NVLINK_RX_BYTES.p95": rx,
    }
    if saturation is not None:
        return saturation >= thresholds["network_nvlink_saturation_fraction"], values
    byte_threshold = thresholds["network_nvlink_bytes_p95"]
    return bool(
        tx is not None and rx is not None and tx >= byte_threshold and rx >= byte_threshold
    ), values


def _nccl_busbw(bundle: EvidenceBundle) -> tuple[float | None, float | None]:
    summary = bundle.nccl_summary
    busbw = _number(
        summary.get("busbw")
        or summary.get("busbw_gbps")
        or summary.get("measured_busbw_gbps")
        or summary.get("bus_bandwidth_gbps")
    )
    expected = _number(
        summary.get("expected_busbw")
        or summary.get("expected_busbw_gbps")
        or summary.get("baseline_busbw_gbps")
    )
    fraction = _number(summary.get("busbw_fraction"))
    if busbw is not None and expected is None and fraction is not None and fraction > 0:
        expected = busbw / fraction
    return busbw, expected


def _cpu_saturated(bundle: EvidenceBundle) -> tuple[bool, Any, str]:
    sources: list[tuple[Mapping[str, Any], str]] = []
    if bundle.cpu_summary:
        sources.append((bundle.cpu_summary, str(bundle.cpu_summary_path or bundle.job_dir)))
    cpu_group = bundle.metrics_summary.get("cpu")
    if isinstance(cpu_group, Mapping):
        sources.append((cpu_group, _source(bundle, "metrics_summary")))
    for source, path in sources:
        for key in ("saturated_core_count", "saturated_cores"):
            value = _number(source.get(key))
            if value is not None and value >= 1:
                return True, value, path
        for key in ("core_saturated", "any_core_saturated", "cpu_core_saturated"):
            value = source.get(key)
            if value is True:
                return True, value, path
        for key in ("max_core_utilization", "max_cpu_percent", "cpu_utilization_p95"):
            value = _number(source.get(key))
            if value is not None and _fraction(value) >= 0.95:
                return True, value, path
    return False, None, str(bundle.cpu_summary_path or bundle.job_dir)


def _healthcheck_failed(healthcheck: Mapping[str, Any]) -> bool:
    if not healthcheck:
        return False
    status = str(healthcheck.get("status") or "").lower()
    if status and status not in {"healthy", "ok", "passed", "success", "external_validated"}:
        return True
    return healthcheck.get("ok") is False


def _validation_reports_launch_failure(report: Mapping[str, Any], job_id: str) -> bool:
    if not report:
        return False
    for job in report.get("jobs") or []:
        if not isinstance(job, Mapping):
            continue
        if str(job.get("job_id") or "") not in {"", job_id}:
            continue
        status_text = " ".join(
            str(job.get(key) or "").lower() for key in ("status", "failure_reason", "reason")
        )
        if "launch" in status_text and ("fail" in status_text or "timeout" in status_text):
            return True
        for downgrade in job.get("downgrades") or []:
            if not isinstance(downgrade, Mapping):
                continue
            text = " ".join(str(value).lower() for value in downgrade.values())
            if "launch" in text and ("fail" in text or "not_proven" in text):
                return True
    return False


def _engine(bundle: EvidenceBundle) -> str:
    for row in bundle.engine_rows:
        engine = row.get("engine")
        if engine:
            return str(engine)
    for source in (bundle.metrics_summary, bundle.operator_profile, bundle.launch_command):
        engine = source.get("engine") if isinstance(source, Mapping) else None
        if engine:
            return str(engine)
    return "unknown"


def _hardware_label(bundle: EvidenceBundle) -> str:
    labels = bundle.metrics_summary.get("labels")
    sources: list[Mapping[str, Any]] = [bundle.operator_profile]
    if isinstance(labels, Mapping):
        sources.append(labels)
    for source in sources:
        for key in ("hardware", "gpu_sku", "sku", "label_hardware"):
            value = source.get(key)
            if value:
                return str(value)
    return ""


def _launch_text(bundle: EvidenceBundle) -> str:
    parts: list[str] = []
    for key in ("engine", "model_path", "quantization", "kv_cache_dtype", "extra_args"):
        value = bundle.launch_command.get(key)
        if value is not None:
            parts.append(str(value))
    argv = bundle.launch_command.get("argv")
    if isinstance(argv, list):
        parts.extend(str(item) for item in argv)
    env = bundle.launch_command.get("env")
    if isinstance(env, Mapping):
        parts.extend(str(item) for pair in env.items() for item in pair)
    parts.append(str(bundle.operator_profile.get("quantization") or ""))
    parts.append(str(bundle.operator_profile.get("model_quantization") or ""))
    return " ".join(parts)


def _fraction(value: float) -> float:
    return value / 100.0 if value > 1.0 else value


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(value for value in values if math.isfinite(value))
    if len(ordered) == 1:
        return ordered[0]
    position = quantile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _int_or_none(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


__all__ = [
    "DEFAULT_THRESHOLDS",
    "REQUIRED_INPUT_KEYS",
    "RULES_TABLE",
    "EvidenceBundle",
    "apply_rules",
    "is_decode_bound",
    "is_host_bound",
    "is_kv_bound",
    "is_model_launch_bound",
    "is_network_bound",
    "is_prefill_bound",
    "is_queue_bound",
]
