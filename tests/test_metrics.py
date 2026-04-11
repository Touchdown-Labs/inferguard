"""Tests for metric parsing and anomaly detection."""

from inferguard.metrics import (
    MetricSnapshot,
    detect_anomalies,
    detect_rlm_anomalies,
    get_effective_kv_threshold,
)


SAMPLE_VLLM_METRICS = """\
vllm:gpu_cache_usage_perc 0.87
vllm:cpu_cache_usage_perc 0.11
vllm:gpu_prefix_cache_hit_rate 0.45
vllm:num_requests_running 5
vllm:num_requests_waiting 2
vllm:num_requests_swapped 0
vllm:num_preemptions_total 10
vllm:time_to_first_token_seconds_sum 1.5
vllm:time_to_first_token_seconds_count 10
vllm:time_per_output_token_seconds_sum 2.0
vllm:time_per_output_token_seconds_count 20
"""


SAMPLE_SGLANG_METRICS = """\
# HELP sglang metrics
sglang:token_usage{model_name="Qwen/Qwen3.5"} 0.52
sglang:cache_hit_rate{model_name="Qwen/Qwen3.5"} 0.28
sglang:num_running_reqs{model_name="Qwen/Qwen3.5"} 8
sglang:num_queue_reqs{model_name="Qwen/Qwen3.5"} 4
sglang:time_to_first_token_seconds_sum{model_name="Qwen/Qwen3.5"} 4.0
sglang:time_to_first_token_seconds_count{model_name="Qwen/Qwen3.5"} 8
sglang:time_per_output_token_seconds_sum{model_name="Qwen/Qwen3.5"} 12.0
sglang:time_per_output_token_seconds_count{model_name="Qwen/Qwen3.5"} 24
"""


def test_from_prometheus_text_vllm() -> None:
    snapshot = MetricSnapshot.from_prometheus_text(SAMPLE_VLLM_METRICS)
    assert snapshot.engine == "vllm"
    assert snapshot.kv_cache_usage == 0.87
    assert snapshot.cpu_cache_usage == 0.11
    assert snapshot.prefix_cache_hit_rate == 0.45
    assert snapshot.requests_running == 5
    assert snapshot.ttft_avg_seconds == 0.15
    assert snapshot.tpot_avg_seconds == 0.1


def test_from_prometheus_text_sglang() -> None:
    snapshot = MetricSnapshot.from_prometheus_text(SAMPLE_SGLANG_METRICS)
    assert snapshot.engine == "sglang"
    assert snapshot.kv_cache_usage == 0.52
    assert snapshot.prefix_cache_hit_rate == 0.28
    assert snapshot.requests_running == 8
    assert snapshot.requests_waiting == 4
    assert snapshot.ttft_avg_seconds == 0.5


def test_detect_preemption_delta() -> None:
    snapshot = MetricSnapshot(timestamp=0, engine="vllm", kv_cache_usage=0.7, preemptions_total=15)
    result = detect_anomalies(snapshot, baseline_ttft=None, previous_preemptions=10)
    assert result.is_anomaly
    assert any("5 new" in reason for reason in result.reasons)


def test_no_preemption_delta() -> None:
    snapshot = MetricSnapshot(timestamp=0, engine="vllm", kv_cache_usage=0.7, preemptions_total=15)
    result = detect_anomalies(snapshot, baseline_ttft=None, previous_preemptions=15)
    assert not result.is_anomaly


def test_effective_kv_threshold_deepseek() -> None:
    assert get_effective_kv_threshold("deepseek-ai/DeepSeek-R1-0528", 0.85) == 0.425


def test_effective_kv_threshold_qwen() -> None:
    assert get_effective_kv_threshold("Qwen/Qwen3.5-72B", 0.85) == 0.595


def test_effective_kv_threshold_unknown() -> None:
    assert get_effective_kv_threshold("openai/gpt-oss-120b", 0.85) == 0.85


def test_detect_rlm_anomalies_kv_surge() -> None:
    previous = MetricSnapshot(
        timestamp=1,
        engine="vllm",
        kv_cache_usage=0.50,
        prefix_cache_hit_rate=0.8,
        requests_running=8,
        preemptions_total=0,
    )
    current = MetricSnapshot(
        timestamp=2,
        engine="vllm",
        kv_cache_usage=0.70,
        prefix_cache_hit_rate=0.2,
        requests_running=8,
        preemptions_total=5,
    )

    reasons = detect_rlm_anomalies(current, previous, "Qwen/Qwen3.5-72B")
    assert any("KV surge" in reason for reason in reasons)
    assert any("prefix cache thrashing" in reason for reason in reasons)
    assert any("preemption storm" in reason for reason in reasons)

