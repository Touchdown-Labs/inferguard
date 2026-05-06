"""Structured evidence parsing for LMCache MP HTTP API payloads."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "inferguard-lmcache-http-evidence/v1"


@dataclass
class LmcacheHttpEvidence:
    schema_version: str = SCHEMA_VERSION
    endpoints: dict[str, dict[str, Any]] = field(default_factory=dict)
    booleans: dict[str, bool] = field(default_factory=dict)
    failure_reasons: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_lmcache_http_payloads(
    *,
    health_text: str = "",
    status_text: str = "",
    metrics_text: str = "",
    threads_text: str = "",
    periodic_threads_text: str = "",
    periodic_threads_health_text: str = "",
) -> dict[str, Any]:
    """Parse best-effort LMCache HTTP API responses into bounded evidence."""

    evidence = LmcacheHttpEvidence()
    payloads = {
        "health": health_text,
        "status": status_text,
        "metrics": metrics_text,
        "threads": threads_text,
        "periodic_threads": periodic_threads_text,
        "periodic_threads_health": periodic_threads_health_text,
    }
    for name, text in payloads.items():
        if not text:
            continue
        evidence.endpoints[name] = _endpoint_row(name, text)
    evidence.booleans = {
        "has_health": "health" in evidence.endpoints,
        "has_status": "status" in evidence.endpoints,
        "has_metrics": "metrics" in evidence.endpoints,
        "has_threads": "threads" in evidence.endpoints,
        "has_periodic_threads": "periodic_threads" in evidence.endpoints,
        "has_periodic_threads_health": "periodic_threads_health" in evidence.endpoints,
        "is_healthy": _is_overall_healthy(evidence.endpoints),
    }
    evidence.failure_reasons = _failure_reasons(evidence.endpoints)
    return evidence.as_dict()


def _endpoint_row(name: str, text: str) -> dict[str, Any]:
    parsed = _parse_json(text)
    row: dict[str, Any] = {
        "present": True,
        "content_type": "json" if parsed is not None else "text",
        "raw_length": len(text),
    }
    if parsed is None:
        normalized = text.strip().lower()
        row.update(
            {
                "status": "healthy" if normalized in {"ok", "healthy", "true"} else "unknown",
                "summary": _truncate(text.strip(), 240),
            }
        )
        return row
    row["json_type"] = type(parsed).__name__
    row["fields"] = _extract_fields(name, parsed)
    row["status"] = _classify_json_status(parsed, row["fields"])
    return row


def _parse_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_fields(name: str, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    fields: dict[str, Any] = {}
    for key in (
        "status",
        "healthy",
        "is_healthy",
        "engine_type",
        "chunk_size",
        "active_sessions",
        "active_prefetch_jobs",
        "registered_gpu_ids",
        "storage_manager",
        "error",
        "failure_reason",
    ):
        if key in payload:
            fields[key] = _safe_value(payload[key])
    if name == "status":
        for key in ("l1", "l2", "l1_memory_usage_bytes", "l1_size_bytes"):
            if key in payload:
                fields[key] = _safe_value(payload[key])
    return fields


def _safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_safe_value(item) for item in value[:20]]
    if isinstance(value, dict):
        return {str(key): _safe_value(val) for key, val in list(value.items())[:30]}
    return str(value)


def _classify_json_status(payload: Any, fields: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return "unknown"
    raw_status = str(fields.get("status") or payload.get("state") or "").lower()
    if fields.get("healthy") is True or fields.get("is_healthy") is True:
        return "healthy"
    if fields.get("healthy") is False or fields.get("is_healthy") is False:
        return "unhealthy"
    if raw_status in {"ok", "healthy", "ready", "running", "success"}:
        return "healthy"
    if raw_status in {"unhealthy", "failed", "error", "degraded"}:
        return "unhealthy"
    if fields.get("error") or fields.get("failure_reason"):
        return "unhealthy"
    return "unknown"


def _is_overall_healthy(endpoints: dict[str, dict[str, Any]]) -> bool:
    if not endpoints:
        return False
    statuses = {str(row.get("status")) for row in endpoints.values()}
    return "unhealthy" not in statuses and "healthy" in statuses


def _failure_reasons(endpoints: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for name, row in endpoints.items():
        if row.get("status") == "unhealthy":
            fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
            failures.append(
                {
                    "code": f"lmcache_http_{name}_unhealthy",
                    "message": str(
                        fields.get("failure_reason")
                        or fields.get("error")
                        or f"LMCache HTTP endpoint {name} reported unhealthy"
                    ),
                }
            )
    return failures


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


__all__ = ["SCHEMA_VERSION", "parse_lmcache_http_payloads"]
