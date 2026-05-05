import json
from pathlib import Path

from inferguard.analyze.operator_brief import build_operator_brief, render_operator_brief_markdown


def test_operator_brief_includes_lmcache_and_measured_vs_inferred_tables(tmp_path: Path) -> None:
    timeline = tmp_path / "runs" / "lmcache" / "metrics_timeline.jsonl"
    timeline.parent.mkdir(parents=True)
    timeline.write_text(
        json.dumps(
            {
                "disagg_snapshot": {
                    "lmcache_hit_count": 90,
                    "lmcache_miss_count": 10,
                    "lmcache_hit_rate": 0.9,
                    "lmcache_eviction_count": 1,
                    "lmcache_tier_hbm_bytes": 1024,
                    "lmcache_tier_cpu_bytes": 2048,
                    "lmcache_tier_disk_bytes": 4096,
                    "lmcache_offload_bytes_total": 8192,
                    "lmcache_retrieve_latency_ms_p95": 7.5,
                    "lmcache_cacheblend_enabled": True,
                    "lmcache_cache_salt_enabled": True,
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report = {
        "input_root": str(tmp_path),
        "cells": [
            {
                "cell_id": "vllm-baseline",
                "framework": "vllm",
                "scenario_type": "multi_round_chat",
                "topology": {"cache_mode": "native"},
                "completion": {"success_rate": 1.0},
                "metrics": {"p99_ttft": 2.0},
                "artifacts": {},
            },
            {
                "cell_id": "vllm-lmcache",
                "framework": "vllm",
                "scenario_type": "multi_round_chat",
                "topology": {"cache_mode": "lmcache-cpu", "slurm_job_id": "123"},
                "completion": {"success_rate": 1.0},
                "metrics": {"p99_ttft": 1.1},
                "artifacts": {"inferguard_bench_metrics_timeline_jsonl": "runs/lmcache/metrics_timeline.jsonl"},
            },
        ],
        "findings": [],
        "artifact_manifest": [],
    }

    brief = build_operator_brief(report)
    md = render_operator_brief_markdown(brief)

    assert brief["lmcache_comparison"]["schema_version"] == "inferguard-lmcache-comparison/v1"
    assert brief["lmcache_comparison"]["rows"][0]["claim_status"] == "measured"
    assert any(row["claim"] == "eviction occurred" and row["status"] == "measured" for row in brief["measured_vs_inferred"])
    assert any(row["claim"] == "cross-tenant isolation" and row["status"] == "measured" for row in brief["measured_vs_inferred"])
    assert "## LMCache comparison" in md
    assert "## Measured vs inferred" in md
    assert "| Claim | Status | Evidence |" in md
