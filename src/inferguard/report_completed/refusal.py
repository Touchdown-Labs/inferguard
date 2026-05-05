"""Evidence gates for PRD §4.7 operator recommendations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

RACK_SCALE_SKUS = {"GB200", "GB300"}


def can_recommend_sku(diagnosis: dict[str, Any], validation: dict[str, Any]) -> bool:
    """Return True only for live-complete runs with comparable multiple SKUs."""

    if _validation_status(validation) != "live_complete":
        return False
    skus = {_normalize_sku(job.get("sku")) for job in _jobs_from_context(diagnosis, validation)}
    skus.discard(None)
    return len(skus) >= 2


def can_claim_lmcache_benefit(metrics: dict[str, Any]) -> bool:
    """Return True only when live LMCache metrics are measured in metrics_summary."""

    for summary in _metrics_summaries(metrics):
        group = _lmcache_group(summary)
        if str(group.get("claim_status")) != "measured":
            continue
        if _has_lmcache_metric_name(group) or _has_lmcache_value(group):
            return True
    return False


def can_justify_gb200(
    diagnosis: dict[str, Any],
    validation: dict[str, Any],
    metrics: dict[str, Any],
) -> bool:
    """Return True only when GB200/GB300 has topology, NCCL, and RDMA evidence."""

    if _validation_status(validation) != "live_complete":
        return False
    jobs = _jobs_from_context(diagnosis, validation) or _jobs_from_context(metrics, validation)
    rack_jobs = [job for job in jobs if _normalize_sku(job.get("sku")) in RACK_SCALE_SKUS]
    if not rack_jobs:
        return False
    return any(
        bool(job.get("has_nccl_evidence"))
        and bool(job.get("has_topology_evidence"))
        and bool(job.get("has_rdma_evidence"))
        for job in rack_jobs
    )


def can_emit_cost(args: Any) -> bool:
    """Return True only when an explicit --cost-input JSON path was supplied."""

    if args is None:
        return False
    if isinstance(args, dict):
        return bool(args.get("cost_input"))
    return bool(getattr(args, "cost_input", None))


def _validation_status(validation: dict[str, Any]) -> str:
    return str(
        validation.get("status")
        or validation.get("executive_verdict_status")
        or "not_enough_evidence"
    )


def _jobs_from_context(*contexts: dict[str, Any]) -> list[dict[str, Any]]:
    for context in contexts:
        jobs = context.get("_jobs") or context.get("jobs")
        if isinstance(jobs, list):
            return [job for job in jobs if isinstance(job, dict)]
    return []


def _metrics_summaries(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    raw = metrics.get("_summaries") or metrics.get("summaries")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if metrics:
        return [metrics]
    return []


def _lmcache_group(summary: dict[str, Any]) -> dict[str, Any]:
    group = summary.get("lmcache")
    if isinstance(group, dict):
        return group
    groups = summary.get("groups")
    if isinstance(groups, dict) and isinstance(groups.get("lmcache"), dict):
        return groups["lmcache"]
    return {}


def _has_lmcache_metric_name(group: dict[str, Any]) -> bool:
    for key in ("source_metrics", "present_source_metrics", "observed_metrics"):
        raw = group.get(key)
        if isinstance(raw, list) and any(str(metric).startswith("lmcache:") for metric in raw):
            return True
        if isinstance(raw, dict) and any(str(metric).startswith("lmcache:") for metric in raw):
            return True
    metrics = group.get("metrics")
    if isinstance(metrics, dict) and any(str(metric).startswith("lmcache:") for metric in metrics):
        return True
    return any(str(key).startswith("lmcache:") for key in group)


def _has_lmcache_value(group: dict[str, Any]) -> bool:
    for key in (
        "retrieve_hit_rate",
        "lookup_hit_rate",
        "num_hit_tokens",
        "num_lookup_hits",
        "lookup_0_hit_requests",
    ):
        if _number(group.get(key)) is not None:
            return True
    metrics = group.get("metrics")
    if isinstance(metrics, dict):
        return any(_number(value) is not None for value in metrics.values())
    return False


def _normalize_sku(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).upper().replace("-", "_").replace(" ", "_")
    for sku in ("GB300", "GB200", "B300", "B200", "H200", "H100"):
        if sku in text:
            return sku
    return None


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


def path_has_text(path: Path, token: str) -> bool:
    """Small shared file predicate used by tests and context assembly."""

    if not path.exists():
        return False
    try:
        return token in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


__all__ = [
    "can_claim_lmcache_benefit",
    "can_emit_cost",
    "can_justify_gb200",
    "can_recommend_sku",
    "path_has_text",
]
