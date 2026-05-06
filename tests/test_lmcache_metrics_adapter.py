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
    snap = _parse_lmcache((FIXTURES / "full.prom").read_text(encoding="utf-8"), url="http://lmcache", role="transfer")

    assert snap.endpoint.engine == "lmcache"
    assert snap.endpoint.connector == "nixl"
    assert snap.lmcache_hit_rate == 0.9
    assert snap.lmcache_tier_disk_bytes == 3221225472
    assert snap.lmcache_tier_local_disk_bytes == 3221225472
    assert snap.lmcache_cache_salt_enabled is True
    assert snap.scrape_error == ""


def test_lmcache_mp_prometheus_fixture_parses_normalized_fields() -> None:
    metrics = parse_lmcache_prometheus((FIXTURES / "mp.prom").read_text(encoding="utf-8"))

    assert metrics.lmcache_enabled is True
    assert metrics.lmcache_mp_mode_enabled is True
    assert metrics.lmcache_connector_type == "LMCacheMPConnector"
    assert metrics.lmcache_lookup_requested_tokens == 10000
    assert metrics.lmcache_lookup_hit_tokens == 6200
    assert metrics.lmcache_hit_count == 6200
    assert metrics.lmcache_miss_count == 3800
    assert metrics.lmcache_hit_rate == 0.62
    assert metrics.lmcache_eviction_count == 3
    assert metrics.lmcache_tier_cpu_bytes == 2147483648
    assert metrics.lmcache_l1_memory_usage_bytes == 2147483648
    assert metrics.lmcache_l2_store_completed == 7
    assert metrics.lmcache_l2_store_failed_keys == 1
    assert metrics.lmcache_event_bus_queue_depth == 0
    assert metrics.lmcache_event_bus_dropped_events_total == 0


def test_lmcache_mp_observability_doc_families_parse() -> None:
    metrics = parse_lmcache_prometheus(
        """
lmcache_mp_l1_chunk_lifetime_seconds_sum 30
lmcache_mp_l1_chunk_lifetime_seconds_count 3
lmcache_mp_l1_chunk_idle_before_evict_seconds_sum 20
lmcache_mp_l1_chunk_idle_before_evict_seconds_count 2
lmcache_mp_l1_chunk_reuse_gap_seconds_sum 12
lmcache_mp_l1_chunk_reuse_gap_seconds_count 4
lmcache_mp_l1_chunk_evict_reuse_gap_seconds_sum 9
lmcache_mp_l1_chunk_evict_reuse_gap_seconds_count 3
lmcache_mp_real_reuse_gap_seconds_sum{cache_salt="tenant-a"} 40
lmcache_mp_real_reuse_gap_seconds_count{cache_salt="tenant-a"} 4
lmcache_mp_real_reuse_gap_chunks_sum{cache_salt="tenant-a"} 100
lmcache_mp_real_reuse_gap_chunks_count{cache_salt="tenant-a"} 5
lmcache_mp_l2_store_tasks_total 10
lmcache_mp_l2_store_keys_total 20
lmcache_mp_l2_store_completed_total{l2_name="fs"} 9
lmcache_mp_l2_store_succeeded_keys_total 18
lmcache_mp_l2_store_failed_keys_total 2
lmcache_mp_l2_prefetch_lookups_total 11
lmcache_mp_l2_prefetch_lookup_keys_total 22
lmcache_mp_l2_prefetch_hit_keys_total 15
lmcache_mp_l2_prefetch_load_tasks_total 6
lmcache_mp_l2_prefetch_load_keys_total 12
lmcache_mp_l2_prefetch_loaded_keys_total 10
lmcache_mp_l2_prefetch_failed_keys_total 2
lmcache_mp_l2_load_completed_total{l2_name="fs"} 5
lmcache_mp_l2_store_throughput_gbs_sum{l2_name="fs"} 8
lmcache_mp_l2_store_throughput_gbs_count{l2_name="fs"} 2
lmcache_mp_l2_load_throughput_gbs_sum{l2_name="fs"} 6
lmcache_mp_l2_load_throughput_gbs_count{l2_name="fs"} 2
lmcache_mp_l0_l1_store_throughput_gbs_sum{engine_id="0"} 10
lmcache_mp_l0_l1_store_throughput_gbs_count{engine_id="0"} 2
lmcache_mp_l0_l1_load_throughput_gbs_sum{engine_id="0"} 14
lmcache_mp_l0_l1_load_throughput_gbs_count{engine_id="0"} 2
lmcache_mp_num_chunks_loaded_total{worker_id="0",model_name="Qwen/Qwen3-8B",cache_salt="tenant-a"} 33
lmcache_mp_inflight_load_memory_usage_bytes{l2_name="fs",adapter_index="0"} 4096
lmcache_mp_event_bus_queue_depth 7
lmcache_mp_event_bus_drain_lag_seconds 0.25
lmcache_mp_event_bus_dropped_events_total 3
lmcache_mp_event_bus_subscriber_exceptions_total 1
"""
    )

    assert metrics.lmcache_l1_chunk_lifetime_seconds == 10
    assert metrics.lmcache_l1_chunk_idle_before_evict_seconds == 10
    assert metrics.lmcache_l1_chunk_reuse_gap_seconds == 3
    assert metrics.lmcache_l1_chunk_evict_reuse_gap_seconds == 3
    assert metrics.lmcache_real_reuse_gap_seconds == 10
    assert metrics.lmcache_real_reuse_gap_chunks == 20
    assert metrics.lmcache_l2_store_tasks == 10
    assert metrics.lmcache_l2_store_keys == 20
    assert metrics.lmcache_l2_store_succeeded_keys == 18
    assert metrics.lmcache_l2_prefetch_lookups == 11
    assert metrics.lmcache_l2_prefetch_lookup_keys == 22
    assert metrics.lmcache_l2_prefetch_load_tasks == 6
    assert metrics.lmcache_l2_prefetch_load_keys == 12
    assert metrics.lmcache_l2_prefetch_failed_keys == 2
    assert metrics.lmcache_l2_load_completed == 5
    assert metrics.lmcache_l2_store_throughput_gbs == 4
    assert metrics.lmcache_l2_load_throughput_gbs == 3
    assert metrics.lmcache_l0_l1_store_throughput_gbs == 5
    assert metrics.lmcache_l0_l1_load_throughput_gbs == 7
    assert metrics.lmcache_num_chunks_loaded == 33
    assert metrics.lmcache_inflight_load_memory_usage_bytes == 4096
    assert metrics.lmcache_event_bus_queue_depth == 7
    assert metrics.lmcache_event_bus_drain_lag_seconds == 0.25
    assert metrics.lmcache_event_bus_dropped_events_total == 3
    assert metrics.lmcache_event_bus_subscriber_exceptions_total == 1


def test_lmcache_real_modal_mp_slice_parses_storage_and_l0_fields() -> None:
    metrics = parse_lmcache_prometheus((FIXTURES / "mp_modal_real_slice.prom").read_text(encoding="utf-8"))

    assert metrics.lmcache_enabled is True
    assert metrics.lmcache_mp_mode_enabled is True
    assert metrics.lmcache_connector_type == "LMCacheMPConnector"
    assert metrics.lmcache_sm_read_requests == 149
    assert metrics.lmcache_sm_read_succeed_keys == 3335
    assert metrics.lmcache_sm_write_failed_keys == 1655
    assert metrics.lmcache_l1_read_keys == 3545
    assert metrics.lmcache_l1_evicted_keys == 1650
    assert metrics.lmcache_l0_block_lifetime_seconds is not None
    assert metrics.lmcache_l0_block_lifetime_seconds > 400


def test_lmcache_unknown_metrics_are_preserved() -> None:
    snap = _parse_lmcache((FIXTURES / "variant_unknown.prom").read_text(encoding="utf-8"), url="http://lmcache", role="prefill")

    assert snap.lmcache_hit_rate == 0.625
    assert snap.lmcache_tier_cpu_bytes == 1024
    assert snap.lmcache_tier_disk_bytes == 2048
    assert snap.lmcache_remote_bytes_received == 256
    assert snap.lmcache_queue_depth == 7
    assert snap.raw_metrics_extra["lmcache_experimental_fragmentation_score"] == 0.42


def test_lmcache_production_observability_metrics_parse() -> None:
    metrics = parse_lmcache_prometheus(
        """
lmcache:num_retrieve_requests_total 11
lmcache:num_store_requests_total 7
lmcache:num_lookup_requests_total 13
lmcache:num_requested_tokens_total 1000
lmcache:num_hit_tokens_total 600
lmcache:num_lookup_tokens_total 900
lmcache:num_lookup_hits_total 500
lmcache:is_healthy 1
lmcache:storage_event_count_total 99
lmcache:remote_read_bytes_total 1024
lmcache:remote_write_bytes_total 2048
lmcache:remote_ping_latency_seconds 0.004
lmcache:remote_ping_errors_total 2
lmcache:num_p2p_requests_total 3
lmcache:num_p2p_transferred_tokens_total 128
lmcache:p2p_time_to_transfer_seconds 0.05
lmcache:p2p_transfer_speed 10
lmcache:chunk_stats_enabled 1
lmcache:total_chunk_requests_total 44
lmcache:total_chunks 30
lmcache:unique_chunks 20
"""
    )

    assert metrics.lmcache_num_retrieve_requests == 11
    assert metrics.lmcache_num_store_requests == 7
    assert metrics.lmcache_num_lookup_requests == 13
    assert metrics.lmcache_num_requested_tokens == 1000
    assert metrics.lmcache_num_hit_tokens == 600
    assert metrics.lmcache_num_lookup_tokens == 900
    assert metrics.lmcache_num_lookup_hits == 500
    assert metrics.lmcache_is_healthy is True
    assert metrics.lmcache_storage_event_count == 99
    assert metrics.lmcache_remote_read_bytes == 1024
    assert metrics.lmcache_remote_write_bytes == 2048
    assert metrics.lmcache_remote_ping_latency_ms == 4
    assert metrics.lmcache_remote_ping_errors == 2
    assert metrics.lmcache_p2p_requests == 3
    assert metrics.lmcache_p2p_transferred_tokens == 128
    assert metrics.lmcache_p2p_time_to_transfer_ms == 50
    assert metrics.lmcache_p2p_transfer_speed == 10
    assert metrics.lmcache_chunk_stats_enabled is True
    assert metrics.lmcache_total_chunk_requests == 44
    assert metrics.lmcache_total_chunks == 30
    assert metrics.lmcache_unique_chunks == 20


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
                "artifacts": {"inferguard_bench_metrics_timeline_jsonl": "cells/lmcache/metrics_timeline.jsonl"},
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
