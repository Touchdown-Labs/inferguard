"""Build canonical profiler bridge runs from parsed artifacts."""

from __future__ import annotations

from inferguard.profilers.schema import (
    CaptureMode,
    CounterSample,
    DeviceInfo,
    KernelEvent,
    NormalizedProfilerRun,
    ProfilerFinding,
    RequestMetrics,
    RooflinePoint,
    Vendor,
    WorkloadInfo,
)


def normalize_profiler_run(
    *,
    run_id: str,
    vendor: Vendor,
    gpu_model: str,
    workload_name: str,
    capture_mode: CaptureMode,
    request_metrics: RequestMetrics | None = None,
    kernel_events: list[KernelEvent] | None = None,
    counter_samples: list[CounterSample] | None = None,
    roofline_points: list[RooflinePoint] | None = None,
    artifacts: dict[str, str] | None = None,
    live_artifacts: bool = False,
) -> NormalizedProfilerRun:
    kernels = list(kernel_events or [])
    counters = list(counter_samples or [])
    roofline = list(roofline_points or [])
    findings: list[ProfilerFinding] = []
    if request_metrics is None:
        findings.append(
            ProfilerFinding(
                code="vllm_metrics_missing",
                message="No vLLM Prometheus metrics were imported; request-level evidence is not proven.",
                confidence="not_proven",
            )
        )
    if capture_mode in {"timeline", "kernel", "roofline"} and not kernels:
        findings.append(
            ProfilerFinding(
                code="timeline_missing",
                message="No timeline/kernel events were imported for the requested deep-profile mode.",
                confidence="blocked",
            )
        )
    confidence = "measured" if live_artifacts and request_metrics and (kernels or capture_mode == "steady") else "partial"
    if findings and confidence == "measured":
        confidence = "partial"
    return NormalizedProfilerRun(
        run_id=run_id,
        device=DeviceInfo(vendor=vendor, model=gpu_model, architecture=_architecture(vendor, gpu_model)),
        workload=WorkloadInfo(name=workload_name),
        capture_mode=capture_mode,
        request_metrics=request_metrics,
        kernel_events=kernels,
        counter_samples=counters,
        roofline_points=roofline,
        findings=findings,
        confidence=confidence,
        artifacts=dict(artifacts or {}),
    )


def _architecture(vendor: Vendor, gpu_model: str) -> str | None:
    model = gpu_model.upper()
    if vendor == "amd":
        if any(token in model for token in ("MI300", "MI325")):
            return "CDNA3"
        if any(token in model for token in ("MI350", "MI355")):
            return "CDNA4"
    if vendor == "nvidia":
        if any(token in model for token in ("H100", "H200")):
            return "Hopper"
        if any(token in model for token in ("B200", "B300", "GB200", "GB300")):
            return "Blackwell"
    return None
