from pathlib import Path

import pytest

from inferguard.compat import build_compat_report
from inferguard.disagg.adapters import _parse_lmcache
from inferguard.disagg.adapters.lmcache import parse_lmcache_prometheus
from inferguard.disagg.metrics_schema import NORMALIZED_LMCACHE_FIELDS

FIXTURES = Path(__file__).parent / "fixtures" / "lmcache_metrics"

MP_COUNTER_FIELDS = (
    ("lmcache_mp.lookup_requested_tokens", "lmcache_lookup_requested_tokens"),
    ("lmcache_mp.lookup_hit_tokens", "lmcache_lookup_hit_tokens"),
    ("lmcache_mp.sm_read_requests", "lmcache_sm_read_requests"),
    ("lmcache_mp.sm_read_succeed_keys", "lmcache_sm_read_succeed_keys"),
    ("lmcache_mp.sm_read_failed_keys", "lmcache_sm_read_failed_keys"),
    ("lmcache_mp.sm_write_requests", "lmcache_sm_write_requests"),
    ("lmcache_mp.sm_write_succeed_keys", "lmcache_sm_write_succeed_keys"),
    ("lmcache_mp.sm_write_failed_keys", "lmcache_sm_write_failed_keys"),
    ("lmcache_mp.l1_read_keys", "lmcache_l1_read_keys"),
    ("lmcache_mp.l1_write_keys", "lmcache_l1_write_keys"),
    ("lmcache_mp.l1_evicted_keys", "lmcache_l1_evicted_keys"),
    ("lmcache_mp.l1_allocation_failure", "lmcache_l1_allocation_failure"),
    ("lmcache_mp.l1_read_failure", "lmcache_l1_read_failure"),
    ("lmcache_mp.l2_store_tasks", "lmcache_l2_store_tasks"),
    ("lmcache_mp.l2_store_keys", "lmcache_l2_store_keys"),
    ("lmcache_mp.l2_store_completed", "lmcache_l2_store_completed"),
    ("lmcache_mp.l2_store_succeeded_keys", "lmcache_l2_store_succeeded_keys"),
    ("lmcache_mp.l2_store_failed_keys", "lmcache_l2_store_failed_keys"),
    ("lmcache_mp.l2_prefetch_lookups", "lmcache_l2_prefetch_lookups"),
    ("lmcache_mp.l2_prefetch_lookup_keys", "lmcache_l2_prefetch_lookup_keys"),
    ("lmcache_mp.l2_prefetch_hit_keys", "lmcache_l2_prefetch_hit_keys"),
    ("lmcache_mp.l2_prefetch_load_tasks", "lmcache_l2_prefetch_load_tasks"),
    ("lmcache_mp.l2_prefetch_load_keys", "lmcache_l2_prefetch_load_keys"),
    ("lmcache_mp.l2_prefetch_loaded_keys", "lmcache_l2_prefetch_loaded_keys"),
    ("lmcache_mp.l2_prefetch_failed_keys", "lmcache_l2_prefetch_failed_keys"),
    ("lmcache_mp.l2_prefetch_failure", "lmcache_l2_prefetch_failure"),
    ("lmcache_mp.l2_load_completed", "lmcache_l2_load_completed"),
    ("lmcache_mp.num_chunks_loaded", "lmcache_num_chunks_loaded"),
    ("lmcache_mp.event_bus.dropped_events", "lmcache_event_bus_dropped_events_total"),
    ("lmcache_mp.event_bus.subscriber_exceptions", "lmcache_event_bus_subscriber_exceptions_total"),
)

MP_GAUGE_FIELDS = (
    ("lmcache_mp.l1_memory_usage_bytes", "lmcache_l1_memory_usage_bytes"),
    ("lmcache_mp.active_prefetch_jobs", "lmcache_active_prefetch_jobs"),
    ("lmcache_mp.num_inflight_l2_stores", "lmcache_num_inflight_l2_stores"),
    ("lmcache_mp.num_inflight_l2_loads", "lmcache_num_inflight_l2_loads"),
    ("lmcache_mp.inflight_load_memory_usage_bytes", "lmcache_inflight_load_memory_usage_bytes"),
    ("lmcache_mp.event_bus.queue_depth", "lmcache_event_bus_queue_depth"),
)

MP_HIST_FIELDS = (
    ("lmcache_mp.l1_chunk_lifetime_seconds", "lmcache_l1_chunk_lifetime_seconds"),
    ("lmcache_mp.l1_chunk_idle_before_evict_seconds", "lmcache_l1_chunk_idle_before_evict_seconds"),
    ("lmcache_mp.l1_chunk_reuse_gap_seconds", "lmcache_l1_chunk_reuse_gap_seconds"),
    ("lmcache_mp.l1_chunk_evict_reuse_gap_seconds", "lmcache_l1_chunk_evict_reuse_gap_seconds"),
    ("lmcache_mp.real_reuse_gap_seconds", "lmcache_real_reuse_gap_seconds"),
    ("lmcache_mp.real_reuse_gap_chunks", "lmcache_real_reuse_gap_chunks"),
    ("lmcache_mp.l0_block_lifetime_seconds", "lmcache_l0_block_lifetime_seconds"),
    ("lmcache_mp.l0_block_idle_before_evict_seconds", "lmcache_l0_block_idle_before_evict_seconds"),
    ("lmcache_mp.l0_block_reuse_gap_seconds", "lmcache_l0_block_reuse_gap_seconds"),
    ("lmcache_mp.l0_l1_store_throughput_gbs", "lmcache_l0_l1_store_throughput_gbs"),
    ("lmcache_mp.l0_l1_load_throughput_gbs", "lmcache_l0_l1_load_throughput_gbs"),
    ("lmcache_mp.l2_store_throughput_gbs", "lmcache_l2_store_throughput_gbs"),
    ("lmcache_mp.l2_load_throughput_gbs", "lmcache_l2_load_throughput_gbs"),
    ("lmcache_mp.event_bus.drain_lag_seconds", "lmcache_event_bus_drain_lag_seconds"),
)


def _mp_name_variants(canonical: str, *, counter: bool = False) -> tuple[str, ...]:
    names = [canonical, canonical.replace(".", "_")]
    if counter:
        names.extend(f"{name}_total" for name in tuple(names))
    return tuple(dict.fromkeys(names))


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
lmcache_mp_l2_prefetch_failure_total 1
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
lmcache_mp_l1_allocation_failure_total 2
lmcache_mp_l1_read_failure_total 1
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
    assert metrics.lmcache_l2_prefetch_failure == 1
    assert metrics.lmcache_l2_load_completed == 5
    assert metrics.lmcache_l1_allocation_failure == 2
    assert metrics.lmcache_l1_read_failure == 1
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


def test_lmcache_l2_label_split_counters_gauges_and_throughput_aggregate() -> None:
    metrics = parse_lmcache_prometheus(
        """
lmcache_mp_l2_store_tasks_total{l2_name="fs"} 4
lmcache_mp_l2_store_tasks_total{l2_name="s3"} 6
lmcache_mp_l2_store_completed_total{l2_name="fs"} 2
lmcache_mp_l2_store_completed_total{l2_name="s3"} 3
lmcache_mp_l2_prefetch_load_tasks_total{l2_name="fs"} 1
lmcache_mp_l2_prefetch_load_tasks_total{l2_name="s3"} 2
lmcache_mp_l2_prefetch_loaded_keys_total{l2_name="fs"} 5
lmcache_mp_l2_prefetch_loaded_keys_total{l2_name="s3"} 7
lmcache_mp_l2_store_throughput_gbs_sum{l2_name="fs"} 1
lmcache_mp_l2_store_throughput_gbs_count{l2_name="fs"} 2
lmcache_mp_l2_store_throughput_gbs_sum{l2_name="s3"} 3
lmcache_mp_l2_store_throughput_gbs_count{l2_name="s3"} 2
lmcache_mp_l2_load_throughput_gbs_sum{l2_name="fs"} 0.2
lmcache_mp_l2_load_throughput_gbs_count{l2_name="fs"} 2
lmcache_mp_l2_load_throughput_gbs_sum{l2_name="s3"} 0.4
lmcache_mp_l2_load_throughput_gbs_count{l2_name="s3"} 2
lmcache_mp_num_inflight_l2_stores{l2_name="fs",adapter_index="0"} 2
lmcache_mp_num_inflight_l2_stores{l2_name="s3",adapter_index="1"} 3
lmcache_mp_num_inflight_l2_loads{l2_name="fs",adapter_index="0"} 1
lmcache_mp_num_inflight_l2_loads{l2_name="s3",adapter_index="1"} 4
lmcache_mp_inflight_load_memory_usage_bytes{l2_name="fs",adapter_index="0"} 1024
lmcache_mp_inflight_load_memory_usage_bytes{l2_name="s3",adapter_index="1"} 2048
lmcache_mp_active_prefetch_jobs 2
"""
    )

    assert metrics.lmcache_l2_store_tasks == 10
    assert metrics.lmcache_l2_store_completed == 5
    assert metrics.lmcache_l2_prefetch_load_tasks == 3
    assert metrics.lmcache_l2_prefetch_loaded_keys == 12
    assert metrics.lmcache_l2_store_throughput_gbs == 1
    assert metrics.lmcache_l2_load_throughput_gbs == pytest.approx(0.15)
    assert metrics.lmcache_num_inflight_l2_stores == 5
    assert metrics.lmcache_num_inflight_l2_loads == 5
    assert metrics.lmcache_inflight_load_memory_usage_bytes == 3072
    assert metrics.lmcache_active_prefetch_jobs == 2


def test_lmcache_l2_status_rows_summaries_and_diagnostics_are_fixture_backed() -> None:
    report = build_compat_report(
        lmcache_text="""
lmcache_mp_sm_read_requests_total 10
lmcache_mp_l1_read_keys_total 10
lmcache_mp_l2_store_tasks_total{l2_name="fs"} 10
lmcache_mp_l2_store_completed_total{l2_name="fs"} 1
lmcache_mp_l2_store_succeeded_keys_total{l2_name="fs"} 1
lmcache_mp_l2_prefetch_load_tasks_total{l2_name="fs"} 6
lmcache_mp_l2_prefetch_load_keys_total{l2_name="fs"} 12
lmcache_mp_l2_prefetch_loaded_keys_total{l2_name="fs"} 2
lmcache_mp_l2_load_completed_total{l2_name="fs"} 1
lmcache_mp_l2_store_throughput_gbs_sum{l2_name="fs"} 0.05
lmcache_mp_l2_store_throughput_gbs_count{l2_name="fs"} 1
lmcache_mp_l2_load_throughput_gbs_sum{l2_name="fs"} 0.04
lmcache_mp_l2_load_throughput_gbs_count{l2_name="fs"} 1
lmcache_mp_num_inflight_l2_stores{l2_name="fs",adapter_index="0"} 4
lmcache_mp_num_inflight_l2_loads{l2_name="fs",adapter_index="0"} 3
lmcache_mp_inflight_load_memory_usage_bytes{l2_name="fs",adapter_index="0"} 8192
lmcache_mp_active_prefetch_jobs 2
""",
        expect_mode="mp",
        l2_configured=True,
    )

    families = {(row["surface"], row["family"]): row for row in report["families"]}
    assert families[("lmcache_mp", "l2_counters")]["status"] == "populated"
    assert families[("lmcache_mp", "l2_throughput")]["status"] == "populated"
    assert families[("lmcache_mp", "l2_inflight_gauges")]["status"] == "populated"
    assert report["lmcache_l2_summary"]["store_backlog"] is True
    assert report["lmcache_l2_summary"]["load_backlog"] is True
    assert report["lmcache_l2_summary"]["store_throughput_gbs"] == 0.05
    codes = {item["code"] for item in report["diagnostic_findings"]}
    assert "lmcache_mp_l2_store_backlog" in codes
    assert "lmcache_mp_l2_load_backlog" in codes
    assert "lmcache_mp_l2_throughput_low" in codes


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


@pytest.mark.parametrize(("canonical", "field_name"), MP_COUNTER_FIELDS)
def test_lmcache_mp_counter_spellings_parse(canonical: str, field_name: str) -> None:
    for metric_name in _mp_name_variants(canonical, counter=True):
        metrics = parse_lmcache_prometheus(f'{metric_name}{{cache_salt="tenant-a",l2_name="fs"}} 7\n')
        assert getattr(metrics, field_name) == 7
        assert metrics.lmcache_enabled is True
        assert metrics.lmcache_mp_mode_enabled is True


@pytest.mark.parametrize(("canonical", "field_name"), MP_GAUGE_FIELDS)
def test_lmcache_mp_gauge_spellings_parse(canonical: str, field_name: str) -> None:
    for metric_name in _mp_name_variants(canonical):
        metrics = parse_lmcache_prometheus(f'{metric_name}{{l2_name="fs",adapter_index="0"}} 7\n')
        assert getattr(metrics, field_name) == 7
        assert metrics.lmcache_enabled is True
        assert metrics.lmcache_mp_mode_enabled is True


@pytest.mark.parametrize(("canonical", "field_name"), MP_HIST_FIELDS)
def test_lmcache_mp_histogram_spellings_parse(canonical: str, field_name: str) -> None:
    for metric_name in _mp_name_variants(canonical):
        metrics = parse_lmcache_prometheus(
            f'{metric_name}_sum{{cache_salt="tenant-a",l2_name="fs"}} 12\n'
            f'{metric_name}_count{{cache_salt="tenant-a",l2_name="fs"}} 3\n'
        )
        assert getattr(metrics, field_name) == 4
        assert metrics.lmcache_enabled is True
        assert metrics.lmcache_mp_mode_enabled is True


def test_lmcache_mp_registry_recognizes_dotted_source_names_and_prometheus_names() -> None:
    dotted_report = build_compat_report(
        lmcache_text="""
lmcache_mp.sm_read_requests 1
lmcache_mp.lookup_requested_tokens{cache_salt="tenant-a"} 10
lmcache_mp.lookup_hit_tokens{cache_salt="tenant-a"} 8
lmcache_mp.l1_read_keys 2
lmcache_mp.l1_memory_usage_bytes 2048
lmcache_mp.l1_allocation_failure 1
lmcache_mp.l1_chunk_reuse_gap_seconds_sum 6
lmcache_mp.l1_chunk_reuse_gap_seconds_count 2
lmcache_mp.l0_block_lifetime_seconds_sum 8
lmcache_mp.l0_block_lifetime_seconds_count 2
lmcache_mp.real_reuse_gap_seconds_sum 12
lmcache_mp.real_reuse_gap_seconds_count 3
lmcache_mp.l2_store_tasks{l2_name="fs"} 5
lmcache_mp.l2_prefetch_failure{l2_name="fs"} 1
lmcache_mp.l2_store_throughput_gbs_sum{l2_name="fs"} 4
lmcache_mp.l2_store_throughput_gbs_count{l2_name="fs"} 2
lmcache_mp.l0_l1_store_throughput_gbs_sum 10
lmcache_mp.l0_l1_store_throughput_gbs_count 2
lmcache_mp.num_chunks_loaded 3
lmcache_mp.active_prefetch_jobs 1
lmcache_mp.num_inflight_l2_stores{l2_name="fs"} 1
lmcache_mp.event_bus.queue_depth 2
lmcache_mp.event_bus.dropped_events 1
""",
        expect_mode="mp",
        l2_configured=True,
    )
    prom_report = build_compat_report(
        lmcache_text="""
lmcache_mp_sm_read_requests_total 1
lmcache_mp_lookup_requested_tokens_total{cache_salt="tenant-a"} 10
lmcache_mp_lookup_hit_tokens_total{cache_salt="tenant-a"} 8
lmcache_mp_l1_read_keys_total 2
lmcache_mp_l1_memory_usage_bytes 2048
lmcache_mp_l1_allocation_failure_total 1
lmcache_mp_l1_chunk_reuse_gap_seconds_sum 6
lmcache_mp_l1_chunk_reuse_gap_seconds_count 2
lmcache_mp_l0_block_lifetime_seconds_sum 8
lmcache_mp_l0_block_lifetime_seconds_count 2
lmcache_mp_real_reuse_gap_seconds_sum 12
lmcache_mp_real_reuse_gap_seconds_count 3
lmcache_mp_l2_store_tasks_total{l2_name="fs"} 5
lmcache_mp_l2_prefetch_failure_total{l2_name="fs"} 1
lmcache_mp_l2_store_throughput_gbs_sum{l2_name="fs"} 4
lmcache_mp_l2_store_throughput_gbs_count{l2_name="fs"} 2
lmcache_mp_l0_l1_store_throughput_gbs_sum 10
lmcache_mp_l0_l1_store_throughput_gbs_count 2
lmcache_mp_num_chunks_loaded_total 3
lmcache_mp_active_prefetch_jobs 1
lmcache_mp_num_inflight_l2_stores{l2_name="fs"} 1
lmcache_mp_event_bus_queue_depth 2
lmcache_mp_event_bus_dropped_events_total 1
""",
        expect_mode="mp",
        l2_configured=True,
    )

    for report in (dotted_report, prom_report):
        families = {(row["surface"], row["family"]): row for row in report["families"]}
        assert report["detected_mode"] == "mp"
        assert report["observed"]["lmcache_mp"] is True
        assert families[("lmcache_mp", "storage_manager")]["status"] == "populated"
        assert families[("lmcache_mp", "lookup_tokens")]["status"] == "populated"
        assert families[("lmcache_mp", "l1_counters")]["status"] == "populated"
        assert families[("lmcache_mp", "l1_memory")]["status"] == "populated"
        assert families[("lmcache_mp", "l1_failures")]["status"] == "populated"
        assert families[("lmcache_mp", "l1_lifecycle")]["status"] == "populated"
        assert families[("lmcache_mp", "l0_lifecycle")]["status"] == "populated"
        assert families[("lmcache_mp", "real_reuse")]["status"] == "populated"
        assert families[("lmcache_mp", "l2_counters")]["status"] == "populated"
        assert families[("lmcache_mp", "l2_failures")]["status"] == "populated"
        assert families[("lmcache_mp", "l2_throughput")]["status"] == "populated"
        assert families[("lmcache_mp", "l0_l1_throughput")]["status"] == "populated"
        assert families[("lmcache_mp", "engine_counters")]["status"] == "populated"
        assert families[("lmcache_mp", "gauges")]["status"] == "populated"
        assert families[("lmcache_mp", "event_bus")]["status"] == "populated"
        assert report["lmcache_l2_summary"]["observed"] is True
        assert any(item["code"] == "lmcache_mp_l2_failures" for item in report["diagnostic_findings"])


def test_lmcache_otel_push_mode_uses_live_evidence_when_prometheus_mp_metrics_are_unavailable() -> None:
    report = build_compat_report(
        engine_text="vllm:request_success_total{finished_reason=\"stop\"} 1\n",
        lmcache_text="",
        expect_mode="mp",
        mp_observability={"tracing_enabled": True},
        lmcache_http_evidence={
            "booleans": {"is_healthy": True},
            "endpoints": {"status": {"fields": {"engine_type": "MPCacheEngine"}}},
        },
        lmcache_log_evidence={"mode_candidates": ["mp"]},
        lmcache_otel_evidence={"claim_status": "measured", "mp_span_count": 3},
    )

    assert report["detected_mode"] == "mp"
    assert report["observed"]["lmcache_mp"] is False
    assert report["observed"]["lmcache_mp_evidence"] is True
    assert report["observed"]["lmcache_mp_metrics_prometheus_unavailable"] is True
    assert report["failure_reasons"] == []
    families = {(row["surface"], row["family"]): row for row in report["families"]}
    assert families[("lmcache_mp", "storage_manager")]["status"] == "not_applicable"
    assert report["surfaces"]["lmcache_otel"]["status"] == "complete"


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


def test_lmcache_production_metrics_reference_families_parse_fixture() -> None:
    metrics = parse_lmcache_prometheus((FIXTURES / "production_full.prom").read_text(encoding="utf-8"))

    assert metrics.lmcache_num_retrieve_requests == 11
    assert metrics.lmcache_num_stored_tokens == 700
    assert metrics.lmcache_num_vllm_hit_tokens == 400
    assert metrics.lmcache_num_prompt_tokens == 1200
    assert metrics.lmcache_retrieve_hit_rate == 0.6
    assert metrics.lmcache_lookup_hit_rate == 0.55
    assert metrics.lmcache_request_cache_hit_rate == 0.6
    assert metrics.lmcache_lookup_0_hit_requests == 4
    assert metrics.lmcache_time_to_retrieve_seconds == pytest.approx(0.02)
    assert metrics.lmcache_time_to_store_seconds == pytest.approx(0.05)
    assert metrics.lmcache_time_to_lookup_seconds == pytest.approx(0.01)
    assert metrics.lmcache_retrieve_speed_tokens_per_second == 1000
    assert metrics.lmcache_store_speed_tokens_per_second == 500
    assert metrics.lmcache_num_slow_retrieval_by_time == 2
    assert metrics.lmcache_num_slow_retrieval_by_speed == 1
    assert metrics.lmcache_retrieve_process_tokens_time_seconds == pytest.approx(0.01)
    assert metrics.lmcache_retrieve_broadcast_time_seconds == pytest.approx(0.02)
    assert metrics.lmcache_retrieve_to_gpu_time_seconds == pytest.approx(0.03)
    assert metrics.lmcache_store_process_tokens_time_seconds == pytest.approx(0.04)
    assert metrics.lmcache_store_from_gpu_time_seconds == pytest.approx(0.05)
    assert metrics.lmcache_store_put_time_seconds == pytest.approx(0.06)
    assert metrics.lmcache_remote_backend_batched_get_blocking_time_seconds == pytest.approx(0.07)
    assert metrics.lmcache_instrumented_connector_batched_get_time_seconds == pytest.approx(0.08)
    assert metrics.lmcache_local_cache_usage_bytes == 1024
    assert metrics.lmcache_remote_cache_usage_bytes == 2048
    assert metrics.lmcache_local_storage_usage_bytes == 4096
    assert metrics.lmcache_request_cache_lifespan_minutes == 15
    assert metrics.lmcache_num_remote_read_requests == 5
    assert metrics.lmcache_remote_read_bytes == 111
    assert metrics.lmcache_num_remote_write_requests == 6
    assert metrics.lmcache_remote_write_bytes == 222
    assert metrics.lmcache_remote_time_to_get_ms == 4
    assert metrics.lmcache_remote_time_to_put_ms == 5
    assert metrics.lmcache_remote_time_to_get_sync_ms == 7
    assert metrics.lmcache_remote_ping_latency_ms == 3.5
    assert metrics.lmcache_remote_ping_successes == 8
    assert metrics.lmcache_remote_ping_error_code == 503
    assert metrics.lmcache_local_cpu_evict_count == 1
    assert metrics.lmcache_local_cpu_evict_keys_count == 2
    assert metrics.lmcache_local_cpu_evict_failed_count == 3
    assert metrics.lmcache_local_cpu_hot_cache_count == 4
    assert metrics.lmcache_local_cpu_keys_in_request_count == 5
    assert metrics.lmcache_active_memory_objs_count == 6
    assert metrics.lmcache_pinned_memory_objs_count == 7
    assert metrics.lmcache_forced_unpin_count == 8
    assert metrics.lmcache_pin_monitor_pinned_objects_count == 9
    assert metrics.lmcache_p2p_time_to_transfer_ms == 50
    assert metrics.lmcache_p2p_transfer_speed == 10
    assert metrics.lmcache_get_blocking_failed_count == 10
    assert metrics.lmcache_put_failed_count == 11
    assert metrics.lmcache_kv_msg_queue_size == 12
    assert metrics.lmcache_remote_put_task_num == 13
    assert metrics.lmcache_chunk_stats_enabled is True
    assert metrics.lmcache_total_chunk_requests == 44
    assert metrics.lmcache_total_chunks == 30
    assert metrics.lmcache_unique_chunks == 20
    assert metrics.lmcache_chunk_statistics_reuse_rate == 0.25
    assert metrics.lmcache_chunk_statistics_bloom_filter_size_mb == 11.5
    assert metrics.lmcache_chunk_statistics_bloom_filter_fill_rate == 0.1
    assert metrics.lmcache_chunk_statistics_file_count == 2
    assert metrics.lmcache_chunk_statistics_current_file_size == 8192
    assert metrics.lmcache_scheduler_unfinished_requests_count == 1
    assert metrics.lmcache_connector_load_specs_count == 2
    assert metrics.lmcache_connector_request_trackers_count == 3
    assert metrics.lmcache_connector_kv_caches_count == 4
    assert metrics.lmcache_connector_layerwise_retrievers_count == 5
    assert metrics.lmcache_connector_invalid_block_ids_count == 6
    assert metrics.lmcache_connector_requests_priority_count == 7


def test_lmcache_cacheblend_metrics_and_embedded_aliases_parse() -> None:
    metrics = parse_lmcache_prometheus(
        """
lmcache_blend_lookup_requests_total 10
lmcache_blend_lookup_fingerprint_hits_total 7
lmcache_blend_lookup_storage_hits_total 6
lmcache_blend_lookup_stale_chunks_total 2
lmcache_blend_lookup_no_gpu_context_errors_total 1
lmcache_blend_retrieve_requests_total 5
lmcache_blend_retrieve_chunks_total 12
lmcache_blend_retrieve_failures_total 1
lmcache_blend_store_pre_computed_requests_total 4
lmcache_blend_store_pre_computed_chunks_total 9
lmcache_blend_store_pre_computed_failures_total 2
lmcache_blend_store_final_requests_total 3
lmcache_blend_store_final_chunks_total 8
lmcache_blend_store_final_failures_total 1
lmcache_blend_fingerprints_registered_total 11
lmcache_blend_chunks_evicted_total 2
lmcache_blend_future_source_only_total 99
lmcache:lmcache_is_healthy 1
lmcache:get_blocking_failed_count 3
lmcache:put_failed_count 4
lmcache:storage_events_ongoing_count 5
lmcache:storage_events_done_count 6
lmcache:storage_events_not_found_count 7
lmcache:chunk_statistics_chunks 8
"""
    )

    assert metrics.lmcache_enabled is True
    assert metrics.lmcache_cacheblend_enabled is True
    assert metrics.lmcache_blend_lookup_requests == 10
    assert metrics.lmcache_blend_lookup_fingerprint_hits == 7
    assert metrics.lmcache_blend_lookup_storage_hits == 6
    assert metrics.lmcache_blend_lookup_stale_chunks == 2
    assert metrics.lmcache_blend_lookup_no_gpu_context_errors == 1
    assert metrics.lmcache_blend_retrieve_requests == 5
    assert metrics.lmcache_blend_retrieve_chunks == 12
    assert metrics.lmcache_blend_retrieve_failures == 1
    assert metrics.lmcache_blend_store_pre_computed_requests == 4
    assert metrics.lmcache_blend_store_pre_computed_chunks == 9
    assert metrics.lmcache_blend_store_pre_computed_failures == 2
    assert metrics.lmcache_blend_store_final_requests == 3
    assert metrics.lmcache_blend_store_final_chunks == 8
    assert metrics.lmcache_blend_store_final_failures == 1
    assert metrics.lmcache_blend_fingerprints_registered == 11
    assert metrics.lmcache_blend_chunks_evicted == 2
    assert metrics.lmcache_is_healthy is True
    assert metrics.lmcache_get_blocking_failed_count == 3
    assert metrics.lmcache_put_failed_count == 4
    assert metrics.lmcache_storage_events_ongoing_count == 5
    assert metrics.lmcache_storage_events_done_count == 6
    assert metrics.lmcache_storage_events_not_found_count == 7
    assert metrics.lmcache_chunk_statistics_count == 8
    assert metrics.raw_metrics_extra["lmcache_blend_future_source_only_total"] == 99


def test_lmcache_cacheblend_summary_aggregates_metrics_for_diagnostics() -> None:
    report = build_compat_report(
        lmcache_text="""
lmcache_blend_lookup_requests_total{model_name="a"} 10
lmcache_blend_lookup_requests_total{model_name="b"} 30
lmcache_blend_lookup_fingerprint_hits_total{model_name="a"} 5
lmcache_blend_lookup_fingerprint_hits_total{model_name="b"} 15
lmcache_blend_lookup_storage_hits_total{model_name="a"} 3
lmcache_blend_lookup_storage_hits_total{model_name="b"} 9
lmcache_blend_lookup_stale_chunks_total{model_name="a"} 1
lmcache_blend_lookup_no_gpu_context_errors_total{model_name="b"} 1
lmcache_blend_retrieve_failures_total{model_name="a"} 1
lmcache_blend_store_pre_computed_failures_total{model_name="b"} 2
lmcache_blend_store_final_failures_total{model_name="b"} 3
lmcache_blend_fingerprints_registered_total{model_name="a"} 4
lmcache_blend_fingerprints_registered_total{model_name="b"} 6
lmcache_blend_chunks_evicted_total{model_name="a"} 2
""",
        expect_mode="auto",
    )

    summary = report["lmcache_cacheblend_summary"]
    assert summary["observed"] is True
    assert summary["lookup_requests"] == 40
    assert summary["lookup_fingerprint_hit_rate"] == 0.5
    assert summary["lookup_storage_hit_rate"] == 0.3
    assert summary["failures"] == 6
    assert summary["fingerprints_registered"] == 10
    assert any(item["code"] == "lmcache_cacheblend_failures" for item in report["diagnostic_findings"])


def test_lmcache_cacheblend_vllm_artifact_shape_is_not_mp_mode() -> None:
    report = build_compat_report(
        engine_text='vllm:request_success_total{finished_reason="stop"} 8\n',
        lmcache_text="""
lmcache:num_lookup_requests_total 8
lmcache:num_retrieve_requests_total 8
lmcache:num_requested_tokens_total 14112
lmcache:num_hit_tokens_total 14112
lmcache_blend_lookup_requests_total 8
lmcache_blend_lookup_requested_tokens_total 14112
lmcache_blend_lookup_hit_tokens_total 14112
lmcache_blend_retrieve_requests_total 8
lmcache_blend_retrieve_chunks_total 48
""",
        expect_mode="auto",
        lmcache_otel_evidence={"claim_status": "measured", "cacheblend_span_count": 24, "span_counts": {"cb.lookup": 8, "cb.retrieve": 8}},
    )

    families = {(row["surface"], row["family"]): row for row in report["families"]}
    assert report["detected_mode"] == "embedded_cacheblend"
    assert report["detected_architecture"]["label"] == "vllm_embedded_cacheblend"
    assert report["failure_reasons"] == []
    assert report["observed"]["lmcache_cacheblend"] is True
    assert families[("lmcache_cacheblend", "lookup")]["status"] == "populated"
    assert families[("lmcache_cacheblend", "retrieve")]["status"] == "populated"
    assert families[("lmcache_mp", "storage_manager")]["status"] == "not_applicable"
    assert families[("lmcache_mp", "lookup_tokens")]["status"] == "not_applicable"
    assert families[("lmcache_mp", "l1_counters")]["status"] == "not_applicable"
    assert families[("lmcache_mp", "l1_memory")]["status"] == "not_applicable"


def test_lmcache_cacheblend_requires_metrics_when_cb_spans_are_present() -> None:
    report = build_compat_report(
        engine_text='vllm:request_success_total{finished_reason="stop"} 8\n',
        lmcache_text="lmcache:num_lookup_requests_total 8\n",
        expect_mode="auto",
        lmcache_otel_evidence={"claim_status": "measured", "cacheblend_span_count": 24, "span_counts": {"cb.lookup": 8, "cb.retrieve": 8}},
    )

    assert report["detected_mode"] == "embedded_cacheblend"
    assert any(
        item.get("code") == "lmcache_cacheblend_family_missing" and item.get("family") == "lookup"
        for item in report["failure_reasons"]
    )


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
