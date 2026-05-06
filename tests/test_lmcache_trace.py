from __future__ import annotations

import struct
import json
from pathlib import Path

from inferguard.lmcache_trace import parse_lmcache_trace_file


def _write_lct(path: Path, records: list[dict[str, object]]) -> None:
    chunks = []
    for record in records:
        payload = json.dumps(record).encode("utf-8")
        chunks.append(struct.pack(">I", len(payload)) + payload)
    path.write_bytes(b"".join(chunks))


def test_lmcache_trace_parses_storage_calls(tmp_path: Path) -> None:
    trace = tmp_path / "sample.lct"
    _write_lct(
        trace,
        [
            {"magic": "LMCT", "trace_level": "storage", "trace_schema_version": 1},
            {"qualname": "StorageManager.reserve_write", "relative_ts": 0.1, "args": {"keys": ["a"]}},
            {"qualname": "StorageManager.finish_write", "relative_ts": 0.2, "args": {"keys": ["a"]}},
            {"qualname": "StorageManager.submit_prefetch_task", "relative_ts": 0.3},
        ],
    )

    evidence = parse_lmcache_trace_file(trace)

    assert evidence["claim_status"] == "measured"
    assert evidence["record_count"] == 3
    assert evidence["header"]["magic"] == "LMCT"
    assert evidence["storage_calls"]["reserve_write"] == 1
    assert evidence["storage_calls"]["submit_prefetch_task"] == 1


def test_lmcache_trace_reports_malformed_file(tmp_path: Path) -> None:
    trace = tmp_path / "bad.lct"
    trace.write_bytes(struct.pack(">I", 100) + b"short")

    evidence = parse_lmcache_trace_file(trace)

    assert evidence["claim_status"] == "not_proven"
    assert "truncated_record" in evidence["parse_error"]
