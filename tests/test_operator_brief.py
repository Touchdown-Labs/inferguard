import json

from typer.testing import CliRunner

from inferguard.analyze import AnalyzeOptions, analyze_results
from inferguard.cli import app


def _write_agg_cell(root, name, conc, p99_ttft, successes=10, total=10, cost=None):
    cell_dir = root / "cells" / name
    cell_dir.mkdir(parents=True)
    payload = {
        "cell_id": name,
        "hw": "b200",
        "model": "deepseek-v4",
        "framework": "vllm",
        "precision": "fp4",
        "scenario_type": "agent-chat",
        "conc": conc,
        "num_requests_total": total,
        "num_requests_successful": successes,
        "p99_ttft": p99_ttft,
        "output_tput_tps": 100 * conc,
    }
    (cell_dir / f"agg_{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    if cost is not None:
        # Analyze derives cost from duration/gpus/cost flags; use duration to shape ordering.
        payload["duration_seconds"] = cost


def test_operator_brief_emits_required_keys_and_cliffs(tmp_path) -> None:
    _write_agg_cell(tmp_path, "c1", 1, 0.10)
    _write_agg_cell(tmp_path, "c2", 2, 0.15)
    _write_agg_cell(tmp_path, "c4", 4, 0.25)
    _write_agg_cell(tmp_path, "c8", 8, 0.30, successes=9, total=10)
    timeline_dir = tmp_path / "cells" / "c4"
    (timeline_dir / "metrics_timeline.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-metrics-timeline/v1",
                "observed_at": "2026-05-01T12:00:00Z",
                "sequence": 7,
                "disagg_snapshot": {"gpu_cache_usage": 0.97, "preemptions_total": 0},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = analyze_results(
        tmp_path,
        AnalyzeOptions(
            output_dir=tmp_path / "inferguard_report", output_format="both", operator_brief=True
        ),
    )

    brief_path = tmp_path / "inferguard_report" / "operator_brief.json"
    md_path = tmp_path / "inferguard_report" / "operator_brief.md"
    assert brief_path.exists()
    assert md_path.exists()
    brief = json.loads(brief_path.read_text())
    assert brief["schema_version"] == "inferguard-operator-brief/v1"
    assert brief["best_stable_config"][0]["cell_id"] == "c2"
    assert brief["cliff_detection"]["ttft_p99"][0]["cell_id"] == "c4"
    assert brief["cliff_detection"]["failure"][0]["cell_id"] == "c8"
    assert any(
        item["status"] == "observed" and item["cell_id"] == "c4"
        for item in brief["cliff_detection"]["oom"]
    )
    assert "recommended_engine_config" in brief
    assert "raw_artifact_paths" in brief
    assert any(path.endswith("report.json") for path in brief["raw_artifact_paths"])
    assert any(item["kind"] == "inferguard_operator_brief" for item in report["artifact_manifest"])


def test_hma_preflight_finding_appears_in_operator_brief(tmp_path) -> None:
    run_dir = tmp_path / "native"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-bench-summary/v1",
                "run_id": "hma-native",
                "command": "replay",
                "model": "deepseek-ai/DeepSeek-V4-Pro",
                "endpoint": "http://local/v1/chat/completions",
                "request_counts": {"total": 1, "success": 1, "failed": 0, "failed_rate": 0.0},
                "runtime_seconds": 1.0,
                "latency_seconds": {"p99": 0.2},
                "ttft_seconds": {"p99": 0.05},
                "concurrency": [{"concurrency": 1}],
                "workloads": {},
                "tokens": {},
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "requests.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "model": "deepseek-ai/DeepSeek-V4-Pro",
                "topology": {"framework": "vllm", "offloading": "cpu"},
            }
        ),
        encoding="utf-8",
    )

    report = analyze_results(
        tmp_path,
        AnalyzeOptions(
            output_dir=tmp_path / "inferguard_report", output_format="both", operator_brief=True
        ),
    )

    assert any(f["code"] == "hma_offload_incompatible" for f in report["findings"])
    brief = json.loads((tmp_path / "inferguard_report" / "operator_brief.json").read_text())
    assert brief["operator_findings"][0]["code"] == "hma_offload_incompatible"
    assert (
        "hma_offload_incompatible"
        in (tmp_path / "inferguard_report" / "operator_brief.md").read_text()
    )


def test_operator_brief_defaults_on_when_gpus_cli_flag_is_provided(tmp_path) -> None:
    _write_agg_cell(tmp_path, "c1", 1, 0.10)

    result = CliRunner().invoke(app, ["analyze", str(tmp_path), "--format", "json", "--gpus", "8"])

    assert result.exit_code == 0
    assert (tmp_path / "inferguard_report" / "operator_brief.json").exists()
    report = json.loads((tmp_path / "inferguard_report" / "report.json").read_text())
    assert report["cells"][0]["metrics"]["num_gpus"] == 8


def test_operator_brief_cost_comparison_table(tmp_path) -> None:
    run_dir = tmp_path / "workloads" / "vllm" / "coding-long" / "native"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-bench-summary/v1",
                "run_id": "cost-native",
                "command": "replay",
                "model": "mock-dsv4",
                "endpoint": "http://local/v1/chat/completions",
                "request_counts": {"total": 2, "success": 2, "failed": 0, "failed_rate": 0.0},
                "runtime_seconds": 1800.0,
                "latency_seconds": {"p99": 0.2},
                "ttft_seconds": {"p99": 0.05},
                "concurrency": [{"concurrency": 1}],
                "workloads": {"coding-long": {"total": 2, "success": 2, "failed": 0}},
                "tokens": {},
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"session_id": "s1", "turn_index": 0, "success": True}),
                json.dumps({"session_id": "s2", "turn_index": 0, "success": True}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "requests.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "run.json").write_text("{}\n", encoding="utf-8")
    (run_dir / "config.json").write_text(
        json.dumps(
            {"model": "mock-dsv4", "topology": {"framework": "vllm", "cache_mode": "native"}}
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            str(tmp_path),
            "--operator-brief",
            "--cost-per-gpu-hour",
            "8",
            "--gpus",
            "4",
        ],
    )

    assert result.exit_code == 0
    brief = json.loads((tmp_path / "inferguard_report" / "operator_brief.json").read_text())
    row = brief["cost_comparison"][0]
    assert row["engine"] == "vllm"
    assert row["cache_mode"] == "native"
    assert row["gpus"] == 4
    assert row["gpu_hour_cost"] == 8
    assert row["completed_sessions"] == 2
    assert row["cost_per_completed_session"] == 8.0
    md = (tmp_path / "inferguard_report" / "operator_brief.md").read_text()
    assert "Cache-mode cost comparison" in md
    assert "Cost per completed session" in md
