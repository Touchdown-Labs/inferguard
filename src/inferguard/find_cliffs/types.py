"""Dataclass contracts for PRD §4.8 capacity cliff detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CAPACITY_CLIFFS_SCHEMA_VERSION = "inferguard-capacity-cliffs/v1"

ClaimStatus = Literal["measured", "inferred", "not_proven"]
CAPACITY_CLIFF_NAMES: tuple[str, ...] = (
    "max_context_before_oom",
    "max_concurrency_before_p99_cliff",
    "throughput_plateau",
    "kv_saturation_point",
    "queue_explosion_point",
    "decode_collapse_point",
)
CLAIM_STATUSES: tuple[ClaimStatus, ...] = ("measured", "inferred", "not_proven")


@dataclass(frozen=True)
class EvidenceRef:
    """A compact reference to one artifact backing a cliff verdict."""

    path: str
    job_id: str = ""
    artifact: str = ""

    def to_dict(self) -> dict[str, str]:
        row = {"path": self.path}
        if self.job_id:
            row["job_id"] = self.job_id
        if self.artifact:
            row["artifact"] = self.artifact
        return row


@dataclass(frozen=True)
class Cliff:
    """One capacity cliff entry in the v1 schema."""

    name: str
    value: int | float | None
    claim_status: ClaimStatus
    evidence_paths: tuple[str, ...] = field(default_factory=tuple)
    evidence_jobs: tuple[str, ...] = field(default_factory=tuple)
    supporting_curve: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    reasoning: str = ""
    confidence: float = 0.0
    recommended_next_run: str = ""

    def __post_init__(self) -> None:
        if self.name not in CAPACITY_CLIFF_NAMES:
            raise ValueError(f"unsupported capacity cliff name: {self.name}")
        if self.claim_status not in CLAIM_STATUSES:
            raise ValueError(f"unsupported claim_status: {self.claim_status}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "claim_status": self.claim_status,
            "evidence_jobs": list(self.evidence_jobs),
            "evidence_paths": list(self.evidence_paths),
            "supporting_curve": [dict(point) for point in self.supporting_curve],
            "reasoning": self.reasoning,
            "confidence": round(float(self.confidence), 3),
            "recommended_next_run": self.recommended_next_run,
        }


@dataclass(frozen=True)
class CapacityCliffs:
    """Top-level `capacity_cliffs.json` contract."""

    results_root: str
    cliffs: tuple[Cliff, ...]
    summary: dict[str, Any]
    claim_reason: str | None = None
    schema_version: str = CAPACITY_CLIFFS_SCHEMA_VERSION

    @property
    def claim_status(self) -> ClaimStatus:
        statuses = {cliff.claim_status for cliff in self.cliffs}
        if "measured" in statuses:
            return "measured"
        if "inferred" in statuses:
            return "inferred"
        return "not_proven"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "results_root": self.results_root,
            "claim_status": self.claim_status,
            **({"claim_reason": self.claim_reason} if self.claim_reason else {}),
            "cliffs": [cliff.to_dict() for cliff in self.cliffs],
            "summary": dict(self.summary),
        }


__all__ = [
    "CAPACITY_CLIFFS_SCHEMA_VERSION",
    "CAPACITY_CLIFF_NAMES",
    "CLAIM_STATUSES",
    "CapacityCliffs",
    "ClaimStatus",
    "Cliff",
    "EvidenceRef",
]
