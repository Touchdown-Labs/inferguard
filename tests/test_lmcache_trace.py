from __future__ import annotations

import json
import struct
from pathlib import Path

from inferguard.lmcache_trace import parse_lmcache_trace_file, parse_lmcache_trace_replay_file


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


def test_lmcache_trace_parses_real_msgpack_records(tmp_path: Path) -> None:
    import msgpack

    trace = tmp_path / "real_msgpack.lct"
    chunks = []
    for record in [
        {
            "magic": "LMCT",
            "format_version": 1,
            "level": "storage",
            "trace_schema_version": 1,
            "sm_config_digest": "abc",
        },
        {
            "qualname": "StorageManager.read_prefetched_results.__enter__",
            "t_mono": 1.0,
            "args": {"request_id": "req-a"},
        },
        {
            "qualname": "StorageManager.finish_read_prefetched",
            "t_mono": 1.2,
            "args": {"request_id": "req-a"},
        },
    ]:
        payload = msgpack.packb(record, use_bin_type=True)
        chunks.append(struct.pack(">I", len(payload)) + payload)
    trace.write_bytes(b"".join(chunks))

    evidence = parse_lmcache_trace_file(trace)

    assert evidence["claim_status"] == "measured"
    assert evidence["header"]["magic"] == "LMCT"
    assert evidence["storage_calls"]["__enter__"] == 1
    assert evidence["storage_calls"]["finish_read_prefetched"] == 1


def test_lmcache_trace_parses_trace_info_output(tmp_path: Path) -> None:
    info = tmp_path / "trace_info.txt"
    info.write_text(
        "\n".join(
            [
                "level: storage",
                "format_version: 1",
                "trace_schema_version: 2",
                "duration: 1.5",
                "sm_config_digest: abc123",
                "total_records: 12",
                "StorageManager.reserve_write: 3",
                "StorageManager.finish_write: 2",
            ]
        ),
        encoding="utf-8",
    )

    evidence = parse_lmcache_trace_replay_file(info)

    assert evidence["claim_status"] == "measured"
    assert evidence["source_kind"] == "trace_info"
    assert evidence["replay_info"]["level"] == "storage"
    assert evidence["replay_info"]["format_version"] == 1
    assert evidence["duration_s"] == 1.5
    assert evidence["op_counts"]["StorageManager.reserve_write"] == 3


def test_lmcache_trace_parses_replay_json_jsonl_and_ops_csv(tmp_path: Path) -> None:
    replay_json = tmp_path / "replay.json"
    replay_json.write_text(
        json.dumps(
            {
                "duration_s": 2.0,
                "ops": [
                    {
                        "qualname": "StorageManager.retrieve",
                        "count": 4,
                        "errors": 1,
                        "mean_ms": 10,
                        "p99_ms": 20,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    replay_jsonl = tmp_path / "replay.jsonl"
    replay_jsonl.write_text(
        "\n".join(
            [
                json.dumps({"qualname": "StorageManager.retrieve", "latency_ms": 4, "failed": False}),
                json.dumps({"qualname": "StorageManager.retrieve", "latency_ms": 8, "failed": True}),
                "not-json",
            ]
        ),
        encoding="utf-8",
    )
    ops_csv = tmp_path / "trace_replay_ops.csv"
    ops_csv.write_text(
        "qualname,count,errors,mean_ms,p50_ms,p90_ms,p99_ms,min_ms,max_ms\n"
        "StorageManager.store,5,0,11,10,15,20,9,21\n",
        encoding="utf-8",
    )

    json_evidence = parse_lmcache_trace_replay_file(replay_json)
    jsonl_evidence = parse_lmcache_trace_replay_file(replay_jsonl)
    csv_evidence = parse_lmcache_trace_replay_file(ops_csv)

    assert json_evidence["claim_status"] == "measured"
    assert json_evidence["source_kind"] == "json"
    assert json_evidence["duration_s"] == 2.0
    assert json_evidence["op_counts"]["StorageManager.retrieve"] == 4
    assert json_evidence["op_errors"]["StorageManager.retrieve"] == 1
    assert json_evidence["latency_ms"]["StorageManager.retrieve"]["max"] == 20.0

    assert jsonl_evidence["claim_status"] == "measured"
    assert jsonl_evidence["source_kind"] == "jsonl"
    assert jsonl_evidence["op_counts"]["StorageManager.retrieve"] == 2
    assert jsonl_evidence["op_errors"]["StorageManager.retrieve"] == 1
    assert jsonl_evidence["failed_rows"] == 1
    assert jsonl_evidence["parse_errors"]

    assert csv_evidence["claim_status"] == "measured"
    assert csv_evidence["source_kind"] == "ops_csv"
    assert csv_evidence["op_counts"]["StorageManager.store"] == 5
    assert csv_evidence["latency_ms"]["StorageManager.store"]["max"] == 21.0
