"""Public entry point for PRD §4.11 cost and capacity reports."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from inferguard.io import load_json_object

from .envelope import derive_safe_concurrency_envelope
from .types import (
    COST_REPORT_SCHEMA_VERSION,
    CostInput,
    CostReport,
    SafeConcurrencyEnvelope,
    UsefulTaskMetric,
)
from .useful_task import compute_useful_task_metric, load_useful_task_definition

_COST_INPUT_MISSING_REASON = "not_proven — cost input not supplied"
_LIVE_COMPLETE_REQUIRED_REASON = (
    "validation_report.status is not live_complete; cost math is inferred until "
    "validate-completed proves live request, healthcheck, engine, and GPU evidence"
)


def compute_cost(
    results_root: str | Path,
    cost_input: str | Path | dict[str, Any] | CostInput,
    slo: str | Path | dict[str, Any] | None = None,
    *,
    useful_task_definition: str | Path | None = None,
    useful_task_min_tokens: int = 1,
    useful_task_slo_ttft_ms: float | None = None,
    slo_ttft_ms: float | None = None,
    slo_e2e_ms: float | None = None,
    slo_success_rate: float = 0.95,
) -> CostReport:
    """Compute cost-per-useful-task and safe concurrency for a completed run root."""

    root = Path(results_root).resolve()
    validation_status = _validation_status(root)
    validation_reason = (
        None
        if validation_status == "live_complete"
        else f"{_LIVE_COMPLETE_REQUIRED_REASON} (status={validation_status})"
    )
    try:
        cost = _coerce_cost_input(cost_input)
        slo_data = _load_slo(slo)
        envelope_ttft_ms = _first_number(
            slo_ttft_ms, _slo_value(slo_data, "slo_ttft_ms", "ttft_ms_p99")
        )
        envelope_e2e_ms = _first_number(
            slo_e2e_ms, _slo_value(slo_data, "slo_e2e_ms", "e2e_latency_ms_p99")
        )
        useful_ttft_ms = _first_number(useful_task_slo_ttft_ms, envelope_ttft_ms)
        useful_definition = load_useful_task_definition(
            useful_task_definition,
            min_completion_tokens=useful_task_min_tokens,
            slo_ttft_ms=useful_ttft_ms,
            slo_e2e_ms=envelope_e2e_ms,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return _downgraded_cost_report(
            f"not_proven — invalid cost/SLO/useful-task JSON: {type(exc).__name__}: {exc}",
            source_path=_source_path(cost_input),
            slo_success_rate=slo_success_rate,
        )

    totals = _empty_totals()
    per_job: list[dict[str, Any]] = []
    skipped_jobs: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    envelope_levels: list[dict[str, Any]] = []

    for spec in _discover_jobs(root):
        job = _load_job(root, spec)
        rows = job["request_rows"]
        all_rows.extend(rows)
        envelope_levels.extend(_job_envelope_levels(job))
        rate = cost.rates_usd_per_gpu_hour.get(str(job["sku"] or "").upper())
        if rate is None:
            skipped_jobs.append(
                {
                    "job_id": job["job_id"],
                    "sku": job["sku"],
                    "reason": "rate missing from cost input",
                    "claim_status": "not_proven",
                }
            )
            continue
        job_cost = _job_cost(job, rate)
        if job_cost["claim_status"] != "measured":
            skipped_jobs.append(
                {
                    "job_id": job["job_id"],
                    "sku": job["sku"],
                    "reason": job_cost["reason"],
                    "claim_status": "not_proven",
                }
            )
            continue
        _accumulate_totals(totals, job, job_cost)
        per_job.append(_job_report(job, job_cost, rate, cost.source_path))

    useful_metric = compute_useful_task_metric(all_rows, useful_definition)
    envelope = derive_safe_concurrency_envelope(
        envelope_levels,
        slo_ttft_ms=envelope_ttft_ms,
        slo_e2e_ms=envelope_e2e_ms,
        slo_success_rate=slo_success_rate,
    )
    cost_per_prompt = _cost_per_million(totals["total_cost_usd"], totals["prompt_tokens_total"])
    cost_per_completion = _cost_per_million(
        totals["total_cost_usd"], totals["completion_tokens_total"]
    )
    cost_per_useful = _safe_div(totals["total_cost_usd"], useful_metric.useful_task_count)
    failed_waste_percent = _safe_div(totals["failed_gpu_seconds"], totals["gpu_seconds_total"])
    if failed_waste_percent is not None:
        failed_waste_percent *= 100.0
    failed_waste_dollars = totals["failed_request_waste_dollars"] or None
    throughput = _safe_div(useful_metric.useful_task_count, totals["total_gpu_hours"])
    field_status = _field_statuses(
        cost_per_prompt=cost_per_prompt,
        cost_per_completion=cost_per_completion,
        cost_per_useful=cost_per_useful,
        failed_waste_percent=failed_waste_percent,
        throughput=throughput,
        envelope_status=envelope.claim_status,
    )
    claim_status = (
        "measured"
        if cost_per_completion is not None and cost_per_useful is not None
        else "not_proven"
    )
    if validation_reason and claim_status == "measured":
        claim_status = "inferred"
        field_status = _downgrade_measured_statuses(field_status)
        per_job = [_downgrade_measured_job(job, validation_reason) for job in per_job]
        useful_metric = _downgrade_useful_task(useful_metric, validation_reason)
        envelope = _downgrade_envelope(envelope, validation_reason)
    return CostReport(
        currency=cost.currency,
        cost_input=cost,
        total_gpu_hours=totals["total_gpu_hours"],
        total_cost_usd=totals["total_cost_usd"],
        prompt_tokens_total=int(totals["prompt_tokens_total"]),
        completion_tokens_total=int(totals["completion_tokens_total"]),
        request_count=int(totals["request_count"]),
        success_count=int(totals["success_count"]),
        failed_request_count=int(totals["failed_request_count"]),
        cost_per_million_prompt_tokens_usd=cost_per_prompt,
        cost_per_million_completion_tokens_usd=cost_per_completion,
        cost_per_useful_task_usd=cost_per_useful,
        failed_request_waste_percent=failed_waste_percent,
        failed_request_waste_dollars=failed_waste_dollars,
        gpu_hour_normalized_throughput=throughput,
        useful_task=useful_metric,
        safe_concurrency_envelope=envelope,
        per_job=per_job,
        skipped_jobs=skipped_jobs,
        claim_status=claim_status,
        claim_status_by_field=field_status,
        claim_reason=validation_reason if claim_status == "inferred" else None,
    )


def refusal_cost_report_fields(reason: str = _COST_INPUT_MISSING_REASON) -> dict[str, Any]:
    """Return canonical null cost fields for report-completed refusal paths."""

    fields = {
        "cost_per_million_prompt_tokens_usd": None,
        "cost_per_million_completion_tokens_usd": None,
        "cost_per_million_generated_tokens_usd": None,
        "cost_per_million_prompt_tokens": None,
        "cost_per_million_generated_tokens": None,
        "cost_per_useful_task_usd": None,
        "cost_per_useful_task": None,
        "failed_request_waste_percent": None,
        "failed_request_waste_dollars": None,
        "gpu_hour_normalized_throughput": None,
        "safe_concurrency_envelope": {
            "safe_concurrency": None,
            "claim_status": "not_proven",
            "reason": reason,
        },
    }
    return {
        **fields,
        "schema_version": COST_REPORT_SCHEMA_VERSION,
        "claim_status": "not_proven",
        "reason": reason,
        "claim_status_by_field": {key: reason for key in fields},
    }


def _downgraded_cost_report(
    reason: str,
    *,
    source_path: str,
    slo_success_rate: float,
) -> CostReport:
    cost = CostInput(rates_usd_per_gpu_hour={}, source_path=source_path)
    useful_task = UsefulTaskMetric(
        definition={"source": "not_proven", "reason": reason},
        request_count=0,
        success_count=0,
        failed_request_count=0,
        useful_task_count=0,
        claim_status="not_proven",
        reason=reason,
    )
    envelope = SafeConcurrencyEnvelope(
        safe_concurrency=None,
        claim_status="not_proven",
        slo_ttft_ms=None,
        slo_e2e_ms=None,
        slo_success_rate=slo_success_rate,
        evaluated_levels=[],
        reason=reason,
    )
    return CostReport(
        currency="USD",
        cost_input=cost,
        total_gpu_hours=0.0,
        total_cost_usd=0.0,
        prompt_tokens_total=0,
        completion_tokens_total=0,
        request_count=0,
        success_count=0,
        failed_request_count=0,
        cost_per_million_prompt_tokens_usd=None,
        cost_per_million_completion_tokens_usd=None,
        cost_per_useful_task_usd=None,
        failed_request_waste_percent=None,
        failed_request_waste_dollars=None,
        gpu_hour_normalized_throughput=None,
        useful_task=useful_task,
        safe_concurrency_envelope=envelope,
        skipped_jobs=[{"reason": reason, "claim_status": "not_proven"}],
        claim_status="not_proven",
        claim_status_by_field={"cost_input": reason},
        claim_reason=reason,
    )


def _validation_status(root: Path) -> str:
    for path in (
        root / "validation_report.json",
        root / "validate" / "validation_report.json",
        root / "validation" / "validation_report.json",
    ):
        data = load_json_object(path)
        if isinstance(data, dict):
            return str(data.get("status") or "missing_required_artifacts")
    return "missing_required_artifacts"


def _downgrade_measured_statuses(statuses: dict[str, str]) -> dict[str, str]:
    return {key: "inferred" if value == "measured" else value for key, value in statuses.items()}


def _downgrade_measured_job(job: dict[str, Any], reason: str) -> dict[str, Any]:
    item = dict(job)
    if item.get("claim_status") == "measured":
        item["claim_status"] = "inferred"
        item["claim_reason"] = reason
    return item


def _downgrade_useful_task(metric: UsefulTaskMetric, reason: str) -> UsefulTaskMetric:
    if metric.claim_status != "measured":
        return metric
    return replace(metric, claim_status="inferred", reason=reason)


def _downgrade_envelope(envelope: SafeConcurrencyEnvelope, reason: str) -> SafeConcurrencyEnvelope:
    if envelope.claim_status != "measured":
        return envelope
    return replace(envelope, claim_status="inferred", reason=reason)


def _source_path(raw: str | Path | dict[str, Any] | CostInput) -> str:
    if isinstance(raw, CostInput):
        return raw.source_path
    if isinstance(raw, str | Path):
        return str(Path(raw).resolve())
    return "operator-supplied-object"


def _coerce_cost_input(raw: str | Path | dict[str, Any] | CostInput) -> CostInput:
    if isinstance(raw, CostInput):
        return raw
    source_path = "operator-supplied-object"
    if isinstance(raw, str | Path):
        source_path = str(Path(raw).resolve())
        data = load_json_object(Path(raw))
        if data is None:
            raise ValueError(f"cost input unavailable or invalid: {source_path}")
    else:
        data = dict(raw)
    if not isinstance(data, dict):
        raise ValueError("cost input must be a JSON object")
    currency = str(data.get("currency") or "USD")
    source_note = data.get("source_note") or data.get("note")
    rates: dict[str, float] = {}
    rate_container = data.get("rates_usd_per_gpu_hour") or data.get("rates") or data.get("skus")
    if isinstance(rate_container, dict):
        _collect_rates(rates, rate_container)
    _collect_rates(rates, data)
    if not rates:
        raise ValueError("cost input did not contain any numeric SKU rates")
    return CostInput(
        rates_usd_per_gpu_hour=rates,
        source_path=source_path,
        currency=currency,
        source_note=str(source_note) if source_note else None,
    )


def _collect_rates(out: dict[str, float], data: dict[str, Any]) -> None:
    for key, value in data.items():
        normalized = _normalize_sku(key)
        if normalized is None:
            continue
        rate = _rate_value(value)
        if rate is not None and rate >= 0:
            out[normalized] = rate


def _rate_value(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("usd_per_gpu_hour", "usd_per_hour", "per_gpu_hour_usd"):
            rate = _number(value.get(key))
            if rate is not None:
                return rate
        return None
    return _number(value)


def _load_slo(raw: str | Path | dict[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str | Path):
        data = load_json_object(Path(raw)) or {}
    else:
        data = dict(raw)
    if not isinstance(data, dict):
        raise ValueError("SLO input must be a JSON object")
    return data


def _discover_jobs(root: Path) -> list[dict[str, Any]]:
    plan_path = root / "matrix_plan.json"
    contract_path = root / "expected_artifact_contract.json"
    plan = _read_json(plan_path) if plan_path.exists() else {}
    contract = _read_json(contract_path) if contract_path.exists() else {}
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


def _load_job(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    job_id = str(spec.get("job_id") or "unknown")
    output_dir = Path(str(spec.get("output_dir") or Path("jobs") / job_id))
    job_dir = output_dir if output_dir.is_absolute() else root / output_dir
    request_summary_path = _first_existing(
        job_dir / "request_profile" / "requests_summary.json",
        job_dir / "request_profile" / "request_summary.json",
    )
    request_rows_path = _first_existing(job_dir / "request_profile" / "requests_profile.jsonl")
    metrics_path = _first_existing(
        job_dir / "metrics" / "metrics_summary.json",
        job_dir / "collect_metrics" / "metrics_summary.json",
    )
    profile_path = _first_existing(
        job_dir / "operator_profile.json",
        job_dir / "manifests" / "operator_profile.json",
    )
    request_summary = _read_json(request_summary_path) if request_summary_path else {}
    metrics_summary = _read_json(metrics_path) if metrics_path else {}
    operator_profile = _read_json(profile_path) if profile_path else {}
    request_rows = _read_jsonl(request_rows_path) if request_rows_path else []
    request_rows = _enrich_request_rows(request_rows, request_summary)
    sku = _normalize_sku(
        spec.get("sku")
        or spec.get("hardware")
        or operator_profile.get("sku")
        or operator_profile.get("hardware")
        or operator_profile.get("gpu_sku")
    )
    return {
        "job_id": job_id,
        "job_dir": job_dir,
        "rel_dir": _rel(job_dir, root),
        "spec": dict(spec),
        "request_summary": request_summary,
        "metrics_summary": metrics_summary,
        "operator_profile": operator_profile,
        "request_rows": request_rows,
        "request_summary_path": _rel(request_summary_path, root) if request_summary_path else None,
        "request_rows_path": _rel(request_rows_path, root) if request_rows_path else None,
        "metrics_path": _rel(metrics_path, root) if metrics_path else None,
        "operator_profile_path": _rel(profile_path, root) if profile_path else None,
        "sku": sku,
        "engine": spec.get("engine")
        or request_summary.get("engine")
        or metrics_summary.get("engine"),
    }


def _enrich_request_rows(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    if not rows:
        return []
    request_count = _int_value(summary.get("request_count")) or len(rows)
    success_count = _int_value(summary.get("success_count")) or request_count
    prompt_avg = _safe_div(_number(summary.get("prompt_tokens_total")) or 0.0, request_count) or 0.0
    completion_avg = (
        _safe_div(
            _number(summary.get("completion_tokens_total")) or 0.0,
            success_count,
        )
        or 0.0
    )
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if item.get("concurrency") is None and summary.get("concurrency") is not None:
            item["concurrency"] = summary["concurrency"]
        if item.get("workload_label") is None and summary.get("workload_label") is not None:
            item["workload_label"] = summary["workload_label"]
        if item.get("engine") is None and summary.get("engine") is not None:
            item["engine"] = summary["engine"]
        if item.get("prompt_tokens") is None and prompt_avg > 0:
            item["prompt_tokens"] = int(prompt_avg)
        if item.get("completion_tokens") is None:
            item["completion_tokens"] = int(completion_avg) if _truthy(item.get("success")) else 0
        enriched.append(item)
    return enriched


def _job_cost(job: dict[str, Any], rate: float) -> dict[str, Any]:
    duration = _duration_seconds(job)
    gpus = _gpu_count(job)
    if duration is None or duration <= 0:
        return {"claim_status": "not_proven", "reason": "duration_seconds unavailable"}
    if gpus <= 0:
        return {"claim_status": "not_proven", "reason": "gpu_count unavailable"}
    gpu_seconds = duration * gpus
    gpu_hours = gpu_seconds / 3600.0
    total_cost = gpu_hours * rate
    request_count = _request_count(job)
    success_count = _success_count(job)
    failed_count = max(request_count - success_count, 0)
    failed_gpu_seconds = _failed_gpu_seconds(job, gpus)
    if failed_gpu_seconds is None:
        failed_gpu_seconds = gpu_seconds * (failed_count / request_count) if request_count else 0.0
    failed_cost = (failed_gpu_seconds / 3600.0) * rate
    return {
        "claim_status": "measured",
        "duration_seconds": duration,
        "gpus": gpus,
        "gpu_seconds": gpu_seconds,
        "gpu_hours": gpu_hours,
        "total_cost_usd": total_cost,
        "request_count": request_count,
        "success_count": success_count,
        "failed_request_count": failed_count,
        "failed_gpu_seconds": failed_gpu_seconds,
        "failed_request_waste_dollars": failed_cost,
    }


def _accumulate_totals(
    totals: dict[str, float], job: dict[str, Any], job_cost: dict[str, Any]
) -> None:
    totals["total_gpu_hours"] += float(job_cost["gpu_hours"])
    totals["gpu_seconds_total"] += float(job_cost["gpu_seconds"])
    totals["total_cost_usd"] += float(job_cost["total_cost_usd"])
    totals["prompt_tokens_total"] += _prompt_tokens(job)
    totals["completion_tokens_total"] += _completion_tokens(job)
    totals["request_count"] += float(job_cost["request_count"])
    totals["success_count"] += float(job_cost["success_count"])
    totals["failed_request_count"] += float(job_cost["failed_request_count"])
    totals["failed_gpu_seconds"] += float(job_cost["failed_gpu_seconds"])
    totals["failed_request_waste_dollars"] += float(job_cost["failed_request_waste_dollars"])


def _job_report(
    job: dict[str, Any],
    job_cost: dict[str, Any],
    rate: float,
    cost_source_path: str,
) -> dict[str, Any]:
    prompt_tokens = _prompt_tokens(job)
    completion_tokens = _completion_tokens(job)
    return {
        "job_id": job["job_id"],
        "sku": job["sku"],
        "engine": job["engine"],
        "usd_per_gpu_hour": rate,
        "cost_input_source": cost_source_path,
        "duration_seconds": job_cost["duration_seconds"],
        "gpus": job_cost["gpus"],
        "gpu_hours": job_cost["gpu_hours"],
        "compute_cost_usd": job_cost["total_cost_usd"],
        "prompt_tokens_total": int(prompt_tokens),
        "completion_tokens_total": int(completion_tokens),
        "cost_per_million_prompt_tokens_usd": _cost_per_million(
            job_cost["total_cost_usd"], prompt_tokens
        ),
        "cost_per_million_completion_tokens_usd": _cost_per_million(
            job_cost["total_cost_usd"], completion_tokens
        ),
        "request_count": job_cost["request_count"],
        "success_count": job_cost["success_count"],
        "failed_request_count": job_cost["failed_request_count"],
        "failed_request_waste_dollars": job_cost["failed_request_waste_dollars"],
        "claim_status": "measured",
        "evidence_paths": [
            path
            for path in (
                job.get("request_summary_path"),
                job.get("request_rows_path"),
                job.get("metrics_path"),
                job.get("operator_profile_path"),
            )
            if path
        ],
    }


def _job_envelope_levels(job: dict[str, Any]) -> list[dict[str, Any]]:
    summary = job.get("request_summary") or {}
    if summary:
        concurrency = _int_value(summary.get("concurrency"))
        if concurrency is not None:
            request_count = _int_value(summary.get("request_count")) or len(job["request_rows"])
            success_count = _int_value(summary.get("success_count")) or 0
            return [
                {
                    "concurrency": concurrency,
                    "request_count": request_count,
                    "success_count": success_count,
                    "success_rate": _number(summary.get("success_rate")),
                    "p99_ttft_ms": _nested_number(summary, "ttft_ms", "p99"),
                    "p99_e2e_ms": _nested_number(summary, "e2e_latency_ms", "p99"),
                    "source": job.get("request_summary_path"),
                }
            ]
    rows = job.get("request_rows") or []
    by_concurrency: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        concurrency = _int_value(row.get("concurrency"))
        if concurrency is not None and concurrency > 0:
            by_concurrency.setdefault(concurrency, []).append(row)
    levels: list[dict[str, Any]] = []
    for concurrency, level_rows in sorted(by_concurrency.items()):
        successes = [row for row in level_rows if _truthy(row.get("success"))]
        levels.append(
            {
                "concurrency": concurrency,
                "request_count": len(level_rows),
                "success_count": len(successes),
                "success_rate": len(successes) / len(level_rows) if level_rows else None,
                "p99_ttft_ms": _percentile([_number(row.get("ttft_ms")) for row in successes], 99),
                "p99_e2e_ms": _percentile(
                    [
                        _number(row.get("e2e_latency_ms") or row.get("latency_ms"))
                        for row in successes
                    ],
                    99,
                ),
                "source": job.get("request_rows_path"),
            }
        )
    return levels


def _failed_gpu_seconds(job: dict[str, Any], gpus: float) -> float | None:
    rows = job.get("request_rows") or []
    request_count = _request_count(job)
    if not rows or len(rows) != request_count:
        return None
    failed_seconds = 0.0
    for row in rows:
        if _truthy(row.get("success")):
            continue
        e2e_ms = _number(row.get("e2e_latency_ms") or row.get("latency_ms"))
        if e2e_ms is None:
            return None
        failed_seconds += e2e_ms / 1000.0
    return failed_seconds * gpus


def _duration_seconds(job: dict[str, Any]) -> float | None:
    request = job.get("request_summary") or {}
    metrics = job.get("metrics_summary") or {}
    for raw in (request.get("duration_seconds"), metrics.get("duration_seconds")):
        value = _number(raw)
        if value is not None and value > 0:
            return value
    rows = job.get("request_rows") or []
    durations = [_number(row.get("e2e_latency_ms") or row.get("latency_ms")) for row in rows]
    clean = [value for value in durations if value is not None]
    return sum(clean) / 1000.0 if clean else None


def _gpu_count(job: dict[str, Any]) -> float:
    profile = job.get("operator_profile") or {}
    for key in ("gpu_count", "gpus", "tensor_parallel_size", "tp"):
        value = _number(profile.get(key))
        if value is not None and value > 0:
            return value
    return 1.0


def _prompt_tokens(job: dict[str, Any]) -> float:
    request = job.get("request_summary") or {}
    summary_value = _number(request.get("prompt_tokens_total"))
    if summary_value is not None:
        return summary_value
    return sum(_number(row.get("prompt_tokens")) or 0.0 for row in job.get("request_rows", []))


def _completion_tokens(job: dict[str, Any]) -> float:
    request = job.get("request_summary") or {}
    summary_value = _number(request.get("completion_tokens_total"))
    if summary_value is not None:
        return summary_value
    keys = ("completion_tokens", "generated_tokens", "output_tokens")
    total = 0.0
    for row in job.get("request_rows", []):
        total += _first_number(*(_number(row.get(key)) for key in keys)) or 0.0
    return total


def _request_count(job: dict[str, Any]) -> int:
    request = job.get("request_summary") or {}
    value = _int_value(request.get("request_count"))
    return value if value is not None else len(job.get("request_rows", []))


def _success_count(job: dict[str, Any]) -> int:
    request = job.get("request_summary") or {}
    value = _int_value(request.get("success_count"))
    if value is not None:
        return value
    return sum(1 for row in job.get("request_rows", []) if _truthy(row.get("success")))


def _field_statuses(
    *,
    cost_per_prompt: float | None,
    cost_per_completion: float | None,
    cost_per_useful: float | None,
    failed_waste_percent: float | None,
    throughput: float | None,
    envelope_status: str,
) -> dict[str, str]:
    measured = "measured"
    not_proven = "not_proven"
    completion_status = measured if cost_per_completion is not None else not_proven
    return {
        "cost_per_million_prompt_tokens_usd": measured
        if cost_per_prompt is not None
        else not_proven,
        "cost_per_million_completion_tokens_usd": completion_status,
        "cost_per_million_generated_tokens_usd": completion_status,
        "cost_per_million_prompt_tokens": measured if cost_per_prompt is not None else not_proven,
        "cost_per_million_generated_tokens": completion_status,
        "cost_per_useful_task_usd": measured if cost_per_useful is not None else not_proven,
        "cost_per_useful_task": measured if cost_per_useful is not None else not_proven,
        "failed_request_waste_percent": measured
        if failed_waste_percent is not None
        else not_proven,
        "failed_request_waste_dollars": measured
        if failed_waste_percent is not None
        else not_proven,
        "gpu_hour_normalized_throughput": measured if throughput is not None else not_proven,
        "safe_concurrency_envelope": envelope_status,
    }


def _empty_totals() -> dict[str, float]:
    return {
        "total_gpu_hours": 0.0,
        "gpu_seconds_total": 0.0,
        "total_cost_usd": 0.0,
        "prompt_tokens_total": 0.0,
        "completion_tokens_total": 0.0,
        "request_count": 0.0,
        "success_count": 0.0,
        "failed_request_count": 0.0,
        "failed_gpu_seconds": 0.0,
        "failed_request_waste_dollars": 0.0,
    }


def _read_json(path: Path) -> dict[str, Any]:
    return load_json_object(path) or {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


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


def _slo_value(data: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _number(data.get(key))
        if value is not None:
            return value
    return None


def _nested_number(data: dict[str, Any], key: str, subkey: str) -> float | None:
    value = data.get(key)
    if isinstance(value, dict):
        return _number(value.get(subkey))
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _int_value(value: Any) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _first_number(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "success", "succeeded"}
    return False


def _percentile(values: list[float | None], pct: int) -> float | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    idx = min(len(clean) - 1, max(0, round((pct / 100) * (len(clean) - 1))))
    return clean[idx]


def _cost_per_million(cost: float, tokens: float) -> float | None:
    if cost <= 0 or tokens <= 0:
        return None
    return cost / (tokens / 1_000_000.0)


def _safe_div(numerator: float, denominator: float | int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _rel(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


__all__ = [
    "COST_REPORT_SCHEMA_VERSION",
    "CostInput",
    "CostReport",
    "compute_cost",
    "refusal_cost_report_fields",
]
