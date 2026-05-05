"""Dataclass contracts for per-request profiling artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

REQUEST_PROFILE_SCHEMA_VERSION = "inferguard-request-profile/v1"
REQUEST_PROFILE_SUMMARY_SCHEMA_VERSION = "inferguard-request-profile-summary/v1"

ClaimStatus = Literal["measured", "inferred", "not_proven"]
TokenSource = Literal["server", "tokenizer", "estimated"]
ErrorType = Literal[
    "connect_error",
    "timeout",
    "http_4xx",
    "http_5xx",
    "stream_truncated",
    "tokenizer_error",
    "unknown",
]
EngineName = Literal["vllm", "sglang", "lmcache", "dynamo-sglang", "agentx-replay"]
ArrivalMode = Literal["closed_loop", "poisson"]


@dataclass(frozen=True)
class RequestProfileOptions:
    endpoint: str
    model: str
    input_jsonl: str
    output_dir: str
    concurrency: int = 1
    timeout_seconds: float = 300.0
    arrival_mode: ArrivalMode = "closed_loop"
    rate_rps: float | None = None
    max_requests: int | None = None
    api_key: str | None = None
    stream: bool = False
    include_usage: bool = False
    continuous_usage_stats: bool = False
    workload_label: str = "default"
    job_id: str | None = None
    seed: int = 0
    engine: EngineName = "vllm"
    model_profile: str | None = None


@dataclass(frozen=True)
class RequestProfileRow:
    request_id: str
    job_id: str
    workload_label: str
    model_profile: str
    engine: EngineName
    context_length: int
    concurrency: int
    prompt_tokens: int
    completion_tokens: int
    prompt_tokens_source: TokenSource
    send_ts: str
    first_token_ts: str | None
    done_ts: str
    ttft_ms: float | None
    e2e_latency_ms: float
    tpot_ms: float | None
    inter_token_latency_ms_p50: float | None
    inter_token_latency_ms_p95: float | None
    decode_tokens_per_sec: float | None
    streaming: bool
    success: bool
    http_status: int | None
    error_type: ErrorType | None
    error_message: str | None
    cached_tokens: int | None
    claim_status: ClaimStatus
    raw_response_ref: str | None = None
    claim_status_per_field: dict[str, ClaimStatus] = field(default_factory=dict)
    schema_version: str = REQUEST_PROFILE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {"schema_version": data.pop("schema_version"), **data}


@dataclass(frozen=True)
class RequestProfileSummary:
    job_id: str
    workload_label: str
    engine: EngineName
    concurrency: int
    request_count: int
    success_count: int
    failure_count: int
    ttft_ms: dict[str, float | None]
    tpot_ms: dict[str, float | None]
    e2e_latency_ms: dict[str, float | None]
    decode_tokens_per_sec: dict[str, float | None]
    prompt_tokens_total: int
    completion_tokens_total: int
    tokens_per_sec_aggregate: float | None
    failure_breakdown: dict[str, int]
    claim_status: ClaimStatus
    success_rate: float
    schema_version: str = REQUEST_PROFILE_SUMMARY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {"schema_version": data.pop("schema_version"), **data}


__all__ = [
    "ArrivalMode",
    "ClaimStatus",
    "EngineName",
    "ErrorType",
    "REQUEST_PROFILE_SCHEMA_VERSION",
    "REQUEST_PROFILE_SUMMARY_SCHEMA_VERSION",
    "RequestProfileOptions",
    "RequestProfileRow",
    "RequestProfileSummary",
    "TokenSource",
]
