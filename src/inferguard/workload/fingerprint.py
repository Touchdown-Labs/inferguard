"""Schemas for workload-intelligence fingerprints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WORKLOAD_FINGERPRINT_SCHEMA_VERSION = "inferguard-workload-fingerprint/v1"


class Distribution(BaseModel):
    p50: float | None = None
    p95: float | None = None
    p99: float | None = None
    max: float | None = None


class CostEstimate(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    baseline_cost_usd: float | None = None
    notes: list[str] = Field(default_factory=list)


class WorkloadFingerprint(BaseModel):
    schema_version: Literal["inferguard-workload-fingerprint/v1"] = (
        WORKLOAD_FINGERPRINT_SCHEMA_VERSION
    )
    sample_count: int
    source_format: str
    input_token_distribution: Distribution
    output_token_distribution: Distribution
    session_length_distribution: Distribution
    prefix_reuse_score: float
    prefill_decode_ratio: float | None = None
    tool_call_fanout_distribution: Distribution
    retry_rate: float
    rag_chunk_volume: int
    burstiness_factor: float | None = None
    p95_latency_sensitivity: Literal["tight", "loose", "batch"] = "loose"
    cacheability_score: float
    privacy_class: Literal["public", "private", "regulated"] = "public"
    workload_classes: dict[str, int] = Field(default_factory=dict)
    cost_per_task_estimate: CostEstimate
    claim_boundary: str = (
        "Fingerprint is pre-flight workload shape evidence. It does not prove engine "
        "performance until benchmark artifacts are collected."
    )

    def as_dict(self) -> dict:
        return self.model_dump(mode="json")
