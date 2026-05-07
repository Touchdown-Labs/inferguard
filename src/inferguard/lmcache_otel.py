"""LMCache OpenTelemetry span evidence parsing."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "inferguard-lmcache-otel-evidence/v1"
LMCache_SPANS = {"mp.store", "mp.retrieve", "mp.lookup_prefetch"}


@dataclass
class LmcacheOtelEvidence:
    schema_version: str = SCHEMA_VERSION
    present: bool = False
    claim_status: str = "not_proven"
    span_count: int = 0
    lmcache_span_count: int = 0
    span_counts: dict[str, int] = field(default_factory=dict)
    latency_seconds: dict[str, dict[str, float]] = field(default_factory=dict)
    attribute_keys: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_lmcache_otel_jsonl(path: Path) -> dict[str, Any]:
    """Parse JSONL or OTLP JSON span exports for LMCache MP span evidence."""

    evidence = LmcacheOtelEvidence(present=True)
    attribute_keys: set[str] = set()
    durations: dict[str, list[float]] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        evidence.parse_errors.append(f"{type(exc).__name__}: {exc}")
        return evidence.as_dict()
    for idx, row in enumerate(_iter_span_rows(text, evidence.parse_errors), start=1):
        if not isinstance(row, dict):
            evidence.parse_errors.append(f"span {idx}: expected object")
            continue
        evidence.span_count += 1
        name = _span_name(row)
        if name not in LMCache_SPANS:
            continue
        evidence.lmcache_span_count += 1
        evidence.span_counts[name] = evidence.span_counts.get(name, 0) + 1
        attrs = _attributes(row)
        attribute_keys.update(attrs)
        duration = _duration_seconds(row)
        if duration is not None:
            durations.setdefault(name, []).append(duration)
    evidence.attribute_keys = sorted(attribute_keys)
    evidence.latency_seconds = {
        name: _duration_summary(values) for name, values in sorted(durations.items())
    }
    evidence.claim_status = "measured" if evidence.lmcache_span_count else "not_proven"
    return evidence.as_dict()


def _iter_span_rows(text: str, parse_errors: list[str]) -> list[Any]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith(("{", "[")):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            parse_errors.append(f"json: {exc.msg}")
        else:
            rows = _spans_from_otlp_json(payload)
            if rows:
                return rows
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                return [payload]
    rows: list[Any] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            parse_errors.append(f"line {idx}: {exc.msg}")
            continue
        rows.extend(_spans_from_otlp_json(row) or [row])
    return rows


def _spans_from_otlp_json(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return rows
    for resource_span in payload.get("resourceSpans") or payload.get("resource_spans") or []:
        if not isinstance(resource_span, dict):
            continue
        for scope_span in resource_span.get("scopeSpans") or resource_span.get("scope_spans") or []:
            if not isinstance(scope_span, dict):
                continue
            for span in scope_span.get("spans") or []:
                if isinstance(span, dict):
                    rows.append(span)
    for span in payload.get("spans") or []:
        if isinstance(span, dict):
            rows.append(span)
    return rows


def _span_name(row: dict[str, Any]) -> str:
    for key in ("name", "span_name", "operationName"):
        if row.get(key):
            return str(row[key])
    return ""


def _attributes(row: dict[str, Any]) -> dict[str, Any]:
    attrs = row.get("attributes") or row.get("tags") or {}
    if isinstance(attrs, list):
        out: dict[str, Any] = {}
        for item in attrs:
            if isinstance(item, dict) and item.get("key"):
                out[str(item["key"])] = _otel_value(item.get("value"))
        return out
    return {str(key): _otel_value(value) for key, value in attrs.items()} if isinstance(attrs, dict) else {}


def _otel_value(value: Any) -> Any:
    if isinstance(value, dict):
        for key in (
            "stringValue",
            "intValue",
            "doubleValue",
            "boolValue",
            "string_value",
            "int_value",
            "double_value",
            "bool_value",
        ):
            if key in value:
                return value[key]
    return value


def _duration_seconds(row: dict[str, Any]) -> float | None:
    for key in ("duration_seconds", "duration", "duration_s"):
        value = _number(row.get(key))
        if value is not None:
            return value
    millis = _number(row.get("duration_ms"))
    if millis is not None:
        return millis / 1000.0
    start = _number(row.get("start_time_unix_nano") or row.get("startTimeUnixNano"))
    end = _number(row.get("end_time_unix_nano") or row.get("endTimeUnixNano"))
    if start is not None and end is not None and end >= start:
        return (end - start) / 1_000_000_000.0
    return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _duration_summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "count": float(len(ordered)),
        "min": ordered[0],
        "max": ordered[-1],
        "avg": sum(ordered) / len(ordered),
    }


__all__ = ["LMCache_SPANS", "SCHEMA_VERSION", "parse_lmcache_otel_jsonl"]
