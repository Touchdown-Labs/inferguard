"""Validation report contracts for completed NeoCloud/GMI runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALIDATION_REPORT_SCHEMA_VERSION = "inferguard-validation-report/v1"
MATRIX_EVIDENCE_CLAIM_IDS = {
    "slurm_env",
    "gpu_inventory",
    "gpu_topology",
    "agentx_ingest_summary",
}

CLAIM_STATUSES = {"measured", "inferred", "synthetic", "not_proven"}
RUN_STATUSES = {
    "live_complete",
    "live_incomplete",
    "synthetic_only",
    "missing_required_artifacts",
    "not_publishable",
}


@dataclass(frozen=True)
class Downgrade:
    """A claim-label downgrade with a short operator-readable reason."""

    claim_id: str
    from_label: str
    to: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "claim_id": self.claim_id,
            "from": self.from_label,
            "to": self.to,
            "reason": self.reason,
        }


@dataclass
class JobValidation:
    """Validation result for one rendered benchmark job."""

    job_id: str
    status: str
    claim_status: str
    required_paths_present: list[str] = field(default_factory=list)
    required_paths_missing: list[str] = field(default_factory=list)
    synthetic_markers: list[str] = field(default_factory=list)
    downgrades: list[Downgrade] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "claim_status": self.claim_status,
            "required_paths_present": sorted(self.required_paths_present),
            "required_paths_missing": sorted(self.required_paths_missing),
            "synthetic_markers": sorted(self.synthetic_markers),
            "downgrades": [downgrade.to_dict() for downgrade in self.downgrades],
        }


@dataclass
class ValidationReport:
    """Top-level completed-run publishability report."""

    status: str
    results_root: str
    matrix_plan_ref: str
    artifact_contract_ref: str
    validated_at: str
    harness_version: str
    jobs: list[JobValidation]
    schema_version: str = VALIDATION_REPORT_SCHEMA_VERSION

    @property
    def summary(self) -> dict[str, int]:
        counts = {status: 0 for status in sorted(RUN_STATUSES)}
        for job in self.jobs:
            counts[job.status] = counts.get(job.status, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "results_root": self.results_root,
            "matrix_plan_ref": self.matrix_plan_ref,
            "artifact_contract_ref": self.artifact_contract_ref,
            "validated_at": self.validated_at,
            "harness_version": self.harness_version,
            "jobs": [job.to_dict() for job in self.jobs],
            "summary": self.summary,
        }
