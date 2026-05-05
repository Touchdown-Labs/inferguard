import json

import pytest

from inferguard.bench.workloads import generate_kv_stress_specs, load_trace_dir
from inferguard.schemas.trace import TraceRecord, TraceValidationError


def _valid_record() -> dict:
    return {
        "trace_id": "trace-1",
        "session_id": "session-1",
        "turn_index": 0,
        "workload_class": "coding-long",
        "messages": [{"role": "user", "content": "hello"}],
        "expected_input_tokens": 8,
        "expected_output_tokens": 4,
        "prefix_group": "repo-a",
        "tool_heavy": False,
        "metadata": {"source": "test"},
    }


def test_trace_record_validates_and_round_trips() -> None:
    record = TraceRecord.from_dict(_valid_record())

    assert record.trace_id == "trace-1"
    assert record.workload_class == "coding-long"
    assert record.as_dict()["metadata"]["source"] == "test"


def test_trace_record_rejects_unknown_workload_class() -> None:
    raw = _valid_record()
    raw["workload_class"] = "unknown"

    with pytest.raises(TraceValidationError, match="workload_class must be one of"):
        TraceRecord.from_dict(raw)


def test_trace_record_requires_chat_messages() -> None:
    raw = _valid_record()
    raw["messages"] = [{"role": "bogus", "content": "x"}]

    with pytest.raises(TraceValidationError, match="role is invalid"):
        TraceRecord.from_dict(raw)


def test_load_trace_dir_loads_flat_jsonl(tmp_path) -> None:
    (tmp_path / "flat.jsonl").write_text(json.dumps(_valid_record()) + "\n", encoding="utf-8")

    specs = load_trace_dir(tmp_path)

    assert [spec.trace_id for spec in specs] == ["trace-1"]
    assert specs[0].workload_class == "coding-long"


def test_load_trace_dir_loads_nested_jsonl(tmp_path) -> None:
    workload_dir = tmp_path / "coding-long"
    workload_dir.mkdir()
    record = _valid_record()
    record["trace_id"] = "nested-trace"
    (workload_dir / "foo.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")

    specs = load_trace_dir(tmp_path)

    assert [spec.trace_id for spec in specs] == ["nested-trace"]
    assert specs[0].workload_class == "coding-long"


def test_kvcast_cold_pressure_generates_unique_contexts() -> None:
    specs = generate_kv_stress_specs(
        context_lengths=[128], output_tokens=8, requests_per_level=3, mode="cold-pressure"
    )

    contents = [spec.messages[-1]["content"] for spec in specs]
    assert len(set(contents)) == 3
    assert {spec.workload_class for spec in specs} == {"kv-pressure"}
    assert all(spec.prefix_group is None for spec in specs)
    assert all(spec.metadata["cache_mode"] == "cold" for spec in specs)


def test_kvcast_prefix_reuse_shares_prefix_group() -> None:
    specs = generate_kv_stress_specs(
        context_lengths=[128], output_tokens=8, requests_per_level=3, mode="prefix-reuse"
    )

    assert {spec.workload_class for spec in specs} == {"prefix-reuse"}
    assert len({spec.prefix_group for spec in specs}) == 1
    assert all(spec.metadata["cache_mode"] == "prefix_reuse" for spec in specs)


def test_kvcast_mixed_agent_includes_multiple_workload_classes() -> None:
    specs = generate_kv_stress_specs(
        context_lengths=[128], output_tokens=8, requests_per_level=10, mode="mixed-agent"
    )

    assert {spec.workload_class for spec in specs} >= {
        "prefix-reuse",
        "kv-pressure",
        "session-resume",
        "tool-heavy",
    }
