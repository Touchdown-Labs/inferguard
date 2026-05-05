import json

from inferguard.analyze.exporters import RLM_TRACE_SCHEMA_VERSION, emit_rlm_trace


def test_emit_rlm_trace_writes_halo_compatible_span_rows(tmp_path) -> None:
    report = {
        "schema_version": "inferguard-analyze/v1.1",
        "generated_at": "2026-05-03T12:00:00Z",
        "input_root": "/tmp/results",
        "analyzer": {"inferguard_version": "0.5.0"},
        "run_summary": {"status": "partial", "total_cells": 1},
        "cross_run": {"worst_ttft_cell_id": "cell-a"},
        "cells": [
            {
                "cell_id": "cell-a",
                "source_format": "native-inferguard-bench",
                "hardware": "b200",
                "model": "deepseek-v4",
                "framework": "vllm",
                "precision": "fp4",
                "scenario_type": "kv-pressure",
                "concurrency": 16,
                "completion": {"status": "failed", "num_requests_total": 8},
                "metrics": {"p99_ttft": 2.5, "kv_cache_usage": 0.94},
                "topology": {"is_slurm": True, "provider": "gmi"},
                "artifacts": {"summary": "summary.json"},
                "findings": [
                    {
                        "code": "kv_transfer_stall",
                        "severity": "critical",
                        "message": "KV transfer stalled.",
                        "cell_id": "cell-a",
                    }
                ],
            }
        ],
        "findings": [
            {
                "code": "kv_transfer_stall",
                "severity": "critical",
                "message": "KV transfer stalled.",
                "cell_id": "cell-a",
            },
            {
                "code": "engine_unidentified",
                "severity": "warning",
                "message": "Could not identify engine.",
            },
        ],
    }

    path = emit_rlm_trace(report, tmp_path / "rlm_trace.jsonl")

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 4
    assert rows[0]["attributes"]["inferguard.schema_version"] == RLM_TRACE_SCHEMA_VERSION
    assert len(rows[0]["trace_id"]) == 32
    assert len(rows[0]["span_id"]) == 16
    assert rows[0]["scope"]["name"] == "inferguard.rlm_exporter"
    assert rows[0]["resource"]["attributes"]["service.name"] == "inferguard"
    assert rows[1]["parent_span_id"] == rows[0]["span_id"]
    assert rows[1]["attributes"]["inferguard.metrics"]["p99_ttft"] == 2.5
    assert rows[2]["status"]["code"] == "STATUS_CODE_ERROR"
    assert rows[2]["attributes"]["inferguard.finding_code"] == "kv_transfer_stall"
    assert rows[3]["name"] == "inferguard.finding.engine_unidentified"
