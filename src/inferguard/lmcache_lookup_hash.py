"""Privacy-bounded LMCache lookup-hash JSONL evidence parsing."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "inferguard-lmcache-lookup-hash-evidence/v1"
MAX_ROW_SUMMARIES = 100
CONFIG_KEYS = {
    "--lookup-hash-log-dir": "lookup_hash_log_dir",
    "lookup_hash_log_dir": "lookup_hash_log_dir",
    "lookup_hash_rotation_interval": "lookup_hash_rotation_interval",
    "lookup_hash_max_size": "lookup_hash_max_size",
    "lookup_hash_max_files": "lookup_hash_max_files",
}


@dataclass
class LmcacheLookupHashEvidence:
    schema_version: str = SCHEMA_VERSION
    present: bool = False
    claim_status: str = "not_proven"
    file_size_bytes: int = 0
    row_count: int = 0
    malformed_rows: int = 0
    truncated: bool = False
    models: list[str] = field(default_factory=list)
    chunk_hash_count: dict[str, int] = field(default_factory=dict)
    chunk_sizes: list[int] = field(default_factory=list)
    seq_len: dict[str, int] = field(default_factory=dict)
    dtypes: list[Any] = field(default_factory=list)
    shapes: list[Any] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    config_evidence: dict[str, Any] = field(default_factory=dict)
    parse_errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_lmcache_lookup_hash_jsonl(path: Path) -> dict[str, Any]:
    """Parse lookup_hashes_*.jsonl without exposing raw chunk hashes."""

    evidence = LmcacheLookupHashEvidence(present=True)
    source = Path(path)
    try:
        evidence.file_size_bytes = source.stat().st_size
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        evidence.parse_errors.append(f"{type(exc).__name__}: {exc}")
        return evidence.as_dict()

    models: set[str] = set()
    chunk_sizes: set[int] = set()
    dtypes_seen: list[Any] = []
    shapes_seen: list[Any] = []
    seq_values: list[int] = []
    hash_counts: list[int] = []

    for idx, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            evidence.malformed_rows += 1
            evidence.parse_errors.append(f"line {idx}: {exc.msg}")
            continue
        if not isinstance(row, dict):
            evidence.malformed_rows += 1
            evidence.parse_errors.append(f"line {idx}: expected object")
            continue
        evidence.row_count += 1
        _collect_config_evidence(row, evidence.config_evidence)
        model = row.get("model_name")
        if isinstance(model, str) and model:
            models.add(model)
        chunk_size = _int(row.get("chunk_size"))
        if chunk_size is not None:
            chunk_sizes.add(chunk_size)
        seq_len = _int(row.get("seq_len"))
        if seq_len is not None:
            seq_values.append(seq_len)
        dtypes = _safe_shape_value(row.get("dtypes"))
        shapes = _safe_shape_value(row.get("shapes"))
        _append_unique(dtypes_seen, dtypes)
        _append_unique(shapes_seen, shapes)
        chunk_hash_count = _chunk_hash_count(row.get("chunk_hashes"))
        hash_counts.append(chunk_hash_count)
        if len(evidence.rows) < MAX_ROW_SUMMARIES:
            evidence.rows.append(_redacted_row(row, chunk_hash_count))
        else:
            evidence.truncated = True

    evidence.models = sorted(models)
    evidence.chunk_sizes = sorted(chunk_sizes)
    evidence.dtypes = dtypes_seen
    evidence.shapes = shapes_seen
    evidence.seq_len = _int_summary(seq_values)
    evidence.chunk_hash_count = _int_summary(hash_counts)
    evidence.claim_status = "measured" if evidence.row_count else "not_proven"
    return evidence.as_dict()


def _redacted_row(row: dict[str, Any], chunk_hash_count: int) -> dict[str, Any]:
    return {
        "timestamp": _safe_scalar(row.get("timestamp")),
        "request_id": _safe_scalar(row.get("request_id")),
        "model_name": _safe_scalar(row.get("model_name")),
        "chunk_size": _safe_scalar(row.get("chunk_size")),
        "seq_len": _safe_scalar(row.get("seq_len")),
        "dtypes": _safe_shape_value(row.get("dtypes")),
        "shapes": _safe_shape_value(row.get("shapes")),
        "chunk_hashes": {"redacted": True, "count": chunk_hash_count},
    }


def _collect_config_evidence(row: dict[str, Any], target: dict[str, Any]) -> None:
    sources = [row]
    config = row.get("config")
    if isinstance(config, dict):
        sources.append(config)
    for source in sources:
        for source_key, target_key in CONFIG_KEYS.items():
            if source_key in source and source[source_key] not in (None, ""):
                target[target_key] = _safe_scalar(source[source_key])


def _chunk_hash_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return len(value)
    if value in (None, ""):
        return 0
    return 1


def _int_summary(values: list[int]) -> dict[str, int]:
    if not values:
        return {"count": 0, "min": 0, "max": 0, "total": 0}
    return {"count": len(values), "min": min(values), "max": max(values), "total": sum(values)}


def _append_unique(values: list[Any], value: Any) -> None:
    if value is None:
        return
    if value not in values:
        values.append(value)


def _safe_shape_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_safe_shape_value(item) for item in value[:20]]
    if isinstance(value, dict):
        return {str(key): _safe_shape_value(val) for key, val in list(value.items())[:30]}
    return str(value)


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["SCHEMA_VERSION", "parse_lmcache_lookup_hash_jsonl"]
