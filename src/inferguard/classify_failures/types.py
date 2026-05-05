"""Dataclass contracts for operator-actionable failure classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

FAILURE_CLASSIFICATION_SCHEMA_VERSION = "inferguard-failure-classification/v1"

ClaimStatus = Literal["measured", "inferred", "not_proven"]
FailureClassName = Literal[
    "oom_hbm_exhaustion",
    "cuda_error",
    "nccl_error",
    "rdma_inactive",
    "model_config_mismatch",
    "tokenizer_or_parser_failure",
    "container_image_incompatibility",
    "endpoint_healthcheck_failure",
    "client_timeout",
    "server_crash",
    "slurm_allocation_failure",
    "not_enough_evidence",
]
TopClassName = FailureClassName | Literal["none"]

FAILURE_CLASS_NAMES: tuple[FailureClassName, ...] = (
    "oom_hbm_exhaustion",
    "cuda_error",
    "nccl_error",
    "rdma_inactive",
    "model_config_mismatch",
    "tokenizer_or_parser_failure",
    "container_image_incompatibility",
    "endpoint_healthcheck_failure",
    "client_timeout",
    "server_crash",
    "slurm_allocation_failure",
    "not_enough_evidence",
)
CLAIM_STATUSES: tuple[ClaimStatus, ...] = ("measured", "inferred", "not_proven")


@dataclass(frozen=True)
class EvidenceRef:
    """A precise reference to raw classifier evidence."""

    path: str
    start_line: int | None = None
    end_line: int | None = None
    excerpt: str = ""
    label: str = ""

    def path_ref(self) -> str:
        """Return the schema's compact evidence path reference."""

        if self.start_line is None:
            ref = self.path
        elif self.end_line is None or self.end_line == self.start_line:
            ref = f"{self.path}:{self.start_line}"
        else:
            ref = f"{self.path}:{self.start_line}-{self.end_line}"
        if self.label:
            ref = f"{ref} {self.label}"
        return ref

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "excerpt": self.excerpt,
            "label": self.label,
        }


@dataclass(frozen=True)
class FailureClass:
    """One ranked failure-class entry in the v1 schema."""

    rank: int
    failure_class: FailureClassName
    confidence: float
    evidence: tuple[EvidenceRef, ...] = field(default_factory=tuple)
    evidence_excerpt: str = ""
    regex_id: str = ""
    claim_status: ClaimStatus = "measured"

    def __post_init__(self) -> None:
        if self.failure_class not in FAILURE_CLASS_NAMES:
            raise ValueError(f"unsupported failure class: {self.failure_class}")
        if self.claim_status not in CLAIM_STATUSES:
            raise ValueError(f"unsupported claim_status: {self.claim_status}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "class": self.failure_class,
            "confidence": round(self.confidence, 3),
            "evidence_paths": [ref.path_ref() for ref in self.evidence],
            "evidence_excerpt": self.evidence_excerpt,
            "regex_id": self.regex_id,
            "claim_status": self.claim_status,
        }


@dataclass(frozen=True)
class FailureClassification:
    """Top-level failure classification artifact."""

    job_id: str
    failures: tuple[FailureClass, ...] = field(default_factory=tuple)
    top_class: TopClassName = "none"
    claim_status: ClaimStatus = "measured"
    schema_version: str = FAILURE_CLASSIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FAILURE_CLASSIFICATION_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        if self.top_class != "none" and self.top_class not in FAILURE_CLASS_NAMES:
            raise ValueError(f"unsupported top_class: {self.top_class}")
        if self.claim_status not in CLAIM_STATUSES:
            raise ValueError(f"unsupported claim_status: {self.claim_status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "failures": [failure.to_dict() for failure in self.failures],
            "top_class": self.top_class,
            "claim_status": self.claim_status,
        }


__all__ = [
    "CLAIM_STATUSES",
    "FAILURE_CLASSIFICATION_SCHEMA_VERSION",
    "FAILURE_CLASS_NAMES",
    "ClaimStatus",
    "EvidenceRef",
    "FailureClass",
    "FailureClassification",
    "FailureClassName",
    "TopClassName",
]
