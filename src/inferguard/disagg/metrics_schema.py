"""Normalized LMCache/TensorMesh metrics schema and Prometheus normalization.

The aliases in this module are intentionally permissive because LMCache metric
names have varied across public examples and integration layers. Parsed fields
are evidence only when the source metric is present in live Prometheus output;
unknown LMCache-prefixed metric names are retained in ``raw_metrics_extra`` for
audit/debugging instead of being discarded.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from inferguard.metrics_core import LabeledSample, parse_labeled_prometheus_text


@dataclass(frozen=True)
class LmcacheMetrics:
    """Normalized LMCache metric snapshot.

    ``None`` means the metric was not present. Boolean fields are parsed from
    numeric gauges or mode labels when available, not inferred from workload
    shape.
    """

    lmcache_enabled: bool | None = None
    lmcache_hit_count: int | None = None
    lmcache_miss_count: int | None = None
    lmcache_hit_rate: float | None = None
    lmcache_eviction_count: int | None = None
    lmcache_save_count: int | None = None
    lmcache_retrieve_count: int | None = None
    lmcache_tier_hbm_bytes: int | None = None
    lmcache_tier_cpu_bytes: int | None = None
    lmcache_tier_disk_bytes: int | None = None
    lmcache_tier_remote_bytes: int | None = None
    lmcache_offload_bytes_total: int | None = None
    lmcache_retrieve_latency_ms_p50: float | None = None
    lmcache_retrieve_latency_ms_p95: float | None = None
    lmcache_retrieve_latency_ms_p99: float | None = None
    lmcache_nixl_transfer_bytes: int | None = None
    lmcache_nixl_transfer_latency_ms: float | None = None
    lmcache_cacheblend_enabled: bool | None = None
    lmcache_cachegen_enabled: bool | None = None
    lmcache_mp_mode_enabled: bool | None = None
    lmcache_connector_type: str | None = None
    lmcache_cache_salt_enabled: bool | None = None
    # Backward-compatible v0.5 provisional fields retained for existing adapter callers.
    lmcache_remote_bytes_sent: int | None = None
    lmcache_remote_bytes_received: int | None = None
    lmcache_queue_depth: int | None = None
    lmcache_num_retrieve_requests: int | None = None
    lmcache_num_store_requests: int | None = None
    lmcache_num_lookup_requests: int | None = None
    lmcache_num_requested_tokens: int | None = None
    lmcache_num_hit_tokens: int | None = None
    lmcache_num_stored_tokens: int | None = None
    lmcache_num_lookup_tokens: int | None = None
    lmcache_num_lookup_hits: int | None = None
    lmcache_num_vllm_hit_tokens: int | None = None
    lmcache_num_prompt_tokens: int | None = None
    lmcache_retrieve_hit_rate: float | None = None
    lmcache_lookup_hit_rate: float | None = None
    lmcache_request_cache_hit_rate: float | None = None
    lmcache_lookup_0_hit_requests: int | None = None
    lmcache_time_to_retrieve_seconds: float | None = None
    lmcache_time_to_store_seconds: float | None = None
    lmcache_time_to_lookup_seconds: float | None = None
    lmcache_retrieve_speed_tokens_per_second: float | None = None
    lmcache_store_speed_tokens_per_second: float | None = None
    lmcache_num_slow_retrieval_by_time: int | None = None
    lmcache_num_slow_retrieval_by_speed: int | None = None
    lmcache_retrieve_process_tokens_time_seconds: float | None = None
    lmcache_retrieve_broadcast_time_seconds: float | None = None
    lmcache_retrieve_to_gpu_time_seconds: float | None = None
    lmcache_store_process_tokens_time_seconds: float | None = None
    lmcache_store_from_gpu_time_seconds: float | None = None
    lmcache_store_put_time_seconds: float | None = None
    lmcache_remote_backend_batched_get_blocking_time_seconds: float | None = None
    lmcache_instrumented_connector_batched_get_time_seconds: float | None = None
    lmcache_local_cache_usage_bytes: int | None = None
    lmcache_remote_cache_usage_bytes: int | None = None
    lmcache_local_storage_usage_bytes: int | None = None
    lmcache_request_cache_lifespan_minutes: float | None = None
    lmcache_is_healthy: bool | None = None
    lmcache_storage_event_count: int | None = None
    lmcache_num_remote_read_requests: int | None = None
    lmcache_num_remote_write_requests: int | None = None
    lmcache_remote_read_bytes: int | None = None
    lmcache_remote_write_bytes: int | None = None
    lmcache_remote_time_to_get_ms: float | None = None
    lmcache_remote_time_to_put_ms: float | None = None
    lmcache_remote_time_to_get_sync_ms: float | None = None
    lmcache_remote_ping_latency_ms: float | None = None
    lmcache_remote_ping_errors: int | None = None
    lmcache_remote_ping_successes: int | None = None
    lmcache_remote_ping_error_code: int | None = None
    lmcache_local_cpu_evict_count: int | None = None
    lmcache_local_cpu_evict_keys_count: int | None = None
    lmcache_local_cpu_evict_failed_count: int | None = None
    lmcache_local_cpu_hot_cache_count: int | None = None
    lmcache_local_cpu_keys_in_request_count: int | None = None
    lmcache_active_memory_objs_count: int | None = None
    lmcache_pinned_memory_objs_count: int | None = None
    lmcache_forced_unpin_count: int | None = None
    lmcache_pin_monitor_pinned_objects_count: int | None = None
    lmcache_p2p_requests: int | None = None
    lmcache_p2p_transferred_tokens: int | None = None
    lmcache_p2p_time_to_transfer_ms: float | None = None
    lmcache_p2p_transfer_speed: float | None = None
    lmcache_chunk_stats_enabled: bool | None = None
    lmcache_total_chunk_requests: int | None = None
    lmcache_total_chunks: int | None = None
    lmcache_unique_chunks: int | None = None
    lmcache_chunk_statistics_reuse_rate: float | None = None
    lmcache_chunk_statistics_bloom_filter_size_mb: float | None = None
    lmcache_chunk_statistics_bloom_filter_fill_rate: float | None = None
    lmcache_chunk_statistics_file_count: int | None = None
    lmcache_chunk_statistics_current_file_size: int | None = None
    lmcache_scheduler_unfinished_requests_count: int | None = None
    lmcache_connector_load_specs_count: int | None = None
    lmcache_connector_request_trackers_count: int | None = None
    lmcache_connector_kv_caches_count: int | None = None
    lmcache_connector_layerwise_retrievers_count: int | None = None
    lmcache_connector_invalid_block_ids_count: int | None = None
    lmcache_connector_requests_priority_count: int | None = None
    lmcache_lookup_requested_tokens: int | None = None
    lmcache_lookup_hit_tokens: int | None = None
    lmcache_sm_read_requests: int | None = None
    lmcache_sm_read_succeed_keys: int | None = None
    lmcache_sm_read_failed_keys: int | None = None
    lmcache_sm_write_requests: int | None = None
    lmcache_sm_write_succeed_keys: int | None = None
    lmcache_sm_write_failed_keys: int | None = None
    lmcache_l1_read_keys: int | None = None
    lmcache_l1_write_keys: int | None = None
    lmcache_l1_evicted_keys: int | None = None
    lmcache_l1_memory_usage_bytes: int | None = None
    lmcache_l1_allocation_failure: int | None = None
    lmcache_l1_read_failure: int | None = None
    lmcache_l1_chunk_lifetime_seconds: float | None = None
    lmcache_l1_chunk_idle_before_evict_seconds: float | None = None
    lmcache_l1_chunk_reuse_gap_seconds: float | None = None
    lmcache_l1_chunk_evict_reuse_gap_seconds: float | None = None
    lmcache_l0_block_lifetime_seconds: float | None = None
    lmcache_l0_block_idle_before_evict_seconds: float | None = None
    lmcache_l0_block_reuse_gap_seconds: float | None = None
    lmcache_real_reuse_gap_seconds: float | None = None
    lmcache_real_reuse_gap_chunks: float | None = None
    lmcache_l2_store_tasks: int | None = None
    lmcache_l2_store_keys: int | None = None
    lmcache_l2_store_completed: int | None = None
    lmcache_l2_store_succeeded_keys: int | None = None
    lmcache_l2_store_failed_keys: int | None = None
    lmcache_l2_prefetch_lookups: int | None = None
    lmcache_l2_prefetch_lookup_keys: int | None = None
    lmcache_l2_prefetch_hit_keys: int | None = None
    lmcache_l2_prefetch_load_tasks: int | None = None
    lmcache_l2_prefetch_load_keys: int | None = None
    lmcache_l2_prefetch_loaded_keys: int | None = None
    lmcache_l2_prefetch_failed_keys: int | None = None
    lmcache_l2_prefetch_failure: int | None = None
    lmcache_l2_load_completed: int | None = None
    lmcache_l2_store_throughput_gbs: float | None = None
    lmcache_l2_load_throughput_gbs: float | None = None
    lmcache_l0_l1_store_throughput_gbs: float | None = None
    lmcache_l0_l1_load_throughput_gbs: float | None = None
    lmcache_num_chunks_loaded: int | None = None
    lmcache_active_prefetch_jobs: int | None = None
    lmcache_num_inflight_l2_stores: int | None = None
    lmcache_num_inflight_l2_loads: int | None = None
    lmcache_inflight_load_memory_usage_bytes: int | None = None
    lmcache_event_bus_queue_depth: int | None = None
    lmcache_event_bus_drain_lag_seconds: float | None = None
    lmcache_event_bus_dropped_events_total: int | None = None
    lmcache_event_bus_subscriber_exceptions_total: int | None = None
    lmcache_blend_lookup_requests: int | None = None
    lmcache_blend_lookup_fingerprint_hits: int | None = None
    lmcache_blend_lookup_storage_hits: int | None = None
    lmcache_blend_lookup_requested_tokens: int | None = None
    lmcache_blend_lookup_hit_tokens: int | None = None
    lmcache_blend_lookup_stale_chunks: int | None = None
    lmcache_blend_lookup_no_gpu_context_errors: int | None = None
    lmcache_blend_l0_gpu_operation_duration_seconds: float | None = None
    lmcache_blend_l0_gpu_transfer_chunks: int | None = None
    lmcache_blend_l0_gpu_transfer_tokens: int | None = None
    lmcache_blend_retrieve_requests: int | None = None
    lmcache_blend_retrieve_chunks: int | None = None
    lmcache_blend_retrieve_failures: int | None = None
    lmcache_blend_store_pre_computed_requests: int | None = None
    lmcache_blend_store_pre_computed_chunks: int | None = None
    lmcache_blend_store_pre_computed_failures: int | None = None
    lmcache_blend_store_final_requests: int | None = None
    lmcache_blend_store_final_chunks: int | None = None
    lmcache_blend_store_final_failures: int | None = None
    lmcache_blend_fingerprints_registered: int | None = None
    lmcache_blend_chunks_evicted: int | None = None
    lmcache_get_blocking_failed_count: int | None = None
    lmcache_put_failed_count: int | None = None
    lmcache_kv_msg_queue_size: int | None = None
    lmcache_remote_put_task_num: int | None = None
    lmcache_storage_events_ongoing_count: int | None = None
    lmcache_storage_events_done_count: int | None = None
    lmcache_storage_events_not_found_count: int | None = None
    lmcache_chunk_statistics_count: int | None = None
    raw_metrics_extra: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


NORMALIZED_LMCACHE_FIELDS: tuple[str, ...] = tuple(
    field for field in LmcacheMetrics.__dataclass_fields__ if field != "raw_metrics_extra"
)


def _mp_aliases(
    canonical_name: str,
    *,
    alias_type: str,
    counter: bool = False,
    aggregate: str | None = None,
) -> tuple[dict[str, Any], ...]:
    names = [canonical_name, canonical_name.replace(".", "_")]
    if counter:
        names.extend(f"{name}_total" for name in tuple(names))
    seen: set[str] = set()
    aliases: list[dict[str, Any]] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        alias: dict[str, Any] = {"name": name, "type": alias_type}
        if aggregate is not None:
            alias["aggregate"] = aggregate
        aliases.append(alias)
    return tuple(aliases)


def _mp_counter_aliases(canonical_name: str, *, aggregate: str | None = None) -> tuple[dict[str, Any], ...]:
    return _mp_aliases(canonical_name, alias_type="int", counter=True, aggregate=aggregate)


def _mp_gauge_aliases(canonical_name: str, *, aggregate: str | None = None) -> tuple[dict[str, Any], ...]:
    return _mp_aliases(canonical_name, alias_type="int", aggregate=aggregate)


def _mp_hist_aliases(canonical_name: str) -> tuple[dict[str, Any], ...]:
    return _mp_aliases(canonical_name, alias_type="hist_avg")


# Selectors use Prometheus label matching. ``convert`` supports seconds->ms.
_ALIAS_TABLE: dict[str, tuple[dict[str, Any], ...]] = {
    "lmcache_enabled": (
        {"name": "lmcache:enabled", "type": "bool"},
        {"name": "lmcache_enabled", "type": "bool"},
        {"name": "lmcache_config_info", "label": "enabled", "type": "bool_label"},
    ),
    "lmcache_hit_count": (
        {"name": "lmcache:hit_count", "type": "int"},
        {"name": "lmcache:hit_count_total", "type": "int"},
        {"name": "lmcache_hit_count", "type": "int"},
        {"name": "lmcache_hits_total", "type": "int"},
        {"name": "lmcache_lookup_hits_total", "type": "int"},
        {"name": "lmcache_retrieve_hit_count_total", "type": "int"},
        {"name": "lmcache_mp_lookup_hit_tokens_total", "type": "int"},
    ),
    "lmcache_miss_count": (
        {"name": "lmcache:miss_count", "type": "int"},
        {"name": "lmcache:miss_count_total", "type": "int"},
        {"name": "lmcache_miss_count", "type": "int"},
        {"name": "lmcache_misses_total", "type": "int"},
        {"name": "lmcache_lookup_misses_total", "type": "int"},
        {"name": "lmcache_retrieve_miss_count_total", "type": "int"},
    ),
    "lmcache_hit_rate": (
        {"name": "lmcache:hit_rate", "type": "float"},
        {"name": "lmcache_hit_rate", "type": "float"},
        {"name": "lmcache_cache_hit_rate", "type": "float"},
    ),
    "lmcache_eviction_count": (
        {"name": "lmcache:eviction_count", "type": "int"},
        {"name": "lmcache:eviction_count_total", "type": "int"},
        {"name": "lmcache_eviction_count", "type": "int"},
        {"name": "lmcache_evictions_total", "type": "int"},
        {"name": "lmcache_cache_evictions_total", "type": "int"},
        {"name": "lmcache_mp_l1_evicted_keys_total", "type": "int"},
    ),
    "lmcache_save_count": (
        {"name": "lmcache:save_count", "type": "int"},
        {"name": "lmcache:save_count_total", "type": "int"},
        {"name": "lmcache_save_count", "type": "int"},
        {"name": "lmcache_saves_total", "type": "int"},
    ),
    "lmcache_retrieve_count": (
        {"name": "lmcache:retrieve_count", "type": "int"},
        {"name": "lmcache:retrieve_count_total", "type": "int"},
        {"name": "lmcache_retrieve_count", "type": "int"},
        {"name": "lmcache_retrieves_total", "type": "int"},
    ),
    "lmcache_tier_hbm_bytes": (
        {"name": "lmcache:tier_usage_bytes", "labels": {"tier": "hbm"}, "type": "int"},
        {"name": "lmcache_tier_usage_bytes", "labels": {"tier": "hbm"}, "type": "int"},
        {"name": "lmcache_tier_hbm_bytes", "type": "int"},
        {"name": "lmcache_gpu_bytes", "type": "int"},
    ),
    "lmcache_tier_cpu_bytes": (
        {"name": "lmcache:tier_usage", "labels": {"tier": "cpu"}, "type": "int"},
        {"name": "lmcache:tier_usage_bytes", "labels": {"tier": "cpu"}, "type": "int"},
        {"name": "lmcache_tier_usage_bytes", "labels": {"tier": "cpu"}, "type": "int"},
        {"name": "lmcache_tier_cpu_bytes", "type": "int"},
        {"name": "lmcache_local_cpu_bytes", "type": "int"},
        {"name": "lmcache_mp_l1_memory_usage_bytes", "type": "int"},
    ),
    "lmcache_tier_disk_bytes": (
        {"name": "lmcache:tier_usage", "labels": {"tier": "local_disk"}, "type": "int"},
        {"name": "lmcache:tier_usage_bytes", "labels": {"tier": "disk"}, "type": "int"},
        {"name": "lmcache:tier_usage_bytes", "labels": {"tier": "local_disk"}, "type": "int"},
        {"name": "lmcache_tier_usage_bytes", "labels": {"tier": "disk"}, "type": "int"},
        {"name": "lmcache_tier_disk_bytes", "type": "int"},
        {"name": "lmcache_tier_local_disk_bytes", "type": "int"},
    ),
    "lmcache_tier_remote_bytes": (
        {"name": "lmcache:tier_usage", "labels": {"tier": "remote"}, "type": "int"},
        {"name": "lmcache:tier_usage_bytes", "labels": {"tier": "remote"}, "type": "int"},
        {"name": "lmcache_tier_usage_bytes", "labels": {"tier": "remote"}, "type": "int"},
        {"name": "lmcache_tier_remote_bytes", "type": "int"},
        {"name": "lmcache_remote_bytes", "type": "int"},
    ),
    "lmcache_offload_bytes_total": (
        {"name": "lmcache:offload_bytes_total", "type": "int"},
        {"name": "lmcache_offload_bytes_total", "type": "int"},
        {"name": "lmcache_remote_bytes_sent_total", "type": "int"},
        {"name": "lmcache:remote_bytes_sent_total", "type": "int"},
    ),
    "lmcache_retrieve_latency_ms_p50": (
        {"name": "lmcache_retrieve_latency_ms", "labels": {"quantile": "0.5"}, "type": "float"},
        {"name": "lmcache_retrieve_latency_ms", "labels": {"quantile": "0.50"}, "type": "float"},
        {"name": "lmcache:retrieve_latency_ms", "labels": {"quantile": "0.5"}, "type": "float"},
        {"name": "lmcache_retrieve_latency_seconds", "labels": {"quantile": "0.5"}, "type": "float", "convert": "seconds_to_ms"},
    ),
    "lmcache_retrieve_latency_ms_p95": (
        {"name": "lmcache_retrieve_latency_ms", "labels": {"quantile": "0.95"}, "type": "float"},
        {"name": "lmcache:retrieve_latency_ms", "labels": {"quantile": "0.95"}, "type": "float"},
        {"name": "lmcache_retrieve_latency_seconds", "labels": {"quantile": "0.95"}, "type": "float", "convert": "seconds_to_ms"},
    ),
    "lmcache_retrieve_latency_ms_p99": (
        {"name": "lmcache_retrieve_latency_ms", "labels": {"quantile": "0.99"}, "type": "float"},
        {"name": "lmcache:retrieve_latency_ms", "labels": {"quantile": "0.99"}, "type": "float"},
        {"name": "lmcache_retrieve_latency_seconds", "labels": {"quantile": "0.99"}, "type": "float", "convert": "seconds_to_ms"},
    ),
    "lmcache_nixl_transfer_bytes": (
        {"name": "lmcache:nixl_transfer_bytes", "type": "int"},
        {"name": "lmcache_nixl_transfer_bytes", "type": "int"},
        {"name": "lmcache_nixl_transfer_bytes_total", "type": "int"},
    ),
    "lmcache_nixl_transfer_latency_ms": (
        {"name": "lmcache:nixl_transfer_latency_ms", "type": "float"},
        {"name": "lmcache_nixl_transfer_latency_ms", "type": "float"},
        {"name": "lmcache_nixl_transfer_latency_seconds", "type": "float", "convert": "seconds_to_ms"},
    ),
    "lmcache_remote_bytes_sent": (
        {"name": "lmcache:remote_bytes_sent_total", "type": "int"},
        {"name": "lmcache_remote_bytes_sent_total", "type": "int"},
    ),
    "lmcache_remote_bytes_received": (
        {"name": "lmcache:remote_bytes_received_total", "type": "int"},
        {"name": "lmcache_remote_bytes_received_total", "type": "int"},
    ),
    "lmcache_queue_depth": (
        {"name": "lmcache:queue_depth", "type": "int"},
        {"name": "lmcache_queue_depth", "type": "int"},
        {"name": "lmcache_mp_event_bus_queue_depth", "type": "int"},
    ),
    "lmcache_num_retrieve_requests": (
        {"name": "lmcache:num_retrieve_requests", "type": "int"},
        {"name": "lmcache_num_retrieve_requests", "type": "int"},
        {"name": "lmcache:num_retrieve_requests_total", "type": "int"},
        {"name": "lmcache_num_retrieve_requests_total", "type": "int"},
    ),
    "lmcache_num_store_requests": (
        {"name": "lmcache:num_store_requests", "type": "int"},
        {"name": "lmcache_num_store_requests", "type": "int"},
        {"name": "lmcache:num_store_requests_total", "type": "int"},
        {"name": "lmcache_num_store_requests_total", "type": "int"},
    ),
    "lmcache_num_lookup_requests": (
        {"name": "lmcache:num_lookup_requests", "type": "int"},
        {"name": "lmcache_num_lookup_requests", "type": "int"},
        {"name": "lmcache:num_lookup_requests_total", "type": "int"},
        {"name": "lmcache_num_lookup_requests_total", "type": "int"},
    ),
    "lmcache_num_requested_tokens": (
        {"name": "lmcache:num_requested_tokens", "type": "int"},
        {"name": "lmcache_num_requested_tokens", "type": "int"},
        {"name": "lmcache:num_requested_tokens_total", "type": "int"},
        {"name": "lmcache_num_requested_tokens_total", "type": "int"},
    ),
    "lmcache_num_hit_tokens": (
        {"name": "lmcache:num_hit_tokens", "type": "int"},
        {"name": "lmcache_num_hit_tokens", "type": "int"},
        {"name": "lmcache:num_hit_tokens_total", "type": "int"},
        {"name": "lmcache_num_hit_tokens_total", "type": "int"},
    ),
    "lmcache_num_stored_tokens": (
        {"name": "lmcache:num_stored_tokens", "type": "int"},
        {"name": "lmcache_num_stored_tokens", "type": "int"},
        {"name": "lmcache:num_stored_tokens_total", "type": "int"},
        {"name": "lmcache_num_stored_tokens_total", "type": "int"},
    ),
    "lmcache_num_lookup_tokens": (
        {"name": "lmcache:num_lookup_tokens", "type": "int"},
        {"name": "lmcache_num_lookup_tokens", "type": "int"},
        {"name": "lmcache:num_lookup_tokens_total", "type": "int"},
        {"name": "lmcache_num_lookup_tokens_total", "type": "int"},
    ),
    "lmcache_num_lookup_hits": (
        {"name": "lmcache:num_lookup_hits", "type": "int"},
        {"name": "lmcache_num_lookup_hits", "type": "int"},
        {"name": "lmcache:num_lookup_hits_total", "type": "int"},
        {"name": "lmcache_num_lookup_hits_total", "type": "int"},
    ),
    "lmcache_num_vllm_hit_tokens": (
        {"name": "lmcache:num_vllm_hit_tokens", "type": "int"},
        {"name": "lmcache_num_vllm_hit_tokens", "type": "int"},
        {"name": "lmcache:num_vllm_hit_tokens_total", "type": "int"},
        {"name": "lmcache_num_vllm_hit_tokens_total", "type": "int"},
    ),
    "lmcache_num_prompt_tokens": (
        {"name": "lmcache:num_prompt_tokens", "type": "int"},
        {"name": "lmcache_num_prompt_tokens", "type": "int"},
        {"name": "lmcache:num_prompt_tokens_total", "type": "int"},
        {"name": "lmcache_num_prompt_tokens_total", "type": "int"},
    ),
    "lmcache_retrieve_hit_rate": (
        {"name": "lmcache:retrieve_hit_rate", "type": "float"},
        {"name": "lmcache_retrieve_hit_rate", "type": "float"},
    ),
    "lmcache_lookup_hit_rate": (
        {"name": "lmcache:lookup_hit_rate", "type": "float"},
        {"name": "lmcache_lookup_hit_rate", "type": "float"},
    ),
    "lmcache_request_cache_hit_rate": (
        {"name": "lmcache:request_cache_hit_rate", "type": "hist_avg"},
        {"name": "lmcache_request_cache_hit_rate", "type": "hist_avg"},
    ),
    "lmcache_lookup_0_hit_requests": (
        {"name": "lmcache:lookup_0_hit_requests", "type": "int"},
        {"name": "lmcache_lookup_0_hit_requests", "type": "int"},
        {"name": "lmcache:lookup_0_hit_requests_total", "type": "int"},
        {"name": "lmcache_lookup_0_hit_requests_total", "type": "int"},
    ),
    "lmcache_time_to_retrieve_seconds": (
        {"name": "lmcache:time_to_retrieve", "type": "hist_avg"},
        {"name": "lmcache_time_to_retrieve", "type": "hist_avg"},
    ),
    "lmcache_time_to_store_seconds": (
        {"name": "lmcache:time_to_store", "type": "hist_avg"},
        {"name": "lmcache_time_to_store", "type": "hist_avg"},
    ),
    "lmcache_time_to_lookup_seconds": (
        {"name": "lmcache:time_to_lookup", "type": "hist_avg"},
        {"name": "lmcache_time_to_lookup", "type": "hist_avg"},
    ),
    "lmcache_retrieve_speed_tokens_per_second": (
        {"name": "lmcache:retrieve_speed", "type": "hist_avg"},
        {"name": "lmcache_retrieve_speed", "type": "hist_avg"},
    ),
    "lmcache_store_speed_tokens_per_second": (
        {"name": "lmcache:store_speed", "type": "hist_avg"},
        {"name": "lmcache_store_speed", "type": "hist_avg"},
    ),
    "lmcache_num_slow_retrieval_by_time": (
        {"name": "lmcache:num_slow_retrieval_by_time", "type": "int"},
        {"name": "lmcache_num_slow_retrieval_by_time", "type": "int"},
        {"name": "lmcache:num_slow_retrieval_by_time_total", "type": "int"},
        {"name": "lmcache_num_slow_retrieval_by_time_total", "type": "int"},
    ),
    "lmcache_num_slow_retrieval_by_speed": (
        {"name": "lmcache:num_slow_retrieval_by_speed", "type": "int"},
        {"name": "lmcache_num_slow_retrieval_by_speed", "type": "int"},
        {"name": "lmcache:num_slow_retrieval_by_speed_total", "type": "int"},
        {"name": "lmcache_num_slow_retrieval_by_speed_total", "type": "int"},
    ),
    "lmcache_retrieve_process_tokens_time_seconds": (
        {"name": "lmcache:retrieve_process_tokens_time", "type": "hist_avg"},
        {"name": "lmcache_retrieve_process_tokens_time", "type": "hist_avg"},
    ),
    "lmcache_retrieve_broadcast_time_seconds": (
        {"name": "lmcache:retrieve_broadcast_time", "type": "hist_avg"},
        {"name": "lmcache_retrieve_broadcast_time", "type": "hist_avg"},
    ),
    "lmcache_retrieve_to_gpu_time_seconds": (
        {"name": "lmcache:retrieve_to_gpu_time", "type": "hist_avg"},
        {"name": "lmcache_retrieve_to_gpu_time", "type": "hist_avg"},
    ),
    "lmcache_store_process_tokens_time_seconds": (
        {"name": "lmcache:store_process_tokens_time", "type": "hist_avg"},
        {"name": "lmcache_store_process_tokens_time", "type": "hist_avg"},
    ),
    "lmcache_store_from_gpu_time_seconds": (
        {"name": "lmcache:store_from_gpu_time", "type": "hist_avg"},
        {"name": "lmcache_store_from_gpu_time", "type": "hist_avg"},
    ),
    "lmcache_store_put_time_seconds": (
        {"name": "lmcache:store_put_time", "type": "hist_avg"},
        {"name": "lmcache_store_put_time", "type": "hist_avg"},
    ),
    "lmcache_remote_backend_batched_get_blocking_time_seconds": (
        {"name": "lmcache:remote_backend_batched_get_blocking_time", "type": "hist_avg"},
        {"name": "lmcache_remote_backend_batched_get_blocking_time", "type": "hist_avg"},
    ),
    "lmcache_instrumented_connector_batched_get_time_seconds": (
        {"name": "lmcache:instrumented_connector_batched_get_time", "type": "hist_avg"},
        {"name": "lmcache_instrumented_connector_batched_get_time", "type": "hist_avg"},
    ),
    "lmcache_local_cache_usage_bytes": (
        {"name": "lmcache:local_cache_usage", "type": "int"},
        {"name": "lmcache_local_cache_usage", "type": "int"},
    ),
    "lmcache_remote_cache_usage_bytes": (
        {"name": "lmcache:remote_cache_usage", "type": "int"},
        {"name": "lmcache_remote_cache_usage", "type": "int"},
    ),
    "lmcache_local_storage_usage_bytes": (
        {"name": "lmcache:local_storage_usage", "type": "int"},
        {"name": "lmcache_local_storage_usage", "type": "int"},
    ),
    "lmcache_request_cache_lifespan_minutes": (
        {"name": "lmcache:request_cache_lifespan", "type": "hist_avg"},
        {"name": "lmcache_request_cache_lifespan", "type": "hist_avg"},
    ),
    "lmcache_is_healthy": (
        {"name": "lmcache:is_healthy", "type": "bool"},
        {"name": "lmcache:lmcache_is_healthy", "type": "bool"},
        {"name": "lmcache_is_healthy", "type": "bool"},
        {"name": "lmcache_lmcache_is_healthy", "type": "bool"},
    ),
    "lmcache_get_blocking_failed_count": (
        {"name": "lmcache:get_blocking_failed_count", "type": "int"},
        {"name": "lmcache_get_blocking_failed_count", "type": "int"},
        {"name": "lmcache:get_blocking_failed_count_total", "type": "int"},
        {"name": "lmcache_get_blocking_failed_count_total", "type": "int"},
        {"name": "lmcache:interval_get_blocking_failed_count", "type": "int"},
    ),
    "lmcache_put_failed_count": (
        {"name": "lmcache:put_failed_count", "type": "int"},
        {"name": "lmcache_put_failed_count", "type": "int"},
        {"name": "lmcache:put_failed_count_total", "type": "int"},
        {"name": "lmcache_put_failed_count_total", "type": "int"},
    ),
    "lmcache_kv_msg_queue_size": (
        {"name": "lmcache:kv_msg_queue_size", "type": "int"},
        {"name": "lmcache_kv_msg_queue_size", "type": "int"},
    ),
    "lmcache_remote_put_task_num": (
        {"name": "lmcache:remote_put_task_num", "type": "int"},
        {"name": "lmcache_remote_put_task_num", "type": "int"},
    ),
    "lmcache_storage_event_count": (
        {"name": "lmcache:storage_event_count", "type": "int"},
        {"name": "lmcache_storage_event_count", "type": "int"},
        {"name": "lmcache:storage_event_count_total", "type": "int"},
        {"name": "lmcache_storage_event_count_total", "type": "int"},
        {"name": "lmcache:storage_events_done_count", "type": "int"},
        {"name": "lmcache_storage_events_done_count", "type": "int"},
    ),
    "lmcache_storage_events_ongoing_count": (
        {"name": "lmcache:storage_events_ongoing_count", "type": "int"},
        {"name": "lmcache_storage_events_ongoing_count", "type": "int"},
    ),
    "lmcache_storage_events_done_count": (
        {"name": "lmcache:storage_events_done_count", "type": "int"},
        {"name": "lmcache_storage_events_done_count", "type": "int"},
    ),
    "lmcache_storage_events_not_found_count": (
        {"name": "lmcache:storage_events_not_found_count", "type": "int"},
        {"name": "lmcache_storage_events_not_found_count", "type": "int"},
    ),
    "lmcache_num_remote_read_requests": (
        {"name": "lmcache:num_remote_read_requests", "type": "int"},
        {"name": "lmcache_num_remote_read_requests", "type": "int"},
        {"name": "lmcache:num_remote_read_requests_total", "type": "int"},
        {"name": "lmcache_num_remote_read_requests_total", "type": "int"},
    ),
    "lmcache_num_remote_write_requests": (
        {"name": "lmcache:num_remote_write_requests", "type": "int"},
        {"name": "lmcache_num_remote_write_requests", "type": "int"},
        {"name": "lmcache:num_remote_write_requests_total", "type": "int"},
        {"name": "lmcache_num_remote_write_requests_total", "type": "int"},
    ),
    "lmcache_remote_read_bytes": (
        {"name": "lmcache:num_remote_read_bytes", "type": "int"},
        {"name": "lmcache_num_remote_read_bytes", "type": "int"},
        {"name": "lmcache:num_remote_read_bytes_total", "type": "int"},
        {"name": "lmcache_num_remote_read_bytes_total", "type": "int"},
        {"name": "lmcache:remote_read_bytes", "type": "int"},
        {"name": "lmcache_remote_read_bytes", "type": "int"},
        {"name": "lmcache:remote_read_bytes_total", "type": "int"},
        {"name": "lmcache_remote_read_bytes_total", "type": "int"},
    ),
    "lmcache_remote_write_bytes": (
        {"name": "lmcache:num_remote_write_bytes", "type": "int"},
        {"name": "lmcache_num_remote_write_bytes", "type": "int"},
        {"name": "lmcache:num_remote_write_bytes_total", "type": "int"},
        {"name": "lmcache_num_remote_write_bytes_total", "type": "int"},
        {"name": "lmcache:remote_write_bytes", "type": "int"},
        {"name": "lmcache_remote_write_bytes", "type": "int"},
        {"name": "lmcache:remote_write_bytes_total", "type": "int"},
        {"name": "lmcache_remote_write_bytes_total", "type": "int"},
    ),
    "lmcache_remote_time_to_get_ms": (
        {"name": "lmcache:remote_time_to_get", "type": "hist_avg"},
        {"name": "lmcache_remote_time_to_get", "type": "hist_avg"},
    ),
    "lmcache_remote_time_to_put_ms": (
        {"name": "lmcache:remote_time_to_put", "type": "hist_avg"},
        {"name": "lmcache_remote_time_to_put", "type": "hist_avg"},
    ),
    "lmcache_remote_time_to_get_sync_ms": (
        {"name": "lmcache:remote_time_to_get_sync", "type": "hist_avg"},
        {"name": "lmcache_remote_time_to_get_sync", "type": "hist_avg"},
    ),
    "lmcache_remote_ping_latency_ms": (
        {"name": "lmcache:remote_ping_latency", "type": "float"},
        {"name": "lmcache_remote_ping_latency", "type": "float"},
        {"name": "lmcache:remote_ping_latency_ms", "type": "float"},
        {"name": "lmcache_remote_ping_latency_ms", "type": "float"},
        {"name": "lmcache:remote_ping_latency_seconds", "type": "float", "convert": "seconds_to_ms"},
        {"name": "lmcache_remote_ping_latency_seconds", "type": "float", "convert": "seconds_to_ms"},
    ),
    "lmcache_remote_ping_errors": (
        {"name": "lmcache:remote_ping_errors", "type": "int"},
        {"name": "lmcache_remote_ping_errors", "type": "int"},
        {"name": "lmcache:remote_ping_errors_total", "type": "int"},
        {"name": "lmcache_remote_ping_errors_total", "type": "int"},
    ),
    "lmcache_remote_ping_successes": (
        {"name": "lmcache:remote_ping_successes", "type": "int"},
        {"name": "lmcache_remote_ping_successes", "type": "int"},
        {"name": "lmcache:remote_ping_successes_total", "type": "int"},
        {"name": "lmcache_remote_ping_successes_total", "type": "int"},
    ),
    "lmcache_remote_ping_error_code": (
        {"name": "lmcache:remote_ping_error_code", "type": "int"},
        {"name": "lmcache_remote_ping_error_code", "type": "int"},
    ),
    "lmcache_local_cpu_evict_count": (
        {"name": "lmcache:local_cpu_evict_count", "type": "int"},
        {"name": "lmcache_local_cpu_evict_count", "type": "int"},
        {"name": "lmcache:local_cpu_evict_count_total", "type": "int"},
        {"name": "lmcache_local_cpu_evict_count_total", "type": "int"},
    ),
    "lmcache_local_cpu_evict_keys_count": (
        {"name": "lmcache:local_cpu_evict_keys_count", "type": "int"},
        {"name": "lmcache_local_cpu_evict_keys_count", "type": "int"},
        {"name": "lmcache:local_cpu_evict_keys_count_total", "type": "int"},
        {"name": "lmcache_local_cpu_evict_keys_count_total", "type": "int"},
    ),
    "lmcache_local_cpu_evict_failed_count": (
        {"name": "lmcache:local_cpu_evict_failed_count", "type": "int"},
        {"name": "lmcache_local_cpu_evict_failed_count", "type": "int"},
        {"name": "lmcache:local_cpu_evict_failed_count_total", "type": "int"},
        {"name": "lmcache_local_cpu_evict_failed_count_total", "type": "int"},
    ),
    "lmcache_local_cpu_hot_cache_count": (
        {"name": "lmcache:local_cpu_hot_cache_count", "type": "int"},
        {"name": "lmcache_local_cpu_hot_cache_count", "type": "int"},
    ),
    "lmcache_local_cpu_keys_in_request_count": (
        {"name": "lmcache:local_cpu_keys_in_request_count", "type": "int"},
        {"name": "lmcache_local_cpu_keys_in_request_count", "type": "int"},
    ),
    "lmcache_active_memory_objs_count": (
        {"name": "lmcache:active_memory_objs_count", "type": "int"},
        {"name": "lmcache_active_memory_objs_count", "type": "int"},
    ),
    "lmcache_pinned_memory_objs_count": (
        {"name": "lmcache:pinned_memory_objs_count", "type": "int"},
        {"name": "lmcache_pinned_memory_objs_count", "type": "int"},
    ),
    "lmcache_forced_unpin_count": (
        {"name": "lmcache:forced_unpin_count", "type": "int"},
        {"name": "lmcache_forced_unpin_count", "type": "int"},
        {"name": "lmcache:forced_unpin_count_total", "type": "int"},
        {"name": "lmcache_forced_unpin_count_total", "type": "int"},
    ),
    "lmcache_pin_monitor_pinned_objects_count": (
        {"name": "lmcache:pin_monitor_pinned_objects_count", "type": "int"},
        {"name": "lmcache_pin_monitor_pinned_objects_count", "type": "int"},
    ),
    "lmcache_p2p_requests": (
        {"name": "lmcache:num_p2p_requests", "type": "int"},
        {"name": "lmcache_num_p2p_requests", "type": "int"},
        {"name": "lmcache:num_p2p_requests_total", "type": "int"},
        {"name": "lmcache_num_p2p_requests_total", "type": "int"},
    ),
    "lmcache_p2p_transferred_tokens": (
        {"name": "lmcache:num_p2p_transferred_tokens", "type": "int"},
        {"name": "lmcache_num_p2p_transferred_tokens", "type": "int"},
        {"name": "lmcache:num_p2p_transferred_tokens_total", "type": "int"},
        {"name": "lmcache_num_p2p_transferred_tokens_total", "type": "int"},
    ),
    "lmcache_p2p_time_to_transfer_ms": (
        {"name": "lmcache:p2p_time_to_transfer", "type": "hist_avg", "convert": "seconds_to_ms"},
        {"name": "lmcache_p2p_time_to_transfer", "type": "hist_avg", "convert": "seconds_to_ms"},
        {"name": "lmcache:p2p_time_to_transfer", "type": "float", "convert": "seconds_to_ms"},
        {"name": "lmcache_p2p_time_to_transfer", "type": "float", "convert": "seconds_to_ms"},
        {"name": "lmcache:p2p_time_to_transfer_seconds", "type": "float", "convert": "seconds_to_ms"},
        {"name": "lmcache_p2p_time_to_transfer_seconds", "type": "float", "convert": "seconds_to_ms"},
    ),
    "lmcache_p2p_transfer_speed": (
        {"name": "lmcache:p2p_transfer_speed", "type": "hist_avg"},
        {"name": "lmcache_p2p_transfer_speed", "type": "hist_avg"},
        {"name": "lmcache:p2p_transfer_speed", "type": "float"},
        {"name": "lmcache_p2p_transfer_speed", "type": "float"},
    ),
    "lmcache_chunk_stats_enabled": (
        {"name": "lmcache:chunk_stats_enabled", "type": "bool"},
        {"name": "lmcache_chunk_stats_enabled", "type": "bool"},
        {"name": "lmcache:chunk_statistics_enabled", "type": "bool"},
        {"name": "lmcache_chunk_statistics_enabled", "type": "bool"},
    ),
    "lmcache_chunk_statistics_count": (
        {"name": "lmcache:chunk_statistics_count", "type": "int"},
        {"name": "lmcache_chunk_statistics_count", "type": "int"},
        {"name": "lmcache:chunk_statistics_total", "type": "int"},
        {"name": "lmcache_chunk_statistics_total", "type": "int"},
        {"name": "lmcache:chunk_statistics_chunks", "type": "int"},
        {"name": "lmcache_chunk_statistics_chunks", "type": "int"},
    ),
    "lmcache_total_chunk_requests": (
        {"name": "lmcache:chunk_statistics_total_requests", "type": "int"},
        {"name": "lmcache_chunk_statistics_total_requests", "type": "int"},
        {"name": "lmcache:total_chunk_requests", "type": "int"},
        {"name": "lmcache_total_chunk_requests", "type": "int"},
        {"name": "lmcache:total_chunk_requests_total", "type": "int"},
        {"name": "lmcache_total_chunk_requests_total", "type": "int"},
    ),
    "lmcache_total_chunks": (
        {"name": "lmcache:chunk_statistics_total_chunks", "type": "int"},
        {"name": "lmcache_chunk_statistics_total_chunks", "type": "int"},
        {"name": "lmcache:total_chunks", "type": "int"},
        {"name": "lmcache_total_chunks", "type": "int"},
    ),
    "lmcache_unique_chunks": (
        {"name": "lmcache:chunk_statistics_unique_chunks", "type": "int"},
        {"name": "lmcache_chunk_statistics_unique_chunks", "type": "int"},
        {"name": "lmcache:unique_chunks", "type": "int"},
        {"name": "lmcache_unique_chunks", "type": "int"},
    ),
    "lmcache_chunk_statistics_reuse_rate": (
        {"name": "lmcache:chunk_statistics_reuse_rate", "type": "float"},
        {"name": "lmcache_chunk_statistics_reuse_rate", "type": "float"},
    ),
    "lmcache_chunk_statistics_bloom_filter_size_mb": (
        {"name": "lmcache:chunk_statistics_bloom_filter_size_mb", "type": "float"},
        {"name": "lmcache_chunk_statistics_bloom_filter_size_mb", "type": "float"},
    ),
    "lmcache_chunk_statistics_bloom_filter_fill_rate": (
        {"name": "lmcache:chunk_statistics_bloom_filter_fill_rate", "type": "float"},
        {"name": "lmcache_chunk_statistics_bloom_filter_fill_rate", "type": "float"},
    ),
    "lmcache_chunk_statistics_file_count": (
        {"name": "lmcache:chunk_statistics_file_count", "type": "int"},
        {"name": "lmcache_chunk_statistics_file_count", "type": "int"},
    ),
    "lmcache_chunk_statistics_current_file_size": (
        {"name": "lmcache:chunk_statistics_current_file_size", "type": "int"},
        {"name": "lmcache_chunk_statistics_current_file_size", "type": "int"},
    ),
    "lmcache_scheduler_unfinished_requests_count": (
        {"name": "lmcache:scheduler_unfinished_requests_count", "type": "int"},
        {"name": "lmcache_scheduler_unfinished_requests_count", "type": "int"},
    ),
    "lmcache_connector_load_specs_count": (
        {"name": "lmcache:connector_load_specs_count", "type": "int"},
        {"name": "lmcache_connector_load_specs_count", "type": "int"},
    ),
    "lmcache_connector_request_trackers_count": (
        {"name": "lmcache:connector_request_trackers_count", "type": "int"},
        {"name": "lmcache_connector_request_trackers_count", "type": "int"},
    ),
    "lmcache_connector_kv_caches_count": (
        {"name": "lmcache:connector_kv_caches_count", "type": "int"},
        {"name": "lmcache_connector_kv_caches_count", "type": "int"},
    ),
    "lmcache_connector_layerwise_retrievers_count": (
        {"name": "lmcache:connector_layerwise_retrievers_count", "type": "int"},
        {"name": "lmcache_connector_layerwise_retrievers_count", "type": "int"},
    ),
    "lmcache_connector_invalid_block_ids_count": (
        {"name": "lmcache:connector_invalid_block_ids_count", "type": "int"},
        {"name": "lmcache_connector_invalid_block_ids_count", "type": "int"},
    ),
    "lmcache_connector_requests_priority_count": (
        {"name": "lmcache:connector_requests_priority_count", "type": "int"},
        {"name": "lmcache_connector_requests_priority_count", "type": "int"},
    ),
    "lmcache_lookup_requested_tokens": (
        *_mp_counter_aliases("lmcache_mp.lookup_requested_tokens"),
    ),
    "lmcache_lookup_hit_tokens": (
        *_mp_counter_aliases("lmcache_mp.lookup_hit_tokens"),
    ),
    "lmcache_sm_read_requests": (
        *_mp_counter_aliases("lmcache_mp.sm_read_requests"),
    ),
    "lmcache_sm_read_succeed_keys": (
        *_mp_counter_aliases("lmcache_mp.sm_read_succeed_keys"),
    ),
    "lmcache_sm_read_failed_keys": (
        *_mp_counter_aliases("lmcache_mp.sm_read_failed_keys"),
    ),
    "lmcache_sm_write_requests": (
        *_mp_counter_aliases("lmcache_mp.sm_write_requests"),
    ),
    "lmcache_sm_write_succeed_keys": (
        *_mp_counter_aliases("lmcache_mp.sm_write_succeed_keys"),
    ),
    "lmcache_sm_write_failed_keys": (
        *_mp_counter_aliases("lmcache_mp.sm_write_failed_keys"),
    ),
    "lmcache_l1_read_keys": (
        *_mp_counter_aliases("lmcache_mp.l1_read_keys"),
    ),
    "lmcache_l1_write_keys": (
        *_mp_counter_aliases("lmcache_mp.l1_write_keys"),
    ),
    "lmcache_l1_evicted_keys": (
        *_mp_counter_aliases("lmcache_mp.l1_evicted_keys"),
    ),
    "lmcache_l1_memory_usage_bytes": (
        *_mp_gauge_aliases("lmcache_mp.l1_memory_usage_bytes"),
    ),
    "lmcache_l1_allocation_failure": (
        *_mp_counter_aliases("lmcache_mp.l1_allocation_failure"),
    ),
    "lmcache_l1_read_failure": (
        *_mp_counter_aliases("lmcache_mp.l1_read_failure"),
    ),
    "lmcache_l1_chunk_lifetime_seconds": (
        *_mp_hist_aliases("lmcache_mp.l1_chunk_lifetime_seconds"),
    ),
    "lmcache_l1_chunk_idle_before_evict_seconds": (
        *_mp_hist_aliases("lmcache_mp.l1_chunk_idle_before_evict_seconds"),
    ),
    "lmcache_l1_chunk_reuse_gap_seconds": (
        *_mp_hist_aliases("lmcache_mp.l1_chunk_reuse_gap_seconds"),
    ),
    "lmcache_l1_chunk_evict_reuse_gap_seconds": (
        *_mp_hist_aliases("lmcache_mp.l1_chunk_evict_reuse_gap_seconds"),
    ),
    "lmcache_l0_block_lifetime_seconds": (
        *_mp_hist_aliases("lmcache_mp.l0_block_lifetime_seconds"),
    ),
    "lmcache_l0_block_idle_before_evict_seconds": (
        *_mp_hist_aliases("lmcache_mp.l0_block_idle_before_evict_seconds"),
    ),
    "lmcache_l0_block_reuse_gap_seconds": (
        *_mp_hist_aliases("lmcache_mp.l0_block_reuse_gap_seconds"),
    ),
    "lmcache_real_reuse_gap_seconds": (
        *_mp_hist_aliases("lmcache_mp.real_reuse_gap_seconds"),
    ),
    "lmcache_real_reuse_gap_chunks": (
        *_mp_hist_aliases("lmcache_mp.real_reuse_gap_chunks"),
    ),
    "lmcache_l2_store_tasks": (
        *_mp_counter_aliases("lmcache_mp.l2_store_tasks", aggregate="sum"),
    ),
    "lmcache_l2_store_keys": (
        *_mp_counter_aliases("lmcache_mp.l2_store_keys", aggregate="sum"),
    ),
    "lmcache_l2_store_completed": (
        *_mp_counter_aliases("lmcache_mp.l2_store_completed", aggregate="sum"),
    ),
    "lmcache_l2_store_succeeded_keys": (
        *_mp_counter_aliases("lmcache_mp.l2_store_succeeded_keys", aggregate="sum"),
    ),
    "lmcache_l2_store_failed_keys": (
        *_mp_counter_aliases("lmcache_mp.l2_store_failed_keys", aggregate="sum"),
    ),
    "lmcache_l2_prefetch_lookups": (
        *_mp_counter_aliases("lmcache_mp.l2_prefetch_lookups", aggregate="sum"),
    ),
    "lmcache_l2_prefetch_lookup_keys": (
        *_mp_counter_aliases("lmcache_mp.l2_prefetch_lookup_keys", aggregate="sum"),
    ),
    "lmcache_l2_prefetch_hit_keys": (
        *_mp_counter_aliases("lmcache_mp.l2_prefetch_hit_keys", aggregate="sum"),
    ),
    "lmcache_l2_prefetch_load_tasks": (
        *_mp_counter_aliases("lmcache_mp.l2_prefetch_load_tasks", aggregate="sum"),
    ),
    "lmcache_l2_prefetch_load_keys": (
        *_mp_counter_aliases("lmcache_mp.l2_prefetch_load_keys", aggregate="sum"),
    ),
    "lmcache_l2_prefetch_loaded_keys": (
        *_mp_counter_aliases("lmcache_mp.l2_prefetch_loaded_keys", aggregate="sum"),
    ),
    "lmcache_l2_prefetch_failed_keys": (
        *_mp_counter_aliases("lmcache_mp.l2_prefetch_failed_keys", aggregate="sum"),
    ),
    "lmcache_l2_prefetch_failure": (
        *_mp_counter_aliases("lmcache_mp.l2_prefetch_failure", aggregate="sum"),
    ),
    "lmcache_l2_load_completed": (
        *_mp_counter_aliases("lmcache_mp.l2_load_completed", aggregate="sum"),
    ),
    "lmcache_l2_store_throughput_gbs": (
        *_mp_hist_aliases("lmcache_mp.l2_store_throughput_gbs"),
    ),
    "lmcache_l2_load_throughput_gbs": (
        *_mp_hist_aliases("lmcache_mp.l2_load_throughput_gbs"),
    ),
    "lmcache_l0_l1_store_throughput_gbs": (
        *_mp_hist_aliases("lmcache_mp.l0_l1_store_throughput_gbs"),
    ),
    "lmcache_l0_l1_load_throughput_gbs": (
        *_mp_hist_aliases("lmcache_mp.l0_l1_load_throughput_gbs"),
    ),
    "lmcache_num_chunks_loaded": (
        *_mp_counter_aliases("lmcache_mp.num_chunks_loaded"),
    ),
    "lmcache_active_prefetch_jobs": (
        *_mp_gauge_aliases("lmcache_mp.active_prefetch_jobs", aggregate="sum"),
    ),
    "lmcache_num_inflight_l2_stores": (
        *_mp_gauge_aliases("lmcache_mp.num_inflight_l2_stores", aggregate="sum"),
    ),
    "lmcache_num_inflight_l2_loads": (
        *_mp_gauge_aliases("lmcache_mp.num_inflight_l2_loads", aggregate="sum"),
    ),
    "lmcache_inflight_load_memory_usage_bytes": (
        *_mp_gauge_aliases("lmcache_mp.inflight_load_memory_usage_bytes", aggregate="sum"),
    ),
    "lmcache_event_bus_queue_depth": (
        *_mp_gauge_aliases("lmcache_mp.event_bus.queue_depth"),
    ),
    "lmcache_event_bus_drain_lag_seconds": (
        {"name": "lmcache_mp.event_bus.drain_lag_seconds", "type": "float"},
        {"name": "lmcache_mp_event_bus_drain_lag_seconds", "type": "float"},
        *_mp_hist_aliases("lmcache_mp.event_bus.drain_lag_seconds"),
    ),
    "lmcache_event_bus_dropped_events_total": (
        *_mp_counter_aliases("lmcache_mp.event_bus.dropped_events"),
    ),
    "lmcache_event_bus_subscriber_exceptions_total": (
        *_mp_counter_aliases("lmcache_mp.event_bus.subscriber_exceptions"),
    ),
    "lmcache_cacheblend_enabled": (
        {"name": "lmcache:cacheblend_enabled", "type": "bool"},
        {"name": "lmcache_cacheblend_enabled", "type": "bool"},
        {"name": "lmcache_config_info", "label": "cacheblend", "type": "bool_label"},
    ),
    "lmcache_cachegen_enabled": (
        {"name": "lmcache:cachegen_enabled", "type": "bool"},
        {"name": "lmcache_cachegen_enabled", "type": "bool"},
        {"name": "lmcache_config_info", "label": "cachegen", "type": "bool_label"},
    ),
    "lmcache_mp_mode_enabled": (
        {"name": "lmcache:mp_mode_enabled", "type": "bool"},
        {"name": "lmcache_mp_mode_enabled", "type": "bool"},
        {"name": "lmcache_config_info", "label": "mp_mode", "type": "bool_label"},
    ),
    "lmcache_connector_type": (
        {"name": "lmcache_config_info", "label": "connector", "type": "str_label"},
        {"name": "lmcache:connector_info", "label": "connector", "type": "str_label"},
        {"name": "lmcache_connector_info", "label": "connector", "type": "str_label"},
        {"name": "lmcache_nixl_transfer_bytes_total", "const": "nixl", "type": "str_const"},
        {"name": "lmcache_mp_lookup_requested_tokens_total", "const": "LMCacheMPConnector", "type": "str_const"},
    ),
    "lmcache_cache_salt_enabled": (
        {"name": "lmcache:cache_salt_enabled", "type": "bool"},
        {"name": "lmcache_cache_salt_enabled", "type": "bool"},
        {"name": "lmcache_config_info", "label": "cache_salt", "type": "bool_label"},
    ),
    "lmcache_blend_lookup_requests": (
        {"name": "lmcache_blend_lookup_requests_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_lookup_requests", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_lookup_fingerprint_hits": (
        {"name": "lmcache_blend_lookup_fingerprint_hits_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_lookup_fingerprint_hits", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_lookup_storage_hits": (
        {"name": "lmcache_blend_lookup_storage_hits_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_lookup_storage_hits", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_lookup_requested_tokens": (
        {"name": "lmcache_blend_lookup_requested_tokens_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_lookup_requested_tokens", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_lookup_hit_tokens": (
        {"name": "lmcache_blend_lookup_hit_tokens_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_lookup_hit_tokens", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_lookup_stale_chunks": (
        {"name": "lmcache_blend_lookup_stale_chunks_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_lookup_stale_chunks", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_lookup_no_gpu_context_errors": (
        {"name": "lmcache_blend_lookup_no_gpu_context_errors_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_lookup_no_gpu_context_errors", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_l0_gpu_operation_duration_seconds": (
        {"name": "lmcache_blend_l0_gpu_operation_duration_seconds", "type": "hist_avg"},
    ),
    "lmcache_blend_l0_gpu_transfer_chunks": (
        {"name": "lmcache_blend_l0_gpu_transfer_chunks_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_l0_gpu_transfer_chunks", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_l0_gpu_transfer_tokens": (
        {"name": "lmcache_blend_l0_gpu_transfer_tokens_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_l0_gpu_transfer_tokens", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_retrieve_requests": (
        {"name": "lmcache_blend_retrieve_requests_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_retrieve_requests", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_retrieve_chunks": (
        {"name": "lmcache_blend_retrieve_chunks_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_retrieve_chunks", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_retrieve_failures": (
        {"name": "lmcache_blend_retrieve_failures_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_retrieve_failures", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_store_pre_computed_requests": (
        {"name": "lmcache_blend_store_pre_computed_requests_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_store_pre_computed_requests", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_store_pre_computed_chunks": (
        {"name": "lmcache_blend_store_pre_computed_chunks_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_store_pre_computed_chunks", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_store_pre_computed_failures": (
        {"name": "lmcache_blend_store_pre_computed_failures_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_store_pre_computed_failures", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_store_final_requests": (
        {"name": "lmcache_blend_store_final_requests_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_store_final_requests", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_store_final_chunks": (
        {"name": "lmcache_blend_store_final_chunks_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_store_final_chunks", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_store_final_failures": (
        {"name": "lmcache_blend_store_final_failures_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_store_final_failures", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_fingerprints_registered": (
        {"name": "lmcache_blend_fingerprints_registered_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_fingerprints_registered", "type": "int", "aggregate": "sum"},
    ),
    "lmcache_blend_chunks_evicted": (
        {"name": "lmcache_blend_chunks_evicted_total", "type": "int", "aggregate": "sum"},
        {"name": "lmcache_blend_chunks_evicted", "type": "int", "aggregate": "sum"},
    ),
}


def parse_lmcache_prometheus(text: str) -> LmcacheMetrics:
    """Normalize LMCache-ish Prometheus exposition text."""
    samples = parse_labeled_prometheus_text(text)
    values: dict[str, Any] = {}
    matched_names: set[str] = set()
    for field_name, aliases in _ALIAS_TABLE.items():
        value, names = _first_alias(samples, aliases)
        if value is not None:
            values[field_name] = value
            matched_names.update(names)
    if values.get("lmcache_hit_rate") is None:
        hit = values.get("lmcache_lookup_hit_tokens") or values.get("lmcache_hit_count")
        requested = values.get("lmcache_lookup_requested_tokens")
        if isinstance(hit, int) and isinstance(requested, int) and requested > 0:
            values["lmcache_hit_rate"] = hit / requested
            if values.get("lmcache_miss_count") is None:
                values["lmcache_miss_count"] = max(requested - hit, 0)
        miss = values.get("lmcache_miss_count")
        if isinstance(hit, int) and isinstance(miss, int) and hit + miss > 0:
            values["lmcache_hit_rate"] = hit / (hit + miss)
    if values.get("lmcache_hit_count") is None and values.get("lmcache_lookup_hit_tokens") is not None:
        values["lmcache_hit_count"] = values["lmcache_lookup_hit_tokens"]
    if any(sample.name.startswith(("lmcache_mp_", "lmcache_mp.")) for sample in samples):
        values["lmcache_mp_mode_enabled"] = True
        values.setdefault("lmcache_enabled", True)
        values.setdefault("lmcache_connector_type", "LMCacheMPConnector")
    if any(sample.name.startswith("lmcache_blend_") for sample in samples):
        values["lmcache_cacheblend_enabled"] = True
        values.setdefault("lmcache_enabled", True)
    values["raw_metrics_extra"] = _raw_extra(samples, matched_names)
    return LmcacheMetrics(**values)


def _first_alias(samples: list[LabeledSample], aliases: tuple[dict[str, Any], ...]) -> tuple[Any | None, set[str]]:
    seen: set[str] = set()
    for alias in aliases:
        if alias.get("type") == "hist_avg":
            base_name = str(alias["name"])
            value = _hist_avg(samples, base_name)
            if value is not None:
                if alias.get("convert") == "seconds_to_ms":
                    value *= 1000.0
                return value, {base_name, f"{base_name}_sum", f"{base_name}_count"}
            continue
        if alias.get("aggregate") == "sum":
            selected = [
                sample
                for sample in samples
                if sample.name == alias["name"] and _labels_match(sample, alias.get("labels") or {})
            ]
            if selected:
                total = sum(_coerce(sample, alias) or 0 for sample in selected)
                return total, {sample.name for sample in selected}
            continue
        for sample in samples:
            if sample.name != alias["name"]:
                continue
            if not _labels_match(sample, alias.get("labels") or {}):
                continue
            value = _coerce(sample, alias)
            if value is not None:
                seen.add(sample.name)
                return value, seen
    return None, seen


def _hist_avg(samples: list[LabeledSample], base_name: str) -> float | None:
    total = 0.0
    count = 0.0
    for sample in samples:
        if sample.name == f"{base_name}_sum":
            total += sample.value
        elif sample.name == f"{base_name}_count":
            count += sample.value
    if count <= 0:
        return None
    return round(total / count, 12)


def _labels_match(sample: LabeledSample, expected: dict[str, str]) -> bool:
    return all(sample.labels.get(key) == value for key, value in expected.items())


def _coerce(sample: LabeledSample, alias: dict[str, Any]) -> Any | None:
    alias_type = alias.get("type")
    value = sample.value
    if alias.get("convert") == "seconds_to_ms":
        value *= 1000.0
    if alias_type == "int":
        return int(value)
    if alias_type == "float":
        return float(value)
    if alias_type == "hist_avg":
        return float(value)
    if alias_type == "bool":
        return bool(value)
    if alias_type == "bool_label":
        raw = sample.labels.get(str(alias.get("label")), "")
        return _truthy_label(raw) if raw else None
    if alias_type == "str_label":
        raw = sample.labels.get(str(alias.get("label")), "")
        return raw.lower() if raw else None
    if alias_type == "str_const":
        return alias.get("const")
    return None


def _truthy_label(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled", "enable"}


def _raw_extra(samples: list[LabeledSample], matched_names: set[str]) -> dict[str, float]:
    extras: dict[str, float] = {}
    for sample in samples:
        if not (sample.name.startswith("lmcache") or sample.name.startswith("lm_cache")):
            continue
        if sample.name in matched_names:
            continue
        extras[sample.name] = sample.value
    return extras


__all__ = ["LmcacheMetrics", "NORMALIZED_LMCACHE_FIELDS", "parse_lmcache_prometheus"]
