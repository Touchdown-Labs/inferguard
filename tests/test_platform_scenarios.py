import json
from pathlib import Path

from typer.testing import CliRunner

from inferguard.analyze import AnalyzeOptions, CompareOptions, analyze_results, compare_runs
from inferguard.cli import app
from inferguard.harness.daemon import Daemon


def _write_native_run(
    root: Path,
    name: str,
    *,
    metrics_rows: list[dict],
    timeline_rows: list[dict] | None = None,
    summary_extra: dict | None = None,
) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True)
    summary = {
        "schema_version": "inferguard-bench-summary/v1",
        "run_id": name,
        "command": "kvcast",
        "model": "mock-dsv4",
        "endpoint": "http://local/v1/chat/completions",
        "request_counts": {
            "total": len(metrics_rows),
            "success": len(metrics_rows),
            "failed": 0,
            "failed_rate": 0.0,
        },
        "runtime_seconds": 60.0,
        "latency_seconds": {"p99": 0.2},
        "ttft_seconds": {"p99": 0.05},
        "concurrency": [{"concurrency": 1}],
        "workloads": {
            "agent-chat": {"total": len(metrics_rows), "success": len(metrics_rows), "failed": 0}
        },
        "tokens": {},
        "limitations": [],
    }
    if summary_extra:
        summary.update(summary_extra)
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run_dir / "metrics.jsonl").write_text(
        "\n".join(json.dumps(row) for row in metrics_rows) + "\n", encoding="utf-8"
    )
    (run_dir / "requests.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    (run_dir / "config.json").write_text(
        json.dumps({"model": "mock-dsv4", "topology": {"framework": "vllm"}}), encoding="utf-8"
    )
    if timeline_rows is not None:
        (run_dir / "metrics_timeline.jsonl").write_text(
            "\n".join(json.dumps(row) for row in timeline_rows) + "\n",
            encoding="utf-8",
        )
    return run_dir


def _metric(customer: str, workload: str = "agent-chat", ttft: float = 0.1, **metadata) -> dict:
    return {
        "request_id": f"{customer}-{workload}-{ttft}",
        "session_id": f"{customer}-session",
        "turn_index": 0,
        "workload_class": workload,
        "success": True,
        "start_time": 1.0,
        "end_time": 1.0 + ttft,
        "latency_seconds": ttft + 0.1,
        "ttft_seconds": ttft,
        "input_tokens": 100,
        "output_tokens": 10,
        "customer_id": customer,
        "metadata": {"customer_id": customer, **metadata},
    }


def test_s21_daemon_and_operator_kv_by_customer(tmp_path: Path) -> None:
    daemon = Daemon()
    daemon.record_event(
        {
            "event_type": "node",
            "kind": "model_call",
            "metadata": {"customer_id": "customer-a", "kv_hbm_bytes": 4096},
            "model_call": {"ttft_seconds": 0.1, "input_tokens": 10, "output_tokens": 5},
        }
    )
    assert daemon.snapshot().kv_by_customer["customer-a"]["hbm_bytes"] > 4096
    assert (
        'inferguard_customer_kv_hbm_bytes{customer_id="customer-a"}'
        in daemon.prometheus_metrics_text()
    )

    _write_native_run(
        tmp_path,
        "s21",
        metrics_rows=[_metric("customer-a"), _metric("customer-b")],
        timeline_rows=[
            {
                "customer_kv_snapshot": {
                    "customer-a": {"hbm_bytes": 800, "share": 0.8},
                    "customer-b": {"hbm_bytes": 200, "share": 0.2},
                }
            },
            {
                "customer_kv_snapshot": {
                    "customer-a": {"hbm_bytes": 900, "share": 0.75},
                    "customer-b": {"hbm_bytes": 300, "share": 0.25},
                }
            },
        ],
    )
    analyze_results(
        tmp_path,
        AnalyzeOptions(output_dir=tmp_path / "report", output_format="both", operator_brief=True),
    )
    brief = json.loads((tmp_path / "report" / "operator_brief.json").read_text())
    assert brief["kv_by_customer"][0]["customer_id"] == "customer-a"
    report = json.loads((tmp_path / "report" / "report.json").read_text())
    assert any(f["code"] == "kv_footprint_imbalance" for f in report["findings"])


def test_s13_cost_by_customer_workload(tmp_path: Path) -> None:
    _write_native_run(
        tmp_path,
        "s13",
        metrics_rows=[
            _metric("customer-a", "agent-chat"),
            _metric("customer-a", "coding-long"),
            _metric("customer-b", "agent-chat"),
        ],
    )
    analyze_results(
        tmp_path,
        AnalyzeOptions(
            output_dir=tmp_path / "report",
            output_format="both",
            operator_brief=True,
            cost_per_gpu_hour=6.0,
            gpus=2,
        ),
    )
    brief = json.loads((tmp_path / "report" / "operator_brief.json").read_text())
    assert {row["customer_id"] for row in brief["customer_workload_cost"]} == {
        "customer-a",
        "customer-b",
    }
    assert "Cost by customer × workload" in (tmp_path / "report" / "operator_brief.md").read_text()


def test_s07_cross_customer_prefix_eviction_finding(tmp_path: Path) -> None:
    _write_native_run(
        tmp_path,
        "s07",
        metrics_rows=[
            _metric(
                "customer-b",
                cache_lineage={"cross_customer": True, "source_customer_id": "customer-a"},
                prefix_eviction_event={
                    "evicting_customer_id": "customer-b",
                    "victim_customer_id": "customer-a",
                },
            )
        ],
    )
    report = analyze_results(
        tmp_path, AnalyzeOptions(output_dir=tmp_path / "report", output_format="json")
    )
    assert any(f["code"] == "prefix_eviction_cross_customer" for f in report["findings"])


def test_s05_multi_tenant_noisy_neighbor_and_cli_flags(tmp_path: Path) -> None:
    _write_native_run(
        tmp_path,
        "s05",
        metrics_rows=[
            _metric("customer-a", ttft=0.1),
            _metric("customer-b", ttft=0.5),
            _metric("customer-b", ttft=0.6),
        ],
    )
    report = analyze_results(
        tmp_path, AnalyzeOptions(output_dir=tmp_path / "report", output_format="json")
    )
    assert any(f["code"] == "multi_tenant_noisy_neighbor" for f in report["findings"])
    help_result = CliRunner().invoke(app, ["bench", "kvcast", "--help"])
    assert "multi-tenant-storm" in help_result.stdout
    assert "--customers" in help_result.stdout


def test_s01_cold_start_ramp_finding_and_cli(tmp_path: Path) -> None:
    _write_native_run(
        tmp_path,
        "s01",
        metrics_rows=[_metric("customer-a")],
        summary_extra={
            "command": "cold-start",
            "cold_start": {
                "model_load_seconds": 12.0,
                "cudagraph_capture_seconds": 18.0,
                "first_60s_p99_ttft_seconds": 1.0,
                "steady_state_p99_ttft_seconds": 0.2,
            },
        },
    )
    analyze_results(
        tmp_path,
        AnalyzeOptions(output_dir=tmp_path / "report", output_format="both", operator_brief=True),
    )
    report = json.loads((tmp_path / "report" / "report.json").read_text())
    finding = next(f for f in report["findings"] if f["code"] == "cold_start_ramp_extended")
    assert finding["evidence"]["model_load_seconds"] == 12.0
    assert finding["evidence"]["cudagraph_capture_seconds"] == 18.0
    assert finding["evidence"]["first_60s_p99_ttft_seconds"] == 1.0
    brief = json.loads((tmp_path / "report" / "operator_brief.json").read_text())
    assert brief["cold_start_decomposition"][0]["model_load_seconds"] == 12.0
    assert "Cold-start decomposition" in (tmp_path / "report" / "operator_brief.md").read_text()
    result = CliRunner().invoke(app, ["bench", "cold-start", "--help"])
    assert result.exit_code == 0
    assert "--capture-seconds" in result.stdout


def test_s03_engine_crash_recovery_slow(tmp_path: Path) -> None:
    _write_native_run(
        tmp_path,
        "s03",
        metrics_rows=[_metric("customer-a")],
        summary_extra={
            "chaos_recovery": {
                "recovery_time_seconds": 45.0,
                "threshold_seconds": 30.0,
                "in_flight_request_loss_count": 7,
                "customer_error_signature": {"status_codes": [503], "errors": ["stream closed"]},
                "successful_retry_count_post_recovery": 5,
            }
        },
    )
    analyze_results(
        tmp_path,
        AnalyzeOptions(output_dir=tmp_path / "report", output_format="both", operator_brief=True),
    )
    report = json.loads((tmp_path / "report" / "report.json").read_text())
    finding = next(f for f in report["findings"] if f["code"] == "engine_crash_recovery_slow")
    assert finding["evidence"]["in_flight_request_loss_count"] == 7
    assert finding["evidence"]["customer_error_signature"]["status_codes"] == [503]
    assert finding["evidence"]["successful_retry_count_post_recovery"] == 5
    brief = json.loads((tmp_path / "report" / "operator_brief.json").read_text())
    assert brief["crash_recovery"][0]["in_flight_request_loss_count"] == 7
    assert "Crash recovery" in (tmp_path / "report" / "operator_brief.md").read_text()


def test_retry_storm_engine_overload_finding(tmp_path: Path) -> None:
    _write_native_run(
        tmp_path,
        "s26",
        metrics_rows=[_metric("customer-a", "tool-heavy"), _metric("customer-a", "tool-heavy")],
        timeline_rows=[
            {"disagg_snapshot": {"requests_waiting": 2, "preemptions_total": 0}},
            {"disagg_snapshot": {"requests_waiting": 64, "preemptions_total": 4}},
        ],
        summary_extra={
            "command": "kvcast",
            "kvcast_mode": "retry-storm",
            "retry_storm": {
                "mode": "retry-storm",
                "burst_multiplier": 50,
                "burst_window_seconds": 30,
                "baseline_rps": 4,
                "burst_peak_qps": 200,
                "queue_depth_max": 64,
                "recovery_seconds": 8.5,
                "preemption_count": 4,
            },
        },
    )
    analyze_results(
        tmp_path,
        AnalyzeOptions(output_dir=tmp_path / "report", output_format="both", operator_brief=True),
    )
    report = json.loads((tmp_path / "report" / "report.json").read_text())
    finding = next(f for f in report["findings"] if f["code"] == "retry_storm_engine_overload")
    assert finding["evidence"]["burst_peak_qps"] == 200
    assert finding["evidence"]["queue_depth_max"] == 64
    assert finding["evidence"]["recovery_seconds"] == 8.5
    assert finding["evidence"]["preemption_count"] == 4
    brief = json.loads((tmp_path / "report" / "operator_brief.json").read_text())
    assert brief["retry_storm"][0]["burst_multiplier"] == 50
    brief_md = (tmp_path / "report" / "operator_brief.md").read_text()
    assert "Retry storm" in brief_md
    result = CliRunner().invoke(app, ["bench", "kvcast", "--help"])
    assert result.exit_code == 0
    assert "retry-storm" in result.stdout
    assert "burst-multiplier" in result.stdout


def test_partial_gpu_degradation_finding(tmp_path: Path) -> None:
    run_dir = _write_native_run(
        tmp_path,
        "s09",
        metrics_rows=[_metric("customer-a")],
    )
    rows = []
    for timestamp in ("2026-05-03T00:00:00Z", "2026-05-03T00:00:05Z"):
        rows.extend(
            [
                {
                    "schema_version": "dcgm-correlated/v1",
                    "timestamp": timestamp,
                    "gpu_index": 0,
                    "gpu_uuid": "GPU-healthy-0",
                    "dcgm_gpu_util": 82.0,
                    "dcgm_gpu_temp": 61.0,
                    "dcgm_ecc_sbe_volatile_total": 0,
                },
                {
                    "schema_version": "dcgm-correlated/v1",
                    "timestamp": timestamp,
                    "gpu_index": 1,
                    "gpu_uuid": "GPU-healthy-1",
                    "dcgm_gpu_util": 80.0,
                    "dcgm_gpu_temp": 62.0,
                    "dcgm_ecc_sbe_volatile_total": 0,
                },
                {
                    "schema_version": "dcgm-correlated/v1",
                    "timestamp": timestamp,
                    "gpu_index": 2,
                    "gpu_uuid": "GPU-degraded-2",
                    "dcgm_gpu_util": 40.0,
                    "dcgm_gpu_temp": 63.0,
                    "dcgm_ecc_sbe_volatile_total": 0,
                },
            ]
        )
    (run_dir / "dcgm-correlated-v1.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    analyze_results(
        tmp_path,
        AnalyzeOptions(output_dir=tmp_path / "report", output_format="both", operator_brief=True),
    )
    report = json.loads((tmp_path / "report" / "report.json").read_text())
    finding = next(f for f in report["findings"] if f["code"] == "gpu_partial_degradation")
    assert finding["evidence"]["gpu_index"] == 2
    assert finding["evidence"]["gpu_uuid"] == "GPU-degraded-2"
    assert finding["evidence"]["divergence_metric"] == "sm_activity_ratio_to_cluster_median"
    brief = json.loads((tmp_path / "report" / "operator_brief.json").read_text())
    assert brief["hardware_health"][0]["gpu_uuid"] == "GPU-degraded-2"
    assert "Hardware health" in (tmp_path / "report" / "operator_brief.md").read_text()


def test_oom_giant_prefill_blast_radius_finding(tmp_path: Path) -> None:
    _write_native_run(
        tmp_path,
        "s11",
        metrics_rows=[_metric("customer-a")],
        timeline_rows=[
            {"oom_giant_prefill": {"stage": "before", "batch_state": {"completed_count": 10}}},
            {"oom_giant_prefill": {"stage": "during", "batch_state": {"in_flight_count": 4}}},
            {"oom_giant_prefill": {"stage": "after", "blast_radius": "continuous_batch_impacted"}},
        ],
        summary_extra={
            "command": "replay",
            "oom_giant_prefill": {
                "inject_giant_prefill_tokens": 800000,
                "killed_batch_count": 1,
                "killed_in_flight_count": 3,
                "engine_recovery_seconds": 12.5,
                "engine": "vllm",
                "blast_radius": "continuous_batch_impacted",
                "engine_behavior_note": "vLLM continuous batching may isolate or amplify the failure.",
            },
        },
    )
    analyze_results(
        tmp_path,
        AnalyzeOptions(output_dir=tmp_path / "report", output_format="both", operator_brief=True),
    )
    report = json.loads((tmp_path / "report" / "report.json").read_text())
    finding = next(f for f in report["findings"] if f["code"] == "oom_giant_prefill_blast_radius")
    assert finding["evidence"]["engine"] == "vllm"
    assert finding["evidence"]["killed_in_flight_count"] == 3
    brief_md = (tmp_path / "report" / "operator_brief.md").read_text()
    assert "oom_giant_prefill_blast_radius" in brief_md
    result = CliRunner().invoke(app, ["bench", "replay", "--help"])
    assert result.exit_code == 0
    assert "giant-prefill" in result.stdout
    assert "allow-chaos" in result.stdout


def test_idle_amortization_curve_finding(tmp_path: Path) -> None:
    _write_native_run(
        tmp_path,
        "s14",
        metrics_rows=[
            _metric("customer-a", "agent-chat"),
            _metric("customer-a", "agent-chat"),
            _metric("customer-b", "coding-long"),
        ],
        summary_extra={
            "command": "replay",
            "runtime_seconds": 100.0,
            "idle_active_mix": {
                "mode": "alternating_active_idle",
                "active_window_seconds": 30.0,
                "idle_window_seconds": 70.0,
                "observed_utilization": 0.30,
                "idle_fraction": 0.70,
            },
        },
    )
    analyze_results(
        tmp_path,
        AnalyzeOptions(
            output_dir=tmp_path / "report",
            output_format="both",
            operator_brief=True,
            cost_per_gpu_hour=8.0,
            gpus=1,
        ),
    )
    report = json.loads((tmp_path / "report" / "report.json").read_text())
    findings = [f for f in report["findings"] if f["code"] == "cost_idle_underutilization_high"]
    assert findings
    assert findings[0]["evidence"]["idle_amortization_penalty"] == 3.0
    brief = json.loads((tmp_path / "report" / "operator_brief.json").read_text())
    economics = brief["cost_economics"]
    assert economics["idle_amortization_penalty"] == 3.0
    assert economics["cost_per_token_by_utilization"]
    assert {row["customer_id"] for row in economics["customer_idle_amortization"]} == {
        "customer-a",
        "customer-b",
    }
    brief_md = (tmp_path / "report" / "operator_brief.md").read_text()
    assert "Cost economics" in brief_md
    assert "Idle amortization by customer" in brief_md
    result = CliRunner().invoke(app, ["bench", "replay", "--help"])
    assert result.exit_code == 0
    assert "idle-active-mix" in result.stdout
    assert "active-window" in result.stdout
    assert "idle-window" in result.stdout


def test_s79_canary_quality_regression_finding_and_cli(tmp_path: Path) -> None:
    _write_native_run(
        tmp_path,
        "s79",
        metrics_rows=[_metric("customer-a", "tool-heavy") for _ in range(12)],
        summary_extra={
            "command": "replay",
            "canary_quality": {
                "eval_set": "heldout.jsonl",
                "baseline_accuracy": 0.96,
                "canary_accuracy": 0.91,
                "accuracy_delta": 0.05,
                "eval_sample_count": 400,
                "p_value": 0.01,
            },
        },
    )
    analyze_results(
        tmp_path,
        AnalyzeOptions(output_dir=tmp_path / "report", output_format="both", operator_brief=True),
    )
    report = json.loads((tmp_path / "report" / "report.json").read_text())
    finding = next(f for f in report["findings"] if f["code"] == "canary_quality_regression")
    assert finding["evidence"]["baseline_accuracy"] == 0.96
    assert finding["evidence"]["canary_accuracy"] == 0.91
    brief = json.loads((tmp_path / "report" / "operator_brief.json").read_text())
    assert brief["quality_regression"][0]["accuracy_delta"] == 0.05
    brief_md = (tmp_path / "report" / "operator_brief.md").read_text()
    assert "Quality regression" in brief_md
    result = CliRunner().invoke(app, ["bench", "replay", "--help"])
    assert result.exit_code == 0
    assert "canary-eval-set" in result.stdout


def test_s80_blue_green_p99_regression_compare(tmp_path: Path) -> None:
    blue = _write_native_run(
        tmp_path,
        "blue",
        metrics_rows=[_metric("customer-a", "agent-chat", ttft=0.10) for _ in range(20)],
    )
    green = _write_native_run(
        tmp_path,
        "green",
        metrics_rows=[_metric("customer-a", "agent-chat", ttft=0.25) for _ in range(20)],
    )
    compare_dir = tmp_path / "compare"
    compare = compare_runs(
        blue,
        green,
        CompareOptions(
            output_dir=compare_dir,
            label_a="blue-vllm-0.20.0",
            label_b="green-vllm-0.20.1",
            blue_green=True,
        ),
    )
    finding = next(f for f in compare["findings"] if f["code"] == "blue_green_p99_regression")
    assert finding["evidence"]["metric"] == "ttft"
    assert finding["evidence"]["regression_factor"] > 1.5
    assert "Blue/green comparison" in (compare_dir / "compare.md").read_text()
    analyze_results(
        compare_dir,
        AnalyzeOptions(
            output_dir=compare_dir / "report", output_format="both", operator_brief=True
        ),
    )
    brief = json.loads((compare_dir / "report" / "operator_brief.json").read_text())
    assert brief["blue_green_comparison"][0]["stack_a_id"] == "blue-vllm-0.20.0"
    assert "Blue/green comparison" in (compare_dir / "report" / "operator_brief.md").read_text()
    result = CliRunner().invoke(app, ["bench", "compare", "--help"])
    assert result.exit_code == 0
    assert "blue-green" in result.stdout


def test_s82_tokenizer_mismatch_preflight_and_operator_brief(tmp_path: Path) -> None:
    config = {
        "model": "mock-dsv4",
        "tokenizer_mismatch": {
            "client_tokenizer": "old-tokenizer",
            "server_tokenizer": "new-tokenizer",
            "client_prompt_tokens": 100,
            "server_prompt_tokens": 108,
            "sample_text_length": 42,
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = CliRunner().invoke(
        app,
        ["preflight", "--config", str(config_path), "--detect-tokenizer-mismatch", "--json"],
    )
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    finding = next(f for f in payload["findings"] if f["code"] == "tokenizer_mismatch_silent_drift")
    assert finding["evidence"]["divergence_pct"] == 0.08
    (tmp_path / "preflight-tokenizer.json").write_text(result.stdout, encoding="utf-8")
    analyze_results(
        tmp_path,
        AnalyzeOptions(output_dir=tmp_path / "report", output_format="both", operator_brief=True),
    )
    brief = json.loads((tmp_path / "report" / "operator_brief.json").read_text())
    assert brief["tokenizer_drift"][0]["client_tokenizer"] == "old-tokenizer"
    assert "Tokenizer/config drift" in (tmp_path / "report" / "operator_brief.md").read_text()


def test_s83_prompt_template_tool_parser_regression(tmp_path: Path) -> None:
    _write_native_run(
        tmp_path,
        "s83",
        metrics_rows=[_metric("customer-a", "tool-heavy") for _ in range(10)],
        summary_extra={
            "command": "replay",
            "tool_call_schema_eval": {
                "schema_id": "chat_template_v3_tool_call",
                "baseline_compliance_rate": 0.99,
                "candidate_compliance_rate": 0.90,
                "compliance_delta": 0.09,
                "divergent_field_paths": ["$.tool_calls[0].function.arguments"],
            },
        },
    )
    analyze_results(
        tmp_path,
        AnalyzeOptions(output_dir=tmp_path / "report", output_format="both", operator_brief=True),
    )
    report = json.loads((tmp_path / "report" / "report.json").read_text())
    finding = next(
        f for f in report["findings"] if f["code"] == "prompt_template_tool_parser_regression"
    )
    assert finding["evidence"]["schema_id"] == "chat_template_v3_tool_call"
    brief = json.loads((tmp_path / "report" / "operator_brief.json").read_text())
    assert brief["output_structure"][0]["candidate_compliance_rate"] == 0.90
    brief_md = (tmp_path / "report" / "operator_brief.md").read_text()
    assert "Output structure / tool parser" in brief_md
    result = CliRunner().invoke(app, ["bench", "replay", "--help"])
    assert result.exit_code == 0
    assert "tool-call-schema" in result.stdout
