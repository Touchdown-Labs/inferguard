"""Router verdict schemas."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

ROUTER_VERDICT_SCHEMA_VERSION = "inferguard-router-verdict/v1"


class BottleneckClass(StrEnum):
    PREFILL_BOUND = "prefill_bound"
    DECODE_BOUND = "decode_bound"
    KV_BOUND = "kv_bound"
    QUEUE_BOUND = "queue_bound"
    NETWORK_BOUND = "network_bound"
    HOST_BOUND = "host_bound"
    QUALITY_BOUND = "quality_bound"


class FindingRef(BaseModel):
    source: str
    code: str
    severity: str = "info"
    message: str = ""
    cell_id: str | None = None


class ExecutionPath(BaseModel):
    target: Literal[
        "openai_api",
        "anthropic_api",
        "gemini_api",
        "hosted_open_api",
        "self_hosted_vllm",
        "self_hosted_sglang",
        "self_hosted_trtllm",
        "self_hosted_dynamo",
        "neocloud_managed_inference",
        "local_mlx",
        "local_ollama",
        "video_diffusion_queue",
    ]
    rationale: str
    confidence: float
    referral_partner: str | None = None


class RouterVerdict(BaseModel):
    schema_version: Literal["inferguard-router-verdict/v1"] = ROUTER_VERDICT_SCHEMA_VERSION
    bottleneck_class: BottleneckClass
    execution_paths: list[ExecutionPath]
    evidence: list[FindingRef] = Field(default_factory=list)
    claim_label: Literal["measured_local", "inferred_without_engine_metrics", "not_proven"] = "inferred_without_engine_metrics"
    claim_boundary: str = (
        "Router verdicts are routing recommendations from workload shape and benchmark "
        "artifacts. They are not live production claims until validated by matching "
        "customer or Slurm run artifacts."
    )

    def as_dict(self) -> dict:
        return self.model_dump(mode="json")
