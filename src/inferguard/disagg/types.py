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
    kv_offload_bytes_gpu_to_cpu: float | None = None
    kv_offload_bytes_cpu_to_gpu: float | None = None
    kv_offload_time_gpu_to_cpu: float | None = None
    kv_offload_time_cpu_to_gpu: float | None = None
    cpu_kv_cache_usage_pct: float | None = None
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
            "kv_offload_bytes_gpu_to_cpu": self.kv_offload_bytes_gpu_to_cpu,
            "kv_offload_bytes_cpu_to_gpu": self.kv_offload_bytes_cpu_to_gpu,
            "kv_offload_time_gpu_to_cpu": self.kv_offload_time_gpu_to_cpu,
            "kv_offload_time_cpu_to_gpu": self.kv_offload_time_cpu_to_gpu,
            "cpu_kv_cache_usage_pct": self.cpu_kv_cache_usage_pct,
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
