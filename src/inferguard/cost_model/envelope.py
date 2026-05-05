"""Safe concurrency envelope derivation for PRD §4.11."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .types import SafeConcurrencyEnvelope


def derive_safe_concurrency_envelope(
    levels: list[dict[str, Any]],
    *,
    slo_ttft_ms: float | None,
    slo_e2e_ms: float | None,
    slo_success_rate: float = 0.95,
) -> SafeConcurrencyEnvelope:
    """Return the largest concurrency satisfying TTFT, E2E, and success-rate SLOs."""

    evaluated = _evaluated_levels(levels)
    if slo_ttft_ms is None or slo_e2e_ms is None:
        return SafeConcurrencyEnvelope(
            safe_concurrency=None,
            claim_status="not_proven",
            slo_ttft_ms=slo_ttft_ms,
            slo_e2e_ms=slo_e2e_ms,
            slo_success_rate=slo_success_rate,
            evaluated_levels=evaluated,
            basis="slo_ttft_and_slo_e2e_required",
            reason="safe concurrency requires both p99 TTFT and p99 E2E SLOs",
        )
    if not evaluated:
        return SafeConcurrencyEnvelope(
            safe_concurrency=None,
            claim_status="not_proven",
            slo_ttft_ms=slo_ttft_ms,
            slo_e2e_ms=slo_e2e_ms,
            slo_success_rate=slo_success_rate,
            evaluated_levels=[],
            basis="request_profile_missing",
            reason="no request_profile summaries or rows were available",
        )

    safe_levels: list[int] = []
    checked: list[dict[str, Any]] = []
    for level in evaluated:
        p99_ttft = _number(level.get("p99_ttft_ms"))
        p99_e2e = _number(level.get("p99_e2e_ms"))
        success_rate = _number(level.get("success_rate"))
        meets = (
            p99_ttft is not None
            and p99_e2e is not None
            and success_rate is not None
            and p99_ttft <= slo_ttft_ms
            and p99_e2e <= slo_e2e_ms
            and success_rate >= slo_success_rate
        )
        row = {
            **level,
            "slo_ttft_ms": slo_ttft_ms,
            "slo_e2e_ms": slo_e2e_ms,
            "slo_success_rate": slo_success_rate,
            "meets_slo": meets,
        }
        checked.append(row)
        if meets:
            safe_levels.append(int(level["concurrency"]))

    safe = max(safe_levels) if safe_levels else None
    external_safe = _external_safe_concurrency(checked)
    basis = "direct_request_profile_slo"
    if external_safe is not None:
        basis = "direct_request_profile_slo_with_find_cliffs_cap"
        safe = min(safe, external_safe) if safe is not None else external_safe
    return SafeConcurrencyEnvelope(
        safe_concurrency=safe,
        claim_status="measured" if safe is not None else "not_proven",
        slo_ttft_ms=slo_ttft_ms,
        slo_e2e_ms=slo_e2e_ms,
        slo_success_rate=slo_success_rate,
        evaluated_levels=checked,
        basis=basis,
        reason=None if safe is not None else "no concurrency level satisfied all SLOs",
    )


def _evaluated_levels(levels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for level in levels:
        concurrency = _int_value(level.get("concurrency"))
        if concurrency is not None and concurrency > 0:
            grouped[concurrency].append(level)
    evaluated: list[dict[str, Any]] = []
    for concurrency in sorted(grouped):
        rows = grouped[concurrency]
        request_count = sum(_int_value(row.get("request_count")) or 0 for row in rows)
        success_count = sum(_int_value(row.get("success_count")) or 0 for row in rows)
        success_rate = (success_count / request_count) if request_count else _max_number(rows, "success_rate")
        evaluated.append(
            {
                "concurrency": concurrency,
                "request_count": request_count,
                "success_count": success_count,
                "success_rate": success_rate,
                "p99_ttft_ms": _max_number(rows, "p99_ttft_ms"),
                "p99_e2e_ms": _max_number(rows, "p99_e2e_ms"),
                "sources": sorted({str(row.get("source")) for row in rows if row.get("source")}),
            }
        )
    return evaluated


def _external_safe_concurrency(levels: list[dict[str, Any]]) -> int | None:
    try:
        from inferguard.find_cliffs import max_concurrency_before_p99_cliff
    except ImportError:
        return None
    try:
        value = max_concurrency_before_p99_cliff(levels)
    except (AttributeError, TypeError, ValueError):
        return None
    return _int_value(value)


def _max_number(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [_number(row.get(key)) for row in rows]
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


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


__all__ = ["derive_safe_concurrency_envelope"]
