"""Comparison helpers for normalized profiler bridge runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from inferguard.profilers.schema import NormalizedProfilerRun, ProfilerFinding


@dataclass(frozen=True)
class ProfilerComparison:
    baseline_run_id: str
    candidate_run_id: str
    findings: tuple[ProfilerFinding, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "baseline_run_id": self.baseline_run_id,
            "candidate_run_id": self.candidate_run_id,
            "findings": [finding.as_dict() for finding in self.findings],
        }


def compare_runs(baseline: NormalizedProfilerRun, candidate: NormalizedProfilerRun) -> ProfilerComparison:
    findings: list[ProfilerFinding] = []
    if baseline.device.vendor != candidate.device.vendor:
        findings.append(
            ProfilerFinding(
                code="cross_vendor_metrics_not_equivalent",
                message="Runs use different profiler vendors; compare normalized lanes and raw counter names side by side.",
                confidence="partial",
                evidence={"baseline_vendor": baseline.device.vendor, "candidate_vendor": candidate.device.vendor},
            )
        )
    if not baseline.request_metrics or not candidate.request_metrics:
        findings.append(
            ProfilerFinding(
                code="request_metrics_missing",
                message="At least one run lacks vLLM request metrics, so latency comparison is not proven.",
                confidence="not_proven",
            )
        )
    return ProfilerComparison(
        baseline_run_id=baseline.run_id,
        candidate_run_id=candidate.run_id,
        findings=tuple(findings),
    )
