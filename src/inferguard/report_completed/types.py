"""Dataclass contracts for PRD §4.7 operator recommendations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

OPERATOR_RECOMMENDATION_SCHEMA_VERSION = "inferguard-operator-recommendation/v1"
OPERATOR_BRIEF_SCHEMA_VERSION = "inferguard-operator-brief/v1"
CLAIM_STATUSES = {"measured", "inferred", "synthetic", "not_proven"}
EXECUTIVE_VERDICT_STATUSES = {
    "live_complete",
    "live_incomplete",
    "synthetic_only",
    "not_enough_evidence",
}


@dataclass(frozen=True)
class Refusal:
    """Evidence gate result for a claim that cannot be made."""

    claim_id: str
    reason: str
    evidence_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "reason": self.reason,
            "evidence_paths": sorted(self.evidence_paths),
        }


@dataclass(frozen=True)
class Section:
    """One operator-facing Markdown section."""

    title: str
    claim_status: str
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "claim_status": self.claim_status,
            "lines": list(self.lines),
        }


@dataclass(frozen=True)
class Claim:
    """One row in the machine-checkable claim table."""

    claim_id: str
    claim_text: str
    status: str
    evidence_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_text": self.claim_text,
            "status": self.status,
            "evidence_paths": sorted(self.evidence_paths),
        }


@dataclass(frozen=True)
class OperatorRecommendation:
    """Canonical GMI-facing completed-run recommendation report."""

    executive_verdict: str
    executive_verdict_status: str
    claim_status: str
    best_gpu_sku: dict[str, Any]
    best_engine: dict[str, Any]
    best_model_config: dict[str, Any]
    bottleneck: dict[str, Any]
    capacity_envelope: dict[str, Any]
    failure_summary: dict[str, Any]
    cost_notes: dict[str, Any]
    lmcache_verdict: dict[str, Any]
    gb200_justification: dict[str, Any]
    recommended_next_run: str
    evidence_artifacts: list[str]
    claim_table: list[Claim]
    sections: list[Section]
    base_operator_brief: dict[str, Any] = field(default_factory=dict)
    refusals: list[Refusal] = field(default_factory=list)
    schema_version: str = OPERATOR_RECOMMENDATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "base_schema_version": OPERATOR_BRIEF_SCHEMA_VERSION,
            "executive_verdict": self.executive_verdict,
            "executive_verdict_status": self.executive_verdict_status,
            "claim_status": self.claim_status,
            "best_gpu_sku": dict(self.best_gpu_sku),
            "best_engine": dict(self.best_engine),
            "best_model_config": dict(self.best_model_config),
            "bottleneck": dict(self.bottleneck),
            "capacity_envelope": dict(self.capacity_envelope),
            "failure_summary": dict(self.failure_summary),
            "cost_notes": dict(self.cost_notes),
            "lmcache_verdict": dict(self.lmcache_verdict),
            "gb200_justification": dict(self.gb200_justification),
            "recommended_next_run": self.recommended_next_run,
            "evidence_artifacts": sorted(self.evidence_artifacts),
            "claim_table": [claim.to_dict() for claim in self.claim_table],
            "sections": [section.to_dict() for section in self.sections],
            "operator_brief_extension": dict(self.base_operator_brief),
            "refusals": [refusal.to_dict() for refusal in self.refusals],
        }


__all__ = [
    "CLAIM_STATUSES",
    "EXECUTIVE_VERDICT_STATUSES",
    "OPERATOR_BRIEF_SCHEMA_VERSION",
    "OPERATOR_RECOMMENDATION_SCHEMA_VERSION",
    "Claim",
    "OperatorRecommendation",
    "Refusal",
    "Section",
]
