"""Prometheus normalization for ``collect-metrics``."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from inferguard.disagg.types import DisaggSnapshot
from inferguard.harness.dcgm_correlate import parse_dcgm_samples, parse_prometheus_text
from inferguard.metrics_core import LabeledSample, parse_labeled_prometheus_text

from .types import ENGINE_GROUPS, GPU_GROUPS, NORMALIZED_GROUPS

VLLM_LOCKED_METRICS: tuple[str, ...] = (
    "vllm:time_to_first_token_seconds",
    "vllm:time_per_output_token_seconds",
    "vllm:inter_token_latency_seconds",
    "vllm:e2e_request_latency_seconds",
    "vllm:request_queue_time_seconds",
    "vllm:request_prefill_time_seconds",
    "vllm:request_decode_time_seconds",
    "vllm:request_prompt_tokens",
    "vllm:request_generation_tokens",
    "vllm:prompt_tokens_total",
    "vllm:generation_tokens_total",
    "vllm:request_success_total",
    "vllm:prefix_cache_queries",
    "vllm:prefix_cache_hits",
    "vllm:external_prefix_cache_queries",
    "vllm:external_prefix_cache_hits",
    "vllm:prompt_tokens_by_source",
    "vllm:prompt_tokens_cached",
    "vllm:num_requests_running",
    "vllm:num_requests_waiting",
    "vllm:gpu_cache_usage_perc",
    "vllm:kv_cache_usage_perc",
    "vllm:cache_config_info",
    "vllm:kv_block_lifetime_seconds",
    "vllm:kv_block_idle_before_evict_seconds",
    "vllm:kv_block_reuse_gap_seconds",
    "vllm:kv_offload_total_bytes",
    "vllm:kv_offload_total_time",
    "vllm:kv_offload_size",
    "vllm:simple_cpu_offload_total_blocks",
    "vllm:simple_cpu_offload_free_blocks",
    "vllm:simple_cpu_offload_used_blocks",
    "vllm:simple_cpu_offload_usage_perc",
    "vllm:simple_cpu_offload_pending_loads",
    "vllm:simple_cpu_offload_pending_stores",
)

SGLANG_LOCKED_METRICS: tuple[str, ...] = (
    "sglang:prompt_tokens_total",
    "sglang:generation_tokens_total",
    "sglang:token_usage",
    "sglang:cache_hit_rate",
    "sglang:num_running_reqs",
    "sglang:num_used_tokens",
    "sglang:gen_throughput",
    "sglang:num_queue_reqs",
    "sglang:time_to_first_token_seconds",
    "sglang:e2e_request_latency_seconds",
    "sglang:time_per_output_token_seconds",
    "sglang:func_latency_seconds",
    "sglang:estimated_flops_per_gpu_total",
    "sglang:num_preemptions_total",
    "sglang:hicache_l1_hit_count_total",
    "sglang:hicache_l2_hit_count_total",
    "sglang:hicache_l3_hit_count_total",
    "sglang:hicache_lookup_count_total",
    "sglang:hicache_l2_bytes",
    "sglang:hicache_l3_bytes",
)

LMCACHE_LOCKED_METRICS: tuple[str, ...] = (
    "lmcache:num_hit_tokens",
    "lmcache:num_lookup_hits",
    "lmcache:num_retrieve_requests",
    "lmcache:num_store_requests",
    "lmcache:num_lookup_requests",
    "lmcache:num_requested_tokens",
    "lmcache:num_lookup_tokens",
    "lmcache:is_healthy",
    "lmcache:num_p2p_requests",
    "lmcache:num_p2p_transferred_tokens",
    "lmcache:p2p_time_to_transfer",
    "lmcache:p2p_transfer_speed",
    "lmcache:chunk_stats_enabled",
    "lmcache:total_chunk_requests",
    "lmcache:total_chunks",
    "lmcache:unique_chunks",
    "lmcache:retrieve_hit_rate",
    "lmcache:lookup_hit_rate",
    "lmcache:lookup_0_hit_requests",
    "lmcache:local_cpu_evict_count",
    "lmcache:local_cpu_evict_keys_count",
    "lmcache:local_cpu_evict_failed_count",
    "lmcache:local_cache_usage",
    "lmcache:remote_cache_usage",
    "lmcache:local_storage_usage",
    "lmcache:local_cpu_hot_cache_count",
    "lmcache_mp_lookup_requested_tokens_total",
    "lmcache_mp_lookup_hit_tokens_total",
    "lmcache_mp_sm_read_requests_total",
    "lmcache_mp_sm_read_succeed_keys_total",
    "lmcache_mp_sm_read_failed_keys_total",
    "lmcache_mp_sm_write_requests_total",
    "lmcache_mp_sm_write_succeed_keys_total",
    "lmcache_mp_sm_write_failed_keys_total",
    "lmcache_mp_l1_read_keys_total",
    "lmcache_mp_l1_write_keys_total",
    "lmcache_mp_l1_evicted_keys_total",
    "lmcache_mp_l1_memory_usage_bytes",
    "lmcache_mp_l1_chunk_lifetime_seconds",
    "lmcache_mp_l1_chunk_idle_before_evict_seconds",
    "lmcache_mp_l1_chunk_reuse_gap_seconds",
    "lmcache_mp_l1_chunk_evict_reuse_gap_seconds",
    "lmcache_mp_l0_block_lifetime_seconds",
    "lmcache_mp_l0_block_idle_before_evict_seconds",
    "lmcache_mp_l0_block_reuse_gap_seconds",
    "lmcache_mp_real_reuse_gap_seconds",
    "lmcache_mp_real_reuse_gap_chunks",
    "lmcache_mp_l2_store_tasks_total",
    "lmcache_mp_l2_store_keys_total",
    "lmcache_mp_l2_store_completed_total",
    "lmcache_mp_l2_store_succeeded_keys_total",
    "lmcache_mp_l2_store_failed_keys_total",
    "lmcache_mp_l2_prefetch_lookups_total",
    "lmcache_mp_l2_prefetch_lookup_keys_total",
    "lmcache_mp_l2_prefetch_hit_keys_total",
    "lmcache_mp_l2_prefetch_load_tasks_total",
    "lmcache_mp_l2_prefetch_load_keys_total",
    "lmcache_mp_l2_prefetch_loaded_keys_total",
    "lmcache_mp_l2_prefetch_failed_keys_total",
    "lmcache_mp_l2_load_completed_total",
    "lmcache_mp_l2_store_throughput_gbs",
    "lmcache_mp_l2_load_throughput_gbs",
    "lmcache_mp_l0_l1_store_throughput_gbs",
    "lmcache_mp_l0_l1_load_throughput_gbs",
    "lmcache_mp_num_chunks_loaded_total",
    "lmcache_mp_active_prefetch_jobs",
    "lmcache_mp_num_inflight_l2_stores",
    "lmcache_mp_num_inflight_l2_loads",
    "lmcache_mp_inflight_load_memory_usage_bytes",
    "lmcache_mp_event_bus_queue_depth",
    "lmcache_mp_event_bus_drain_lag_seconds",
    "lmcache_mp_event_bus_dropped_events_total",
    "lmcache_mp_event_bus_subscriber_exceptions_total",
)

ENGINE_SOURCE_METRICS: dict[str, tuple[str, ...]] = {
    "prefill": (
        "vllm:request_prefill_time_seconds",
        "vllm:prompt_tokens_total",
        "sglang:prompt_tokens_total",
    ),
    "decode": (
        "vllm:request_decode_time_seconds",
        "vllm:generation_tokens_total",
        "vllm:request_success_total",
        "vllm:time_per_output_token_seconds",
        "vllm:inter_token_latency_seconds",
        "sglang:generation_tokens_total",
        "sglang:gen_throughput",
        "sglang:time_per_output_token_seconds",
    ),
    "queue": (
        "vllm:num_requests_running",
        "vllm:num_requests_waiting",
        "vllm:request_queue_time_seconds",
        "sglang:num_running_reqs",
        "sglang:num_queue_reqs",
        "sglang:num_preemptions_total",
    ),
    "kv_cache": (
        "vllm:kv_cache_usage_perc",
        "vllm:gpu_cache_usage_perc",
        "vllm:kv_block_lifetime_seconds",
        "vllm:kv_block_idle_before_evict_seconds",
        "vllm:kv_block_reuse_gap_seconds",
        "vllm:kv_offload_total_bytes",
        "vllm:kv_offload_total_time",
        "vllm:kv_offload_size",
        "vllm:simple_cpu_offload_total_blocks",
        "vllm:simple_cpu_offload_free_blocks",
        "vllm:simple_cpu_offload_used_blocks",
        "vllm:simple_cpu_offload_usage_perc",
        "vllm:simple_cpu_offload_pending_loads",
        "vllm:simple_cpu_offload_pending_stores",
        "sglang:token_usage",
        "sglang:num_used_tokens",
        "sglang:hicache_l1_hit_count_total",
        "sglang:hicache_l2_hit_count_total",
        "sglang:hicache_l3_hit_count_total",
        "sglang:hicache_lookup_count_total",
        "sglang:hicache_l2_bytes",
        "sglang:hicache_l3_bytes",
        "vllm:kv_transfer_sent_bytes_total",
        "vllm:kv_transfer_recv_bytes_total",
        "vllm:kv_transfer_errors_total",
        "sglang:kv_transfer_sent_bytes_total",
        "sglang:kv_transfer_recv_bytes_total",
        "sglang:kv_transfer_errors_total",
        "dynamo:kvbm_block_residency_seconds",
        "dynamo:kvbm_blocks",
        "dynamo:kvbm_evictions_total",
        "dynamo:kvbm_promotions_total",
    ),
    "prefix_cache": (
        "vllm:prefix_cache_queries",
        "vllm:prefix_cache_hits",
        "vllm:prefix_cache_queries_total",
        "vllm:prefix_cache_hits_total",
        "vllm:external_prefix_cache_queries",
        "vllm:external_prefix_cache_hits",
        "vllm:external_prefix_cache_queries_total",
        "vllm:external_prefix_cache_hits_total",
        "vllm:prompt_tokens_by_source",
        "vllm:prompt_tokens_by_source_total",
        "vllm:prompt_tokens_cached",
        "vllm:prompt_tokens_cached_total",
        "sglang:cache_hit_rate",
    ),
    "lmcache": LMCACHE_LOCKED_METRICS
    + (
        "lmcache:enabled",
        "lmcache:connector_info",
        "lmcache_config_info",
        "lmcache:num_retrieve_requests",
        "lmcache:num_store_requests",
        "lmcache:num_lookup_requests",
        "lmcache:num_requested_tokens",
        "lmcache:num_hit_tokens",
        "lmcache:num_lookup_tokens",
        "lmcache:num_lookup_hits",
        "lmcache:is_healthy",
        "lmcache:num_p2p_requests",
        "lmcache:num_p2p_transferred_tokens",
        "lmcache:p2p_time_to_transfer",
        "lmcache:p2p_transfer_speed",
        "lmcache:chunk_stats_enabled",
        "lmcache:total_chunk_requests",
        "lmcache:total_chunks",
        "lmcache:unique_chunks",
        "lmcache_hit_count",
        "lmcache_miss_count",
        "lmcache_hit_rate",
        "lmcache_evictions_total",
        "lmcache_tier_usage_bytes",
        "lmcache_retrieve_latency_ms",
    ),
}

DCGM_FIELD_SPECS: dict[str, dict[str, str]] = {
    "DCGM_FI_DEV_GPU_UTIL": {"group": "gpu_util", "field_id": "203", "alias": "dcgm_gpu_util"},
    "DCGM_FI_PROF_GR_ENGINE_ACTIVE": {
        "group": "gpu_util",
        "field_id": "1001",
        "alias": "dcgm_prof_gr_engine_active",
    },
    "DCGM_FI_PROF_SM_ACTIVE": {
        "group": "gpu_util",
        "field_id": "1002",
        "alias": "dcgm_prof_sm_active",
    },
    "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE": {
        "group": "gpu_util",
        "field_id": "1004",
        "alias": "dcgm_prof_pipe_tensor_active",
    },
    "DCGM_FI_PROF_DRAM_ACTIVE": {
        "group": "gpu_util",
        "field_id": "1005",
        "alias": "dcgm_prof_dram_active",
    },
    "DCGM_FI_DEV_FB_USED": {"group": "hbm", "field_id": "252", "alias": "dcgm_fb_used"},
    "DCGM_FI_DEV_FB_FREE": {"group": "hbm", "field_id": "251", "alias": "dcgm_fb_free"},
    "DCGM_FI_PROF_NVLINK_TX_BYTES": {
        "group": "nvlink",
        "field_id": "1011",
        "alias": "dcgm_prof_nvlink_tx_bytes",
    },
    "DCGM_FI_PROF_NVLINK_RX_BYTES": {
        "group": "nvlink",
        "field_id": "1012",
        "alias": "dcgm_prof_nvlink_rx_bytes",
    },
    "DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL": {
        "group": "nvlink",
        "field_id": "",
        "alias": "dcgm_nvlink_bandwidth_total",
    },
    "DCGM_FI_PROF_PCIE_TX_BYTES": {
        "group": "pcie",
        "field_id": "1009",
        "alias": "dcgm_prof_pcie_tx_bytes",
    },
    "DCGM_FI_PROF_PCIE_RX_BYTES": {
        "group": "pcie",
        "field_id": "1010",
        "alias": "dcgm_prof_pcie_rx_bytes",
    },
    "DCGM_FI_DEV_POWER_USAGE": {
        "group": "power",
        "field_id": "155",
        "alias": "dcgm_power_usage",
    },
    "DCGM_FI_DEV_XID_ERRORS": {
        "group": "xid_ecc",
        "field_id": "230",
        "alias": "dcgm_xid_errors",
    },
}


def normalize_engine_sample(
    engine: str,
    raw_text: str,
    *,
    snapshot: DisaggSnapshot | None = None,
) -> dict[str, Any]:
    """Normalize one engine Prometheus scrape into PRD §4.3 metric groups."""

    samples = parse_labeled_prometheus_text(raw_text)
    observed_metrics = _observed_metrics(samples)
    model_name = _model_name(samples, engine)
    mtp_detected = _mtp_detected(samples) or _text_mentions_mtp(raw_text)
    groups = {
        "prefill": _prefill_group(samples, observed_metrics),
        "decode": _decode_group(samples, observed_metrics),
        "queue": _queue_group(samples, observed_metrics, snapshot),
        "kv_cache": _kv_cache_group(samples, observed_metrics, snapshot),
        "prefix_cache": _prefix_cache_group(samples, observed_metrics, mtp_detected=mtp_detected),
        "lmcache": _lmcache_group(samples, observed_metrics),
    }
    for group_name, group in groups.items():
        group["source_metrics"] = _present_source_metrics(group_name, observed_metrics)
        if group.get("claim_status") is None:
            group["claim_status"] = _claim_status(group)
    return {
        "engine": engine,
        "model_name": model_name,
        "observed_metrics": observed_metrics,
        "groups": groups,
    }


def normalize_dcgm_sample(
    raw_text: str,
    *,
    observed_at: str,
    sequence: int,
    timestamp_window_seconds: int,
    labels: Mapping[str, str] | None = None,
    scrape_error: str = "",
) -> list[dict[str, Any]]:
    """Normalize one DCGM Prometheus scrape into ``dcgm-correlated/v1`` rows."""

    parsed_samples = parse_prometheus_text(raw_text)
    base_rows = parse_dcgm_samples(parsed_samples)
    original_rows = _dcgm_original_rows(parsed_samples)
    row_keys = set(original_rows)
    row_keys.update((row.get("gpu_uuid"), row.get("gpu_index")) for row in base_rows)
    if not row_keys:
        row_keys.add((None, None))

    by_key = {(row.get("gpu_uuid"), row.get("gpu_index")): row for row in base_rows}
    out: list[dict[str, Any]] = []
    for gpu_uuid, gpu_index in sorted(
        row_keys,
        key=lambda key: (key[1] is None, key[1] if key[1] is not None else 0, str(key[0])),
    ):
        base = dict(by_key.get((gpu_uuid, gpu_index), {}))
        metrics = dict(original_rows.get((gpu_uuid, gpu_index), {}))
        fields = {
            spec["alias"]: metrics.get(name)
            for name, spec in DCGM_FIELD_SPECS.items()
            if spec["alias"] not in base
        }
        fields.update(base)
        field_ids = {
            name: spec["field_id"]
            for name, spec in DCGM_FIELD_SPECS.items()
            if spec["field_id"] and name in metrics
        }
        out.append(
            {
                "sequence": sequence,
                "observed_at": observed_at,
                "timestamp_window_seconds": timestamp_window_seconds,
                "gpu_uuid": gpu_uuid,
                "gpu_index": gpu_index,
                "fields": fields,
                "metrics": metrics,
                "field_ids": field_ids,
                "labels": dict(labels or {}),
                "scrape_error": scrape_error,
            }
        )
    return out


def build_metrics_summary(
    *,
    engine: str,
    duration_seconds: float,
    engine_rows: Iterable[Mapping[str, Any]],
    gpu_rows: Iterable[Mapping[str, Any]],
    sample_count: int,
    dcgm_sample_count: int,
    generated_at: str,
    labels: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the ``inferguard-metrics-summary/v1`` group dictionary."""

    groups: dict[str, dict[str, Any]] = {group: {"claim_status": "not_proven"} for group in NORMALIZED_GROUPS}
    engine_by_group: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in engine_rows:
        engine_by_group[str(row.get("group"))].append(row)
    for group in ENGINE_GROUPS:
        groups[group] = _summarize_engine_group(group, engine_by_group.get(group, []))

    gpu_by_group: dict[str, dict[str, list[float]]] = {
        group: defaultdict(list) for group in GPU_GROUPS
    }
    for row in gpu_rows:
        metrics = row.get("metrics")
        if not isinstance(metrics, Mapping):
            continue
        for name, value in metrics.items():
            spec = DCGM_FIELD_SPECS.get(str(name))
            number = _number(value)
            if spec is None or number is None:
                continue
            gpu_by_group[spec["group"]][str(name)].append(number)
    for group in GPU_GROUPS:
        groups[group] = _summarize_gpu_group(group, gpu_by_group[group])

    return {
        "engine": engine,
        "duration_seconds": duration_seconds,
        "sample_count": sample_count,
        "dcgm_sample_count": dcgm_sample_count,
        "generated_at": generated_at,
        "labels": dict(labels or {}),
        "groups": groups,
    }


def _prefill_group(
    samples: list[LabeledSample],
    observed: Mapping[str, float],
) -> dict[str, Any]:
    prompt_tokens = _sum_metric(samples, "vllm:prompt_tokens_total", "sglang:prompt_tokens_total")
    return _group(
        request_prefill_time_seconds=_hist_value(samples, "vllm:request_prefill_time_seconds"),
        prompt_tokens_total=prompt_tokens,
        prompt_tokens_source=_source_for(observed, "vllm:prompt_tokens_total", "sglang:prompt_tokens_total"),
    )


def _decode_group(
    samples: list[LabeledSample],
    observed: Mapping[str, float],
) -> dict[str, Any]:
    tpot, source = _preferred_metric(
        samples,
        "vllm:time_per_output_token_seconds",
        "vllm:inter_token_latency_seconds",
        "sglang:time_per_output_token_seconds",
    )
    return _group(
        request_decode_time_seconds=_hist_value(samples, "vllm:request_decode_time_seconds"),
        generation_tokens_total=_sum_metric(
            samples, "vllm:generation_tokens_total", "sglang:generation_tokens_total"
        ),
        request_success_total=_sum_metric(samples, "vllm:request_success_total"),
        time_per_output_token_seconds=tpot,
        time_per_output_token_source=source,
        gen_throughput=_last_metric(samples, "sglang:gen_throughput"),
    )


def _queue_group(
    samples: list[LabeledSample],
    observed: Mapping[str, float],
    snapshot: DisaggSnapshot | None,
) -> dict[str, Any]:
    running = _sum_metric(samples, "vllm:num_requests_running", "sglang:num_running_reqs")
    waiting = _sum_metric(samples, "vllm:num_requests_waiting", "sglang:num_queue_reqs")
    if snapshot is not None and not snapshot.scrape_error:
        running = running if running is not None else _number(snapshot.requests_running)
        waiting = waiting if waiting is not None else _number(snapshot.requests_waiting)
    return _group(
        requests_running=running,
        requests_waiting=waiting,
        request_queue_time_seconds=_hist_value(samples, "vllm:request_queue_time_seconds"),
        running_source=_source_for(observed, "vllm:num_requests_running", "sglang:num_running_reqs"),
        waiting_source=_source_for(observed, "vllm:num_requests_waiting", "sglang:num_queue_reqs"),
        num_preemptions_total=_sum_metric(samples, "sglang:num_preemptions_total"),
    )


def _kv_cache_group(
    samples: list[LabeledSample],
    observed: Mapping[str, float],
    snapshot: DisaggSnapshot | None,
) -> dict[str, Any]:
    kv_v1 = _max_metric(samples, "vllm:kv_cache_usage_perc")
    kv_v0 = _max_metric(samples, "vllm:gpu_cache_usage_perc")
    usage_fraction = kv_v1 if kv_v1 is not None else kv_v0
    usage_source = "vllm:kv_cache_usage_perc" if kv_v1 is not None else None
    if usage_fraction is None and snapshot is not None and not snapshot.scrape_error:
        usage_fraction = _number(snapshot.kv_cache_usage)
        usage_source = "disagg:snapshot.kv_cache_usage" if usage_fraction is not None else None
    if usage_source is None and kv_v0 is not None:
        usage_source = "vllm:gpu_cache_usage_perc"

    token_usage = _max_metric(samples, "sglang:token_usage")
    return _group(
        usage_fraction=usage_fraction,
        usage_fraction_source=usage_source,
        token_usage=token_usage,
        num_used_tokens=_sum_metric(samples, "sglang:num_used_tokens"),
        hicache_l1_hit_count_total=_sum_metric(samples, "sglang:hicache_l1_hit_count_total"),
        hicache_l2_hit_count_total=_sum_metric(samples, "sglang:hicache_l2_hit_count_total"),
        hicache_l3_hit_count_total=_sum_metric(samples, "sglang:hicache_l3_hit_count_total"),
        hicache_lookup_count_total=_sum_metric(samples, "sglang:hicache_lookup_count_total"),
        hicache_l2_bytes=_max_metric(samples, "sglang:hicache_l2_bytes"),
        hicache_l3_bytes=_max_metric(samples, "sglang:hicache_l3_bytes"),
        kv_block_lifetime_seconds=_hist_value(samples, "vllm:kv_block_lifetime_seconds"),
        kv_block_idle_before_evict_seconds=_hist_value(
            samples, "vllm:kv_block_idle_before_evict_seconds"
        ),
        kv_block_reuse_gap_seconds=_hist_value(samples, "vllm:kv_block_reuse_gap_seconds"),
        kv_offload_bytes_gpu_to_cpu=_labeled_sum(
            samples, "vllm:kv_offload_total_bytes", {"transfer_type": "GPU_to_CPU"}
        ),
        kv_offload_bytes_cpu_to_gpu=_labeled_sum(
            samples, "vllm:kv_offload_total_bytes", {"transfer_type": "CPU_to_GPU"}
        ),
        kv_offload_time_gpu_to_cpu=_labeled_sum(
            samples, "vllm:kv_offload_total_time", {"transfer_type": "GPU_to_CPU"}
        ),
        kv_offload_time_cpu_to_gpu=_labeled_sum(
            samples, "vllm:kv_offload_total_time", {"transfer_type": "CPU_to_GPU"}
        ),
        simple_cpu_offload_total_blocks=_max_metric(
            samples, "vllm:simple_cpu_offload_total_blocks"
        ),
        simple_cpu_offload_free_blocks=_max_metric(
            samples, "vllm:simple_cpu_offload_free_blocks"
        ),
        simple_cpu_offload_used_blocks=_max_metric(
            samples, "vllm:simple_cpu_offload_used_blocks"
        ),
        simple_cpu_offload_usage_perc=_max_metric(samples, "vllm:simple_cpu_offload_usage_perc"),
        simple_cpu_offload_pending_loads=_max_metric(
            samples, "vllm:simple_cpu_offload_pending_loads"
        ),
        simple_cpu_offload_pending_stores=_max_metric(
            samples, "vllm:simple_cpu_offload_pending_stores"
        ),
        kv_transfer_sent_bytes_total=_sum_metric(
            samples, "vllm:kv_transfer_sent_bytes_total", "sglang:kv_transfer_sent_bytes_total"
        ),
        kv_transfer_recv_bytes_total=_sum_metric(
            samples, "vllm:kv_transfer_recv_bytes_total", "sglang:kv_transfer_recv_bytes_total"
        ),
        kv_transfer_errors_total=_sum_metric(
            samples, "vllm:kv_transfer_errors_total", "sglang:kv_transfer_errors_total"
        ),
        dynamo_kvbm_block_residency_seconds=_hist_value(
            samples, "dynamo:kvbm_block_residency_seconds"
        ),
        dynamo_kvbm_l1_count=_labeled_sum(samples, "dynamo:kvbm_blocks", {"tier": "l1_gpu"}),
        dynamo_kvbm_l2_count=_labeled_sum(samples, "dynamo:kvbm_blocks", {"tier": "l2_cpu"}),
        dynamo_kvbm_l3_count=_labeled_sum(
            samples, "dynamo:kvbm_blocks", {"tier": "l3_storage"}
        ),
        dynamo_l1_blocks=_labeled_sum(samples, "dynamo:kvbm_blocks", {"tier": "l1_gpu"}),
        dynamo_l2_blocks=_labeled_sum(samples, "dynamo:kvbm_blocks", {"tier": "l2_cpu"}),
        dynamo_l3_blocks=_labeled_sum(samples, "dynamo:kvbm_blocks", {"tier": "l3_storage"}),
        dynamo_evictions_total=_sum_metric(samples, "dynamo:kvbm_evictions_total"),
        dynamo_promotions_total=_sum_metric(samples, "dynamo:kvbm_promotions_total"),
    )


def _prefix_cache_group(
    samples: list[LabeledSample],
    observed: Mapping[str, float],
    *,
    mtp_detected: bool,
) -> dict[str, Any]:
    queries = _sum_metric(samples, "vllm:prefix_cache_queries", "vllm:prefix_cache_queries_total")
    hits = _sum_metric(samples, "vllm:prefix_cache_hits", "vllm:prefix_cache_hits_total")
    external_queries = _sum_metric(
        samples, "vllm:external_prefix_cache_queries", "vllm:external_prefix_cache_queries_total"
    )
    external_hits = _sum_metric(
        samples, "vllm:external_prefix_cache_hits", "vllm:external_prefix_cache_hits_total"
    )
    cached_total = _sum_metric(
        samples, "vllm:prompt_tokens_cached", "vllm:prompt_tokens_cached_total"
    )
    sglang_hit_rate = _max_metric(samples, "sglang:cache_hit_rate")
    hit_rate = sglang_hit_rate
    source = "sglang:cache_hit_rate" if sglang_hit_rate is not None else None
    if hit_rate is None and hits is not None and queries and queries > 0:
        hit_rate = hits / queries
        source = "vllm:prefix_cache_hits/vllm:prefix_cache_queries"
    claim_status = None
    field_claims: dict[str, str] = {}
    if mtp_detected and sglang_hit_rate == 0:
        claim_status = "inferred"
        field_claims["hit_rate"] = "inferred"
    prompt_tokens_local_compute = _first_non_none(
        _labeled_sum(samples, "vllm:prompt_tokens_by_source_total", {"source": "local_compute"}),
        _labeled_sum(samples, "vllm:prompt_tokens_by_source", {"source": "local_compute"}),
    )
    prompt_tokens_local_cache_hit = _first_non_none(
        _labeled_sum(samples, "vllm:prompt_tokens_by_source_total", {"source": "local_cache_hit"}),
        _labeled_sum(samples, "vllm:prompt_tokens_by_source", {"source": "local_cache_hit"}),
    )
    prompt_tokens_external_kv_transfer = _first_non_none(
        _labeled_sum(
            samples, "vllm:prompt_tokens_by_source_total", {"source": "external_kv_transfer"}
        ),
        _labeled_sum(samples, "vllm:prompt_tokens_by_source", {"source": "external_kv_transfer"}),
    )
    group = _group(
        queries=queries,
        hits=hits,
        external_queries=external_queries,
        external_hits=external_hits,
        external_hit_rate=(
            external_hits / external_queries
            if external_hits is not None and external_queries and external_queries > 0
            else None
        ),
        prompt_tokens_local_compute=prompt_tokens_local_compute,
        prompt_tokens_local_cache_hit=prompt_tokens_local_cache_hit,
        prompt_tokens_external_kv_transfer=prompt_tokens_external_kv_transfer,
        prompt_tokens_cached_total=cached_total,
        hit_rate=hit_rate,
        hit_rate_source=source,
        claim_status=claim_status,
        claim_status_per_field=field_claims,
    )
    return group


def _lmcache_group(
    samples: list[LabeledSample],
    observed: Mapping[str, float],
) -> dict[str, Any]:
    mp_present = any(sample.name.startswith("lmcache_mp_") for sample in samples)
    mp_requested = _sum_metric(samples, "lmcache_mp_lookup_requested_tokens_total")
    mp_hit = _sum_metric(samples, "lmcache_mp_lookup_hit_tokens_total")
    mp_hit_rate = mp_hit / mp_requested if mp_hit is not None and mp_requested and mp_requested > 0 else None
    hit_count = _sum_metric(
        samples,
        "lmcache:num_hit_tokens",
        "lmcache:num_lookup_hits",
        "lmcache_hit_count",
        "lmcache:hit_count",
        "lmcache_mp_lookup_hit_tokens_total",
    )
    miss_count = _sum_metric(samples, "lmcache_miss_count", "lmcache:miss_count")
    if miss_count is None and mp_hit is not None and mp_requested is not None:
        miss_count = max(mp_requested - mp_hit, 0.0)
    retrieve_hit_rate = _max_metric(
        samples, "lmcache:retrieve_hit_rate", "lmcache_retrieve_hit_rate", "lmcache:hit_rate", "lmcache_hit_rate"
    )
    if retrieve_hit_rate is None and mp_hit_rate is not None:
        retrieve_hit_rate = mp_hit_rate
    if retrieve_hit_rate is None and hit_count is not None and miss_count is not None:
        total = hit_count + miss_count
        retrieve_hit_rate = hit_count / total if total > 0 else None
    connector, backend = _lmcache_connector(samples)
    if mp_present:
        if connector in {None, "LMCacheConnectorV1"}:
            connector = "LMCacheMPConnector"
        backend = backend or "mp"
    return _group(
        mp_mode_enabled=mp_present or None,
        num_hit_tokens=_sum_metric(samples, "lmcache:num_hit_tokens", "lmcache_hit_count", "lmcache_mp_lookup_hit_tokens_total"),
        num_lookup_hits=_sum_metric(samples, "lmcache:num_lookup_hits", "lmcache_hit_count", "lmcache_mp_lookup_hit_tokens_total"),
        num_retrieve_requests=_sum_metric(samples, "lmcache:num_retrieve_requests", "lmcache_num_retrieve_requests"),
        num_store_requests=_sum_metric(samples, "lmcache:num_store_requests", "lmcache_num_store_requests"),
        num_lookup_requests=_sum_metric(samples, "lmcache:num_lookup_requests", "lmcache_num_lookup_requests"),
        num_requested_tokens=_sum_metric(samples, "lmcache:num_requested_tokens", "lmcache_num_requested_tokens"),
        num_lookup_tokens=_sum_metric(samples, "lmcache:num_lookup_tokens", "lmcache_num_lookup_tokens"),
        lookup_requested_tokens=mp_requested,
        lookup_hit_tokens=mp_hit,
        retrieve_hit_rate=retrieve_hit_rate,
        lookup_hit_rate=_max_metric(samples, "lmcache:lookup_hit_rate", "lmcache_lookup_hit_rate") or mp_hit_rate,
        lookup_0_hit_requests=_sum_metric(samples, "lmcache:lookup_0_hit_requests"),
        sm_read_requests=_sum_metric(samples, "lmcache_mp_sm_read_requests_total"),
        sm_read_succeed_keys=_sum_metric(samples, "lmcache_mp_sm_read_succeed_keys_total"),
        sm_read_failed_keys=_sum_metric(samples, "lmcache_mp_sm_read_failed_keys_total"),
        sm_write_requests=_sum_metric(samples, "lmcache_mp_sm_write_requests_total"),
        sm_write_succeed_keys=_sum_metric(samples, "lmcache_mp_sm_write_succeed_keys_total"),
        sm_write_failed_keys=_sum_metric(samples, "lmcache_mp_sm_write_failed_keys_total"),
        local_cpu_evict_count=_sum_metric(
            samples,
            "lmcache:local_cpu_evict_count",
            "lmcache_evictions_total",
            "lmcache:eviction_count",
            "lmcache_mp_l1_evicted_keys_total",
        ),
        local_cpu_evict_keys_count=_sum_metric(samples, "lmcache:local_cpu_evict_keys_count"),
        local_cpu_evict_failed_count=_sum_metric(samples, "lmcache:local_cpu_evict_failed_count"),
        local_cache_usage=_max_metric(samples, "lmcache:local_cache_usage")
        or _labeled_sum(samples, "lmcache_tier_usage_bytes", {"tier": "cpu"})
        or _labeled_sum(samples, "lmcache:tier_usage_bytes", {"tier": "cpu"})
        or _max_metric(samples, "lmcache_mp_l1_memory_usage_bytes"),
        remote_cache_usage=_max_metric(samples, "lmcache:remote_cache_usage")
        or _labeled_sum(samples, "lmcache_tier_usage_bytes", {"tier": "remote"})
        or _labeled_sum(samples, "lmcache:tier_usage_bytes", {"tier": "remote"}),
        local_storage_usage=_max_metric(samples, "lmcache:local_storage_usage")
        or _labeled_sum(samples, "lmcache_tier_usage_bytes", {"tier": "disk"})
        or _labeled_sum(samples, "lmcache:tier_usage_bytes", {"tier": "disk"})
        or _labeled_sum(samples, "lmcache:tier_usage_bytes", {"tier": "local_disk"}),
        local_cpu_hot_cache_count=_max_metric(samples, "lmcache:local_cpu_hot_cache_count"),
        l1_read_keys=_sum_metric(samples, "lmcache_mp_l1_read_keys_total"),
        l1_write_keys=_sum_metric(samples, "lmcache_mp_l1_write_keys_total"),
        l1_evicted_keys=_sum_metric(samples, "lmcache_mp_l1_evicted_keys_total"),
        l1_memory_usage_bytes=_max_metric(samples, "lmcache_mp_l1_memory_usage_bytes"),
        l1_chunk_lifetime_seconds=_hist_value(samples, "lmcache_mp_l1_chunk_lifetime_seconds"),
        l1_chunk_idle_before_evict_seconds=_hist_value(samples, "lmcache_mp_l1_chunk_idle_before_evict_seconds"),
        l1_chunk_reuse_gap_seconds=_hist_value(samples, "lmcache_mp_l1_chunk_reuse_gap_seconds"),
        l1_chunk_evict_reuse_gap_seconds=_hist_value(samples, "lmcache_mp_l1_chunk_evict_reuse_gap_seconds"),
        l0_block_lifetime_seconds=_hist_value(samples, "lmcache_mp_l0_block_lifetime_seconds"),
        l0_block_idle_before_evict_seconds=_hist_value(
            samples, "lmcache_mp_l0_block_idle_before_evict_seconds"
        ),
        l0_block_reuse_gap_seconds=_hist_value(samples, "lmcache_mp_l0_block_reuse_gap_seconds"),
        real_reuse_gap_seconds=_hist_value(samples, "lmcache_mp_real_reuse_gap_seconds"),
        real_reuse_gap_chunks=_hist_value(samples, "lmcache_mp_real_reuse_gap_chunks"),
        l2_store_tasks=_sum_metric(samples, "lmcache_mp_l2_store_tasks_total"),
        l2_store_keys=_sum_metric(samples, "lmcache_mp_l2_store_keys_total"),
        l2_store_completed=_sum_metric(samples, "lmcache_mp_l2_store_completed_total"),
        l2_store_succeeded_keys=_sum_metric(samples, "lmcache_mp_l2_store_succeeded_keys_total"),
        l2_store_failed_keys=_sum_metric(samples, "lmcache_mp_l2_store_failed_keys_total"),
        l2_prefetch_lookups=_sum_metric(samples, "lmcache_mp_l2_prefetch_lookups_total"),
        l2_prefetch_lookup_keys=_sum_metric(samples, "lmcache_mp_l2_prefetch_lookup_keys_total"),
        l2_prefetch_hit_keys=_sum_metric(samples, "lmcache_mp_l2_prefetch_hit_keys_total"),
        l2_prefetch_load_tasks=_sum_metric(samples, "lmcache_mp_l2_prefetch_load_tasks_total"),
        l2_prefetch_load_keys=_sum_metric(samples, "lmcache_mp_l2_prefetch_load_keys_total"),
        l2_prefetch_loaded_keys=_sum_metric(samples, "lmcache_mp_l2_prefetch_loaded_keys_total"),
        l2_prefetch_failed_keys=_sum_metric(samples, "lmcache_mp_l2_prefetch_failed_keys_total"),
        l2_load_completed=_sum_metric(samples, "lmcache_mp_l2_load_completed_total"),
        l2_store_throughput_gbs=_hist_value(samples, "lmcache_mp_l2_store_throughput_gbs"),
        l2_load_throughput_gbs=_hist_value(samples, "lmcache_mp_l2_load_throughput_gbs"),
        l0_l1_store_throughput_gbs=_hist_value(samples, "lmcache_mp_l0_l1_store_throughput_gbs"),
        l0_l1_load_throughput_gbs=_hist_value(samples, "lmcache_mp_l0_l1_load_throughput_gbs"),
        num_chunks_loaded=_sum_metric(samples, "lmcache_mp_num_chunks_loaded_total"),
        active_prefetch_jobs=_max_metric(samples, "lmcache_mp_active_prefetch_jobs"),
        num_inflight_l2_stores=_sum_metric(samples, "lmcache_mp_num_inflight_l2_stores"),
        num_inflight_l2_loads=_sum_metric(samples, "lmcache_mp_num_inflight_l2_loads"),
        inflight_load_memory_usage_bytes=_sum_metric(samples, "lmcache_mp_inflight_load_memory_usage_bytes"),
        event_bus_queue_depth=_max_metric(samples, "lmcache_mp_event_bus_queue_depth"),
        event_bus_drain_lag_seconds=_hist_value(samples, "lmcache_mp_event_bus_drain_lag_seconds")
        or _max_metric(samples, "lmcache_mp_event_bus_drain_lag_seconds"),
        event_bus_dropped_events_total=_sum_metric(samples, "lmcache_mp_event_bus_dropped_events_total"),
        event_bus_subscriber_exceptions_total=_sum_metric(samples, "lmcache_mp_event_bus_subscriber_exceptions_total"),
        is_healthy=_max_metric(samples, "lmcache:is_healthy", "lmcache_is_healthy"),
        storage_event_count=_sum_metric(samples, "lmcache:storage_event_count", "lmcache_storage_event_count"),
        remote_read_bytes=_sum_metric(samples, "lmcache:remote_read_bytes", "lmcache_remote_read_bytes"),
        remote_write_bytes=_sum_metric(samples, "lmcache:remote_write_bytes", "lmcache_remote_write_bytes"),
        remote_ping_latency_ms=_max_metric(samples, "lmcache:remote_ping_latency_ms", "lmcache_remote_ping_latency_ms"),
        remote_ping_errors=_sum_metric(samples, "lmcache:remote_ping_errors", "lmcache_remote_ping_errors"),
        p2p_requests=_sum_metric(samples, "lmcache:num_p2p_requests", "lmcache_num_p2p_requests"),
        p2p_transferred_tokens=_sum_metric(
            samples, "lmcache:num_p2p_transferred_tokens", "lmcache_num_p2p_transferred_tokens"
        ),
        p2p_time_to_transfer=_max_metric(
            samples, "lmcache:p2p_time_to_transfer", "lmcache_p2p_time_to_transfer"
        ),
        p2p_transfer_speed=_max_metric(samples, "lmcache:p2p_transfer_speed", "lmcache_p2p_transfer_speed"),
        chunk_stats_enabled=_max_metric(samples, "lmcache:chunk_stats_enabled", "lmcache_chunk_stats_enabled"),
        total_chunk_requests=_sum_metric(samples, "lmcache:total_chunk_requests", "lmcache_total_chunk_requests"),
        total_chunks=_max_metric(samples, "lmcache:total_chunks", "lmcache_total_chunks"),
        unique_chunks=_max_metric(samples, "lmcache:unique_chunks", "lmcache_unique_chunks"),
        connector=connector,
        backend=backend,
    )


def _group(
    *,
    claim_status: str | None = None,
    claim_status_per_field: Mapping[str, str] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    clean = {key: value for key, value in fields.items() if value is not None}
    clean["claim_status"] = claim_status
    clean["claim_status_per_field"] = dict(claim_status_per_field or {})
    return clean


def _claim_status(group: Mapping[str, Any]) -> str:
    if group.get("claim_status") in {"measured", "inferred", "synthetic", "not_proven"}:
        return str(group["claim_status"])
    field_names = {
        key
        for key, value in group.items()
        if key not in {"claim_status", "claim_status_per_field", "source_metrics"}
        and value is not None
        and value != {}
        and value != ""
    }
    return "measured" if field_names else "not_proven"


def _present_source_metrics(group: str, observed: Mapping[str, float]) -> list[str]:
    prefixes = ENGINE_SOURCE_METRICS[group]
    present: set[str] = set()
    for name in observed:
        if any(name == prefix or name.startswith(f"{prefix}_") for prefix in prefixes):
            present.add(name)
    return sorted(present)


def _observed_metrics(samples: list[LabeledSample]) -> dict[str, float]:
    values: dict[str, float] = {}
    for sample in samples:
        if not math.isfinite(sample.value):
            continue
        current = values.get(sample.name)
        values[sample.name] = sample.value if current is None else current + sample.value
    for base in VLLM_LOCKED_METRICS + SGLANG_LOCKED_METRICS + LMCACHE_LOCKED_METRICS:
        if base in values:
            continue
        hist = _hist_value(samples, base)
        if hist is not None:
            values[base] = hist
    return dict(sorted(values.items()))


def _model_name(samples: Iterable[LabeledSample], engine: str) -> str:
    for sample in samples:
        for key in ("model_name", "served_model_name", "model"):
            value = sample.labels.get(key)
            if value:
                return value
    return f"{engine}-default"


def _last_metric(samples: Iterable[LabeledSample], *names: str) -> float | None:
    value = None
    for sample in samples:
        if sample.name in names and math.isfinite(sample.value):
            value = sample.value
    return value


def _max_metric(samples: Iterable[LabeledSample], *names: str) -> float | None:
    values = [sample.value for sample in samples if sample.name in names and math.isfinite(sample.value)]
    return max(values) if values else None


def _sum_metric(samples: Iterable[LabeledSample], *names: str) -> float | None:
    values = [sample.value for sample in samples if sample.name in names and math.isfinite(sample.value)]
    return sum(values) if values else None


def _labeled_sum(samples: Iterable[LabeledSample], name: str, labels: Mapping[str, str]) -> float | None:
    values = [
        sample.value
        for sample in samples
        if sample.name == name
        and all(sample.labels.get(key) == value for key, value in labels.items())
        and math.isfinite(sample.value)
    ]
    return sum(values) if values else None


def _hist_value(samples: Iterable[LabeledSample], base_name: str) -> float | None:
    quantile_value = _quantile_value(samples, base_name)
    if quantile_value is not None:
        return quantile_value
    total = _last_metric(samples, f"{base_name}_sum")
    count = _last_metric(samples, f"{base_name}_count")
    if total is None or count is None or count <= 0:
        return None
    return total / count


def _quantile_value(samples: Iterable[LabeledSample], base_name: str) -> float | None:
    preferred = ("0.95", "0.99", "0.5", "0.50", "p95", "p99", "p50")
    matches = [sample for sample in samples if sample.name == base_name and "quantile" in sample.labels]
    for quantile in preferred:
        for sample in matches:
            if sample.labels.get("quantile") == quantile and math.isfinite(sample.value):
                return sample.value
    return None


def _preferred_metric(samples: list[LabeledSample], *names: str) -> tuple[float | None, str | None]:
    for name in names:
        value = _hist_value(samples, name)
        if value is not None:
            return value, name
        value = _max_metric(samples, name)
        if value is not None:
            return value, name
    return None, None


def _source_for(observed: Mapping[str, float], *names: str) -> str | None:
    for name in names:
        if name in observed:
            return name
    return None


def _first_non_none(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _mtp_detected(samples: Iterable[LabeledSample]) -> bool:
    for sample in samples:
        blob = " ".join([sample.name, *sample.labels.keys(), *sample.labels.values()]).lower()
        if "mtp" in blob or "speculative" in blob:
            return True
    return False


def _text_mentions_mtp(raw_text: str) -> bool:
    lowered = raw_text.lower()
    return "mtp" in lowered or "speculative" in lowered


def _lmcache_connector(samples: Iterable[LabeledSample]) -> tuple[str | None, str | None]:
    saw_lmcache = False
    backend = None
    config_samples: list[LabeledSample] = []
    for sample in samples:
        is_lmcache_metric = sample.name.startswith(("lmcache", "lm_cache"))
        is_cache_config = sample.name in {"vllm:cache_config_info", "lmcache_config_info"}
        if not (is_lmcache_metric or is_cache_config):
            continue
        config_samples.append(sample)
        saw_lmcache = saw_lmcache or is_lmcache_metric or _labels_mention_lmcache(sample)
    for sample in config_samples:
        for key in ("kv_connector", "connector_class", "connector_type"):
            value = sample.labels.get(key)
            if value == "LMCacheConnectorV1":
                return value, backend
        value = sample.labels.get("connector")
        if value and value.startswith("LMCache"):
            return value, backend
    for sample in config_samples:
        for key in ("kv_connector", "connector_class", "connector_type"):
            value = sample.labels.get(key)
            if value:
                return value, backend
        value = sample.labels.get("connector")
        if value and value.startswith("LMCache"):
            return value, backend
        if value:
            backend = value
    if saw_lmcache:
        return "LMCacheConnectorV1", backend
    return None, backend


def _labels_mention_lmcache(sample: LabeledSample) -> bool:
    return any(str(value).startswith("LMCache") for value in sample.labels.values())


def _dcgm_original_rows(samples: Iterable[Any]) -> dict[tuple[str | None, int | None], dict[str, float]]:
    rows: dict[tuple[str | None, int | None], dict[str, float]] = defaultdict(dict)
    for sample in samples:
        if sample.name not in DCGM_FIELD_SPECS:
            continue
        gpu_uuid = _gpu_uuid(sample.labels)
        gpu_index = _gpu_index(sample.labels.get("gpu"))
        key = (gpu_uuid or (f"gpu-index-{gpu_index}" if gpu_index is not None else None), gpu_index)
        current = rows[key].get(sample.name)
        if sample.name == "DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL":
            rows[key][sample.name] = sample.value if current is None else current + sample.value
        else:
            rows[key][sample.name] = sample.value
    return dict(rows)


def _gpu_uuid(labels: Mapping[str, str]) -> str | None:
    for key in ("UUID", "uuid", "gpu_uuid", "GPU_UUID"):
        value = labels.get(key)
        if value:
            return value
    return None


def _gpu_index(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _summarize_engine_group(group: str, rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    field_values: dict[str, list[float]] = defaultdict(list)
    last_values: dict[str, Any] = {}
    source_metrics: set[str] = set()
    statuses: list[str] = []
    field_status: dict[str, str] = {}
    for row in rows:
        statuses.append(str(row.get("claim_status") or "not_proven"))
        source_metrics.update(str(name) for name in row.get("source_metrics") or [])
        normalized = row.get("normalized")
        if not isinstance(normalized, Mapping):
            continue
        field_status.update(
            {
                str(key): str(value)
                for key, value in (row.get("claim_status_per_field") or {}).items()
            }
        )
        for key, value in normalized.items():
            number = _number(value)
            if number is not None:
                field_values[str(key)].append(number)
            if value is not None and value != "":
                last_values[str(key)] = value
    status = _aggregate_claim_status(statuses, bool(last_values or source_metrics))
    summary: dict[str, Any] = {"claim_status": status, "source_metrics": sorted(source_metrics)}
    if field_status:
        summary["claim_status_per_field"] = dict(sorted(field_status.items()))
    for key, value in sorted(last_values.items()):
        if key == "usage_fraction" and field_values.get(key):
            summary[key] = max(field_values[key])
        else:
            summary[key] = value
    stats = {key: _stats(values) for key, values in sorted(field_values.items()) if values}
    if stats:
        summary["stats"] = stats
    if group == "kv_cache":
        source = _preferred_usage_source(rows)
        if source is not None:
            summary["usage_fraction_source"] = source
    return summary


def _preferred_usage_source(rows: Iterable[Mapping[str, Any]]) -> str | None:
    fallback = None
    for row in rows:
        normalized = row.get("normalized")
        if not isinstance(normalized, Mapping):
            continue
        source = normalized.get("usage_fraction_source")
        if source == "vllm:kv_cache_usage_perc":
            return "vllm:kv_cache_usage_perc"
        if source and fallback is None:
            fallback = str(source)
    return fallback


def _summarize_gpu_group(group: str, metrics: Mapping[str, list[float]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"claim_status": "not_proven"}
    if not any(values for values in metrics.values()):
        return summary
    summary["claim_status"] = "measured"
    for name, values in sorted(metrics.items()):
        stat = _stats(values)
        if group == "hbm":
            stat["max_mib"] = stat["max"]
        summary[name] = stat
    return summary


def _aggregate_claim_status(statuses: list[str], has_evidence: bool) -> str:
    if not has_evidence:
        return "not_proven"
    if "inferred" in statuses:
        return "inferred"
    if "synthetic" in statuses:
        return "synthetic"
    return "measured"


def _stats(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(value for value in values if math.isfinite(value))
    if not ordered:
        return {"count": 0, "p50": None, "p95": None, "max": None}  # type: ignore[dict-item]
    return {
        "count": len(ordered),
        "p50": _percentile(ordered, 0.50),
        "p95": _percentile(ordered, 0.95),
        "max": max(ordered),
    }


def _percentile(ordered: list[float], quantile: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = quantile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


__all__ = [
    "DCGM_FIELD_SPECS",
    "ENGINE_SOURCE_METRICS",
    "LMCACHE_LOCKED_METRICS",
    "SGLANG_LOCKED_METRICS",
    "VLLM_LOCKED_METRICS",
    "build_metrics_summary",
    "normalize_dcgm_sample",
    "normalize_engine_sample",
]
