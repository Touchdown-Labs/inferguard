"""Typed contracts for ``inferguard profile`` artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from inferguard.disagg.types import EngineName, Severity

PROFILE_SAMPLE_SCHEMA_VERSION = "inferguard-profile-sample/v1"
PROFILE_SUMMARY_SCHEMA_VERSION = "inferguard-profile-summary/v1"

ProfileMode = Literal["single-endpoint", "prefill-decode"]
ProfileFindingCode = Literal[
    "profile_kv_cache_high",
    "profile_kv_cache_critical",
    "profile_preemptions_rising",
    "profile_queue_backlog",
    "profile_prefix_hit_rate_low",
    "profile_offload_churn",
    "profile_metrics_unavailable",
    "kv_footprint_imbalance",
    "prefix_eviction_cross_customer",
    "cold_start_ramp_extended",
    "engine_crash_recovery_slow",
]


@dataclass(frozen=True)
class ProfileFinding:
    """A profile-local finding emitted while sampling a live endpoint."""

    code: ProfileFindingCode | str
    severity: Severity
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class ProfileSample:
    """One JSONL row from the profile live loop."""

    profile_id: str
    sequence: int
    observed_at: str
    mode: ProfileMode
    snapshot: dict[str, Any]
    deltas: dict[str, int | float]
    findings: list[ProfileFinding] = field(default_factory=list)
    schema_version: str = PROFILE_SAMPLE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "sequence": self.sequence,
            "observed_at": self.observed_at,
            "mode": self.mode,
            "snapshot": self.snapshot,
            "deltas": dict(self.deltas),
            "findings": [finding.as_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class ProfileSummary:
    """End-of-window summary for ``inferguard profile live``."""

    profile_id: str
    duration_seconds: float
    sample_count: int
    engine: EngineName | str
    highest_kv_cache_usage: float | None
    max_requests_waiting: int | None
    preemptions_total_delta: int | None
    prefix_cache_hit_rate_observed: float | None
    recommendation: str
    findings: list[ProfileFinding] = field(default_factory=list)
    schema_version: str = PROFILE_SUMMARY_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "duration_seconds": self.duration_seconds,
            "sample_count": self.sample_count,
            "engine": self.engine,
            "highest_kv_cache_usage": self.highest_kv_cache_usage,
            "max_requests_waiting": self.max_requests_waiting,
            "preemptions_total_delta": self.preemptions_total_delta,
            "prefix_cache_hit_rate_observed": self.prefix_cache_hit_rate_observed,
            "recommendation": self.recommendation,
            "findings": [finding.as_dict() for finding in self.findings],
        }
