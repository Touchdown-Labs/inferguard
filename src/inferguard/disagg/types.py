"""Normalized data types for the disaggregated-serving diagnostic surface.

These are the public contract for JSON output on both the CLI and the MCP
tools. Changing the shape in any breaking way requires a v2 sibling and a
semver-minor bump. See ``docs/SCHEMAS.md`` in this repo.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = "disagg-status/v1"

EngineName = Literal["vllm", "sglang", "dynamo", "lmcache", "llm-d", "unknown"]
Role = Literal["prefill", "decode", "transfer"]
Severity = Literal["info", "warning", "critical"]
FindingCode = Literal[
    "hma_offload_incompatible",
    "connector_mismatch",
    "prefill_decode_imbalance",
    "kv_transfer_errors_present",
    "kv_transfer_stall",
    "endpoint_unreachable",
    "engine_unidentified",
    "kv_footprint_imbalance",
    "prefix_eviction_cross_customer",
    "cold_start_ramp_extended",
    "engine_crash_recovery_slow",
    "multi_tenant_noisy_neighbor",
    "gpu_partial_degradation",
    "oom_giant_prefill_blast_radius",
    "cost_idle_underutilization_high",
    "retry_storm_engine_overload",
    "canary_quality_regression",
    "blue_green_p99_regression",
    "tokenizer_mismatch_silent_drift",
    "prompt_template_tool_parser_regression",
]


@dataclass(frozen=True)
class EndpointId:
    """Identity of a single scrape target."""

    url: str
    role: Role
    engine: EngineName
    engine_version: str = ""
    connector: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DisaggSnapshot:
    """Normalized metric snapshot for a single endpoint.

    Fields are ``None`` when the engine does not expose a corresponding
    metric. Consumers should branch on presence, not on zero.
    """

    endpoint: EndpointId
    scraped_at: float
    kv_cache_usage: float | None = None
    requests_running: int | None = None
    requests_waiting: int | None = None
    requests_swapped: int | None = None
    preemptions_total: int | None = None
    ttft_avg_seconds: float | None = None
    tpot_avg_seconds: float | None = None
    kv_transfer_sent_bytes_total: int | None = None
    kv_transfer_recv_bytes_total: int | None = None
    kv_transfer_errors_total: int | None = None
    vllm_offload_dma_bytes_per_sec: float | None = None
    vllm_offload_async_queue_depth: int | None = None
    vllm_offload_eviction_count: int | None = None
    prefix_cache_hits: int | None = None
    prefix_cache_queries: int | None = None
    cpu_prefix_cache_hits: int | None = None
    cpu_prefix_cache_queries: int | None = None
    external_prefix_cache_hits: int | None = None
    external_prefix_cache_queries: int | None = None
    prompt_tokens_cached_total: int | None = None
    prompt_tokens_local_compute: int | None = None
    prompt_tokens_local_cache_hit: int | None = None
    prompt_tokens_external_kv_transfer: int | None = None
    kv_offload_bytes_gpu_to_cpu: float | None = None
    kv_offload_bytes_cpu_to_gpu: float | None = None
    kv_offload_time_gpu_to_cpu: float | None = None
    kv_offload_time_cpu_to_gpu: float | None = None
    cpu_kv_cache_usage_pct: float | None = None
    simple_cpu_offload_total_blocks: int | None = None
    simple_cpu_offload_free_blocks: int | None = None
    simple_cpu_offload_used_blocks: int | None = None
    simple_cpu_offload_usage_perc: float | None = None
    simple_cpu_offload_pending_loads: int | None = None
    simple_cpu_offload_pending_stores: int | None = None
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
    lmcache_tier_local_disk_bytes: int | None = None
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
    dynamo_block_residency_seconds: float | None = None
    dynamo_block_l1_count: int | None = None
    dynamo_block_l2_count: int | None = None
    dynamo_block_l3_count: int | None = None
    dynamo_kvbm_evictions: int | None = None
    dynamo_kvbm_promotions: int | None = None
    sglang_hicache_l1_hit_count: int | None = None
    sglang_hicache_l2_hit_count: int | None = None
    sglang_hicache_l3_hit_count: int | None = None
    sglang_hicache_lookup_count: int | None = None
    sglang_hicache_l2_bytes: int | None = None
    sglang_hicache_l3_bytes: int | None = None
    prefill_queue_depth: int | None = None
    decode_queue_depth: int | None = None
    scrape_error: str = ""
    raw_labels: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint.as_dict(),
            "scraped_at": self.scraped_at,
            "kv_cache_usage": self.kv_cache_usage,
            "requests_running": self.requests_running,
            "requests_waiting": self.requests_waiting,
            "requests_swapped": self.requests_swapped,
            "preemptions_total": self.preemptions_total,
            "ttft_avg_seconds": self.ttft_avg_seconds,
            "tpot_avg_seconds": self.tpot_avg_seconds,
            "kv_transfer_sent_bytes_total": self.kv_transfer_sent_bytes_total,
            "kv_transfer_recv_bytes_total": self.kv_transfer_recv_bytes_total,
            "kv_transfer_errors_total": self.kv_transfer_errors_total,
            "vllm_offload_dma_bytes_per_sec": self.vllm_offload_dma_bytes_per_sec,
            "vllm_offload_async_queue_depth": self.vllm_offload_async_queue_depth,
            "vllm_offload_eviction_count": self.vllm_offload_eviction_count,
            "prefix_cache_hits": self.prefix_cache_hits,
            "prefix_cache_queries": self.prefix_cache_queries,
            "cpu_prefix_cache_hits": self.cpu_prefix_cache_hits,
            "cpu_prefix_cache_queries": self.cpu_prefix_cache_queries,
            "external_prefix_cache_hits": self.external_prefix_cache_hits,
            "external_prefix_cache_queries": self.external_prefix_cache_queries,
            "prompt_tokens_cached_total": self.prompt_tokens_cached_total,
            "prompt_tokens_local_compute": self.prompt_tokens_local_compute,
            "prompt_tokens_local_cache_hit": self.prompt_tokens_local_cache_hit,
            "prompt_tokens_external_kv_transfer": self.prompt_tokens_external_kv_transfer,
            "kv_offload_bytes_gpu_to_cpu": self.kv_offload_bytes_gpu_to_cpu,
            "kv_offload_bytes_cpu_to_gpu": self.kv_offload_bytes_cpu_to_gpu,
            "kv_offload_time_gpu_to_cpu": self.kv_offload_time_gpu_to_cpu,
            "kv_offload_time_cpu_to_gpu": self.kv_offload_time_cpu_to_gpu,
            "cpu_kv_cache_usage_pct": self.cpu_kv_cache_usage_pct,
            "simple_cpu_offload_total_blocks": self.simple_cpu_offload_total_blocks,
            "simple_cpu_offload_free_blocks": self.simple_cpu_offload_free_blocks,
            "simple_cpu_offload_used_blocks": self.simple_cpu_offload_used_blocks,
            "simple_cpu_offload_usage_perc": self.simple_cpu_offload_usage_perc,
            "simple_cpu_offload_pending_loads": self.simple_cpu_offload_pending_loads,
            "simple_cpu_offload_pending_stores": self.simple_cpu_offload_pending_stores,
            "lmcache_enabled": self.lmcache_enabled,
            "lmcache_hit_count": self.lmcache_hit_count,
            "lmcache_miss_count": self.lmcache_miss_count,
            "lmcache_hit_rate": self.lmcache_hit_rate,
            "lmcache_eviction_count": self.lmcache_eviction_count,
            "lmcache_save_count": self.lmcache_save_count,
            "lmcache_retrieve_count": self.lmcache_retrieve_count,
            "lmcache_tier_hbm_bytes": self.lmcache_tier_hbm_bytes,
            "lmcache_tier_cpu_bytes": self.lmcache_tier_cpu_bytes,
            "lmcache_tier_disk_bytes": self.lmcache_tier_disk_bytes,
            "lmcache_tier_local_disk_bytes": self.lmcache_tier_local_disk_bytes,
            "lmcache_tier_remote_bytes": self.lmcache_tier_remote_bytes,
            "lmcache_offload_bytes_total": self.lmcache_offload_bytes_total,
            "lmcache_retrieve_latency_ms_p50": self.lmcache_retrieve_latency_ms_p50,
            "lmcache_retrieve_latency_ms_p95": self.lmcache_retrieve_latency_ms_p95,
            "lmcache_retrieve_latency_ms_p99": self.lmcache_retrieve_latency_ms_p99,
            "lmcache_nixl_transfer_bytes": self.lmcache_nixl_transfer_bytes,
            "lmcache_nixl_transfer_latency_ms": self.lmcache_nixl_transfer_latency_ms,
            "lmcache_cacheblend_enabled": self.lmcache_cacheblend_enabled,
            "lmcache_cachegen_enabled": self.lmcache_cachegen_enabled,
            "lmcache_mp_mode_enabled": self.lmcache_mp_mode_enabled,
            "lmcache_connector_type": self.lmcache_connector_type,
            "lmcache_cache_salt_enabled": self.lmcache_cache_salt_enabled,
            "lmcache_remote_bytes_sent": self.lmcache_remote_bytes_sent,
            "lmcache_remote_bytes_received": self.lmcache_remote_bytes_received,
            "lmcache_queue_depth": self.lmcache_queue_depth,
            "lmcache_num_retrieve_requests": self.lmcache_num_retrieve_requests,
            "lmcache_num_store_requests": self.lmcache_num_store_requests,
            "lmcache_num_lookup_requests": self.lmcache_num_lookup_requests,
            "lmcache_num_requested_tokens": self.lmcache_num_requested_tokens,
            "lmcache_num_hit_tokens": self.lmcache_num_hit_tokens,
            "lmcache_num_stored_tokens": self.lmcache_num_stored_tokens,
            "lmcache_num_lookup_tokens": self.lmcache_num_lookup_tokens,
            "lmcache_num_lookup_hits": self.lmcache_num_lookup_hits,
            "lmcache_num_vllm_hit_tokens": self.lmcache_num_vllm_hit_tokens,
            "lmcache_num_prompt_tokens": self.lmcache_num_prompt_tokens,
            "lmcache_retrieve_hit_rate": self.lmcache_retrieve_hit_rate,
            "lmcache_lookup_hit_rate": self.lmcache_lookup_hit_rate,
            "lmcache_request_cache_hit_rate": self.lmcache_request_cache_hit_rate,
            "lmcache_lookup_0_hit_requests": self.lmcache_lookup_0_hit_requests,
            "lmcache_time_to_retrieve_seconds": self.lmcache_time_to_retrieve_seconds,
            "lmcache_time_to_store_seconds": self.lmcache_time_to_store_seconds,
            "lmcache_time_to_lookup_seconds": self.lmcache_time_to_lookup_seconds,
            "lmcache_retrieve_speed_tokens_per_second": self.lmcache_retrieve_speed_tokens_per_second,
            "lmcache_store_speed_tokens_per_second": self.lmcache_store_speed_tokens_per_second,
            "lmcache_num_slow_retrieval_by_time": self.lmcache_num_slow_retrieval_by_time,
            "lmcache_num_slow_retrieval_by_speed": self.lmcache_num_slow_retrieval_by_speed,
            "lmcache_retrieve_process_tokens_time_seconds": self.lmcache_retrieve_process_tokens_time_seconds,
            "lmcache_retrieve_broadcast_time_seconds": self.lmcache_retrieve_broadcast_time_seconds,
            "lmcache_retrieve_to_gpu_time_seconds": self.lmcache_retrieve_to_gpu_time_seconds,
            "lmcache_store_process_tokens_time_seconds": self.lmcache_store_process_tokens_time_seconds,
            "lmcache_store_from_gpu_time_seconds": self.lmcache_store_from_gpu_time_seconds,
            "lmcache_store_put_time_seconds": self.lmcache_store_put_time_seconds,
            "lmcache_remote_backend_batched_get_blocking_time_seconds": self.lmcache_remote_backend_batched_get_blocking_time_seconds,
            "lmcache_instrumented_connector_batched_get_time_seconds": self.lmcache_instrumented_connector_batched_get_time_seconds,
            "lmcache_local_cache_usage_bytes": self.lmcache_local_cache_usage_bytes,
            "lmcache_remote_cache_usage_bytes": self.lmcache_remote_cache_usage_bytes,
            "lmcache_local_storage_usage_bytes": self.lmcache_local_storage_usage_bytes,
            "lmcache_request_cache_lifespan_minutes": self.lmcache_request_cache_lifespan_minutes,
            "lmcache_is_healthy": self.lmcache_is_healthy,
            "lmcache_storage_event_count": self.lmcache_storage_event_count,
            "lmcache_num_remote_read_requests": self.lmcache_num_remote_read_requests,
            "lmcache_num_remote_write_requests": self.lmcache_num_remote_write_requests,
            "lmcache_remote_read_bytes": self.lmcache_remote_read_bytes,
            "lmcache_remote_write_bytes": self.lmcache_remote_write_bytes,
            "lmcache_remote_time_to_get_ms": self.lmcache_remote_time_to_get_ms,
            "lmcache_remote_time_to_put_ms": self.lmcache_remote_time_to_put_ms,
            "lmcache_remote_time_to_get_sync_ms": self.lmcache_remote_time_to_get_sync_ms,
            "lmcache_remote_ping_latency_ms": self.lmcache_remote_ping_latency_ms,
            "lmcache_remote_ping_errors": self.lmcache_remote_ping_errors,
            "lmcache_remote_ping_successes": self.lmcache_remote_ping_successes,
            "lmcache_remote_ping_error_code": self.lmcache_remote_ping_error_code,
            "lmcache_local_cpu_evict_count": self.lmcache_local_cpu_evict_count,
            "lmcache_local_cpu_evict_keys_count": self.lmcache_local_cpu_evict_keys_count,
            "lmcache_local_cpu_evict_failed_count": self.lmcache_local_cpu_evict_failed_count,
            "lmcache_local_cpu_hot_cache_count": self.lmcache_local_cpu_hot_cache_count,
            "lmcache_local_cpu_keys_in_request_count": self.lmcache_local_cpu_keys_in_request_count,
            "lmcache_active_memory_objs_count": self.lmcache_active_memory_objs_count,
            "lmcache_pinned_memory_objs_count": self.lmcache_pinned_memory_objs_count,
            "lmcache_forced_unpin_count": self.lmcache_forced_unpin_count,
            "lmcache_pin_monitor_pinned_objects_count": self.lmcache_pin_monitor_pinned_objects_count,
            "lmcache_p2p_requests": self.lmcache_p2p_requests,
            "lmcache_p2p_transferred_tokens": self.lmcache_p2p_transferred_tokens,
            "lmcache_p2p_time_to_transfer_ms": self.lmcache_p2p_time_to_transfer_ms,
            "lmcache_p2p_transfer_speed": self.lmcache_p2p_transfer_speed,
            "lmcache_chunk_stats_enabled": self.lmcache_chunk_stats_enabled,
            "lmcache_total_chunk_requests": self.lmcache_total_chunk_requests,
            "lmcache_total_chunks": self.lmcache_total_chunks,
            "lmcache_unique_chunks": self.lmcache_unique_chunks,
            "lmcache_chunk_statistics_reuse_rate": self.lmcache_chunk_statistics_reuse_rate,
            "lmcache_chunk_statistics_bloom_filter_size_mb": self.lmcache_chunk_statistics_bloom_filter_size_mb,
            "lmcache_chunk_statistics_bloom_filter_fill_rate": self.lmcache_chunk_statistics_bloom_filter_fill_rate,
            "lmcache_chunk_statistics_file_count": self.lmcache_chunk_statistics_file_count,
            "lmcache_chunk_statistics_current_file_size": self.lmcache_chunk_statistics_current_file_size,
            "lmcache_scheduler_unfinished_requests_count": self.lmcache_scheduler_unfinished_requests_count,
            "lmcache_connector_load_specs_count": self.lmcache_connector_load_specs_count,
            "lmcache_connector_request_trackers_count": self.lmcache_connector_request_trackers_count,
            "lmcache_connector_kv_caches_count": self.lmcache_connector_kv_caches_count,
            "lmcache_connector_layerwise_retrievers_count": self.lmcache_connector_layerwise_retrievers_count,
            "lmcache_connector_invalid_block_ids_count": self.lmcache_connector_invalid_block_ids_count,
            "lmcache_connector_requests_priority_count": self.lmcache_connector_requests_priority_count,
            "lmcache_lookup_requested_tokens": self.lmcache_lookup_requested_tokens,
            "lmcache_lookup_hit_tokens": self.lmcache_lookup_hit_tokens,
            "lmcache_sm_read_requests": self.lmcache_sm_read_requests,
            "lmcache_sm_read_succeed_keys": self.lmcache_sm_read_succeed_keys,
            "lmcache_sm_read_failed_keys": self.lmcache_sm_read_failed_keys,
            "lmcache_sm_write_requests": self.lmcache_sm_write_requests,
            "lmcache_sm_write_succeed_keys": self.lmcache_sm_write_succeed_keys,
            "lmcache_sm_write_failed_keys": self.lmcache_sm_write_failed_keys,
            "lmcache_l1_read_keys": self.lmcache_l1_read_keys,
            "lmcache_l1_write_keys": self.lmcache_l1_write_keys,
            "lmcache_l1_evicted_keys": self.lmcache_l1_evicted_keys,
            "lmcache_l1_memory_usage_bytes": self.lmcache_l1_memory_usage_bytes,
            "lmcache_l1_allocation_failure": self.lmcache_l1_allocation_failure,
            "lmcache_l1_read_failure": self.lmcache_l1_read_failure,
            "lmcache_l1_chunk_lifetime_seconds": self.lmcache_l1_chunk_lifetime_seconds,
            "lmcache_l1_chunk_idle_before_evict_seconds": self.lmcache_l1_chunk_idle_before_evict_seconds,
            "lmcache_l1_chunk_reuse_gap_seconds": self.lmcache_l1_chunk_reuse_gap_seconds,
            "lmcache_l1_chunk_evict_reuse_gap_seconds": self.lmcache_l1_chunk_evict_reuse_gap_seconds,
            "lmcache_l0_block_lifetime_seconds": self.lmcache_l0_block_lifetime_seconds,
            "lmcache_l0_block_idle_before_evict_seconds": self.lmcache_l0_block_idle_before_evict_seconds,
            "lmcache_l0_block_reuse_gap_seconds": self.lmcache_l0_block_reuse_gap_seconds,
            "lmcache_real_reuse_gap_seconds": self.lmcache_real_reuse_gap_seconds,
            "lmcache_real_reuse_gap_chunks": self.lmcache_real_reuse_gap_chunks,
            "lmcache_l2_store_tasks": self.lmcache_l2_store_tasks,
            "lmcache_l2_store_keys": self.lmcache_l2_store_keys,
            "lmcache_l2_store_completed": self.lmcache_l2_store_completed,
            "lmcache_l2_store_succeeded_keys": self.lmcache_l2_store_succeeded_keys,
            "lmcache_l2_store_failed_keys": self.lmcache_l2_store_failed_keys,
            "lmcache_l2_prefetch_lookups": self.lmcache_l2_prefetch_lookups,
            "lmcache_l2_prefetch_lookup_keys": self.lmcache_l2_prefetch_lookup_keys,
            "lmcache_l2_prefetch_hit_keys": self.lmcache_l2_prefetch_hit_keys,
            "lmcache_l2_prefetch_load_tasks": self.lmcache_l2_prefetch_load_tasks,
            "lmcache_l2_prefetch_load_keys": self.lmcache_l2_prefetch_load_keys,
            "lmcache_l2_prefetch_loaded_keys": self.lmcache_l2_prefetch_loaded_keys,
            "lmcache_l2_prefetch_failed_keys": self.lmcache_l2_prefetch_failed_keys,
            "lmcache_l2_prefetch_failure": self.lmcache_l2_prefetch_failure,
            "lmcache_l2_load_completed": self.lmcache_l2_load_completed,
            "lmcache_l2_store_throughput_gbs": self.lmcache_l2_store_throughput_gbs,
            "lmcache_l2_load_throughput_gbs": self.lmcache_l2_load_throughput_gbs,
            "lmcache_l0_l1_store_throughput_gbs": self.lmcache_l0_l1_store_throughput_gbs,
            "lmcache_l0_l1_load_throughput_gbs": self.lmcache_l0_l1_load_throughput_gbs,
            "lmcache_num_chunks_loaded": self.lmcache_num_chunks_loaded,
            "lmcache_active_prefetch_jobs": self.lmcache_active_prefetch_jobs,
            "lmcache_num_inflight_l2_stores": self.lmcache_num_inflight_l2_stores,
            "lmcache_num_inflight_l2_loads": self.lmcache_num_inflight_l2_loads,
            "lmcache_inflight_load_memory_usage_bytes": self.lmcache_inflight_load_memory_usage_bytes,
            "lmcache_event_bus_queue_depth": self.lmcache_event_bus_queue_depth,
            "lmcache_event_bus_drain_lag_seconds": self.lmcache_event_bus_drain_lag_seconds,
            "lmcache_event_bus_dropped_events_total": self.lmcache_event_bus_dropped_events_total,
            "lmcache_event_bus_subscriber_exceptions_total": self.lmcache_event_bus_subscriber_exceptions_total,
            "lmcache_blend_lookup_requests": self.lmcache_blend_lookup_requests,
            "lmcache_blend_lookup_fingerprint_hits": self.lmcache_blend_lookup_fingerprint_hits,
            "lmcache_blend_lookup_storage_hits": self.lmcache_blend_lookup_storage_hits,
            "lmcache_blend_lookup_requested_tokens": self.lmcache_blend_lookup_requested_tokens,
            "lmcache_blend_lookup_hit_tokens": self.lmcache_blend_lookup_hit_tokens,
            "lmcache_blend_lookup_stale_chunks": self.lmcache_blend_lookup_stale_chunks,
            "lmcache_blend_lookup_no_gpu_context_errors": self.lmcache_blend_lookup_no_gpu_context_errors,
            "lmcache_blend_l0_gpu_operation_duration_seconds": self.lmcache_blend_l0_gpu_operation_duration_seconds,
            "lmcache_blend_l0_gpu_transfer_chunks": self.lmcache_blend_l0_gpu_transfer_chunks,
            "lmcache_blend_l0_gpu_transfer_tokens": self.lmcache_blend_l0_gpu_transfer_tokens,
            "lmcache_blend_retrieve_requests": self.lmcache_blend_retrieve_requests,
            "lmcache_blend_retrieve_chunks": self.lmcache_blend_retrieve_chunks,
            "lmcache_blend_retrieve_failures": self.lmcache_blend_retrieve_failures,
            "lmcache_blend_store_pre_computed_requests": self.lmcache_blend_store_pre_computed_requests,
            "lmcache_blend_store_pre_computed_chunks": self.lmcache_blend_store_pre_computed_chunks,
            "lmcache_blend_store_pre_computed_failures": self.lmcache_blend_store_pre_computed_failures,
            "lmcache_blend_store_final_requests": self.lmcache_blend_store_final_requests,
            "lmcache_blend_store_final_chunks": self.lmcache_blend_store_final_chunks,
            "lmcache_blend_store_final_failures": self.lmcache_blend_store_final_failures,
            "lmcache_blend_fingerprints_registered": self.lmcache_blend_fingerprints_registered,
            "lmcache_blend_chunks_evicted": self.lmcache_blend_chunks_evicted,
            "lmcache_get_blocking_failed_count": self.lmcache_get_blocking_failed_count,
            "lmcache_put_failed_count": self.lmcache_put_failed_count,
            "lmcache_kv_msg_queue_size": self.lmcache_kv_msg_queue_size,
            "lmcache_remote_put_task_num": self.lmcache_remote_put_task_num,
            "lmcache_storage_events_ongoing_count": self.lmcache_storage_events_ongoing_count,
            "lmcache_storage_events_done_count": self.lmcache_storage_events_done_count,
            "lmcache_storage_events_not_found_count": self.lmcache_storage_events_not_found_count,
            "lmcache_chunk_statistics_count": self.lmcache_chunk_statistics_count,
            "raw_metrics_extra": dict(self.raw_metrics_extra),
            "dynamo_block_residency_seconds": self.dynamo_block_residency_seconds,
            "dynamo_block_l1_count": self.dynamo_block_l1_count,
            "dynamo_block_l2_count": self.dynamo_block_l2_count,
            "dynamo_block_l3_count": self.dynamo_block_l3_count,
            "dynamo_kvbm_evictions": self.dynamo_kvbm_evictions,
            "dynamo_kvbm_promotions": self.dynamo_kvbm_promotions,
            "sglang_hicache_l1_hit_count": self.sglang_hicache_l1_hit_count,
            "sglang_hicache_l2_hit_count": self.sglang_hicache_l2_hit_count,
            "sglang_hicache_l3_hit_count": self.sglang_hicache_l3_hit_count,
            "sglang_hicache_lookup_count": self.sglang_hicache_lookup_count,
            "sglang_hicache_l2_bytes": self.sglang_hicache_l2_bytes,
            "sglang_hicache_l3_bytes": self.sglang_hicache_l3_bytes,
            "prefill_queue_depth": self.prefill_queue_depth,
            "decode_queue_depth": self.decode_queue_depth,
            "scrape_error": self.scrape_error,
            "raw_labels": dict(self.raw_labels),
        }


@dataclass(frozen=True)
class DisaggFinding:
    """A single diagnostic observation about a disagg deployment."""

    code: FindingCode
    severity: Severity
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class DisaggStatus:
    """Top-level diagnostic result for a prefill/decode/(transfer) triple."""

    prefill: DisaggSnapshot
    decode: DisaggSnapshot
    transfer: DisaggSnapshot | None
    findings: list[DisaggFinding] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "prefill": self.prefill.as_dict(),
            "decode": self.decode.as_dict(),
            "transfer": self.transfer.as_dict() if self.transfer is not None else None,
            "findings": [f.as_dict() for f in self.findings],
        }
