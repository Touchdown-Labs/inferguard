"""No-GPU parser tests for the InferGuard Profiler Bridge."""

from __future__ import annotations

from pathlib import Path

from inferguard.profilers.amd_rocm import (
    parse_rocprof_compute_pmc_perf_csv,
    parse_rocprof_compute_roofline_csv,
    parse_rocprofv3_kernel_trace_csv,
)
from inferguard.profilers.normalize import normalize_profiler_run
from inferguard.profilers.nvidia_nsight import parse_ncu_csv, parse_nsys_kernel_summary_csv
from inferguard.profilers.vllm_metrics import parse_vllm_prometheus

FIXTURES = Path(__file__).parent / "fixtures" / "profilers"


def test_vllm_prometheus_parser_extracts_request_lanes() -> None:
    metrics = parse_vllm_prometheus((FIXTURES / "vllm" / "prometheus_example.prom").read_text())
    assert metrics.ttft_seconds == 1.25
    assert metrics.itl_seconds == 0.045
    assert metrics.queue_depth == 2
    assert "vllm:generation_tokens_total" in metrics.raw_metrics


def test_nvidia_nsight_parsers_normalize_kernel_and_counter_artifacts() -> None:
    kernels = parse_nsys_kernel_summary_csv(FIXTURES / "nvidia" / "nsys_stats_kernel_sum.csv")
    counters = parse_ncu_csv(FIXTURES / "nvidia" / "ncu_kernel_summary.csv")
    assert kernels[0].vendor == "nvidia"
    assert kernels[0].duration_ms == 12
    assert {sample.name for sample in counters} >= {"occupancy_proxy", "memory_bandwidth_proxy", "tensor_utilization_proxy"}


def test_amd_rocm_parsers_normalize_kernel_counter_and_roofline_artifacts() -> None:
    kernels = parse_rocprofv3_kernel_trace_csv(FIXTURES / "amd" / "rocprofv3_kernel_trace.csv")
    counters = parse_rocprof_compute_pmc_perf_csv(FIXTURES / "amd" / "rocprof_compute_pmc_perf.csv")
    roofline = parse_rocprof_compute_roofline_csv(FIXTURES / "amd" / "rocprof_compute_roofline.csv")
    assert kernels[0].vendor == "amd"
    assert kernels[0].duration_ms == 15
    assert {sample.name for sample in counters} >= {"occupancy_proxy", "memory_bandwidth_proxy", "mfma_valu_utilization_proxy"}
    assert roofline[0].bound == "memory"


def test_normalized_run_keeps_fixture_backed_profile_partial_until_live_artifacts() -> None:
    metrics = parse_vllm_prometheus((FIXTURES / "vllm" / "prometheus_example.prom").read_text())
    kernels = parse_rocprofv3_kernel_trace_csv(FIXTURES / "amd" / "rocprofv3_kernel_trace.csv")
    run = normalize_profiler_run(
        run_id="fixture-amd-mi355x",
        vendor="amd",
        gpu_model="MI355X",
        workload_name="latency-baseline",
        capture_mode="timeline",
        request_metrics=metrics,
        kernel_events=kernels,
        artifacts={"vllm_metrics": "prometheus_example.prom", "rocprofv3": "rocprofv3_kernel_trace.csv"},
    )
    data = run.as_dict()
    assert data["schema_version"] == "inferguard-profiler-bridge/v1"
    assert data["device"]["architecture"] == "CDNA4"
    assert data["confidence"] == "partial"
    assert data["kernel_events"]
