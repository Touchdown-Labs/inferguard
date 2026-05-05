"""Section builders for the PRD §4.7 completed-run operator report."""

from __future__ import annotations

from collections import Counter
from math import inf
from typing import Any

from inferguard.cost_model import compute_cost, refusal_cost_report_fields

from .refusal import can_claim_lmcache_benefit, can_emit_cost, can_justify_gb200, can_recommend_sku
from .types import Claim, Refusal, Section

TOP_LEVEL_CLAIMS = (
    "executive_verdict",
    "best_gpu_sku",
    "best_engine",
    "best_model_config",
    "bottleneck",
    "capacity_envelope",
    "failure_summary",
    "cost_notes",
    "lmcache_verdict",
    "gb200_justification",
)
RACK_SCALE_SKUS = {"GB200", "GB300"}


def executive_verdict(context: dict[str, Any]) -> dict[str, Any]:
    status = _executive_status(context)
    if status == "synthetic_only":
        verdict = "harness validation only — no live evidence"
        claim_status = "synthetic"
    elif status == "live_complete":
        sku = context.get("computed", {}).get("best_gpu_sku", {}).get("value")
        engine = context.get("computed", {}).get("best_engine", {}).get("value")
        if sku and engine:
            verdict = f"recommend {sku} on {engine} for the measured workload"
            claim_status = "measured"
        elif sku:
            verdict = f"recommend {sku}; engine comparator not proven"
            claim_status = "measured"
        elif engine:
            verdict = f"recommend {engine}; SKU comparator not proven"
            claim_status = "measured"
        else:
            verdict = "live evidence complete; comparator evidence is insufficient for a SKU or engine verdict"
            claim_status = "measured"
    elif status == "live_incomplete":
        verdict = "live evidence incomplete — recommendations refused where evidence is missing"
        claim_status = "not_proven"
    else:
        verdict = "not_enough_evidence"
        claim_status = "not_proven"
    evidence = _validation_evidence(context)
    section = Section(
        title="Executive verdict",
        claim_status=claim_status,
        lines=[_claim_line(claim_status, verdict, evidence)],
    )
    claim = Claim("executive_verdict", verdict, claim_status, evidence)
    return {
        "executive_verdict": verdict,
        "executive_verdict_status": status,
        "claim_status": claim_status,
        "section": section,
        "claim": claim,
    }


def measured_vs_inferred_vs_synthetic_table(context: dict[str, Any]) -> Section:
    rows = context.get("computed", {}).get("claims", [])
    lines = [
        "| Claim | Label | Evidence |",
        "|---|---|---|",
    ]
    for claim in rows:
        evidence = (
            ", ".join(claim.evidence_paths) if claim.evidence_paths else "not_proven evidence gate"
        )
        lines.append(f"| {claim.claim_id} | [{claim.status}] | {evidence} |")
    return Section("Measured vs inferred vs synthetic", _aggregate_claim_status(rows), lines)


def best_gpu_sku(context: dict[str, Any]) -> dict[str, Any]:
    validation = context.get("validation", {})
    diagnosis = {"_jobs": context.get("jobs", [])}
    evidence = _job_profile_evidence(context) + _validation_evidence(context)
    if not can_recommend_sku(diagnosis, validation):
        status = "synthetic" if _executive_status(context) == "synthetic_only" else "not_proven"
        reason = "not_proven — see " + _evidence_ref(
            evidence or _expected_job_paths(context, "operator_profile.json")
        )
        value = None
        return _claim_result(
            "best_gpu_sku",
            {"value": value, "claim_status": status, "reason": reason},
            status,
            "Best GPU SKU",
            f"No SKU verdict: {reason}",
            evidence,
            refusal=Refusal(
                "best_gpu_sku", "missing_live_complete_or_multi_sku_comparator", evidence
            ),
        )

    winner = _best_job(context, group_key="sku")
    if winner is None:
        reason = "not_proven — see " + _evidence_ref(evidence)
        return _claim_result(
            "best_gpu_sku",
            {"value": None, "claim_status": "not_proven", "reason": reason},
            "not_proven",
            "Best GPU SKU",
            f"No SKU verdict: {reason}",
            evidence,
            refusal=Refusal("best_gpu_sku", "no_scored_sku_run", evidence),
        )
    sku = winner.get("sku")
    if sku in RACK_SCALE_SKUS and not can_justify_gb200(
        diagnosis, validation, {"_jobs": context.get("jobs", [])}
    ):
        rack_evidence = _rack_evidence(context)
        reason = "not_proven — see " + _evidence_ref(rack_evidence)
        return _claim_result(
            "best_gpu_sku",
            {"value": None, "claim_status": "not_proven", "reason": reason},
            "not_proven",
            "Best GPU SKU",
            f"No GB200/GB300 SKU verdict: {reason}",
            rack_evidence,
            refusal=Refusal("best_gpu_sku", "rack_scale_topology_nccl_rdma_missing", rack_evidence),
        )
    claim_text = f"{sku} has the strongest measured score among comparable SKUs."
    return _claim_result(
        "best_gpu_sku",
        {"value": sku, "claim_status": "measured", "reason": claim_text},
        "measured",
        "Best GPU SKU",
        claim_text,
        _job_evidence(winner),
    )


def best_engine(context: dict[str, Any]) -> dict[str, Any]:
    evidence = _job_metrics_evidence(context) + _validation_evidence(context)
    status = _executive_status(context)
    engines = {job.get("engine") for job in context.get("jobs", []) if job.get("engine")}
    if status != "live_complete" or len(engines) < 2 or _engine_metrics_not_proven(context):
        label = "synthetic" if status == "synthetic_only" else "not_proven"
        reason = "not_proven — see " + _evidence_ref(
            evidence or _expected_job_paths(context, "metrics/metrics_summary.json")
        )
        return _claim_result(
            "best_engine",
            {"value": None, "claim_status": label, "reason": reason},
            label,
            "Best engine",
            f"No engine verdict: {reason}",
            evidence,
            refusal=Refusal("best_engine", "missing_live_multi_engine_measured_metrics", evidence),
        )
    winner = _best_job(context, group_key="engine")
    if winner is None:
        reason = "not_proven — see " + _evidence_ref(evidence)
        return _claim_result(
            "best_engine",
            {"value": None, "claim_status": "not_proven", "reason": reason},
            "not_proven",
            "Best engine",
            f"No engine verdict: {reason}",
            evidence,
            refusal=Refusal("best_engine", "no_scored_engine_run", evidence),
        )
    engine = winner.get("engine")
    claim_text = f"{engine} has the strongest measured score among comparable engines."
    return _claim_result(
        "best_engine",
        {"value": engine, "claim_status": "measured", "reason": claim_text},
        "measured",
        "Best engine",
        claim_text,
        _job_evidence(winner),
    )


def best_model_config(context: dict[str, Any]) -> dict[str, Any]:
    status = _executive_status(context)
    winner = _best_job(context)
    evidence = _job_profile_evidence(context) + _job_diagnosis_evidence(context)
    verdict = _bottleneck_verdict(winner) if winner else "not_enough_evidence"
    if status == "synthetic_only":
        label = "synthetic"
    elif verdict == "not_enough_evidence" or winner is None:
        label = "not_proven"
    else:
        label = "inferred"
    if label == "not_proven":
        reason = "not_proven — see " + _evidence_ref(evidence)
        value = None
        text = f"No model-config verdict: {reason}"
        refusal = Refusal("best_model_config", "bottleneck_not_enough_evidence", evidence)
    elif label == "synthetic":
        reason = "synthetic — live model-config evidence is absent"
        value = None
        text = reason
        refusal = None
    else:
        value = _model_config(winner)
        reason = f"Config is inferred from the measured {verdict} bottleneck and launch/profile artifacts."
        text = reason
        refusal = None
    return _claim_result(
        "best_model_config",
        {"value": value, "claim_status": label, "reason": reason},
        label,
        "Best model config",
        text,
        _job_evidence(winner) if winner else evidence,
        refusal=refusal,
    )


def bottleneck(context: dict[str, Any]) -> dict[str, Any]:
    status = _executive_status(context)
    winner = _best_job(context)
    evidence = _job_diagnosis_evidence(context) + _job_metrics_evidence(context)
    verdict = _bottleneck_verdict(winner) if winner else "not_enough_evidence"
    if status == "synthetic_only":
        label = "synthetic"
        text = "Bottleneck verdict is synthetic because no live metrics are present."
    elif verdict == "not_enough_evidence":
        label = "not_proven"
        text = "No bottleneck verdict: not_proven — see " + _evidence_ref(evidence)
    else:
        label = _claim_status_from_payload(
            winner.get("diagnosis") if winner else {}, default="measured"
        )
        text = f"Bottleneck verdict: {verdict}."
    return _claim_result(
        "bottleneck",
        {"verdict": verdict, "claim_status": label},
        label,
        "Bottleneck",
        text,
        _job_evidence(winner) if winner else evidence,
        refusal=None
        if label != "not_proven"
        else Refusal("bottleneck", "diagnosis_missing", evidence),
    )


def capacity_envelope(context: dict[str, Any]) -> dict[str, Any]:
    capacity = context.get("capacity_cliffs") or {}
    evidence = _paths(context, "capacity_cliffs")
    if not capacity:
        reason = "not_proven — see " + _evidence_ref(evidence or ["capacity_cliffs.json"])
        return _claim_result(
            "capacity_envelope",
            {
                "max_concurrency": None,
                "max_context": None,
                "claim_status": "not_proven",
                "reason": reason,
            },
            "not_proven",
            "Capacity envelope",
            f"No capacity envelope: {reason}",
            evidence,
            refusal=Refusal(
                "capacity_envelope", "capacity_cliffs_missing", evidence or ["capacity_cliffs.json"]
            ),
        )
    summary = capacity.get("summary") if isinstance(capacity.get("summary"), dict) else capacity
    value = {
        "max_concurrency": _int_or_none(summary.get("max_concurrency")),
        "max_context": _int_or_none(summary.get("max_context")),
        "claim_status": _claim_status_from_payload(summary, default="measured"),
    }
    text = (
        f"Capacity envelope: concurrency={value['max_concurrency']} context={value['max_context']}."
    )
    return _claim_result(
        "capacity_envelope", value, value["claim_status"], "Capacity envelope", text, evidence
    )


def failure_summary(context: dict[str, Any]) -> dict[str, Any]:
    status = _executive_status(context)
    evidence = _job_failure_evidence(context)
    failures = [_failure_class(job) for job in context.get("jobs", []) if _failure_class(job)]
    top_class = _top_non_empty(failures) or "not_enough_evidence"
    if status == "synthetic_only":
        label = "synthetic"
        text = "Failure summary is synthetic because no live failure artifacts are present."
    elif top_class == "not_enough_evidence":
        label = "not_proven"
        text = "No failure summary: not_proven — see " + _evidence_ref(evidence)
    else:
        label = _failure_claim_status(context)
        text = f"Top failure class: {top_class}."
    return _claim_result(
        "failure_summary",
        {"top_class": top_class, "claim_status": label},
        label,
        "Failure summary",
        text,
        evidence,
        refusal=None
        if label != "not_proven"
        else Refusal("failure_summary", "failure_classification_missing", evidence),
    )


def cost_notes(context: dict[str, Any]) -> dict[str, Any]:
    evidence = _paths(context, "cost_input") + _job_request_evidence(context)
    if not can_emit_cost(context.get("args")):
        reason = "not_proven — cost input not supplied"
        value = refusal_cost_report_fields(reason)
        return _claim_result(
            "cost_notes",
            value,
            "not_proven",
            "Cost notes",
            f"No cost claim: {reason}",
            evidence,
            refusal=Refusal("cost_notes", "cost_input_missing", evidence or ["--cost-input"]),
        )
    args = context.get("args") or {}
    try:
        report = compute_cost(
            context["results_root"],
            args["cost_input"],
            context.get("slo") or None,
            useful_task_definition=args.get("useful_task_definition"),
            useful_task_min_tokens=int(args.get("useful_task_min_tokens") or 1),
            useful_task_slo_ttft_ms=_number(args.get("useful_task_slo_ttft_ms")),
            slo_ttft_ms=_number(args.get("slo_ttft_ms")),
            slo_e2e_ms=_number(args.get("slo_e2e_ms")),
            slo_success_rate=_number(args.get("slo_success_rate")) or 0.95,
        )
    except (OSError, ValueError, KeyError) as exc:
        reason = "not_proven — see " + _evidence_ref(evidence)
        value = refusal_cost_report_fields(reason)
        value["error"] = str(exc)
        return _claim_result(
            "cost_notes",
            value,
            "not_proven",
            "Cost notes",
            f"No cost claim: {reason}",
            evidence,
            refusal=Refusal("cost_notes", "cost_inputs_or_token_totals_insufficient", evidence),
        )
    value = report.to_dict()
    if value["claim_status"] == "measured":
        text = (
            "Cost report measured from explicit cost input: "
            f"completion=${_money(value.get('cost_per_million_completion_tokens_usd'))}/M generated tokens; "
            f"useful_task=${_money(value.get('cost_per_useful_task_usd'))}; "
            f"safe_concurrency={_display(value.get('safe_concurrency_envelope', {}).get('safe_concurrency'))}."
        )
    else:
        text = (
            "Cost report could not prove useful-task economics: "
            f"completion=${_money(value.get('cost_per_million_completion_tokens_usd'))}/M generated tokens; "
            f"useful_task={_display(value.get('cost_per_useful_task_usd'))}; "
            f"safe_concurrency={_display(value.get('safe_concurrency_envelope', {}).get('safe_concurrency'))}."
        )
    return _claim_result(
        "cost_notes",
        value,
        value["claim_status"],
        "Cost notes",
        text,
        evidence,
    )


def recommended_next_run(context: dict[str, Any]) -> dict[str, Any]:
    computed = context.get("computed", {})
    status = _executive_status(context)
    label = "measured" if status == "live_complete" else "not_proven"
    if status == "synthetic_only":
        label = "synthetic"
        text = "Run live request-profile plus collect-metrics on the target GMI partition."
    elif computed.get("best_gpu_sku", {}).get("claim_status") == "not_proven":
        text = "Run a two-SKU live comparator with identical workload, model, and engine settings."
    elif computed.get("best_engine", {}).get("claim_status") == "not_proven":
        text = "Run a live vLLM versus SGLang comparator on the selected SKU."
    elif computed.get("capacity_envelope", {}).get("claim_status") == "not_proven":
        text = (
            "Run find-cliffs to establish max concurrency and max context before operator sign-off."
        )
    elif computed.get("cost_notes", {}).get("claim_status") == "not_proven":
        text = "Re-run report-completed with --cost-input after rates are approved."
    else:
        text = (
            "Repeat the winning SKU and engine once to confirm stability before customer handoff."
        )
    section = Section(
        "Recommended next run", label, [_claim_line(label, text, _validation_evidence(context))]
    )
    return {"value": text, "section": section}


def evidence_artifacts(context: dict[str, Any]) -> dict[str, Any]:
    paths = sorted(set(context.get("evidence_artifacts", [])))
    lines = [_claim_line("measured", path, [path]) for path in paths] or [
        _claim_line("not_proven", "No input artifacts were readable.", [])
    ]
    return {
        "value": paths,
        "section": Section("Evidence artifacts", "measured" if paths else "not_proven", lines),
    }


def lmcache_verdict(context: dict[str, Any]) -> dict[str, Any]:
    metrics = {"_summaries": [job.get("metrics_summary", {}) for job in context.get("jobs", [])]}
    evidence = _job_metrics_evidence(context)
    if not can_claim_lmcache_benefit(metrics):
        reason = "not_proven — see " + _evidence_ref(
            evidence or _expected_job_paths(context, "metrics/metrics_summary.json")
        )
        return _claim_result(
            "lmcache_verdict",
            {"value": None, "claim_status": "not_proven", "reason": reason},
            "not_proven",
            "LMCache verdict",
            f"No LMCache verdict: {reason}",
            evidence,
            refusal=Refusal("lmcache_verdict", "live_lmcache_metrics_missing", evidence),
        )
    hit_rates = [
        _lmcache_hit_rate(job.get("metrics_summary", {})) for job in context.get("jobs", [])
    ]
    hit_rates = [value for value in hit_rates if value is not None]
    verdict = "helpful" if hit_rates and max(hit_rates) >= 0.05 else "harmful"
    text = f"LMCache verdict: {verdict} from live lmcache:* metrics."
    return _claim_result(
        "lmcache_verdict",
        {"value": verdict, "claim_status": "measured"},
        "measured",
        "LMCache verdict",
        text,
        evidence,
    )


def gb200_justification(context: dict[str, Any]) -> dict[str, Any]:
    validation = context.get("validation", {})
    diagnosis = {"_jobs": context.get("jobs", [])}
    metrics = {"_jobs": context.get("jobs", [])}
    evidence = _rack_evidence(context)
    if not can_justify_gb200(diagnosis, validation, metrics):
        reason = "not_proven — see " + _evidence_ref(evidence or _expected_rack_paths(context))
        return _claim_result(
            "gb200_justification",
            {"value": "not_proven", "claim_status": "not_proven", "reason": reason},
            "not_proven",
            "GB200 justification",
            f"No GB200/GB300 justification: {reason}",
            evidence,
            refusal=Refusal("gb200_justification", "gb200_topology_nccl_rdma_missing", evidence),
        )
    text = "GB200/GB300 rack-scale evidence includes topology, NCCL bus bandwidth, and RDMA active state."
    return _claim_result(
        "gb200_justification",
        {"value": "yes", "claim_status": "measured"},
        "measured",
        "GB200 justification",
        text,
        evidence,
    )


def _claim_result(
    claim_id: str,
    value: dict[str, Any],
    label: str,
    title: str,
    text: str,
    evidence: list[str],
    *,
    refusal: Refusal | None = None,
) -> dict[str, Any]:
    section = Section(title, label, [_claim_line(label, text, evidence)])
    claim = Claim(claim_id, text, label, evidence)
    return {"value": value, "section": section, "claim": claim, "refusal": refusal}


def _executive_status(context: dict[str, Any]) -> str:
    validation = context.get("validation") or {}
    status = str(validation.get("status") or "not_enough_evidence")
    if status == "live_complete":
        return "live_complete"
    if status == "synthetic_only":
        return "synthetic_only"
    if status in {"live_incomplete", "not_publishable"}:
        return "live_incomplete" if status == "live_incomplete" else "not_enough_evidence"
    return "not_enough_evidence"


def _claim_line(label: str, text: str, evidence: list[str]) -> str:
    if label == "not_proven" and evidence:
        return f"[{label}] {text}"
    if evidence:
        return f"[{label}] {text} Evidence: {', '.join(evidence)}"
    return f"[{label}] {text}"


def _evidence_ref(evidence: list[str]) -> str:
    return ", ".join(sorted(set(evidence))) if evidence else "required upstream artifacts"


def _validation_evidence(context: dict[str, Any]) -> list[str]:
    return (
        _paths(context, "validation")
        + _paths(context, "matrix_plan")
        + _paths(context, "artifact_contract")
    )


def _job_evidence(job: dict[str, Any] | None) -> list[str]:
    if not job:
        return []
    evidence = []
    for key in (
        "request_summary",
        "metrics_summary",
        "diagnosis",
        "failure",
        "operator_profile",
        "healthcheck",
    ):
        path = job.get("paths", {}).get(key)
        if path:
            evidence.append(path)
    return sorted(set(evidence))


def _job_profile_evidence(context: dict[str, Any]) -> list[str]:
    return _job_paths(context, "operator_profile")


def _job_metrics_evidence(context: dict[str, Any]) -> list[str]:
    return (
        _job_paths(context, "metrics_summary")
        + _job_paths(context, "engine_timeline")
        + _job_paths(context, "gpu_timeline")
    )


def _job_request_evidence(context: dict[str, Any]) -> list[str]:
    return _job_paths(context, "request_summary") + _job_paths(context, "request_profile")


def _job_diagnosis_evidence(context: dict[str, Any]) -> list[str]:
    return _job_paths(context, "diagnosis")


def _job_failure_evidence(context: dict[str, Any]) -> list[str]:
    return _job_paths(context, "failure")


def _rack_evidence(context: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    for job in context.get("jobs", []):
        if job.get("sku") not in RACK_SCALE_SKUS:
            continue
        for key in ("nccl", "topology", "rdma", "gpu_timeline", "metrics_summary"):
            path = job.get("paths", {}).get(key)
            if path:
                evidence.append(path)
    return sorted(set(evidence))


def _job_paths(context: dict[str, Any], key: str) -> list[str]:
    paths = []
    for job in context.get("jobs", []):
        path = job.get("paths", {}).get(key)
        if path:
            paths.append(path)
    return sorted(set(paths))


def _paths(context: dict[str, Any], key: str) -> list[str]:
    path = context.get("paths", {}).get(key)
    if isinstance(path, str):
        return [path]
    if isinstance(path, list):
        return [str(item) for item in path]
    return []


def _expected_job_paths(context: dict[str, Any], suffix: str) -> list[str]:
    jobs = context.get("jobs", [])
    if not jobs:
        return [f"jobs/*/{suffix}"]
    return [f"{job.get('rel_dir', 'jobs/*')}/{suffix}" for job in jobs]


def _expected_rack_paths(context: dict[str, Any]) -> list[str]:
    jobs = [job for job in context.get("jobs", []) if job.get("sku") in RACK_SCALE_SKUS]
    if not jobs:
        return [
            "jobs/*/preflight/nccl_all_reduce.txt",
            "jobs/*/preflight/nvidia_smi_topo.txt",
            "jobs/*/preflight/ib_state.txt",
        ]
    return [
        path
        for job in jobs
        for path in (
            f"{job.get('rel_dir')}/preflight/nccl_all_reduce.txt",
            f"{job.get('rel_dir')}/preflight/nvidia_smi_topo.txt",
            f"{job.get('rel_dir')}/preflight/ib_state.txt",
        )
    ]


def _best_job(context: dict[str, Any], group_key: str | None = None) -> dict[str, Any] | None:
    candidates = [job for job in context.get("jobs", []) if _has_score_evidence(job)]
    if group_key:
        candidates = [job for job in candidates if job.get(group_key)]
    if not candidates:
        return None
    return min(candidates, key=_job_score)


def _job_score(job: dict[str, Any]) -> tuple[float, float, float, float, str]:
    request = job.get("request_summary") or {}
    success_rate = _success_rate(request)
    e2e = _nested_number(request, "e2e_latency_ms", "p99")
    ttft = _nested_number(request, "ttft_ms", "p95")
    tpot = _nested_number(request, "tpot_ms", "p95")
    tps = _number(request.get("tokens_per_sec_aggregate"))
    if tps is None:
        tps = _nested_number(request, "decode_tokens_per_sec", "p50")
    latency = e2e if e2e is not None else ttft if ttft is not None else inf
    token_latency = tpot if tpot is not None else inf
    throughput = -tps if tps is not None else 0.0
    return (-success_rate, latency, token_latency, throughput, str(job.get("job_id") or ""))


def _has_score_evidence(job: dict[str, Any]) -> bool:
    request = job.get("request_summary") or {}
    return bool(request) and (
        _nested_number(request, "e2e_latency_ms", "p99") is not None
        or _nested_number(request, "ttft_ms", "p95") is not None
        or _number(request.get("tokens_per_sec_aggregate")) is not None
        or _number(request.get("success_rate")) is not None
    )


def _success_rate(request: dict[str, Any]) -> float:
    value = _number(request.get("success_rate"))
    if value is not None:
        return value
    successes = _number(request.get("success_count"))
    count = _number(request.get("request_count"))
    if successes is not None and count and count > 0:
        return successes / count
    return 0.0


def _engine_metrics_not_proven(context: dict[str, Any]) -> bool:
    for job in context.get("jobs", []):
        summary = job.get("metrics_summary") or {}
        if _metrics_summary_claim_status(summary) == "not_proven":
            return True
    return False


def _metrics_summary_claim_status(summary: dict[str, Any]) -> str:
    direct = summary.get("claim_status")
    if isinstance(direct, str):
        return direct
    statuses = []
    for value in summary.values():
        if isinstance(value, dict) and isinstance(value.get("claim_status"), str):
            statuses.append(value["claim_status"])
    if statuses and all(status == "not_proven" for status in statuses):
        return "not_proven"
    if "measured" in statuses:
        return "measured"
    return "measured" if summary else "not_proven"


def _model_config(job: dict[str, Any]) -> dict[str, Any]:
    profile = job.get("operator_profile") or {}
    request = job.get("request_summary") or {}
    config = profile.get("model_config") if isinstance(profile.get("model_config"), dict) else {}
    return {
        "sku": job.get("sku"),
        "engine": job.get("engine"),
        "model": profile.get("model")
        or profile.get("model_path")
        or request.get("model")
        or job.get("model"),
        "model_profile": profile.get("model_profile") or request.get("model_profile"),
        "quantization": profile.get("quantization") or config.get("quantization"),
        "kv_cache_dtype": profile.get("kv_cache_dtype") or config.get("kv_cache_dtype"),
        "tensor_parallel_size": _int_or_none(
            profile.get("tensor_parallel_size") or profile.get("tp")
        ),
        "max_model_len": _int_or_none(profile.get("max_model_len") or config.get("max_model_len")),
        "concurrency": _int_or_none(request.get("concurrency") or profile.get("concurrency")),
        "context_length": _int_or_none(
            request.get("context_length") or profile.get("context_length")
        ),
    }


def _bottleneck_verdict(job: dict[str, Any] | None) -> str:
    if not job:
        return "not_enough_evidence"
    diagnosis = job.get("diagnosis") or {}
    verdict = (
        diagnosis.get("verdict") or diagnosis.get("bottleneck") or diagnosis.get("top_bottleneck")
    )
    return str(verdict or "not_enough_evidence")


def _failure_class(job: dict[str, Any]) -> str | None:
    failure = job.get("failure") or {}
    value = failure.get("top_class") or failure.get("failure_class") or failure.get("class")
    if value is None and isinstance(failure.get("failures"), list) and failure["failures"]:
        first = failure["failures"][0]
        if isinstance(first, dict):
            value = first.get("class")
    return str(value) if value else None


def _failure_claim_status(context: dict[str, Any]) -> str:
    statuses = []
    for job in context.get("jobs", []):
        status = _claim_status_from_payload(job.get("failure") or {}, default="measured")
        statuses.append(status)
    if "measured" in statuses:
        return "measured"
    if statuses:
        return statuses[0]
    return "not_proven"


def _top_non_empty(values: list[str]) -> str | None:
    cleaned = [value for value in values if value and value != "not_enough_evidence"]
    if not cleaned:
        return None
    return Counter(cleaned).most_common(1)[0][0]


def _compute_cost_per_million_completion_tokens(context: dict[str, Any]) -> float | None:
    rates = context.get("cost_rates") or {}
    total_cost = 0.0
    total_completion_tokens = 0.0
    for job in context.get("jobs", []):
        sku = job.get("sku")
        rate = _number(rates.get(str(sku))) if sku else None
        if rate is None:
            continue
        request = job.get("request_summary") or {}
        completion_tokens = _number(request.get("completion_tokens_total"))
        if not completion_tokens or completion_tokens <= 0:
            continue
        duration = _duration_seconds(job)
        if duration is None or duration <= 0:
            continue
        gpus = _gpu_count(job)
        total_cost += rate * gpus * (duration / 3600.0)
        total_completion_tokens += completion_tokens
    if total_cost <= 0 or total_completion_tokens <= 0:
        return None
    return total_cost / (total_completion_tokens / 1_000_000.0)


def _duration_seconds(job: dict[str, Any]) -> float | None:
    request = job.get("request_summary") or {}
    metrics = job.get("metrics_summary") or {}
    health = job.get("healthcheck") or {}
    for raw in (
        request.get("duration_seconds"),
        metrics.get("duration_seconds"),
        health.get("ready_after_seconds"),
    ):
        value = _number(raw)
        if value is not None and value > 0:
            return value
    return None


def _gpu_count(job: dict[str, Any]) -> float:
    profile = job.get("operator_profile") or {}
    for key in ("gpu_count", "gpus", "tensor_parallel_size", "tp"):
        value = _number(profile.get(key))
        if value is not None and value > 0:
            return value
    return 1.0


def _lmcache_hit_rate(summary: dict[str, Any]) -> float | None:
    group = summary.get("lmcache") if isinstance(summary.get("lmcache"), dict) else {}
    for key in ("retrieve_hit_rate", "lookup_hit_rate"):
        value = _number(group.get(key))
        if value is not None:
            return value
    metrics = group.get("metrics")
    if isinstance(metrics, dict):
        for key in ("lmcache:retrieve_hit_rate", "lmcache:lookup_hit_rate"):
            value = _number(metrics.get(key))
            if value is not None:
                return value
    return None


def _claim_status_from_payload(payload: dict[str, Any], *, default: str) -> str:
    status = payload.get("claim_status") if isinstance(payload, dict) else None
    return str(status) if status in {"measured", "inferred", "synthetic", "not_proven"} else default


def _aggregate_claim_status(claims: list[Claim]) -> str:
    statuses = {claim.status for claim in claims}
    if "not_proven" in statuses:
        return "not_proven"
    if "synthetic" in statuses:
        return "synthetic"
    if "inferred" in statuses:
        return "inferred"
    return "measured" if statuses else "not_proven"


def _nested_number(data: dict[str, Any], key: str, subkey: str) -> float | None:
    value = data.get(key)
    if isinstance(value, dict):
        return _number(value.get(subkey))
    return None


def _int_or_none(raw: Any) -> int | None:
    value = _number(raw)
    if value is None:
        return None
    return int(value)


def _number(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _money(raw: Any) -> str:
    value = _number(raw)
    return "null" if value is None else f"{value:.4f}"


def _display(raw: Any) -> str:
    return "null" if raw is None else str(raw)
