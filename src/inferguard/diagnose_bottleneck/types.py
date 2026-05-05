"""Contracts for PRD §4.5 bottleneck diagnosis artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

BOTTLENECK_DIAGNOSIS_SCHEMA_VERSION = "inferguard-bottleneck-diagnosis/v1"

ClaimStatus = Literal["measured", "inferred", "synthetic", "not_proven"]


class Verdict(StrEnum):
    """The locked eight-class operator verdict surface."""

    PREFILL_BOUND = "prefill_bound"
    DECODE_BOUND = "decode_bound"
    QUEUE_BOUND = "queue_bound"
    KV_BOUND = "kv_bound"
    NETWORK_BOUND = "network_bound"
    HOST_BOUND = "host_bound"
    MODEL_LAUNCH_BOUND = "model_launch_bound"
    NOT_ENOUGH_EVIDENCE = "not_enough_evidence"


VERDICT_VALUES: tuple[str, ...] = tuple(verdict.value for verdict in Verdict)


@dataclass(frozen=True)
class Evidence:
    """One metric observation used to support or reject a verdict."""

    metric: str
    source: str
    value: Any | None = None
    value_p95: Any | None = None
    claim_status: ClaimStatus | str = "measured"
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "metric": self.metric,
            "source": self.source,
            "claim_status": self.claim_status,
        }
        if self.value_p95 is not None:
            row["value_p95"] = self.value_p95
        if self.value is not None:
            row["value"] = self.value
        if "value" not in row and "value_p95" not in row:
            row["value"] = None
        if self.note:
            row["note"] = self.note
        return row


@dataclass(frozen=True)
class Downgrade:
    """A claim-status downgrade with an operator-readable reason."""

    claim_id: str
    from_label: ClaimStatus | str
    to: ClaimStatus | str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "claim_id": self.claim_id,
            "from": str(self.from_label),
            "to": str(self.to),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BottleneckDiagnosis:
    """The emitted `bottleneck_diagnosis.json` contract."""

    job_id: str
    verdict: Verdict | str
    confidence: float
    claim_status: ClaimStatus | str
    primary_evidence: list[Evidence]
    secondary_evidence: list[Evidence] = field(default_factory=list)
    supporting_request_rows: list[str] = field(default_factory=list)
    rule_fired: str = ""
    reasoning: str = ""
    recommended_next_probe: str = ""
    downgrades: list[Downgrade] = field(default_factory=list)
    evidence_paths: list[str] = field(default_factory=list)
    metric_values: dict[str, Any] = field(default_factory=dict)
    schema_version: str = BOTTLENECK_DIAGNOSIS_SCHEMA_VERSION

    def summary_line(self) -> str:
        return (
            "inferguard diagnose-bottleneck: "
            f"verdict={str(self.verdict)} "
            f"confidence={self.confidence:.3f} "
            f"evidence_paths={len(self.evidence_paths)} "
            f"claim={self.claim_status}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "verdict": str(self.verdict),
            "confidence": float(self.confidence),
            "claim_status": self.claim_status,
            "evidence_paths": list(self.evidence_paths),
            "metric_values": {key: self.metric_values[key] for key in sorted(self.metric_values)},
            "primary_evidence": [evidence.to_dict() for evidence in self.primary_evidence],
            "secondary_evidence": [evidence.to_dict() for evidence in self.secondary_evidence],
            "supporting_request_rows": list(self.supporting_request_rows),
            "rule_fired": self.rule_fired,
            "reasoning": self.reasoning,
            "recommended_next_probe": self.recommended_next_probe,
            "downgrades": [downgrade.to_dict() for downgrade in self.downgrades],
        }


__all__ = [
    "BOTTLENECK_DIAGNOSIS_SCHEMA_VERSION",
    "VERDICT_VALUES",
    "BottleneckDiagnosis",
    "ClaimStatus",
    "Downgrade",
    "Evidence",
    "Verdict",
]
