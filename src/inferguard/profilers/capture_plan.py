"""Dry-run capture plan generation for profiler bridge runs.

This module never shells out. It emits command templates and artifact manifests
that engineers can run once NVIDIA or AMD bare-metal access is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from inferguard.profilers.schema import CaptureMode, Vendor


@dataclass(frozen=True)
class CaptureCommand:
    name: str
    command: tuple[str, ...]
    expected_artifacts: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": list(self.command),
            "expected_artifacts": list(self.expected_artifacts),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ProfilerCaptureRequest:
    vendor: Vendor
    gpu_model: str
    model: str
    output_dir: str
    runtime: str = "vllm"
    workload_name: str = "latency-baseline"
    mode: CaptureMode = "steady"
    vllm_command: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CapturePlan:
    vendor: Vendor
    gpu_model: str
    mode: CaptureMode
    commands: tuple[CaptureCommand, ...]
    expected_manifest: dict[str, str]
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "gpu_model": self.gpu_model,
            "mode": self.mode,
            "commands": [command.as_dict() for command in self.commands],
            "expected_manifest": dict(self.expected_manifest),
            "warnings": list(self.warnings),
        }


def build_capture_plan(request: ProfilerCaptureRequest) -> CapturePlan:
    if request.vendor == "nvidia":
        return _nvidia_plan(request)
    if request.vendor == "amd":
        return _amd_plan(request)
    if request.vendor == "vllm":
        return _steady_vllm_plan(request)
    raise ValueError(f"unsupported profiler vendor: {request.vendor}")


def _serve_command(request: ProfilerCaptureRequest) -> tuple[str, ...]:
    if request.vllm_command:
        return request.vllm_command
    return ("vllm", "serve", request.model, "--enable-metrics", "--port", "8000")


def _steady_command(request: ProfilerCaptureRequest) -> CaptureCommand:
    return CaptureCommand(
        name="vllm_steady_metrics",
        command=("curl", "-fsS", "http://127.0.0.1:8000/metrics", "-o", f"{request.output_dir}/vllm.prom"),
        expected_artifacts=("vllm.prom", "benchmark_serving.json"),
        notes=("Run steady benchmark separately from deep-profile runs; vLLM profiling can slow inference.",),
    )


def _steady_vllm_plan(request: ProfilerCaptureRequest) -> CapturePlan:
    return CapturePlan(
        vendor="vllm",
        gpu_model=request.gpu_model,
        mode="steady",
        commands=(_steady_command(request),),
        expected_manifest={"vllm_metrics": "vllm.prom", "benchmark": "benchmark_serving.json"},
    )


def _nvidia_plan(request: ProfilerCaptureRequest) -> CapturePlan:
    commands = [_steady_command(request)]
    manifest = {"vllm_metrics": "vllm.prom", "benchmark": "benchmark_serving.json"}
    if request.mode in {"timeline", "kernel", "roofline"}:
        commands.append(
            CaptureCommand(
                name="nsys_timeline",
                command=(
                    "nsys",
                    "profile",
                    "-o",
                    f"{request.output_dir}/nsys_report",
                    "--trace-fork-before-exec=true",
                    "--cuda-graph-trace=node",
                    *_serve_command(request),
                ),
                expected_artifacts=("nsys_report.nsys-rep", "nsys_stats_kernel_sum.csv"),
                notes=("Use NVTX ranges to align prefill/decode/kv_transfer phases.",),
            )
        )
        commands.append(
            CaptureCommand(
                name="nsys_stats",
                command=(
                    "nsys",
                    "stats",
                    "--report",
                    "cuda_gpu_kern_sum,cuda_gpu_mem_time_sum,nvtx_sum",
                    "--format",
                    "csv",
                    f"{request.output_dir}/nsys_report.nsys-rep",
                ),
                expected_artifacts=("nsys_stats_kernel_sum.csv",),
            )
        )
        manifest["nsys"] = "nsys_stats_kernel_sum.csv"
    if request.mode in {"kernel", "roofline"}:
        commands.append(
            CaptureCommand(
                name="ncu_kernel_counters",
                command=(
                    "ncu",
                    "--csv",
                    "--set",
                    "full",
                    "--target-processes",
                    "all",
                    "--nvtx",
                    "--log-file",
                    f"{request.output_dir}/ncu_kernel_summary.csv",
                    *_serve_command(request),
                ),
                expected_artifacts=("ncu_kernel_summary.csv",),
                notes=("Use after timeline narrows the kernel/range of interest.",),
            )
        )
        manifest["ncu"] = "ncu_kernel_summary.csv"
    return CapturePlan(
        vendor="nvidia",
        gpu_model=request.gpu_model,
        mode=request.mode,
        commands=tuple(commands),
        expected_manifest=manifest,
        warnings=("Deep profiling artifacts are not steady-state benchmark proof.",),
    )


def _amd_plan(request: ProfilerCaptureRequest) -> CapturePlan:
    commands = [_steady_command(request)]
    manifest = {"vllm_metrics": "vllm.prom", "benchmark": "benchmark_serving.json"}
    if request.mode in {"timeline", "kernel", "roofline"}:
        commands.append(
            CaptureCommand(
                name="rocprofv3_timeline",
                command=(
                    "rocprofv3",
                    "--runtime-trace",
                    "--kernel-trace",
                    "--memory-copy-trace",
                    "--marker-trace",
                    "--output-format",
                    "csv",
                    "--output-directory",
                    f"{request.output_dir}/rocprofv3",
                    "--",
                    *_serve_command(request),
                ),
                expected_artifacts=("rocprofv3/kernel_trace.csv",),
                notes=("Use ROCTx ranges as the AMD counterpart to NVIDIA NVTX ranges.",),
            )
        )
        manifest["rocprofv3"] = "rocprofv3/kernel_trace.csv"
    if request.mode in {"kernel", "roofline"}:
        commands.append(
            CaptureCommand(
                name="rocprof_compute_counters",
                command=(
                    "rocprof-compute",
                    "profile",
                    "-n",
                    request.workload_name,
                    "--format-rocprof-output",
                    "csv",
                    "--",
                    *_serve_command(request),
                ),
                expected_artifacts=("rocprof_compute_pmc_perf.csv",),
                notes=("Run rocprofv3-avail first when selecting hardware counters.",),
            )
        )
        manifest["rocprof_compute"] = "rocprof_compute_pmc_perf.csv"
    if request.mode == "roofline":
        commands.append(
            CaptureCommand(
                name="rocprof_compute_roofline",
                command=(
                    "rocprof-compute",
                    "profile",
                    "-n",
                    f"{request.workload_name}-roof",
                    "--roof-only",
                    "--roofline-data-type",
                    "fp16",
                    "--",
                    *_serve_command(request),
                ),
                expected_artifacts=("rocprof_compute_roofline.csv",),
            )
        )
        manifest["rocprof_compute_roofline"] = "rocprof_compute_roofline.csv"
    return CapturePlan(
        vendor="amd",
        gpu_model=request.gpu_model,
        mode=request.mode,
        commands=tuple(commands),
        expected_manifest=manifest,
        warnings=("Synthetic ROCm fixtures are parser proof only, not live AMD validation.",),
    )
