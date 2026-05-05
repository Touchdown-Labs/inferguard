from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from inferguard.agentx_adapter import convert_agentx_result_to_canonical, ingest_agentx_results_dir

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agentx_results"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _csv_row_count(path: Path) -> int:
    return max(0, len(path.read_text(encoding="utf-8").splitlines()) - 1)


def test_basic_ingest(tmp_path: Path) -> None:
    source = FIXTURES / "minimal"
    artifacts = ingest_agentx_results_dir(source, output_dir=tmp_path / "job")
    rows = _read_jsonl(artifacts.request_profile_jsonl)

    assert len(rows) == _csv_row_count(source / "result.csv")
    assert artifacts.summary.request_count == len(rows)
    assert artifacts.summary.success_count == len(rows)


def test_missing_fields_marked(tmp_path: Path) -> None:
    artifacts = ingest_agentx_results_dir(FIXTURES / "full", output_dir=tmp_path / "job")
    rows = _read_jsonl(artifacts.request_profile_jsonl)

    for row in rows:
        assert row["ttft_ms"] is None
        assert row["tpot_ms"] is None
        assert row["cached_tokens"] is None
        assert row["claim_status_per_field"]["ttft_ms"] == "not_proven"
        assert row["claim_status_per_field"]["tpot_ms"] == "not_proven"
        assert row["claim_status_per_field"]["cached_tokens"] == "not_proven"
        assert row["raw_response_ref"] == str(FIXTURES / "full" / "result.csv")


def test_schema_version_locked(tmp_path: Path) -> None:
    artifacts = ingest_agentx_results_dir(FIXTURES / "full", output_dir=tmp_path / "job")
    summary = _read_json(artifacts.agentx_ingest_summary_json)

    assert summary["schema_version"] == "inferguard-bench-agentx/v1"
    assert summary["ingest_summary_schema_version"] == "inferguard-agentx-ingest-summary/v1"


def test_marker_required(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "ingest-agentx",
            "--agentx-results-dir",
            str(FIXTURES / "no_marker"),
            "--output-dir",
            str(tmp_path / "job"),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "agentx_run_metadata.json" in completed.stderr


def test_under_target_flagged(tmp_path: Path) -> None:
    artifacts = ingest_agentx_results_dir(FIXTURES / "under_target", output_dir=tmp_path / "job")
    summary = _read_json(artifacts.agentx_ingest_summary_json)

    assert summary["inputs_under_target_warning"] is True


def test_stdout_summary_format(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "ingest-agentx",
            "--agentx-results-dir",
            str(FIXTURES / "full"),
            "--output-dir",
            str(tmp_path / "job"),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert re.match(
        r"^inferguard ingest-agentx: requests=\d+ success=\d+ mapped_metrics=\d+ claim=\w+\n$",
        completed.stdout,
    )


def test_malformed_csv_emits_failed_summary_without_raise(tmp_path: Path) -> None:
    artifacts = convert_agentx_result_to_canonical(
        FIXTURES / "malformed" / "result.csv",
        {
            "output_dir": str(tmp_path / "job"),
            "job_id": "agentx-malformed",
            "engine": "vllm",
            "workload_label": "agent-chat-bad",
        },
    )
    summary = _read_json(artifacts.agentx_ingest_summary_json)

    assert summary["status"] == "ingest_failed"
    assert summary["error_type"] == "missing_required_columns"
    assert "completion_tokens" in summary["missing_required_columns"]


def test_full_fixture_smoke_outputs_canonical_artifacts(tmp_path: Path) -> None:
    artifacts = convert_agentx_result_to_canonical(
        FIXTURES / "full" / "result.csv",
        {
            "output_dir": str(tmp_path / "job"),
            "job_id": "agentx-full-smoke",
            "engine": "vllm",
            "workload_label": "agent-chat",
            "model_profile": "dsv4-agentx",
            "concurrency": 3,
        },
    )

    assert artifacts.request_profile_jsonl.exists()
    assert artifacts.requests_summary_json.exists()
    assert artifacts.agentx_ingest_summary_json.exists()
    rows = _read_jsonl(artifacts.request_profile_jsonl)
    summary = _read_json(artifacts.requests_summary_json)
    gpu_rows = _read_jsonl(artifacts.gpu_metrics_timeline_jsonl)
    engine_rows = _read_jsonl(artifacts.engine_metrics_timeline_jsonl)

    assert rows
    assert summary["schema_version"] == "inferguard-request-profile-summary/v1"
    assert all(row["schema_version"] == "inferguard-request-profile/v1" for row in rows)
    assert all(row["ttft_ms"] is None and row["tpot_ms"] is None for row in rows)
    assert all(row["claim_status_per_field"]["ttft_ms"] == "not_proven" for row in rows)
    assert gpu_rows and engine_rows
