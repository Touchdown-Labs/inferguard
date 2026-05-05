import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from inferguard.analyze.compare import CompareError, CompareOptions, compare_runs
from inferguard.cli import app


def test_compare_runs_emits_json_and_markdown(tmp_path: Path) -> None:
    run_a = _write_run(
        tmp_path / "vllm",
        engine="vllm",
        ttft_by_trace={"trace-1": 0.20, "trace-2": 0.22, "trace-3": 0.24},
        latency_by_trace={"trace-1": 0.40, "trace-2": 0.44, "trace-3": 0.48},
    )
    run_b = _write_run(
        tmp_path / "sglang",
        engine="sglang",
        ttft_by_trace={"trace-1": 0.10, "trace-2": 0.11, "trace-3": 0.12},
        latency_by_trace={"trace-1": 0.25, "trace-2": 0.27, "trace-3": 0.29},
    )

    report = compare_runs(
        run_a,
        run_b,
        CompareOptions(
            output_dir=tmp_path / "compare",
            label_a="vllm",
            label_b="sglang",
            cost_per_gpu_hour=10.0,
            gpus=8,
        ),
    )

    assert report["schema_version"] == "inferguard-compare/v1"
    assert report["trace_identity"]["status"] == "ok"
    assert report["workload_classes"][0]["workload_class"] == "coding-long"
    assert report["workload_classes"][0]["best_engine"] == "sglang"
    assert report["workload_classes"][0]["delta"]["p99_ttft_seconds"] < 0
    assert (tmp_path / "compare" / "compare.json").exists()
    assert "InferGuard Bench Compare Report" in (tmp_path / "compare" / "compare.md").read_text(
        encoding="utf-8"
    )


def test_compare_warns_on_low_trace_identity_overlap(tmp_path: Path) -> None:
    run_a = _write_run(
        tmp_path / "a",
        engine="vllm",
        traces=["trace-1", "trace-2"],
    )
    run_b = _write_run(
        tmp_path / "b",
        engine="sglang",
        traces=["other-1", "other-2"],
    )

    report = compare_runs(run_a, run_b, CompareOptions(output_dir=tmp_path / "compare"))

    assert report["trace_identity"]["overlap_ratio"] == 0.0
    assert report["findings"][0]["code"] == "trace_identity_overlap_low"
    assert report["findings"][0]["severity"] == "warning"


def test_compare_strict_identity_fails_on_low_overlap(tmp_path: Path) -> None:
    run_a = _write_run(tmp_path / "a", engine="vllm", traces=["trace-1"])
    run_b = _write_run(tmp_path / "b", engine="sglang", traces=["other-1"])

    with pytest.raises(CompareError, match="Trace identity overlap"):
        compare_runs(run_a, run_b, CompareOptions(output_dir=tmp_path / "compare", strict_identity=True))


def test_bench_compare_help_surfaces_options() -> None:
    result = CliRunner().invoke(app, ["bench", "compare", "--help"])

    assert result.exit_code == 0
    assert "--output-dir" in result.stdout
    assert "--strict-identity" in result.stdout


def test_bench_compare_cli_writes_artifacts(tmp_path: Path) -> None:
    run_a = _write_run(tmp_path / "vllm", engine="vllm")
    run_b = _write_run(tmp_path / "sglang", engine="sglang")

    result = CliRunner().invoke(
        app,
        [
            "bench",
            "compare",
            str(run_a),
            str(run_b),
            "--output-dir",
            str(tmp_path / "compare"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "inferguard-compare/v1"
    assert (tmp_path / "compare" / "compare.md").exists()


def _write_run(
    path: Path,
    *,
    engine: str,
    traces: list[str] | None = None,
    ttft_by_trace: dict[str, float] | None = None,
    latency_by_trace: dict[str, float] | None = None,
) -> Path:
    path.mkdir(parents=True)
    traces = traces or ["trace-1", "trace-2"]
    ttft_by_trace = ttft_by_trace or {trace: 0.10 for trace in traces}
    latency_by_trace = latency_by_trace or {trace: 0.30 for trace in traces}
    requests = [
        {
            "request_id": f"req-{trace}",
            "trace_id": trace,
            "session_id": "session-1",
            "turn_index": idx,
            "workload_class": "coding-long",
            "messages": [{"role": "user", "content": "hello"}],
            "expected_input_tokens": 16,
            "expected_output_tokens": 10,
            "prefix_group": None,
            "tool_heavy": False,
            "metadata": {},
        }
        for idx, trace in enumerate(traces)
    ]
    metrics = [
        {
            "request_id": f"req-{trace}:seq-{idx}",
            "trace_id": trace,
            "session_id": "session-1",
            "turn_index": idx,
            "workload_class": "coding-long",
            "concurrency": 1,
            "success": True,
            "start_time": float(idx),
            "end_time": float(idx) + latency_by_trace[trace],
            "latency_seconds": latency_by_trace[trace],
            "ttft_seconds": ttft_by_trace[trace],
            "input_tokens": 16,
            "output_tokens": 10,
            "input_tokens_source": "estimated",
            "output_tokens_source": "estimated",
            "tokens_per_second": 10 / latency_by_trace[trace],
            "metadata": {"phase": "measurement"},
        }
        for idx, trace in enumerate(traces)
    ]
    _write_jsonl(path / "requests.jsonl", requests)
    _write_jsonl(path / "metrics.jsonl", metrics)
    (path / "config.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-bench-config/v1",
                "run_id": f"run-{engine}",
                "command": "replay",
                "topology": {"framework": engine},
            }
        ),
        encoding="utf-8",
    )
    (path / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-bench-summary/v1",
                "run_id": f"run-{engine}",
                "command": "replay",
                "model": "model",
                "endpoint": "http://local/v1/chat/completions",
                "benchmark_mode": "replay",
                "engine": engine,
                "request_counts": {"total": len(metrics), "success": len(metrics), "failed": 0},
                "runtime_seconds": 1.0,
                "ttft_seconds": {"p99": max(ttft_by_trace.values())},
                "latency_seconds": {"p99": max(latency_by_trace.values())},
                "workloads": {
                    "coding-long": {"total": len(metrics), "success": len(metrics), "failed": 0}
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
