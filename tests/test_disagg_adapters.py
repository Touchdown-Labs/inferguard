"""Tests for the per-engine adapters and engine auto-detection."""

from pathlib import Path

from inferguard.disagg.adapters import (
    LLMD_FIELD_MAP,
    _parse_dynamo,
    _parse_lmcache,
    _parse_sglang,
    _parse_vllm,
    _parse_with_map,
)
from inferguard.disagg.engines import detect_engine


def _fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text()


def test_detect_engine_vllm() -> None:
    assert detect_engine(_fixture("vllm.txt")) == "vllm"


def test_detect_engine_sglang() -> None:
    assert detect_engine(_fixture("sglang.txt")) == "sglang"


def test_detect_engine_lmcache() -> None:
    assert detect_engine(_fixture("lmcache.txt")) == "lmcache"


def test_detect_engine_unknown_for_empty() -> None:
    assert detect_engine("# no samples here\n") == "unknown"


def test_detect_engine_dynamo_prefixes() -> None:
    assert detect_engine("dynamo_foo 1\n") == "dynamo"
    assert detect_engine("nv_llm_bar 1\n") == "dynamo"
    assert detect_engine("dynamo:kvbm_blocks 1\n") == "dynamo"


def test_detect_engine_llmd_prefixes() -> None:
    assert detect_engine("llmd_foo 1\n") == "llm-d"
    assert detect_engine("llm_d_bar 1\n") == "llm-d"


def test_parse_llmd_is_explicitly_adapter_pending() -> None:
    snap = _parse_with_map(
        "llmd_prefill_queue_depth 1\n",
        url="http://dlm",
        role="prefill",
        engine="llm-d",
        field_map=LLMD_FIELD_MAP,
    )

    assert LLMD_FIELD_MAP == {}
    assert snap.endpoint.engine == "llm-d"
    assert snap.scrape_error == "adapter_not_implemented"


def test_parse_vllm_fixture() -> None:
    snap = _parse_vllm(_fixture("vllm.txt"), url="http://p", role="prefill")
    assert snap.endpoint.engine == "vllm"
    assert snap.endpoint.role == "prefill"
    assert snap.endpoint.connector == "nixl"
    assert snap.kv_cache_usage == 0.82
    assert snap.requests_running == 24
    assert snap.requests_waiting == 8
    assert snap.preemptions_total == 3
    assert snap.kv_transfer_sent_bytes_total == 104857600
    assert snap.kv_transfer_errors_total == 0
    assert snap.prefix_cache_hits == 42
    assert snap.prefix_cache_queries == 56
    assert snap.cpu_prefix_cache_hits == 7
    assert snap.cpu_prefix_cache_queries == 14
    assert snap.kv_offload_bytes_gpu_to_cpu == 1024.0
    assert snap.kv_offload_bytes_cpu_to_gpu == 512.0
    assert snap.kv_offload_time_gpu_to_cpu == 0.25
    assert snap.kv_offload_time_cpu_to_gpu == 0.125
    assert snap.cpu_kv_cache_usage_pct == 0.35
    assert snap.ttft_avg_seconds is not None
    assert snap.tpot_avg_seconds is not None
    assert snap.scrape_error == ""


def test_parse_sglang_fixture() -> None:
    snap = _parse_sglang(_fixture("sglang.txt"), url="http://d", role="decode")
    assert snap.endpoint.engine == "sglang"
    assert snap.endpoint.role == "decode"
    assert snap.endpoint.connector == "mooncake"
    assert snap.kv_cache_usage == 0.55
    assert snap.requests_running == 12
    assert snap.kv_transfer_errors_total == 0


def test_parse_sglang_mooncake_is_connector_label_not_runtime_proof() -> None:
    snap = _parse_sglang(
        'sglang:token_usage 0.10\n'
        'sglang:num_running_reqs 1\n'
        'sglang:kv_transfer_sent_bytes_total{connector="mooncake"} 1024\n'
        'sglang:kv_transfer_recv_bytes_total{connector="mooncake"} 2048\n'
        'sglang:kv_transfer_errors_total{connector="mooncake"} 0\n',
        url="http://sglang",
        role="decode",
    )

    assert snap.endpoint.engine == "sglang"
    assert snap.endpoint.connector == "mooncake"
    assert snap.kv_transfer_sent_bytes_total == 1024
    assert snap.kv_transfer_recv_bytes_total == 2048
    assert snap.scrape_error == ""


def test_parse_vllm_no_metrics_returns_error() -> None:
    snap = _parse_vllm("# nothing\n", url="http://x", role="prefill")
    assert snap.scrape_error == "no_metrics_recognized"
    assert snap.kv_cache_usage is None


def test_parse_sglang_no_metrics_returns_error() -> None:
    snap = _parse_sglang("# nothing\n", url="http://x", role="decode")
    assert snap.scrape_error == "no_metrics_recognized"


def test_parse_vllm_offload_fields() -> None:
    text = _fixture("vllm.txt") + """
vllm:kv_offload_dma_bytes_per_second 83400000000
vllm:kv_offload_async_queue_depth 5
vllm:kv_offload_eviction_count_total 11
"""
    snap = _parse_vllm(text, url="http://p", role="prefill")
    assert snap.vllm_offload_dma_bytes_per_sec == 83400000000.0
    assert snap.vllm_offload_async_queue_depth == 5
    assert snap.vllm_offload_eviction_count == 11


def test_parse_vllm_simple_cpu_offload_fixture() -> None:
    snap = _parse_vllm(_fixture("vllm_simple_cpu_offload.prom"), url="http://p", role="prefill")

    assert snap.endpoint.engine == "vllm"
    assert snap.kv_offload_bytes_gpu_to_cpu == 13870000000.0
    assert snap.kv_offload_bytes_cpu_to_gpu == 4770000000.0
    assert snap.kv_offload_time_gpu_to_cpu == 0.42
    assert snap.kv_offload_time_cpu_to_gpu == 0.19
    assert snap.simple_cpu_offload_total_blocks == 1024
    assert snap.simple_cpu_offload_used_blocks == 768
    assert snap.simple_cpu_offload_usage_perc == 0.75
    assert snap.simple_cpu_offload_pending_loads == 2
    assert snap.simple_cpu_offload_pending_stores == 3


def test_parse_lmcache_fixture() -> None:
    snap = _parse_lmcache(_fixture("lmcache.txt"), url="http://p", role="prefill")
    assert snap.endpoint.engine == "lmcache"
    assert snap.lmcache_hit_rate == 0.73
    assert snap.lmcache_eviction_count == 4
    assert snap.lmcache_tier_cpu_bytes == 2147483648
    assert snap.lmcache_tier_local_disk_bytes == 1073741824
    assert snap.lmcache_tier_remote_bytes == 536870912
    assert snap.lmcache_remote_bytes_sent == 33554432
    assert snap.lmcache_remote_bytes_received == 67108864
    assert snap.lmcache_queue_depth == 2
    assert snap.scrape_error == ""


def test_parse_dynamo_kvbm_fixture() -> None:
    snap = _parse_dynamo(_fixture("dynamo_kvbm.txt"), url="http://t", role="transfer")
    assert snap.endpoint.engine == "dynamo"
    assert snap.dynamo_block_residency_seconds == 6.0
    assert snap.dynamo_block_l1_count == 128
    assert snap.dynamo_block_l2_count == 64
    assert snap.dynamo_block_l3_count == 16
    assert snap.dynamo_kvbm_evictions == 3
    assert snap.dynamo_kvbm_promotions == 9
    assert snap.scrape_error == ""


def test_parse_sglang_hicache_fixture() -> None:
    snap = _parse_sglang(_fixture("sglang_hicache.txt"), url="http://d", role="decode")
    assert snap.endpoint.engine == "sglang"
    assert snap.endpoint.connector == "mooncake"
    assert snap.sglang_hicache_l1_hit_count == 900
    assert snap.sglang_hicache_l2_hit_count == 120
    assert snap.sglang_hicache_l3_hit_count == 30
    assert snap.sglang_hicache_lookup_count == 1100
    assert snap.sglang_hicache_l2_bytes == 4294967296
    assert snap.sglang_hicache_l3_bytes == 8589934592
