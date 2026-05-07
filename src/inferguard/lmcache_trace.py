"""LMCache MP trace-recording (.lct) evidence parsing."""

from __future__ import annotations

import csv
import hashlib
import json
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "inferguard-lmcache-trace-evidence/v1"
MAX_RECORDS = 10_000
REPLAY_SCHEMA_VERSION = "inferguard-lmcache-trace-replay-evidence/v1"


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


@dataclass
class LmcacheTraceReplayEvidence:
    schema_version: str = REPLAY_SCHEMA_VERSION
    present: bool = False
    claim_status: str = "not_proven"
    source_kind: str = ""
    file_size_bytes: int = 0
    replay_info: dict[str, Any] = field(default_factory=dict)
    duration_s: float | None = None
    op_counts: dict[str, int] = field(default_factory=dict)
    op_errors: dict[str, int] = field(default_factory=dict)
    latency_ms: dict[str, dict[str, float]] = field(default_factory=dict)
    rows_seen: int = 0
    failed_rows: int = 0
    parse_errors: list[str] = field(default_factory=list)

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


def parse_lmcache_trace_replay_file(path: Path) -> dict[str, Any]:
    """Parse LMCache trace info/replay JSON, JSONL, or trace_replay_ops.csv output."""

    evidence = LmcacheTraceReplayEvidence(present=True)
    source = Path(path)
    try:
        evidence.file_size_bytes = source.stat().st_size
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        evidence.parse_errors.append(f"{type(exc).__name__}: {exc}")
        return evidence.as_dict()
    if not text.strip():
        evidence.parse_errors.append("empty_replay_file")
        return evidence.as_dict()
    kind = _replay_source_kind(source, text)
    evidence.source_kind = kind
    try:
        if kind == "ops_csv":
            _parse_replay_ops_csv(text, evidence)
        elif kind == "jsonl":
            _parse_replay_jsonl(text, evidence)
        elif kind == "json":
            _parse_replay_json(text, evidence)
        else:
            _parse_trace_info_text(text, evidence)
    except Exception as exc:  # noqa: BLE001 - malformed replay output must be non-fatal
        evidence.parse_errors.append(f"{type(exc).__name__}: {exc}")
    evidence.op_counts = dict(sorted(evidence.op_counts.items()))
    evidence.op_errors = dict(sorted(evidence.op_errors.items()))
    evidence.latency_ms = dict(sorted(evidence.latency_ms.items()))
    evidence.claim_status = (
        "measured" if evidence.replay_info or evidence.op_counts or evidence.rows_seen else "not_proven"
    )
    return evidence.as_dict()


def parse_lmcache_trace_replay_dir(path: Path) -> dict[str, Any]:
    """Parse all recognized LMCache replay artifacts in a directory."""

    evidence = LmcacheTraceReplayEvidence(present=True, source_kind="directory")
    root = Path(path)
    if not root.exists():
        evidence.parse_errors.append("directory_not_found")
        return evidence.as_dict()
    if not root.is_dir():
        evidence.parse_errors.append("not_a_directory")
        return evidence.as_dict()
    candidates = [
        *root.glob("trace_replay_ops.csv"),
        *root.glob("*.json"),
        *root.glob("*.jsonl"),
        *root.glob("*.txt"),
    ]
    for candidate in candidates:
        child = parse_lmcache_trace_replay_file(candidate)
        if child.get("parse_errors"):
            evidence.parse_errors.extend(
                f"{candidate.name}: {error}" for error in child.get("parse_errors", [])
            )
        evidence.file_size_bytes += int(child.get("file_size_bytes") or 0)
        evidence.rows_seen += int(child.get("rows_seen") or 0)
        evidence.failed_rows += int(child.get("failed_rows") or 0)
        if child.get("duration_s") is not None:
            evidence.duration_s = child.get("duration_s")
        evidence.replay_info.update(child.get("replay_info") or {})
        _merge_counts(evidence.op_counts, child.get("op_counts") or {})
        _merge_counts(evidence.op_errors, child.get("op_errors") or {})
        _merge_latency_summaries(evidence.latency_ms, child.get("latency_ms") or {})
    evidence.claim_status = (
        "measured" if evidence.replay_info or evidence.op_counts or evidence.rows_seen else "not_proven"
    )
    return evidence.as_dict()


def _replay_source_kind(path: Path, text: str) -> str:
    if path.name == "trace_replay_ops.csv" or path.suffix.lower() == ".csv":
        return "ops_csv"
    stripped = text.lstrip()
    if path.suffix.lower() == ".jsonl":
        return "jsonl"
    if path.suffix.lower() == ".json" or stripped.startswith(("{", "[")):
        return "json"
    return "trace_info"


def _parse_trace_info_text(text: str, evidence: LmcacheTraceReplayEvidence) -> None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = _split_key_value(stripped)
        if key is None:
            continue
        normalized_key = key.strip().lower().replace(" ", "_")
        safe_value = _parse_scalar(value)
        if normalized_key in {
            "level",
            "format_version",
            "trace_schema_version",
            "duration",
            "duration_s",
            "sm_config_digest",
            "total_records",
        }:
            out_key = "duration_s" if normalized_key == "duration" else normalized_key
            evidence.replay_info[out_key] = safe_value
            if out_key == "duration_s":
                evidence.duration_s = _number(safe_value)
            continue
        count = _int(value)
        if count is not None and _looks_like_qualname(key):
            evidence.op_counts[key.strip()] = evidence.op_counts.get(key.strip(), 0) + count


def _parse_replay_json(text: str, evidence: LmcacheTraceReplayEvidence) -> None:
    payload = json.loads(text)
    if isinstance(payload, list):
        for item in payload:
            _parse_replay_json_op(item, evidence)
        return
    if not isinstance(payload, dict):
        evidence.parse_errors.append("json_root_not_object")
        return
    for key in (
        "level",
        "format_version",
        "trace_schema_version",
        "sm_config_digest",
        "total_records",
    ):
        if key in payload:
            evidence.replay_info[key] = _safe_value(payload[key])
    duration = _number(payload.get("duration_s") or payload.get("duration"))
    if duration is not None:
        evidence.duration_s = duration
        evidence.replay_info["duration_s"] = duration
    ops = payload.get("ops") or payload.get("operations") or []
    if isinstance(ops, dict):
        for qualname, value in ops.items():
            if isinstance(value, dict):
                _parse_replay_json_op({"qualname": qualname, **value}, evidence)
            else:
                count = _int(value)
                if count is not None:
                    evidence.op_counts[str(qualname)] = evidence.op_counts.get(str(qualname), 0) + count
    elif isinstance(ops, list):
        for op in ops:
            _parse_replay_json_op(op, evidence)


def _parse_replay_json_op(value: Any, evidence: LmcacheTraceReplayEvidence) -> None:
    if not isinstance(value, dict):
        return
    qualname = str(value.get("qualname") or value.get("name") or "")
    if not qualname:
        return
    count = _int(value.get("count")) or 1
    errors = _int(value.get("errors") or value.get("failed") or value.get("failures")) or 0
    evidence.op_counts[qualname] = evidence.op_counts.get(qualname, 0) + count
    if errors:
        evidence.op_errors[qualname] = evidence.op_errors.get(qualname, 0) + errors
    latency_values = [
        _number(value.get(key))
        for key in ("latency_ms", "mean_ms", "p50_ms", "p90_ms", "p99_ms", "min_ms", "max_ms")
    ]
    latency_values = [item for item in latency_values if item is not None]
    if latency_values:
        evidence.latency_ms[qualname] = _duration_summary(latency_values)


def _parse_replay_jsonl(text: str, evidence: LmcacheTraceReplayEvidence) -> None:
    latencies: dict[str, list[float]] = {}
    for idx, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            evidence.parse_errors.append(f"line {idx}: {exc.msg}")
            continue
        if not isinstance(row, dict):
            evidence.parse_errors.append(f"line {idx}: expected object")
            continue
        qualname = str(row.get("qualname") or row.get("name") or "")
        if not qualname:
            evidence.parse_errors.append(f"line {idx}: missing qualname")
            continue
        evidence.rows_seen += 1
        evidence.op_counts[qualname] = evidence.op_counts.get(qualname, 0) + 1
        failed = bool(row.get("failed"))
        if failed:
            evidence.failed_rows += 1
            evidence.op_errors[qualname] = evidence.op_errors.get(qualname, 0) + 1
        latency = _number(row.get("latency_ms"))
        if latency is not None:
            latencies.setdefault(qualname, []).append(latency)
    for qualname, values in latencies.items():
        evidence.latency_ms[qualname] = _duration_summary(values)


def _parse_replay_ops_csv(text: str, evidence: LmcacheTraceReplayEvidence) -> None:
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        evidence.parse_errors.append("csv_missing_header")
        return
    for idx, row in enumerate(reader, start=2):
        qualname = str(row.get("qualname") or "").strip()
        if not qualname:
            evidence.parse_errors.append(f"row {idx}: missing qualname")
            continue
        count = _int(row.get("count")) or 0
        errors = _int(row.get("errors")) or 0
        evidence.rows_seen += 1
        evidence.op_counts[qualname] = evidence.op_counts.get(qualname, 0) + count
        if errors:
            evidence.failed_rows += errors
            evidence.op_errors[qualname] = evidence.op_errors.get(qualname, 0) + errors
        latency_values = [
            _number(row.get(key))
            for key in ("mean_ms", "p50_ms", "p90_ms", "p99_ms", "min_ms", "max_ms")
        ]
        latency_values = [item for item in latency_values if item is not None]
        if latency_values:
            evidence.latency_ms[qualname] = _duration_summary(latency_values)


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


def _split_key_value(line: str) -> tuple[str | None, str]:
    for separator in (":", "="):
        if separator in line:
            key, value = line.split(separator, 1)
            return key.strip(), value.strip()
    parts = line.rsplit(maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None, ""


def _parse_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return _safe_value(value)
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped.lower() in {"true", "false"}:
        return stripped.lower() == "true"
    integer = _int(stripped)
    if integer is not None:
        return integer
    number = _number(stripped)
    if number is not None:
        return number
    return stripped


def _looks_like_qualname(value: str) -> bool:
    stripped = value.strip()
    return "." in stripped or stripped.startswith(("StorageManager", "LMCache", "lmcache"))


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
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


def _merge_counts(target: dict[str, int], source: dict[str, Any]) -> None:
    for key, value in source.items():
        count = _int(value)
        if count is not None:
            target[str(key)] = target.get(str(key), 0) + count


def _merge_latency_summaries(
    target: dict[str, dict[str, float]], source: dict[str, Any]
) -> None:
    for key, value in source.items():
        if not isinstance(value, dict):
            continue
        existing = target.get(str(key))
        if existing is None:
            target[str(key)] = {
                str(metric): float(amount)
                for metric, amount in value.items()
                if _number(amount) is not None
            }
            continue
        existing_count = existing.get("count", 0.0)
        incoming_count = _number(value.get("count")) or 0.0
        if incoming_count <= 0:
            continue
        total_count = existing_count + incoming_count
        existing["min"] = min(existing.get("min", value.get("min", 0.0)), float(value.get("min", 0.0)))
        existing["max"] = max(existing.get("max", value.get("max", 0.0)), float(value.get("max", 0.0)))
        existing["avg"] = (
            (existing.get("avg", 0.0) * existing_count)
            + (float(value.get("avg", 0.0)) * incoming_count)
        ) / total_count
        existing["count"] = total_count


__all__ = [
    "REPLAY_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "parse_lmcache_trace_file",
    "parse_lmcache_trace_replay_dir",
    "parse_lmcache_trace_replay_file",
]
