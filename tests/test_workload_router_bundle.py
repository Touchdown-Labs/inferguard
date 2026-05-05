import json

from typer.testing import CliRunner

from inferguard.cli import app


def test_workload_analyze_router_classify_and_emit_bundle(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    records = []
    for index in range(4):
        records.append(
            {
                "trace_id": f"trace-{index}",
                "session_id": "session-a",
                "workload_class": "coding-long",
                "messages": [
                    {"role": "system", "content": "You are a coding assistant with repo context."},
                    {"role": "user", "content": "document alpha " * 2000},
                ],
                "expected_input_tokens": 40000,
                "expected_output_tokens": 512,
                "rag_chunks": ["a", "b", "c", "d"],
            }
        )
    (logs / "requests.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )

    fingerprint_path = tmp_path / "fingerprint.json"
    result = CliRunner().invoke(
        app,
        [
            "workload",
            "analyze",
            str(logs),
            "--emit",
            str(fingerprint_path),
            "--privacy-class",
            "private",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    assert fingerprint["schema_version"] == "inferguard-workload-fingerprint/v1"
    assert fingerprint["sample_count"] == 4
    assert fingerprint["cacheability_score"] > 0.5
    assert fingerprint["input_token_distribution"]["p95"] == 40000

    run_dir = tmp_path / "run"
    cell_dir = run_dir / "native"
    cell_dir.mkdir(parents=True)
    (cell_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-bench-summary/v1",
                "run_id": "router-test",
                "command": "replay",
                "model": "deepseek-v4",
                "endpoint": "http://local/v1/chat/completions",
                "request_counts": {"total": 4, "success": 4, "failed": 0, "failed_rate": 0.0},
                "runtime_seconds": 10.0,
                "latency_seconds": {"p50": 1.0, "p95": 2.0, "p99": 2.5},
                "ttft_seconds": {"p50": 0.5, "p95": 1.0, "p99": 1.4},
                "average_tokens_per_second": 10.0,
                "throughput_req_per_second": 0.4,
                "output_tokens_per_second_wall": 20.0,
                "tokens": {"input_total": 160000, "output_total": 2048},
                "concurrency": [{"concurrency": 4}],
                "workloads": {"coding-long": {"total": 4, "success": 4, "failed": 0}},
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    for name in ("metrics.jsonl", "requests.jsonl", "run.json", "config.json"):
        (cell_dir / name).write_text("{}\n", encoding="utf-8")

    verdict_path = tmp_path / "verdict.json"
    result = CliRunner().invoke(
        app,
        [
            "router",
            "classify",
            str(run_dir),
            "--workload-fingerprint",
            str(fingerprint_path),
            "--hardware-fleet",
            "b200,gb200",
            "--emit",
            str(verdict_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert verdict["schema_version"] == "inferguard-router-verdict/v1"
    assert verdict["bottleneck_class"] == "kv_bound"
    assert verdict["execution_paths"][0]["target"] == "self_hosted_vllm"
    assert verdict["claim_label"] == "measured_local"

    bundle_dir = tmp_path / "bundle"
    result = CliRunner().invoke(
        app,
        [
            "emit-bundle",
            str(verdict_path),
            "--output",
            str(bundle_dir),
            "--target",
            "slurm",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads(result.stdout)
    assert manifest["schema_version"] == "inferguard-deployment-bundle/v1"
    assert (bundle_dir / "slurm" / "run_recommended_path.sbatch").exists()
    assert (bundle_dir / "prometheus-rules.yaml").exists()
    assert (bundle_dir / "cost-floor.csv").exists()
    assert (bundle_dir / "RUNBOOK.md").exists()
    assert (
        json.loads((bundle_dir / "meta.json").read_text(encoding="utf-8"))["bottleneck_class"]
        == "kv_bound"
    )


def test_router_classify_quality_regression_prefers_frontier_api(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "report.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-analyze/v1.1",
                "cells": [{"cell_id": "canary", "source_format": "inferguard-bench-native"}],
                "findings": [
                    {
                        "code": "canary_quality_regression",
                        "severity": "critical",
                        "message": "candidate quality regressed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["router", "classify", str(run_dir), "--json"])

    assert result.exit_code == 0, result.output
    verdict = json.loads(result.stdout)
    assert verdict["bottleneck_class"] == "quality_bound"
    assert verdict["execution_paths"][0]["target"] == "openai_api"
