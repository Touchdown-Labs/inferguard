"""Dataclass contracts for PRD §4.11 cost reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

COST_REPORT_SCHEMA_VERSION = "inferguard-cost/v1"


@dataclass(frozen=True)
class CostInput:
    """Operator-supplied SKU rate map used as the cost audit trail."""

    rates_usd_per_gpu_hour: dict[str, float]
    source_path: str
    currency: str = "USD"
    source_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "currency": self.currency,
            "rates_usd_per_gpu_hour": dict(sorted(self.rates_usd_per_gpu_hour.items())),
            "source_note": self.source_note,
        }


@dataclass(frozen=True)
class UsefulTaskMetric:
    """Useful-task count and definition used for cost-per-useful-task."""

    definition: dict[str, Any]
    request_count: int
    success_count: int
    failed_request_count: int
    useful_task_count: int
    claim_status: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "definition": dict(self.definition),
            "request_count": self.request_count,
            "success_count": self.success_count,
            "failed_request_count": self.failed_request_count,
            "useful_task_count": self.useful_task_count,
            "claim_status": self.claim_status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SafeConcurrencyEnvelope:
    """Largest concurrency level that satisfies TTFT, E2E, and success-rate SLOs."""

    safe_concurrency: int | None
    claim_status: str
    slo_ttft_ms: float | None
    slo_e2e_ms: float | None
    slo_success_rate: float
    evaluated_levels: list[dict[str, Any]] = field(default_factory=list)
    basis: str = "direct_request_profile_slo"
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "safe_concurrency": self.safe_concurrency,
            "claim_status": self.claim_status,
            "slo_ttft_ms": self.slo_ttft_ms,
            "slo_e2e_ms": self.slo_e2e_ms,
            "slo_success_rate": self.slo_success_rate,
            "evaluated_levels": [dict(level) for level in self.evaluated_levels],
            "basis": self.basis,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CostReport:
    """Canonical machine-readable PRD §4.11 cost report."""

    currency: str
    cost_input: CostInput
    total_gpu_hours: float
    total_cost_usd: float
    prompt_tokens_total: int
    completion_tokens_total: int
    request_count: int
    success_count: int
    failed_request_count: int
    cost_per_million_prompt_tokens_usd: float | None
    cost_per_million_completion_tokens_usd: float | None
    cost_per_useful_task_usd: float | None
    failed_request_waste_percent: float | None
    failed_request_waste_dollars: float | None
    gpu_hour_normalized_throughput: float | None
    useful_task: UsefulTaskMetric
    safe_concurrency_envelope: SafeConcurrencyEnvelope
    per_job: list[dict[str, Any]] = field(default_factory=list)
    skipped_jobs: list[dict[str, Any]] = field(default_factory=list)
    claim_status: str = "not_proven"
    claim_status_by_field: dict[str, str] = field(default_factory=dict)
    claim_reason: str | None = None
    schema_version: str = COST_REPORT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        prompt_cost = self.cost_per_million_prompt_tokens_usd
        completion_cost = self.cost_per_million_completion_tokens_usd
        useful_cost = self.cost_per_useful_task_usd
        return {
            "schema_version": self.schema_version,
            "claim_status": self.claim_status,
            **({"claim_reason": self.claim_reason} if self.claim_reason else {}),
            "currency": self.currency,
            "cost_input": self.cost_input.to_dict(),
            "rate_audit_trail": [
                {
                    "sku": sku,
                    "usd_per_gpu_hour": rate,
                    "source_path": self.cost_input.source_path,
                }
                for sku, rate in sorted(self.cost_input.rates_usd_per_gpu_hour.items())
            ],
            "total_gpu_hours": self.total_gpu_hours,
            "total_cost_usd": self.total_cost_usd,
            "prompt_tokens_total": self.prompt_tokens_total,
            "completion_tokens_total": self.completion_tokens_total,
            "generated_tokens_total": self.completion_tokens_total,
            "request_count": self.request_count,
            "success_count": self.success_count,
            "failed_request_count": self.failed_request_count,
            "useful_task_count": self.useful_task.useful_task_count,
            "cost_per_million_prompt_tokens_usd": prompt_cost,
            "cost_per_million_completion_tokens_usd": completion_cost,
            "cost_per_million_generated_tokens_usd": completion_cost,
            "cost_per_million_prompt_tokens": prompt_cost,
            "cost_per_million_generated_tokens": completion_cost,
            "cost_per_useful_task_usd": useful_cost,
            "cost_per_useful_task": useful_cost,
            "failed_request_waste_percent": self.failed_request_waste_percent,
            "failed_request_waste_dollars": self.failed_request_waste_dollars,
            "gpu_hour_normalized_throughput": self.gpu_hour_normalized_throughput,
            "useful_task": self.useful_task.to_dict(),
            "safe_concurrency_envelope": self.safe_concurrency_envelope.to_dict(),
            "per_job": [dict(job) for job in self.per_job],
            "skipped_jobs": [dict(job) for job in self.skipped_jobs],
            "claim_status_by_field": dict(self.claim_status_by_field),
        }


__all__ = [
    "COST_REPORT_SCHEMA_VERSION",
    "CostInput",
    "CostReport",
    "SafeConcurrencyEnvelope",
    "UsefulTaskMetric",
]
