"""Canonical schema for the InferGuard Profiler Bridge.

The schema intentionally represents parsed profiler artifacts without claiming
semantic equivalence between vendor-specific counters. Confidence fields keep
synthetic fixtures, partial imports, and future live artifacts clearly separated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PROFILER_BRIDGE_SCHEMA_VERSION = "inferguard-profiler-bridge/v1"

Vendor = Literal["nvidia", "amd", "vllm", "unknown"]
CaptureMode = Literal["steady", "timeline", "kernel", "roofline"]
Confidence = Literal["measured", "partial", "not_proven", "blocked"]
PhaseName = Literal[
    "server_startup",
    "warmup",
    "prefill",
    "decode",
    "kv_transfer",
    "scheduler_wait",
    "communication",
    "postprocess",
    "unknown",
]


@dataclass(frozen=True)
class DeviceInfo:
    vendor: Vendor
    model: str
    architecture: str | None = None
    source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "model": self.model,
            "architecture": self.architecture,
            "source": self.source,
        }


@dataclass(frozen=True)
class WorkloadInfo:
    name: str
    runtime: str = "vllm"
    input_tokens: int | None = None
    output_tokens: int | None = None
    concurrency: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "runtime": self.runtime,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "concurrency": self.concurrency,
        }


@dataclass(frozen=True)
class RequestMetrics:
    source: str
    ttft_seconds: float | None = None
    itl_seconds: float | None = None
    latency_seconds: float | None = None
    tokens_per_second: float | None = None
    requests_per_second: float | None = None
    queue_depth: float | None = None
    raw_metrics: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "ttft_seconds": self.ttft_seconds,
            "itl_seconds": self.itl_seconds,
            "latency_seconds": self.latency_seconds,
            "tokens_per_second": self.tokens_per_second,
            "requests_per_second": self.requests_per_second,
            "queue_depth": self.queue_depth,
            "raw_metrics": dict(self.raw_metrics),
        }


@dataclass(frozen=True)
class KernelEvent:
    source: str
    vendor: Vendor
    name: str
    duration_ms: float | None = None
    calls: int | None = None
    phase: PhaseName = "unknown"
    raw: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "vendor": self.vendor,
            "name": self.name,
            "duration_ms": self.duration_ms,
            "calls": self.calls,
            "phase": self.phase,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class CounterSample:
    source: str
    vendor: Vendor
    name: str
    value: float
    unit: str | None = None
    kernel_name: str | None = None
    raw_name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "vendor": self.vendor,
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "kernel_name": self.kernel_name,
            "raw_name": self.raw_name,
        }


@dataclass(frozen=True)
class RooflinePoint:
    source: str
    vendor: Vendor
    kernel_name: str
    arithmetic_intensity: float | None = None
    performance: float | None = None
    bound: str | None = None
    raw: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "vendor": self.vendor,
            "kernel_name": self.kernel_name,
            "arithmetic_intensity": self.arithmetic_intensity,
            "performance": self.performance,
            "bound": self.bound,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class ProfilerFinding:
    code: str
    message: str
    confidence: Confidence
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "confidence": self.confidence,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class NormalizedProfilerRun:
    run_id: str
    device: DeviceInfo
    workload: WorkloadInfo
    capture_mode: CaptureMode
    request_metrics: RequestMetrics | None = None
    kernel_events: list[KernelEvent] = field(default_factory=list)
    counter_samples: list[CounterSample] = field(default_factory=list)
    roofline_points: list[RooflinePoint] = field(default_factory=list)
    findings: list[ProfilerFinding] = field(default_factory=list)
    confidence: Confidence = "partial"
    artifacts: dict[str, str] = field(default_factory=dict)
    schema_version: str = PROFILER_BRIDGE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "device": self.device.as_dict(),
            "workload": self.workload.as_dict(),
            "capture_mode": self.capture_mode,
            "request_metrics": self.request_metrics.as_dict() if self.request_metrics else None,
            "kernel_events": [event.as_dict() for event in self.kernel_events],
            "counter_samples": [sample.as_dict() for sample in self.counter_samples],
            "roofline_points": [point.as_dict() for point in self.roofline_points],
            "findings": [finding.as_dict() for finding in self.findings],
            "confidence": self.confidence,
            "artifacts": dict(self.artifacts),
        }
