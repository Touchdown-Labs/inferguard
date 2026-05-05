from pathlib import Path

from inferguard.disagg.adapters import _parse_lmcache
from inferguard.disagg.adapters.lmcache import parse_lmcache_prometheus
from inferguard.disagg.metrics_schema import NORMALIZED_LMCACHE_FIELDS

FIXTURES = Path(__file__).parent / "fixtures" / "lmcache_metrics"


def test_lmcache_prometheus_fixture_parses_normalized_fields() -> None:
    metrics = parse_lmcache_prometheus((FIXTURES / "full.prom").read_text(encoding="utf-8"))

    assert "lmcache_hit_rate" in NORMALIZED_LMCACHE_FIELDS
    assert metrics.lmcache_enabled is True
    assert metrics.lmcache_hit_count == 90
    assert metrics.lmcache_miss_count == 10
    assert metrics.lmcache_hit_rate == 0.9
    assert metrics.lmcache_eviction_count == 3
    assert metrics.lmcache_save_count == 75
    assert metrics.lmcache_retrieve_count == 100
    assert metrics.lmcache_tier_hbm_bytes == 1073741824
    assert metrics.lmcache_tier_cpu_bytes == 2147483648
    assert metrics.lmcache_tier_disk_bytes == 3221225472
    assert metrics.lmcache_tier_remote_bytes == 536870912
    assert metrics.lmcache_offload_bytes_total == 268435456
    assert metrics.lmcache_retrieve_latency_ms_p50 == 1.5
    assert metrics.lmcache_retrieve_latency_ms_p95 == 8.25
    assert metrics.lmcache_retrieve_latency_ms_p99 == 12.5
    assert metrics.lmcache_nixl_transfer_bytes == 67108864
    assert metrics.lmcache_nixl_transfer_latency_ms == 4.0
    assert metrics.lmcache_cacheblend_enabled is True
    assert metrics.lmcache_cachegen_enabled is False
    assert metrics.lmcache_mp_mode_enabled is True
    assert metrics.lmcache_connector_type == "nixl"
    assert metrics.lmcache_cache_salt_enabled is True


def test_lmcache_adapter_snapshot_exposes_normalized_fields() -> None:
    snap = _parse_lmcache(
        (FIXTURES / "full.prom").read_text(encoding="utf-8"), url="http://lmcache", role="transfer"
    )

    assert snap.endpoint.engine == "lmcache"
    assert snap.endpoint.connector == "nixl"
    assert snap.lmcache_hit_rate == 0.9
    assert snap.lmcache_tier_disk_bytes == 3221225472
    assert snap.lmcache_tier_local_disk_bytes == 3221225472
    assert snap.lmcache_cache_salt_enabled is True
    assert snap.scrape_error == ""


def test_lmcache_unknown_metrics_are_preserved() -> None:
    snap = _parse_lmcache(
        (FIXTURES / "variant_unknown.prom").read_text(encoding="utf-8"),
        url="http://lmcache",
        role="prefill",
    )

    assert snap.lmcache_hit_rate == 0.625
    assert snap.lmcache_tier_cpu_bytes == 1024
    assert snap.lmcache_tier_disk_bytes == 2048
    assert snap.lmcache_remote_bytes_received == 256
    assert snap.lmcache_queue_depth == 7
    assert snap.raw_metrics_extra["lmcache_experimental_fragmentation_score"] == 0.42


def test_operator_brief_renders_lmcache_sections(tmp_path: Path) -> None:
    from inferguard.analyze.operator_brief import (
        build_operator_brief,
        render_operator_brief_markdown,
    )

    timeline = tmp_path / "cells" / "lmcache" / "metrics_timeline.jsonl"
    timeline.parent.mkdir(parents=True)
    timeline.write_text(
        '{"disagg_snapshot":{"lmcache_hit_count":9,"lmcache_miss_count":1,"lmcache_eviction_count":0,"lmcache_tier_cpu_bytes":1024,"lmcache_cache_salt_enabled":true}}\n',
        encoding="utf-8",
    )
    report = {
        "input_root": str(tmp_path),
        "cells": [
            {
                "cell_id": "baseline",
                "framework": "vllm",
                "scenario_type": "long_doc_qa",
                "topology": {"cache_mode": "native"},
                "completion": {"success_rate": 1.0},
                "metrics": {"p99_ttft": 2.0},
                "artifacts": {},
            },
            {
                "cell_id": "lmcache",
                "framework": "vllm",
                "scenario_type": "long_doc_qa",
                "topology": {"cache_mode": "lmcache-cpu"},
                "completion": {"success_rate": 1.0},
                "metrics": {"p99_ttft": 1.2},
                "artifacts": {
                    "inferguard_bench_metrics_timeline_jsonl": "cells/lmcache/metrics_timeline.jsonl"
                },
            },
        ],
        "findings": [],
        "artifact_manifest": [],
    }

    brief = build_operator_brief(report)
    md = render_operator_brief_markdown(brief)

    assert brief["lmcache_comparison"]["rows"][0]["claim_status"] == "measured"
    assert brief["measured_vs_inferred"]
    assert "## LMCache comparison" in md
    assert "## Measured vs inferred" in md
