"""Public entry point for PRD §4.7 ``report-completed``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inferguard.analyze.operator_brief import build_operator_brief
from inferguard.io import load_json_object
from inferguard.validate import validate_run

from . import sections
from .types import Claim, OperatorRecommendation, Refusal, Section


@dataclass(frozen=True)
class RecommendationOptions:
    """Optional report-completed inputs supplied by the operator."""

    cost_input: Path | None = None
    workload_fingerprint: Path | None = None
    slo: Path | None = None
    useful_task_definition: Path | None = None
    useful_task_min_tokens: int = 1
    useful_task_slo_ttft_ms: float | None = None
    slo_ttft_ms: float | None = None
    slo_e2e_ms: float | None = None
    slo_success_rate: float = 0.95


def build_recommendation(
    results_root: str | Path,
    opts: RecommendationOptions | None = None,
) -> OperatorRecommendation:
    """Read a completed run directory and return the canonical recommendation."""

    root = Path(results_root).resolve()
    options = opts or RecommendationOptions()
    context = _build_context(root, options)
    computed, claim_results, refusals = _compute_claims(context)
    context["computed"] = computed
    executive = sections.executive_verdict(context)
    computed.update(
        {
            "executive_verdict": executive["executive_verdict"],
            "executive_verdict_status": executive["executive_verdict_status"],
            "claim_status": executive["claim_status"],
        }
    )
    next_run = sections.recommended_next_run(context)
    evidence = sections.evidence_artifacts(context)
    claims: list[Claim] = [executive["claim"], *claim_results]
    context["computed"]["claims"] = claims
    measured_table = sections.measured_vs_inferred_vs_synthetic_table(context)
    ordered_sections: list[Section] = [
        executive["section"],
        measured_table,
        computed["best_gpu_sku_section"],
        computed["best_engine_section"],
        computed["best_model_config_section"],
        computed["bottleneck_section"],
        computed["capacity_envelope_section"],
        computed["failure_summary_section"],
        computed["cost_notes_section"],
        next_run["section"],
        evidence["section"],
    ]
    return OperatorRecommendation(
        executive_verdict=executive["executive_verdict"],
        executive_verdict_status=executive["executive_verdict_status"],
        claim_status=executive["claim_status"],
        best_gpu_sku=computed["best_gpu_sku"],
        best_engine=computed["best_engine"],
        best_model_config=computed["best_model_config"],
        bottleneck=computed["bottleneck"],
        capacity_envelope=computed["capacity_envelope"],
        failure_summary=computed["failure_summary"],
        cost_notes=computed["cost_notes"],
        lmcache_verdict=computed["lmcache_verdict"],
        gb200_justification=computed["gb200_justification"],
        recommended_next_run=next_run["value"],
        evidence_artifacts=evidence["value"],
        claim_table=claims,
        sections=ordered_sections,
        base_operator_brief=context.get("operator_brief", {}),
        refusals=refusals,
    )


def _compute_claims(
    context: dict[str, Any],
) -> tuple[dict[str, Any], list[Claim], list[Refusal]]:
    computed: dict[str, Any] = {}
    claims: list[Claim] = []
    refusals: list[Refusal] = []
    builders = (
        ("best_gpu_sku", sections.best_gpu_sku),
        ("best_engine", sections.best_engine),
        ("best_model_config", sections.best_model_config),
        ("bottleneck", sections.bottleneck),
        ("capacity_envelope", sections.capacity_envelope),
        ("failure_summary", sections.failure_summary),
        ("cost_notes", sections.cost_notes),
        ("lmcache_verdict", sections.lmcache_verdict),
        ("gb200_justification", sections.gb200_justification),
    )
    for key, builder in builders:
        result = builder(context)
        computed[key] = result["value"]
        if key not in {"lmcache_verdict", "gb200_justification"}:
            computed[f"{key}_section"] = result["section"]
        claims.append(result["claim"])
        refusal = result.get("refusal")
        if isinstance(refusal, Refusal):
            refusals.append(refusal)
    return computed, claims, refusals


def _build_context(root: Path, options: RecommendationOptions) -> dict[str, Any]:
    evidence: set[str] = set()
    paths: dict[str, str | list[str]] = {}
    plan_path = root / "matrix_plan.json"
    contract_path = root / "expected_artifact_contract.json"
    plan = _read_json(plan_path, root, evidence) if plan_path.exists() else {}
    contract = _read_json(contract_path, root, evidence) if contract_path.exists() else {}
    if plan_path.exists():
        paths["matrix_plan"] = _rel(plan_path, root)
    if contract_path.exists():
        paths["artifact_contract"] = _rel(contract_path, root)

    validation_path = _first_existing(
        root / "validation_report.json",
        root / "validate" / "validation_report.json",
        root / "validation" / "validation_report.json",
    )
    if validation_path:
        validation = _read_json(validation_path, root, evidence)
        paths["validation"] = _rel(validation_path, root)
    else:
        validation = validate_run(root, contract=contract_path, plan=plan_path).to_dict()

    cost_rates: dict[str, Any] = {}
    if options.cost_input:
        cost_path = Path(options.cost_input).resolve()
        cost_rates = _read_json(cost_path, root, evidence)
        paths["cost_input"] = _rel(cost_path, root)
    workload_fingerprint: dict[str, Any] = {}
    if options.workload_fingerprint:
        path = Path(options.workload_fingerprint).resolve()
        workload_fingerprint = _read_json(path, root, evidence)
        paths["workload_fingerprint"] = _rel(path, root)
    slo: dict[str, Any] = {}
    if options.slo:
        path = Path(options.slo).resolve()
        slo = _read_json(path, root, evidence)
        paths["slo"] = _rel(path, root)
    if options.useful_task_definition:
        path = Path(options.useful_task_definition).resolve()
        paths["useful_task_definition"] = _rel(path, root)
        evidence.add(_rel(path, root))

    capacity_path = _first_existing(
        root / "capacity_cliffs.json", root / "cliffs" / "capacity_cliffs.json"
    )
    capacity: dict[str, Any] = {}
    if capacity_path:
        capacity = _read_json(capacity_path, root, evidence)
        paths["capacity_cliffs"] = _rel(capacity_path, root)

    jobs = [_build_job(root, job, evidence) for job in _jobs(root, plan, contract)]
    jobs = [job for job in jobs if job]
    context = {
        "results_root": str(root),
        "validation": validation,
        "plan": plan,
        "contract": contract,
        "jobs": jobs,
        "capacity_cliffs": capacity,
        "cost_rates": cost_rates,
        "workload_fingerprint": workload_fingerprint,
        "slo": slo,
        "args": {
            "cost_input": str(options.cost_input) if options.cost_input else None,
            "useful_task_definition": str(options.useful_task_definition)
            if options.useful_task_definition
            else None,
            "useful_task_min_tokens": options.useful_task_min_tokens,
            "useful_task_slo_ttft_ms": options.useful_task_slo_ttft_ms,
            "slo_ttft_ms": options.slo_ttft_ms,
            "slo_e2e_ms": options.slo_e2e_ms,
            "slo_success_rate": options.slo_success_rate,
        },
        "paths": paths,
        "evidence_artifacts": sorted(evidence),
    }
    context["operator_brief"] = _operator_brief_extension(root, jobs)
    return context


def _jobs(root: Path, plan: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    raw = plan.get("jobs") if isinstance(plan.get("jobs"), list) else None
    if raw:
        return [job for job in raw if isinstance(job, dict)]
    raw = contract.get("per_job") if isinstance(contract.get("per_job"), list) else None
    if raw:
        return [job for job in raw if isinstance(job, dict)]
    jobs_dir = root / "jobs"
    if jobs_dir.exists():
        return [
            {"job_id": path.name, "output_dir": f"jobs/{path.name}"}
            for path in sorted(item for item in jobs_dir.iterdir() if item.is_dir())
        ]
    if (root / "request_profile").exists() or (root / "metrics").exists():
        return [{"job_id": root.name, "output_dir": "."}]
    return []


def _build_job(root: Path, spec: dict[str, Any], evidence: set[str]) -> dict[str, Any]:
    job_id = str(spec.get("job_id") or "unknown")
    output_dir = Path(str(spec.get("output_dir") or Path("jobs") / job_id))
    job_dir = output_dir if output_dir.is_absolute() else root / output_dir
    rel_dir = _rel(job_dir, root)
    profile_path = _first_existing(
        job_dir / "operator_profile.json", job_dir / "manifests" / "operator_profile.json"
    )
    request_path = _first_existing(
        job_dir / "request_profile" / "requests_summary.json",
        job_dir / "request_profile" / "request_summary.json",
    )
    metrics_path = _first_existing(
        job_dir / "metrics" / "metrics_summary.json",
        job_dir / "collect_metrics" / "metrics_summary.json",
    )
    diagnosis_path = _first_existing(
        job_dir / "diagnosis" / "bottleneck_diagnosis.json",
        job_dir / "diagnose_bottleneck" / "bottleneck_diagnosis.json",
    )
    failure_path = _first_existing(
        job_dir / "diagnosis" / "failure_classification.json",
        job_dir / "classify_failures" / "failure_classification.json",
    )
    health_path = _first_existing(
        job_dir / "launch" / "healthcheck.json",
        job_dir / "launch_engine" / "launch" / "healthcheck.json",
        job_dir / "launch_engine" / "healthcheck.json",
    )
    engine_timeline = _first_existing(
        job_dir / "metrics" / "engine_metrics_timeline.jsonl",
        job_dir / "collect_metrics" / "engine_metrics_timeline.jsonl",
    )
    gpu_timeline = _first_existing(
        job_dir / "metrics" / "gpu_metrics_timeline.jsonl",
        job_dir / "collect_metrics" / "gpu_metrics_timeline.jsonl",
    )
    request_profile = _first_existing(job_dir / "request_profile" / "requests_profile.jsonl")
    nccl_path = _first_existing(job_dir / "preflight" / "nccl_all_reduce.txt")
    topology_path = _first_existing(
        job_dir / "preflight" / "nvidia_smi_topo.txt",
        job_dir / "preflight" / "gpu_topology.txt",
        job_dir / "preflight" / "nvlink_status.txt",
    )
    rdma_path = _first_existing(job_dir / "preflight" / "ib_state.txt")

    profile = _read_json(profile_path, root, evidence) if profile_path else {}
    request = _read_json(request_path, root, evidence) if request_path else {}
    metrics = _read_json(metrics_path, root, evidence) if metrics_path else {}
    diagnosis = _read_json(diagnosis_path, root, evidence) if diagnosis_path else {}
    failure = _read_json(failure_path, root, evidence) if failure_path else {}
    healthcheck = _read_json(health_path, root, evidence) if health_path else {}

    paths = {
        "operator_profile": _maybe_rel(profile_path, root),
        "request_summary": _maybe_rel(request_path, root),
        "metrics_summary": _maybe_rel(metrics_path, root),
        "diagnosis": _maybe_rel(diagnosis_path, root),
        "failure": _maybe_rel(failure_path, root),
        "healthcheck": _maybe_rel(health_path, root),
        "engine_timeline": _maybe_track(engine_timeline, root, evidence),
        "gpu_timeline": _maybe_track(gpu_timeline, root, evidence),
        "request_profile": _maybe_track(request_profile, root, evidence),
        "nccl": _maybe_track(nccl_path, root, evidence),
        "topology": _maybe_track(topology_path, root, evidence),
        "rdma": _maybe_track(rdma_path, root, evidence),
    }
    paths = {key: value for key, value in paths.items() if value}
    nccl_text = _read_text(nccl_path, root, evidence) if nccl_path else ""
    topology_text = _read_text(topology_path, root, evidence) if topology_path else ""
    rdma_text = _read_text(rdma_path, root, evidence) if rdma_path else ""
    sku = _normalize_sku(
        spec.get("sku")
        or spec.get("hardware")
        or profile.get("sku")
        or profile.get("hardware")
        or profile.get("gpu_sku")
        or profile.get("hardware_sku")
    )
    engine = _normalize_engine(
        spec.get("engine")
        or profile.get("engine")
        or request.get("engine")
        or metrics.get("engine")
    )
    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "rel_dir": rel_dir,
        "spec": dict(spec),
        "operator_profile": profile,
        "request_summary": request,
        "metrics_summary": metrics,
        "diagnosis": diagnosis,
        "failure": failure,
        "healthcheck": healthcheck,
        "paths": paths,
        "sku": sku,
        "engine": engine,
        "model": profile.get("model") or profile.get("model_profile") or spec.get("model_profile"),
        "has_nccl_evidence": "busbw" in nccl_text.lower(),
        "has_topology_evidence": bool(topology_text.strip()),
        "has_rdma_evidence": "State: Active" in rdma_text,
    }


def _operator_brief_extension(root: Path, jobs: list[dict[str, Any]]) -> dict[str, Any]:
    cells = []
    for job in jobs:
        request = job.get("request_summary") or {}
        paths = job.get("paths") or {}
        cell = {
            "cell_id": job.get("job_id"),
            "config": {
                "engine": job.get("engine"),
                "sku": job.get("sku"),
                "concurrency": request.get("concurrency"),
            },
            "workload": {"workload_class": request.get("workload_label") or "default"},
            "completion": {"success_rate": request.get("success_rate")},
            "metrics": {
                "p99_ttft": _seconds(
                    _nested(request, "ttft_ms", "p99") or _nested(request, "ttft_ms", "p95")
                ),
                "p99_latency": _seconds(_nested(request, "e2e_latency_ms", "p99")),
            },
            "artifacts": {"metrics_timeline": paths.get("engine_timeline")},
        }
        cells.append(cell)
    brief = build_operator_brief(
        {
            "input_root": str(root),
            "cells": cells,
            "findings": [],
            "artifact_manifest": [
                {"path": path, "present": True}
                for path in sorted(
                    {path for job in jobs for path in (job.get("paths") or {}).values()}
                )
            ],
        }
    )
    return {
        "schema_version": brief.get("schema_version"),
        "summary": brief.get("summary"),
        "measured_vs_inferred": brief.get("measured_vs_inferred"),
        "recommended_engine_config": brief.get("recommended_engine_config"),
        "raw_artifact_paths": brief.get("raw_artifact_paths"),
    }


def _read_json(path: Path, root: Path, evidence: set[str]) -> dict[str, Any]:
    evidence.add(_rel(path, root))
    return load_json_object(path) or {}


def _read_text(path: Path, root: Path, evidence: set[str]) -> str:
    evidence.add(_rel(path, root))
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _maybe_track(path: Path | None, root: Path, evidence: set[str]) -> str | None:
    if path is None:
        return None
    evidence.add(_rel(path, root))
    return _rel(path, root)


def _maybe_rel(path: Path | None, root: Path) -> str | None:
    return _rel(path, root) if path else None


def _first_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _normalize_sku(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).upper().replace("-", "_").replace(" ", "_")
    for sku in ("GB300", "GB200", "B300", "B200", "H200", "H100"):
        if sku in text:
            return sku
    return None


def _normalize_engine(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).lower().replace("_", "-")
    if "sglang" in text:
        return "sglang"
    if "vllm" in text:
        return "vllm"
    if "lmcache" in text:
        return "lmcache"
    return text or None


def _rel(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def _nested(data: dict[str, Any], key: str, subkey: str) -> float | None:
    value = data.get(key)
    if isinstance(value, dict):
        raw = value.get(subkey)
        if isinstance(raw, int | float):
            return float(raw)
    return None


def _seconds(ms: float | None) -> float | None:
    return None if ms is None else ms / 1000.0


__all__ = ["RecommendationOptions", "build_recommendation"]
