"""Dataclass contracts for AgentX replay result ingestion."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from inferguard.bench.agentx_bridge import AGENTX_SCHEMA_VERSION

AGENTX_INGEST_SUMMARY_SCHEMA_VERSION = "inferguard-agentx-ingest-summary/v1"

IngestStatus = Literal["ingested", "ingest_failed"]
AgentXClaimStatus = Literal["measured", "inferred", "not_proven"]


@dataclass(frozen=True)
class AgentXIngestSummary:
    """Summary emitted beside canonical InferGuard artifacts."""

    job_id: str
    status: IngestStatus
    request_count: int
    success_count: int
    mapped_metrics_count: int
    claim_status: AgentXClaimStatus
    raw_artifact_paths: dict[str, str]
    canonical_artifact_paths: dict[str, str]
    engine: str = "vllm"
    workload_label: str = "agentx-replay"
    model_profile: str = "agentx-replay"
    inputs_under_target_warning: bool = False
    warnings: list[str] = field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    missing_required_columns: list[str] = field(default_factory=list)
    field_claim_status: dict[str, AgentXClaimStatus] = field(default_factory=dict)
    field_evidence_paths: dict[str, list[str]] = field(default_factory=dict)
    generated_at: str = ""
    ingest_summary_schema_version: str = AGENTX_INGEST_SUMMARY_SCHEMA_VERSION
    schema_version: str = AGENTX_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {"schema_version": data.pop("schema_version"), **data}

    def summary_line(self) -> str:
        return (
            "inferguard ingest-agentx: "
            f"requests={self.request_count} "
            f"success={self.success_count} "
            f"mapped_metrics={self.mapped_metrics_count} "
            f"claim={self.claim_status}"
        )


@dataclass(frozen=True)
class CanonicalArtifacts:
    """Paths produced by an AgentX canonical ingest run."""

    request_profile_jsonl: Path
    requests_summary_json: Path
    engine_metrics_timeline_jsonl: Path
    gpu_metrics_timeline_jsonl: Path
    agentx_ingest_summary_json: Path
    agentx_ingest_summary_md: Path
    summary: AgentXIngestSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_profile_jsonl": str(self.request_profile_jsonl),
            "requests_summary_json": str(self.requests_summary_json),
            "engine_metrics_timeline_jsonl": str(self.engine_metrics_timeline_jsonl),
            "gpu_metrics_timeline_jsonl": str(self.gpu_metrics_timeline_jsonl),
            "agentx_ingest_summary_json": str(self.agentx_ingest_summary_json),
            "agentx_ingest_summary_md": str(self.agentx_ingest_summary_md),
            "summary": self.summary.to_dict(),
        }


__all__ = [
    "AGENTX_INGEST_SUMMARY_SCHEMA_VERSION",
    "AgentXClaimStatus",
    "AgentXIngestSummary",
    "CanonicalArtifacts",
    "IngestStatus",
]
