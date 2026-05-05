import json

from typer.testing import CliRunner

from inferguard.cli import app


def _write_native_bench_fixture(root):
    run_dir = root / "native"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-bench-summary/v1",
                "run_id": "replay-cost",
                "command": "replay",
                "model": "test-model",
                "endpoint": "http://local/v1/chat/completions",
                "request_counts": {"total": 3, "success": 3, "failed": 0, "failed_rate": 0.0},
                "runtime_seconds": 100.0,
                "latency_seconds": {"p50": 0.2, "p95": 0.3, "p99": 0.3},
                "ttft_seconds": {"p50": 0.05, "p95": 0.06, "p99": 0.06},
                "average_tokens_per_second": 10.0,
                "throughput_req_per_second": 0.03,
                "output_tokens_per_second_wall": 20.0,
                "tokens": {
                    "input_total": 1_000_000,
                    "output_total": 2_000_000,
                    "estimated_input_tokens": 1_000_000,
                    "estimated_output_tokens": 2_000_000,
                },
                "concurrency": [{"concurrency": 1}],
                "workloads": {"coding": {"total": 3, "success": 3, "failed": 0}},
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    rows = [
        {"session_id": "s1", "turn_index": 0, "success": True},
        {"session_id": "s1", "turn_index": 1, "success": True},
        {"session_id": "s2", "turn_index": 0, "success": True},
    ]
    (run_dir / "metrics.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    (run_dir / "requests.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    (run_dir / "config.json").write_text("{}\n", encoding="utf-8")
    return run_dir


def test_analyze_no_artifacts_exits_3(tmp_path) -> None:
    result = CliRunner().invoke(app, ["analyze", str(tmp_path)])

    assert result.exit_code == 3
    assert "no supported benchmark artifacts" in result.stderr


def test_analyze_valid_agg_json_produces_report(tmp_path) -> None:
    cell_dir = tmp_path / "rigs" / "h200" / "cell-a"
    cell_dir.mkdir(parents=True)
    (cell_dir / "agg_cell.json").write_text(
        json.dumps(
            {
                "cell_id": "h200-fp8-c16",
                "hw": "h200",
                "model": "deepseek-v4",
                "infmax_model_prefix": "deepseek",
                "framework": "vllm",
                "precision": "fp8",
                "image": "registry.example/inferencex:v1",
                "disagg": True,
                "isl": 8192,
                "osl": 1024,
                "conc": 16,
                "num_requests_total": 10,
                "num_requests_successful": 10,
                "output_tput_tps": 123.4,
                "p50_ttft": 0.12,
                "p90_ttft": 0.32,
                "p95_ttft": 0.37,
                "p99_ttft": 0.42,
                "p50_tpot": 0.01,
                "p90_tpot": 0.02,
                "p95_tpot": 0.03,
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["analyze", str(tmp_path), "--format", "json", "--json"])

    assert result.exit_code == 0
    report = json.loads((tmp_path / "inferguard_report" / "report.json").read_text())
    assert report["schema_version"] == "inferguard-analyze/v1.1"
    assert report["run_summary"]["total_cells"] == 1
    assert report["cells"][0]["cell_id"] == "h200-fp8-c16"
    assert report["cells"][0]["infmax_model_prefix"] == "deepseek"
    assert report["cells"][0]["image"] == "registry.example/inferencex:v1"
    assert report["cells"][0]["disagg"] is True
    assert report["cells"][0]["metrics"]["output_tput_tps"] == 123.4
    assert report["cells"][0]["metrics"]["p50_ttft"] == 0.12
    assert report["cells"][0]["metrics"]["p90_ttft"] == 0.32
    assert report["cells"][0]["metrics"]["p95_ttft"] == 0.37
    assert report["cells"][0]["metrics"]["p50_tpot"] == 0.01
    assert report["cells"][0]["metrics"]["p90_tpot"] == 0.02
    assert report["cells"][0]["metrics"]["p95_tpot"] == 0.03
    assert json.loads(result.stdout)["schema_version"] == "inferguard-analyze/v1.1"


def test_analyze_agentx_csv_produces_cells(tmp_path) -> None:
    cell_dir = tmp_path / "agentx" / "cell-b"
    cell_dir.mkdir(parents=True)
    (cell_dir / "detailed_results.csv").write_text(
        "success,request_start_time,request_complete_time,ttft,ttlt,itl,input_tokens,output_tokens_expected,output_tokens_actual,cache_hit_blocks,cache_miss_blocks\n"
        "true,0,2,0.10,2.0,0.02,100,64,50,8,2\n"
        "true,1,3,0.20,2.0,0.03,100,64,50,7,3\n",
        encoding="utf-8",
    )
    (cell_dir / "metrics_server_metrics.csv").write_text(
        "prefix_cache_hits,prefix_cache_queries,kv_offload_bytes_gpu_to_cpu,kv_offload_bytes_cpu_to_gpu,prompt_tokens_total,generation_tokens_total,request_success_total\n"
        "15,20,0,0,200,100,2\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["analyze", str(tmp_path), "--format", "json"])

    assert result.exit_code == 0
    report = json.loads((tmp_path / "inferguard_report" / "report.json").read_text())
    cell = report["cells"][0]
    assert cell["source_format"] == "agentx-trace-replay"
    assert cell["completion"]["num_requests_successful"] == 2
    assert cell["metrics"]["p99_ttft"] == 0.199
    assert cell["metrics"]["input_tokens"] == 200
    assert cell["metrics"]["output_tokens_expected"] == 128
    assert cell["metrics"]["server_gpu_cache_hit_rate"] == 0.75
    assert cell["metrics"]["prompt_tokens_total"] == 200
    assert cell["metrics"]["generation_tokens_total"] == 100
    assert cell["metrics"]["request_success_total"] == 2


def test_analyze_timeline_finding_is_included_and_markdown_written(tmp_path) -> None:
    cell_dir = tmp_path / "gb200" / "recipe"
    cell_dir.mkdir(parents=True)
    (cell_dir / "agg_recipe.json").write_text(
        json.dumps(
            {
                "cell_id": "gb200-recipe",
                "hw": "gb200",
                "num_requests_total": 1,
                "num_requests_successful": 1,
            }
        ),
        encoding="utf-8",
    )
    (cell_dir / "inferguard_timeline.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-timeline/v1",
                "observed_at": "2026-04-29T22:01:30Z",
                "sequence": 0,
                "capabilities": {
                    "diagnosis": "on",
                    "actuation": "off",
                    "replay": "off",
                    "recall": "off",
                },
                "disagg_status": {
                    "schema_version": "disagg-status/v1",
                    "prefill": {},
                    "decode": {},
                    "findings": [
                        {
                            "code": "prefill_decode_imbalance",
                            "severity": "warning",
                            "message": "prefill and decode queues diverged",
                            "evidence": {"prefill_queue": 8},
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app, ["analyze", str(tmp_path), "--format", "both", "--fail-on", "never"]
    )

    assert result.exit_code == 0
    report = json.loads((tmp_path / "inferguard_report" / "report.json").read_text())
    assert (tmp_path / "inferguard_report" / "report.md").exists()
    assert any(f["code"] == "prefill_decode_imbalance" for f in report["findings"])
    assert report["cells"][0]["timeline"]["sample_count"] == 1


def test_analyze_fail_on_critical_exits_2(tmp_path) -> None:
    cell_dir = tmp_path / "bad-cell"
    cell_dir.mkdir()
    (cell_dir / "agg_bad.json").write_text(
        json.dumps({"cell_id": "bad-cell", "num_requests_total": 5, "num_requests_successful": 0}),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app, ["analyze", str(tmp_path), "--format", "json", "--fail-on", "critical"]
    )

    assert result.exit_code == 2
    report = json.loads((tmp_path / "inferguard_report" / "report.json").read_text())
    assert any(f["code"] == "invalid_run_no_successful_requests" for f in report["findings"])


def test_analyze_native_cost_flags_add_cost_block(tmp_path) -> None:
    _write_native_bench_fixture(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            str(tmp_path),
            "--format",
            "both",
            "--cost-per-gpu-hour",
            "4.50",
            "--gpus",
            "8",
        ],
    )

    assert result.exit_code == 0
    report = json.loads((tmp_path / "inferguard_report" / "report.json").read_text())
    cost = report["cells"][0]["cost"]
    assert cost["schema_version"] == "inferguard-cost/v1"
    assert cost["currency"] == "USD"
    assert cost["completed_sessions"] == 2
    assert cost["completed_requests"] == 3
    assert cost["completion_basis"] == "session-based"
    assert cost["gpu_hours"] == 100.0 * 8 / 3600
    assert cost["compute_cost"] == 1.0
    assert cost["cost_per_completed_session"] == 0.5
    assert cost["cost_per_completed_request"] == 1.0 / 3
    assert cost["cost_per_million_input_tokens"] == 1.0
    assert cost["cost_per_million_output_tokens"] == 0.5
    assert report["run_summary"]["cost"]["compute_cost"] == 1.0
    report_md = (tmp_path / "inferguard_report" / "report.md").read_text()
    assert "Campaign cost: USD 1.0000" in report_md
    assert "#### Cost" in report_md


def test_analyze_without_cost_flags_omits_cost_block(tmp_path) -> None:
    _write_native_bench_fixture(tmp_path)

    result = CliRunner().invoke(app, ["analyze", str(tmp_path), "--format", "json"])

    assert result.exit_code == 0
    report = json.loads((tmp_path / "inferguard_report" / "report.json").read_text())
    assert "cost" not in report["cells"][0]
    assert "cost" not in report["run_summary"]
