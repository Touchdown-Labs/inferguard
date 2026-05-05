"""AgentX cache/offload field-name alignment tests."""

from pathlib import Path

from inferguard.disagg.adapters import _parse_vllm

AGENTX_FIELDS = (
    "prefix_cache_hits",
    "prefix_cache_queries",
    "cpu_prefix_cache_hits",
    "cpu_prefix_cache_queries",
    "kv_offload_bytes_gpu_to_cpu",
    "kv_offload_bytes_cpu_to_gpu",
    "kv_offload_time_gpu_to_cpu",
    "kv_offload_time_cpu_to_gpu",
    "cpu_kv_cache_usage_pct",
)


def test_vllm_adapter_emits_agentx_cache_and_offload_field_names() -> None:
    text = (Path(__file__).parent / "fixtures" / "vllm.txt").read_text()
    payload = _parse_vllm(text, url="http://p", role="prefill").as_dict()
    for field in AGENTX_FIELDS:
        assert field in payload
