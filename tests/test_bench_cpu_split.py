from inferguard.bench.runner import _gpu_idle_ratio_block
from inferguard.bench.types import RequestMetric


def _metric(latency: float, tool_ms: float, queue_ms: float = 0.0) -> RequestMetric:
    return RequestMetric(
        request_id="r",
        trace_id="t",
        session_id="s",
        turn_index=0,
        workload_class="tool-heavy",
        concurrency=1,
        success=True,
        start_time=0.0,
        end_time=latency,
        latency_seconds=latency,
        ttft_seconds=0.01,
        input_tokens=1,
        output_tokens=1,
        input_tokens_source="estimated",
        output_tokens_source="estimated",
        tokens_per_second=1.0,
        client_queue_time_ms=queue_ms,
        engine_processing_time_ms=max(0.0, latency * 1000.0 - tool_ms - queue_ms),
        tool_simulation_time_ms=tool_ms,
        network_overhead_ms=0.0,
    )


def test_gpu_idle_ratio_high_tool_sim() -> None:
    block = _gpu_idle_ratio_block([_metric(1.0, 800.0), _metric(1.0, 900.0)], 2.0)
    assert block["p50"] >= 0.8
    assert block["p99"] <= 1.0
    assert block["overall"] == 0.85


def test_gpu_idle_ratio_low_tool_sim() -> None:
    block = _gpu_idle_ratio_block([_metric(1.0, 0.0), _metric(1.0, 100.0)], 2.0)
    assert block["p50"] == 0.0
    assert block["p99"] == 0.1
    assert block["overall"] == 0.05
