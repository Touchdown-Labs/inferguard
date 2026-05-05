import asyncio
import json
from pathlib import Path

import pytest

from inferguard.analyze import AnalyzeOptions, analyze_results
from inferguard.bench.runner import BenchConfig, run_replay
from tests.fixtures.mock_vllm_server import start_mock_servers

RIG_PROFILES = ["h100", "h200", "b200", "b300", "gb200"]
NATIVE_ARTIFACTS = [
    "run.json",
    "config.json",
    "requests.jsonl",
    "metrics.jsonl",
    "metrics_timeline.jsonl",
    "summary.json",
    "report.md",
]


@pytest.mark.integration
@pytest.mark.parametrize("rig_profile", RIG_PROFILES)
def test_mock_vllm_replay_and_analyze_e2e(tmp_path: Path, rig_profile: str) -> None:
    trace_dir = _write_mini_trace_dir(tmp_path)
    run_dir = tmp_path / f"bench-{rig_profile}"
    report_dir = tmp_path / f"inferguard-report-{rig_profile}"
    mock = start_mock_servers(rig_profile)
    try:
        if rig_profile == "gb200":
            assert mock.decode_url is not None
            assert mock.decode_metrics_url is not None

        asyncio.run(
            run_replay(
                BenchConfig(
                    command="replay",
                    endpoint=mock.endpoint_url,
                    model="mock-dsv4",
                    trace_dir=trace_dir,
                    concurrency_levels=[1, 2],
                    output_dir=run_dir,
                    output_tokens=64,
                    metrics_url=mock.metrics_url,
                    metrics_interval_seconds=0.01,
                    metrics_engine="vllm",
                    timeout_seconds=10,
                )
            )
        )
    finally:
        mock.teardown()

    for artifact in NATIVE_ARTIFACTS:
        assert (run_dir / artifact).exists(), artifact

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["request_counts"]["success"] >= 1
    assert summary["metrics_timeline_present"] is True

    metrics = _read_jsonl(run_dir / "metrics.jsonl")
    assert any(row["kv_pressure_label"] == "measured" for row in metrics)

    timeline = _read_jsonl(run_dir / "metrics_timeline.jsonl")
    cache_usage = [
        row["disagg_snapshot"].get("kv_cache_usage")
        for row in timeline
        if row.get("disagg_snapshot", {}).get("kv_cache_usage") is not None
    ]
    assert cache_usage
    assert max(cache_usage) > min(cache_usage)

    report = analyze_results(
        run_dir,
        AnalyzeOptions(
            output_dir=report_dir,
            output_format="json",
            cost_per_gpu_hour=4.50,
            gpus=8,
        ),
    )
    report_json = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report == report_json
    assert report_json["run_summary"]["cost"]["cost_per_completed_session"] > 0


def _write_mini_trace_dir(tmp_path: Path) -> Path:
    trace_dir = tmp_path / "isb1-mini"
    trace_dir.mkdir()
    records = [
        {
            "trace_id": "coding-long-1",
            "session_id": "coding-session-1",
            "turn_index": 0,
            "workload_class": "coding-long",
            "messages": [
                {"role": "system", "content": "You are a deterministic coding assistant."},
                {
                    "role": "user",
                    "content": "coding-long workload: explain how to reduce KV cache pressure.",
                },
            ],
            "expected_input_tokens": 64,
            "expected_output_tokens": 64,
            "prefix_group": "repo-a",
            "tool_heavy": False,
            "metadata": {"rig_test": True},
        },
        {
            "trace_id": "coding-long-2",
            "session_id": "coding-session-2",
            "turn_index": 0,
            "workload_class": "coding-long",
            "messages": [
                {"role": "system", "content": "You are a deterministic coding assistant."},
                {
                    "role": "user",
                    "content": "coding-long workload: summarize prefix reuse and batch sizing tradeoffs.",
                },
            ],
            "expected_input_tokens": 80,
            "expected_output_tokens": 64,
            "prefix_group": "repo-b",
            "tool_heavy": False,
            "metadata": {"rig_test": True},
        },
    ]
    path = trace_dir / "coding-long.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return trace_dir


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
