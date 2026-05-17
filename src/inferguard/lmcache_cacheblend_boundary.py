"""CacheBlend L0 boundary evidence helpers.

The LMCache upstream evidence file is intentionally opt-in JSONL. It can carry
request-scoped lifecycle checkpoints for CacheBlend L0 GPU movement, but
InferGuard must never surface raw token IDs, block IDs, hashes, or object keys in
reports.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

_FORBIDDEN_KEYS = frozenset({"token_ids", "block_ids", "hashes", "object_keys"})


def read_cacheblend_boundary_evidence_jsonl(path: Path | None) -> dict[str, Any] | None:
    """Read a redacted CacheBlend L0 boundary evidence JSONL summary.

    Only shape-level lifecycle fields are retained. Raw token/block/hash/object
    identifiers are ignored even when present in the input file.
    """

    if path is None:
        return None
    event_counts: Counter[str] = Counter()
    stages: set[str] = set()
    row_count = 0
    parse_errors = 0
    safe_rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {
            "present": False,
            "claim_status": "not_proven",
            "row_count": 0,
            "event_counts": {},
            "stages": [],
            "parse_errors": 1,
            "records": [],
        }

    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        if not isinstance(payload, dict):
            parse_errors += 1
            continue

        row_count += 1
        stage = _safe_str(payload.get("stage") or payload.get("operation"))
        event = _safe_str(payload.get("event") or payload.get("phase"))
        if stage:
            stages.add(stage)
        key = f"{stage}.{event}" if stage and event else stage or event or "unknown"
        event_counts[key] += 1

        safe_row: dict[str, Any] = {}
        for key_name in ("stage", "operation", "event", "phase", "request_id"):
            value = payload.get(key_name)
            if isinstance(value, str) and value:
                safe_row[key_name] = value
        for key_name in ("chunk_count", "num_chunks", "token_count", "num_tokens"):
            value = payload.get(key_name)
            if isinstance(value, int | float) and not isinstance(value, bool):
                safe_row[key_name] = value
        if isinstance(payload.get("success"), bool):
            safe_row["success"] = payload["success"]
        if safe_row:
            safe_rows.append(safe_row)

    return {
        "present": True,
        "claim_status": "measured" if row_count > 0 else "not_proven",
        "row_count": row_count,
        "event_counts": dict(sorted(event_counts.items())),
        "stages": sorted(stages),
        "parse_errors": parse_errors,
        "records": safe_rows,
    }


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


__all__ = ["read_cacheblend_boundary_evidence_jsonl"]
