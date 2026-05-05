"""Datatypes for native InferGuard bench runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    name: str
    latency_ms: float
    count: int = 1


@dataclass(frozen=True)
class RequestSpec:
    request_id: str
    trace_id: str
    session_id: str
    turn_index: int
    workload_class: str
    messages: list[dict[str, Any]]
    expected_input_tokens: int | None
    expected_output_tokens: int | None
    prefix_group: str | None
    tool_heavy: bool
    customer_id: str | None = None
    sla_tier: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RequestMetric:
    request_id: str
    trace_id: str
    session_id: str
    turn_index: int
    workload_class: str
    concurrency: int
    success: bool
    start_time: float
    end_time: float
    latency_seconds: float
    ttft_seconds: float | None
    input_tokens: int
    output_tokens: int
    input_tokens_source: str
    output_tokens_source: str
    tokens_per_second: float | None
    error: str | None = None
    status_code: int | None = None
    first_sse_seconds: float | None = None
    first_content_token_seconds: float | None = None
    done_seen: bool = False
    valid_content_seen: bool = False
    prefix_group: str | None = None
    tool_heavy: bool = False
    kv_pressure_label: str | None = None
    client_queue_time_ms: float | None = None
    engine_processing_time_ms: float | None = None
    tool_simulation_time_ms: float | None = None
    network_overhead_ms: float | None = None
    customer_id: str | None = None
    sla_tier: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
