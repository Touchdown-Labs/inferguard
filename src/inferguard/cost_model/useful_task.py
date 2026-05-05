"""Useful-task definition for PRD §4.11 cost-per-useful-task."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .types import UsefulTaskMetric


@dataclass(frozen=True)
class UsefulTask:
    """A request that succeeded, produced enough output, and met supplied SLOs."""

    min_completion_tokens: int = 1
    slo_ttft_ms: float | None = None
    slo_e2e_ms: float | None = None
    source: str = "default"
    workload_label: str | None = None

    def __post_init__(self) -> None:
        if self.min_completion_tokens < 0:
            raise ValueError("min_completion_tokens must be non-negative")

    def is_useful(self, row: dict[str, Any]) -> bool:
        if not _truthy(row.get("success")):
            return False
        completion_tokens = _number(
            row.get("completion_tokens")
            or row.get("generated_tokens")
            or row.get("output_tokens")
            or row.get("completion_tokens_total")
        )
        if completion_tokens is None or completion_tokens < self.min_completion_tokens:
            return False
        if self.workload_label and str(row.get("workload_label") or "") != self.workload_label:
            return False
        if self.slo_ttft_ms is not None:
            ttft_ms = _number(row.get("ttft_ms"))
            if ttft_ms is None or ttft_ms > self.slo_ttft_ms:
                return False
        if self.slo_e2e_ms is not None:
            e2e_ms = _number(row.get("e2e_latency_ms") or row.get("latency_ms"))
            if e2e_ms is None or e2e_ms > self.slo_e2e_ms:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "success_required": True,
            "min_completion_tokens": self.min_completion_tokens,
            "slo_ttft_ms": self.slo_ttft_ms,
            "slo_e2e_ms": self.slo_e2e_ms,
            "workload_label": self.workload_label,
            "source": self.source,
        }


def load_useful_task_definition(
    path: str | Path | None,
    *,
    min_completion_tokens: int = 1,
    slo_ttft_ms: float | None = None,
    slo_e2e_ms: float | None = None,
) -> UsefulTask:
    """Load an optional operator override while preserving locked defaults."""

    if path is None:
        return UsefulTask(
            min_completion_tokens=min_completion_tokens,
            slo_ttft_ms=slo_ttft_ms,
            slo_e2e_ms=slo_e2e_ms,
        )
    definition_path = Path(path).resolve()
    data = json.loads(definition_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected useful-task JSON object: {definition_path}")
    loaded_min_tokens = _int_value(
        data.get("min_completion_tokens")
        or data.get("useful_task_min_tokens")
        or data.get("completion_tokens_min"),
        default=min_completion_tokens,
    )
    return UsefulTask(
        min_completion_tokens=loaded_min_tokens,
        slo_ttft_ms=_number(data.get("slo_ttft_ms") or data.get("useful_task_slo_ttft_ms"))
        if (data.get("slo_ttft_ms") or data.get("useful_task_slo_ttft_ms")) is not None
        else slo_ttft_ms,
        slo_e2e_ms=_number(data.get("slo_e2e_ms") or data.get("useful_task_slo_e2e_ms"))
        if (data.get("slo_e2e_ms") or data.get("useful_task_slo_e2e_ms")) is not None
        else slo_e2e_ms,
        source=str(definition_path),
        workload_label=str(data["workload_label"]) if data.get("workload_label") else None,
    )


def compute_useful_task_metric(
    rows: list[dict[str, Any]], definition: UsefulTask
) -> UsefulTaskMetric:
    request_count = len(rows)
    success_count = sum(1 for row in rows if _truthy(row.get("success")))
    useful_count = sum(1 for row in rows if definition.is_useful(row))
    claim_status = "measured" if useful_count > 0 else "not_proven"
    reason = None if useful_count > 0 else "no request_profile row satisfied useful-task criteria"
    return UsefulTaskMetric(
        definition=definition.to_dict(),
        request_count=request_count,
        success_count=success_count,
        failed_request_count=max(request_count - success_count, 0),
        useful_task_count=useful_count,
        claim_status=claim_status,
        reason=reason,
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "success", "succeeded"}
    return False


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


def _int_value(value: Any, *, default: int) -> int:
    number = _number(value)
    return default if number is None else int(number)


__all__ = ["UsefulTask", "compute_useful_task_metric", "load_useful_task_definition"]
