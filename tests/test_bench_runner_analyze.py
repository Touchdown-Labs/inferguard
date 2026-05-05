import asyncio
import json
import time

import pytest

from inferguard.analyze import AnalyzeError, AnalyzeOptions, analyze_results
from inferguard.bench.client import ChatResult
from inferguard.bench.runner import BenchConfig, run_replay
from inferguard.disagg.types import DisaggSnapshot, EndpointId


class FakeClient:
    def __init__(self, endpoint: str, *, model: str, timeout: float = 300.0) -> None:
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout

    async def stream_chat(self, http, *, messages, output_tokens, metadata=None):
        return ChatResult(
            success=True,
            start_time=1.0,
            end_time=1.25,
            latency_seconds=0.25,
            ttft_seconds=0.05,
            output_text="ok",
            input_tokens=12,
            output_tokens=2,
            input_tokens_source="estimated",
            output_tokens_source="estimated",
            status_code=200,
        )


class SlowFakeClient(FakeClient):
    async def stream_chat(self, http, *, messages, output_tokens, metadata=None):
        start = time.perf_counter()
        await asyncio.sleep(0.05)
        end = time.perf_counter()
        return ChatResult(
            success=True,
            start_time=start,
            end_time=end,
            latency_seconds=end - start,
            ttft_seconds=0.01,
            output_text="ok",
            input_tokens=12,
            output_tokens=2,
            input_tokens_source="estimated",
            output_tokens_source="estimated",
            status_code=200,
        )


async def _replay_writes_native_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("inferguard.bench.runner.OpenAIStreamingChatClient", FakeClient)
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    (trace_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "trace_id": "trace-1",
                "session_id": "session-1",
                "turn_index": 0,
                "workload_class": "coding-long",
                "messages": [{"role": "user", "content": "hello"}],
                "expected_input_tokens": 8,
                "expected_output_tokens": 4,
                "prefix_group": "repo-a",
                "tool_heavy": False,
                "metadata": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"

    result = await run_replay(
        BenchConfig(
            command="replay",
            endpoint="http://local/v1/chat/completions",
            model="test-model",
            trace_dir=trace_dir,
            concurrency_levels=[1, 2],
            output_dir=out,
            output_tokens=4,
        )
    )

    assert result["summary"]["schema_version"] == "inferguard-bench-summary/v1"
    for name in ["run.json", "config.json", "requests.jsonl", "metrics.jsonl", "summary.json", "report.md"]:
        assert (out / name).exists()
    metrics = [json.loads(line) for line in (out / "metrics.jsonl").read_text().splitlines()]
    assert {row["concurrency"] for row in metrics} == {1, 2}
    assert metrics[0]["input_tokens_source"] == "estimated"
    assert not (out / "metrics_timeline.jsonl").exists()
    summary = json.loads((out / "summary.json").read_text())
    assert summary["metrics_timeline_present"] is False


def test_replay_writes_native_artifacts(monkeypatch, tmp_path) -> None:
    asyncio.run(_replay_writes_native_artifacts(monkeypatch, tmp_path))


async def _replay_writes_metrics_timeline(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("inferguard.bench.runner.OpenAIStreamingChatClient", SlowFakeClient)

    async def fake_scrape(url, role, engine, client):
        return DisaggSnapshot(
            endpoint=EndpointId(url=url, role=role, engine=engine or "vllm"),
            scraped_at=time.time(),
            kv_cache_usage=0.42,
            prefix_cache_hits=3,
            prefix_cache_queries=4,
        )

    monkeypatch.setattr("inferguard.bench.runner.scrape", fake_scrape)
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    (trace_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "trace_id": "trace-metrics",
                "session_id": "session-metrics",
                "turn_index": 0,
                "workload_class": "kv-pressure",
                "messages": [{"role": "user", "content": "hello"}],
                "expected_input_tokens": 8,
                "expected_output_tokens": 4,
                "metadata": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out-metrics"

    await run_replay(
        BenchConfig(
            command="replay",
            endpoint="http://local/v1/chat/completions",
            model="test-model",
            trace_dir=trace_dir,
            concurrency_levels=[1],
            output_dir=out,
            output_tokens=4,
            metrics_url="http://local:8000/metrics",
            metrics_interval_seconds=0.01,
            metrics_engine="vllm",
        )
    )

    timeline = [json.loads(line) for line in (out / "metrics_timeline.jsonl").read_text().splitlines()]
    assert len(timeline) >= 1
    assert timeline[0]["schema_version"] == "inferguard-metrics-timeline/v1"
    assert timeline[0]["disagg_snapshot"]["kv_cache_usage"] == 0.42
    assert timeline[0]["disagg_snapshot"]["prefix_cache_hits"] == 3
    assert timeline[0]["disagg_snapshot"]["prefix_cache_queries"] == 4
    summary = json.loads((out / "summary.json").read_text())
    assert summary["metrics_timeline_present"] is True
    metrics = [json.loads(line) for line in (out / "metrics.jsonl").read_text().splitlines()]
    assert any(row["kv_pressure_label"] == "measured" for row in metrics)


def test_replay_writes_metrics_timeline(monkeypatch, tmp_path) -> None:
    asyncio.run(_replay_writes_metrics_timeline(monkeypatch, tmp_path))


def test_analyzer_reads_native_bench_output(tmp_path) -> None:
    run_dir = tmp_path / "native"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-bench-summary/v1",
                "run_id": "replay-test",
                "command": "replay",
                "model": "test-model",
                "endpoint": "http://local/v1/chat/completions",
                "request_counts": {"total": 2, "success": 2, "failed": 0, "failed_rate": 0.0},
                "runtime_seconds": 1.0,
                "latency_seconds": {"p50": 0.2, "p95": 0.3, "p99": 0.3},
                "ttft_seconds": {"p50": 0.05, "p95": 0.06, "p99": 0.06},
                "average_tokens_per_second": 10.0,
                "throughput_req_per_second": 2.0,
                "output_tokens_per_second_wall": 4.0,
                "tokens": {
                    "input_total": 20,
                    "output_total": 4,
                    "estimated_input_tokens": 20,
                    "estimated_output_tokens": 4,
                },
                "concurrency": [{"concurrency": 1}],
                "workloads": {"coding": {"total": 2, "success": 2, "failed": 0}},
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "requests.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    (run_dir / "config.json").write_text("{}\n", encoding="utf-8")
    (run_dir / "metrics_timeline.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-metrics-timeline/v1",
                "observed_at": "2026-05-01T12:00:00Z",
                "sequence": 0,
                "disagg_snapshot": {"prefix_cache_hits": 6, "prefix_cache_queries": 8},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = analyze_results(tmp_path, AnalyzeOptions(output_dir=tmp_path / "report", output_format="json"))

    assert report["cells"][0]["source_format"] == "inferguard-bench-native"
    assert report["cells"][0]["metrics"]["p99_ttft"] == 0.06
    assert report["cells"][0]["completion"]["num_requests_successful"] == 2
    assert report["cells"][0]["metrics"]["server_gpu_cache_hit_rate"] == 0.75


def test_analyzer_strict_flags_missing_native_companions(tmp_path) -> None:
    run_dir = tmp_path / "native"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-bench-summary/v1",
                "run_id": "replay-missing",
                "command": "replay",
                "model": "test-model",
                "endpoint": "http://local/v1/chat/completions",
                "request_counts": {"total": 1, "success": 1, "failed": 0, "failed_rate": 0.0},
                "runtime_seconds": 1.0,
                "latency_seconds": {"p50": 0.2, "p95": 0.2, "p99": 0.2},
                "ttft_seconds": {"p50": 0.05, "p95": 0.05, "p99": 0.05},
                "tokens": {},
                "concurrency": [],
                "workloads": {},
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AnalyzeError, match="strict mode failed"):
        analyze_results(
            tmp_path,
            AnalyzeOptions(output_dir=tmp_path / "report", output_format="json", strict=True),
        )


async def _replay_redacts_request_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("inferguard.bench.runner.OpenAIStreamingChatClient", FakeClient)
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    (trace_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "trace_id": "trace-redact",
                "session_id": "session-redact",
                "turn_index": 0,
                "workload_class": "coding-long",
                "messages": [{"role": "user", "content": "secret customer prompt"}],
                "expected_input_tokens": 8,
                "expected_output_tokens": 4,
                "metadata": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out-redacted"

    await run_replay(
        BenchConfig(
            command="replay",
            endpoint="http://local/v1/chat/completions",
            model="test-model",
            trace_dir=trace_dir,
            concurrency_levels=[1],
            output_dir=out,
            output_tokens=4,
            redact_prompts=True,
        )
    )

    request_artifact = json.loads((out / "requests.jsonl").read_text().splitlines()[0])
    assert request_artifact["messages"][0]["content"] == "<redacted>"
    assert "secret customer prompt" not in (out / "requests.jsonl").read_text()
    summary = json.loads((out / "summary.json").read_text())
    assert summary["redact_prompts"] is True


def test_replay_redacts_request_artifacts(monkeypatch, tmp_path) -> None:
    asyncio.run(_replay_redacts_request_artifacts(monkeypatch, tmp_path))
