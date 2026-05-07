"""LMCache MP trace-recording (.lct) evidence parsing."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "inferguard-lmcache-trace-evidence/v1"
MAX_RECORDS = 10_000


@dataclass
class LmcacheTraceEvidence:
    schema_version: str = SCHEMA_VERSION
    present: bool = False
    claim_status: str = "not_proven"
    file_size_bytes: int = 0
    sha256: str = ""
    header: dict[str, Any] = field(default_factory=dict)
    record_count: int = 0
    truncated: bool = False
    storage_calls: dict[str, int] = field(default_factory=dict)
    first_record: dict[str, Any] | None = None
    last_record: dict[str, Any] | None = None
    parse_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_lmcache_trace_file(path: Path) -> dict[str, Any]:
    """Parse a length-prefixed msgpack LMCache trace recording."""

    evidence = LmcacheTraceEvidence(present=True)
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        evidence.parse_error = f"{type(exc).__name__}: {exc}"
        return evidence.as_dict()
    evidence.file_size_bytes = len(data)
    evidence.sha256 = hashlib.sha256(data).hexdigest()
    if not data:
        evidence.parse_error = "empty_trace_file"
        return evidence.as_dict()
    try:
        records = list(_iter_msgpack_records(data, max_records=MAX_RECORDS + 1))
    except Exception as exc:  # noqa: BLE001 - malformed trace must become evidence, not crash
        evidence.parse_error = f"{type(exc).__name__}: {exc}"
        return evidence.as_dict()
    if not records:
        evidence.parse_error = "no_records"
        return evidence.as_dict()
    evidence.header = _safe_mapping(records[0])
    body = records[1:]
    if len(body) > MAX_RECORDS:
        evidence.truncated = True
        body = body[:MAX_RECORDS]
    evidence.record_count = len(body)
    calls: dict[str, int] = {}
    for record in body:
        row = _safe_mapping(record)
        qualname = str(row.get("qualname") or row.get("call") or row.get("name") or "")
        short = qualname.rsplit(".", 1)[-1] if qualname else "unknown"
        calls[short] = calls.get(short, 0) + 1
        if evidence.first_record is None:
            evidence.first_record = _compact_record(row)
        evidence.last_record = _compact_record(row)
    evidence.storage_calls = dict(sorted(calls.items()))
    evidence.claim_status = "measured" if evidence.record_count else "not_proven"
    return evidence.as_dict()


def _iter_msgpack_records(data: bytes, *, max_records: int) -> list[Any]:
    offset = 0
    records: list[Any] = []
    while offset < len(data) and len(records) < max_records:
        if offset + 4 > len(data):
            raise ValueError("truncated_length_prefix")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
        if length <= 0:
            raise ValueError("invalid_record_length")
        if offset + length > len(data):
            raise ValueError("truncated_record")
        records.append(_unpack_record(data[offset : offset + length]))
        offset += length
    return records


def _unpack_record(payload: bytes) -> Any:
    try:
        import msgpack  # type: ignore[import-not-found]

        try:
            return msgpack.unpackb(payload, raw=False)
        except Exception:
            pass
    except ImportError:
        pass
    return json.loads(payload.decode("utf-8"))


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"value": _safe_value(value)}
    return {str(key): _safe_value(val) for key, val in value.items()}


def _compact_record(row: dict[str, Any]) -> dict[str, Any]:
    keep = {}
    for key in ("relative_ts", "wall_ts", "monotonic_ts", "qualname", "args"):
        if key in row:
            keep[key] = _safe_value(row[key])
    return keep or {key: _safe_value(value) for key, value in list(row.items())[:6]}


def _safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, list):
        return [_safe_value(item) for item in value[:20]]
    if isinstance(value, dict):
        return {str(key): _safe_value(val) for key, val in list(value.items())[:30]}
    return str(value)


__all__ = ["SCHEMA_VERSION", "parse_lmcache_trace_file"]
