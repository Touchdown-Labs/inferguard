from __future__ import annotations

import json
from pathlib import Path

import pytest

from inferguard.schemas.agent_trace import (
    AgentTraceValidationError,
    iter_agent_trace_jsonl,
    validate_agent_trace_event,
    validate_trace_integrity,
)
from inferguard.schemas.telemetry import TelemetryValidationError, validate_telemetry_payload


def model_node() -> dict:
    return {
        "schema_version": "agent-trace/v1",
        "event_type": "node",
        "trace_id": "trace-1",
        "node_id": "node-1",
        "parent_node_ids": [],
        "timestamp_start": 1.0,
        "timestamp_end": 2.0,
        "kind": "model_call",
        "framework": "raw_openai",
        "model_call": {
            "endpoint": "http://localhost:8000/v1/chat/completions",
            "model": "deepseek-ai/DeepSeek-V4-Pro",
            "input_tokens": 8192,
            "output_tokens": 1024,
            "input_tokens_source": "api",
            "output_tokens_source": "api",
            "ttft_seconds": 0.420,
            "tpot_seconds": 0.012,
            "latency_seconds": 12.345,
            "tool_choice": "auto",
            "stream": True,
            "stop_reason": "tool_use",
            "request_id": "req-1",
            "kv_pressure_label": "measured",
        },
    }


def summary_event() -> dict:
    return {
        "schema_version": "agent-trace/v1",
        "event_type": "summary",
        "trace_id": "trace-1",
        "started_at": "2026-04-30T12:00:00Z",
        "completed_at": "2026-04-30T12:05:23Z",
        "total_seconds": 323.0,
        "node_counts": {"model_call": 12, "tool_call": 47, "branch": 3, "retry": 1},
        "total_tokens": {"input": 524288, "output": 4096},
        "tool_stall_total_seconds": 145.0,
        "tool_stall_pct": 0.45,
        "exit_status": "success",
        "error_message": None,
        "framework_version": {"langgraph": "0.4.x"},
        "rig_label": "h200",
        "engine": "vllm",
        "redaction": {"prompts_redacted": True, "tool_args_redacted": True},
    }


def valid_trace() -> list[dict]:
    summary = summary_event()
    summary["node_counts"] = {"model_call": 1, "tool_call": 0, "branch": 0, "retry": 0}
    summary["total_tokens"] = {"input": 8192, "output": 1024}
    return [model_node(), summary]


def error_text(errors: list[object]) -> str:
    return "\n".join(str(error) for error in errors)


def telemetry_payload() -> dict:
    return {
        "schema_version": "inferguard-telemetry/v1",
        "consent_token": "token",
        "anonymized_deployment_id": "0123456789abcdef",
        "uploaded_at": "2026-04-30T12:05:23Z",
        "payload_kind": "agent-trace-summary",
        "rig_fingerprint": {
            "gpu_model": "H200",
            "gpu_count_bucket": "8",
            "engine": "vllm",
            "engine_version_major_minor": "0.20",
        },
        "aggregates": {
            "ttft_p50_ms_bucketed": 420,
            "ttft_p99_ms_bucketed": 5500,
            "kv_pressure_p95_bucketed": 0.85,
            "prefix_cache_hit_rate_bucketed": 0.42,
            "tool_stall_pct_bucketed": 0.40,
            "node_counts": {"model_call": 12, "tool_call": 47},
            "concurrency_cliff_estimate": 32,
        },
        "dp_params": {"epsilon": 1.0, "delta": 1e-5, "mechanism": "stub", "library": "stub"},
    }


@pytest.mark.harness
def test_agent_trace_model_node_schema_accepts_locked_example() -> None:
    event = validate_agent_trace_event(model_node())
    assert event.as_dict()["model_call"]["input_tokens_source"] == "api"


@pytest.mark.harness
def test_agent_trace_summary_schema_accepts_locked_example() -> None:
    event = validate_agent_trace_event(summary_event())
    assert event.as_dict()["total_tokens"]["output"] == 4096


@pytest.mark.harness
def test_agent_trace_rejects_unknown_fields() -> None:
    data = model_node()
    data["prompt"] = "must not be invented"
    with pytest.raises(AgentTraceValidationError):
        validate_agent_trace_event(data)


@pytest.mark.harness
def test_agent_trace_requires_conditional_model_call() -> None:
    data = model_node()
    del data["model_call"]
    with pytest.raises(AgentTraceValidationError):
        validate_agent_trace_event(data)


@pytest.mark.harness
def test_agent_trace_rejects_timestamp_reversal() -> None:
    data = model_node()
    data["timestamp_end"] = 0.5
    with pytest.raises(AgentTraceValidationError):
        validate_agent_trace_event(data)


@pytest.mark.harness
def test_agent_trace_accepts_tool_and_branch_nodes() -> None:
    tool = model_node()
    tool["kind"] = "tool_call"
    tool.pop("model_call")
    tool["tool_call"] = {
        "name": "filesystem.read_file",
        "wall_time_seconds": 0.083,
        "stall_seconds": 0.003,
        "result_size_bytes": 4096,
        "result_kind": "text",
        "is_external": True,
        "is_io_bound": True,
    }
    branch = model_node()
    branch["kind"] = "branch"
    branch.pop("model_call")
    branch["branch"] = {"branch_kind": "fan_out", "siblings": ["a", "b"]}
    assert validate_agent_trace_event(tool).as_dict()["tool_call"]["result_kind"] == "text"
    assert validate_agent_trace_event(branch).as_dict()["branch"]["branch_kind"] == "fan_out"


@pytest.mark.harness
def test_telemetry_schema_accepts_locked_example() -> None:
    payload = validate_telemetry_payload(telemetry_payload())
    assert payload.as_dict()["schema_version"] == "inferguard-telemetry/v1"


@pytest.mark.harness
def test_telemetry_schema_rejects_bad_deployment_id() -> None:
    payload = telemetry_payload()
    payload["anonymized_deployment_id"] = "not-hex"
    with pytest.raises(TelemetryValidationError):
        validate_telemetry_payload(payload)


@pytest.mark.harness
def test_telemetry_schema_rejects_non_stub_unknown_mechanism() -> None:
    payload = telemetry_payload()
    payload["dp_params"]["mechanism"] = "unknown"
    with pytest.raises(TelemetryValidationError):
        validate_telemetry_payload(payload)


@pytest.mark.harness
def test_telemetry_schema_json_round_trip() -> None:
    payload = telemetry_payload()
    decoded = json.loads(json.dumps(payload))
    assert (
        validate_telemetry_payload(decoded).as_dict()["aggregates"]["node_counts"]["model_call"]
        == 12
    )


@pytest.mark.harness
def test_trace_integrity_rejects_duplicate_node_ids() -> None:
    trace = valid_trace()
    duplicate = model_node()
    duplicate["timestamp_start"] = 3.0
    duplicate["timestamp_end"] = 4.0
    trace.insert(1, duplicate)
    trace[-1]["node_counts"]["model_call"] = 2

    errors = validate_trace_integrity(trace)

    assert "duplicate node_id" in error_text(errors)


@pytest.mark.harness
def test_trace_integrity_rejects_orphan_parent_node_ids() -> None:
    trace = valid_trace()
    trace[0]["parent_node_ids"] = ["missing-parent"]

    errors = validate_trace_integrity(trace)

    assert "parent_node_id 'missing-parent'" in error_text(errors)


@pytest.mark.harness
def test_trace_integrity_rejects_mixed_trace_ids() -> None:
    trace = valid_trace()
    trace[1]["trace_id"] = "trace-2"

    errors = validate_trace_integrity(trace)

    assert "exactly one trace_id" in error_text(errors)


@pytest.mark.harness
def test_trace_integrity_accepts_valid_trace() -> None:
    assert validate_trace_integrity(valid_trace()) == []


@pytest.mark.harness
def test_trace_integrity_rejects_summary_mismatched_model_count() -> None:
    trace = valid_trace()
    trace[-1]["node_counts"]["model_call"] = 99

    errors = validate_trace_integrity(trace)

    assert "node_counts.model_call" in error_text(errors)


@pytest.mark.harness
def test_trace_integrity_rejects_non_monotonic_node_timestamps() -> None:
    trace = valid_trace()
    trace[0]["timestamp_start"] = 5.0
    trace[0]["timestamp_end"] = 4.0

    errors = validate_trace_integrity(trace)

    assert "timestamp_end must be >= timestamp_start" in error_text(errors)


@pytest.mark.harness
def test_trace_integrity_rejects_summary_completed_before_node_end() -> None:
    trace = valid_trace()
    trace[0]["timestamp_end"] = 9_999_999_999.0

    errors = validate_trace_integrity(trace)

    assert "completed_at" in error_text(errors)


@pytest.mark.harness
def test_trace_integrity_rejects_summary_not_at_end() -> None:
    trace = valid_trace()
    trace = [trace[1], trace[0]]

    errors = validate_trace_integrity(trace)

    assert "summary event must appear last" in error_text(errors)


@pytest.mark.harness
def test_trace_integrity_round_trips_canonical_valid_trace(tmp_path: Path) -> None:
    trace_path = tmp_path / "agent-trace.jsonl"
    trace_path.write_text(
        "\n".join(json.dumps(event) for event in valid_trace()) + "\n", encoding="utf-8"
    )

    decoded = [event.as_dict() for event in iter_agent_trace_jsonl(trace_path)]

    assert decoded == valid_trace()
    assert validate_trace_integrity(decoded) == []


@pytest.mark.harness
def test_trace_integrity_rejects_trace_with_no_summary_event() -> None:
    errors = validate_trace_integrity([model_node()])

    assert "summary event" in error_text(errors)


@pytest.mark.harness
def test_trace_integrity_rejects_summary_with_no_preceding_nodes() -> None:
    summary = summary_event()
    summary["node_counts"]["model_call"] = 0

    errors = validate_trace_integrity([summary])

    assert "at least one preceding node" in error_text(errors)
