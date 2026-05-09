"""Capture-plan and report tests for the no-bare-metal profiler bridge."""

from __future__ import annotations

from inferguard.profilers.capture_plan import ProfilerCaptureRequest, build_capture_plan
from inferguard.profilers.normalize import normalize_profiler_run
from inferguard.profilers.report import render_markdown_report


def test_nvidia_kernel_capture_plan_includes_vllm_nsys_and_ncu_steps() -> None:
    plan = build_capture_plan(
        ProfilerCaptureRequest(
            vendor="nvidia",
            gpu_model="GB300",
            model="meta-llama/Llama-3.1-8B-Instruct",
            output_dir="/tmp/profiler",
            mode="kernel",
        )
    )
    names = [command.name for command in plan.commands]
    assert names == ["vllm_steady_metrics", "nsys_timeline", "nsys_stats", "ncu_kernel_counters"]
    assert plan.expected_manifest["ncu"] == "ncu_kernel_summary.csv"
    assert any("Deep profiling" in warning for warning in plan.warnings)


def test_amd_roofline_capture_plan_includes_roctx_rocprof_and_roofline_steps() -> None:
    plan = build_capture_plan(
        ProfilerCaptureRequest(
            vendor="amd",
            gpu_model="MI355X",
            model="meta-llama/Llama-3.1-8B-Instruct",
            output_dir="/tmp/profiler",
            mode="roofline",
        )
    )
    rendered = " ".join(" ".join(command.command) for command in plan.commands)
    assert "rocprofv3" in rendered
    assert "rocprof-compute" in rendered
    assert "--marker-trace" in rendered
    assert plan.expected_manifest["rocprof_compute_roofline"] == "rocprof_compute_roofline.csv"


def test_report_distinguishes_missing_live_artifacts_from_performance_claims() -> None:
    run = normalize_profiler_run(
        run_id="no-gpu-scaffold",
        vendor="nvidia",
        gpu_model="H100",
        workload_name="latency-baseline",
        capture_mode="timeline",
    )
    report = render_markdown_report(run)
    assert "Confidence: `partial`" in report
    assert "timeline_missing" in report
    assert "parser behavior only" in report
