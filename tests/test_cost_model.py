from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from inferguard.cost_model import compute_cost
from inferguard.cost_model.types import COST_REPORT_SCHEMA_VERSION

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
RUN_DIRS = FIXTURES / "run_dirs"
COST_INPUTS = FIXTURES / "cost_inputs"


def copy_fixture(tmp_path: Path, name: str) -> Path:
    src = RUN_DIRS / name
    dst = tmp_path / name
    shutil.copytree(src, dst)
    return dst


def run_cli(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *map(str, args)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_basic_cost(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")

    report = compute_cost(
        root,
        COST_INPUTS / "gmi_b200_per_hour.json",
        slo_ttft_ms=500,
        slo_e2e_ms=5000,
    ).to_dict()

    assert report["cost_per_million_completion_tokens_usd"] > 0
    assert report["claim_status"] == "measured"


def test_zero_useful_tasks(tmp_path: Path) -> None:
    root = write_run_dir(
        tmp_path / "all_failures",
        [
            request_row(
                "r1", success=False, completion_tokens=0, ttft_ms=None, e2e_latency_ms=2000
            ),
            request_row(
                "r2", success=False, completion_tokens=0, ttft_ms=None, e2e_latency_ms=2500
            ),
        ],
        concurrency=1,
        success_count=0,
        duration_seconds=12,
    )

    report = compute_cost(
        root,
        COST_INPUTS / "h200_4usd.json",
        slo_ttft_ms=500,
        slo_e2e_ms=5000,
    ).to_dict()

    assert report["cost_per_useful_task_usd"] is None
    assert report["claim_status"] in {"not_proven", "inferred"}


def test_waste_percent(tmp_path: Path) -> None:
    root = write_run_dir(
        tmp_path / "partial_failures",
        [
            request_row("r1", success=True, completion_tokens=64, ttft_ms=100, e2e_latency_ms=1000),
            request_row(
                "r2", success=False, completion_tokens=0, ttft_ms=None, e2e_latency_ms=2000
            ),
        ],
        concurrency=1,
        success_count=1,
        duration_seconds=10,
    )

    report = compute_cost(
        root,
        COST_INPUTS / "h200_4usd.json",
        slo_ttft_ms=500,
        slo_e2e_ms=5000,
    ).to_dict()

    assert report["failed_request_waste_percent"] >= 0
    assert report["failed_request_waste_percent"] <= 100
    assert report["failed_request_waste_dollars"] >= 0


def test_missing_cost_input(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")

    completed = run_cli("compute-cost", "--results-root", root)

    assert completed.returncode == 2


def test_truncated_cost_input_downgrades_without_crash(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    cost_input = tmp_path / "truncated_cost.json"
    cost_input.write_text('{"H200": {"usd_per_gpu_hour": ', encoding="utf-8")

    report = compute_cost(root, cost_input).to_dict()

    assert report["claim_status"] == "not_proven"
    assert report["safe_concurrency_envelope"]["claim_status"] == "not_proven"


def test_measured_cost_requires_live_complete_validation(tmp_path: Path) -> None:
    root = write_run_dir(
        tmp_path / "no_validation",
        [request_row("r1", success=True, completion_tokens=64, ttft_ms=100, e2e_latency_ms=1000)],
        concurrency=1,
        success_count=1,
        duration_seconds=10,
    )

    report = compute_cost(
        root,
        COST_INPUTS / "h200_4usd.json",
        slo_ttft_ms=500,
        slo_e2e_ms=5000,
    ).to_dict()

    assert report["claim_status"] == "inferred"
    assert report["claim_reason"].startswith("validation_report.status is not live_complete")
    assert all(job["claim_status"] == "inferred" for job in report["per_job"])


def test_prompt_decode_separated(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")

    report = compute_cost(
        root,
        COST_INPUTS / "gmi_b200_per_hour.json",
        slo_ttft_ms=500,
        slo_e2e_ms=5000,
    ).to_dict()

    assert report["cost_per_million_prompt_tokens_usd"] is not None
    assert report["cost_per_million_completion_tokens_usd"] is not None
    assert "cost_per_million_tokens_usd" not in report


def test_schema_version_locked(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")

    report = compute_cost(
        root,
        COST_INPUTS / "gmi_b200_per_hour.json",
        slo_ttft_ms=500,
        slo_e2e_ms=5000,
    ).to_dict()

    assert report["schema_version"] == COST_REPORT_SCHEMA_VERSION == "inferguard-cost/v1"


def test_stdout_summary_format(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")

    completed = run_cli(
        "compute-cost",
        "--results-root",
        root,
        "--cost-input",
        COST_INPUTS / "gmi_b200_per_hour.json",
        "--slo-ttft-ms",
        "500",
        "--slo-e2e-ms",
        "5000",
    )

    assert completed.returncode == 0, completed.stderr
    assert re.match(
        r"^inferguard compute-cost: cost_per_m_completion_usd=[\d.]+ "
        r"cost_per_useful_task_usd=\S+ safe_concurrency=\S+ claim=\w+\n$",
        completed.stdout,
    )


def test_safe_concurrency_requires_ttft_and_e2e_slos(tmp_path: Path) -> None:
    root = write_sweep_run_dir(tmp_path / "sweep")

    report = compute_cost(root, COST_INPUTS / "h200_4usd.json", slo_ttft_ms=500).to_dict()
    envelope = report["safe_concurrency_envelope"]

    assert envelope["safe_concurrency"] is None
    assert envelope["claim_status"] == "not_proven"
    assert "both p99 TTFT and p99 E2E" in envelope["reason"]


def test_safe_concurrency_largest_level_under_slos(tmp_path: Path) -> None:
    root = write_sweep_run_dir(tmp_path / "sweep")

    report = compute_cost(
        root,
        COST_INPUTS / "h200_4usd.json",
        slo_ttft_ms=500,
        slo_e2e_ms=5000,
        slo_success_rate=0.95,
    ).to_dict()

    assert report["safe_concurrency_envelope"]["safe_concurrency"] == 2
    assert report["safe_concurrency_envelope"]["claim_status"] == "measured"


def test_report_completed_cost_notes_with_input(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete_with_artifacts")

    completed = run_cli(
        "report-completed",
        "--results-root",
        root,
        "--cost-input",
        COST_INPUTS / "gmi_b200_per_hour.json",
        "--slo-ttft-ms",
        "500",
        "--slo-e2e-ms",
        "5000",
        "--useful-task-min-tokens",
        "32",
    )

    assert completed.returncode == 0, completed.stderr
    rec = json.loads((root / "report" / "operator_recommendation.json").read_text(encoding="utf-8"))
    cost_notes = rec["cost_notes"]
    assert cost_notes["claim_status"] == "measured"
    assert cost_notes["cost_per_useful_task"] is not None
    assert cost_notes["cost_per_million_prompt_tokens"] is not None
    assert cost_notes["cost_per_million_generated_tokens"] is not None
    assert cost_notes["gpu_hour_normalized_throughput"] is not None
    assert cost_notes["safe_concurrency_envelope"]["safe_concurrency"] == 8


def test_report_completed_without_cost_input_refuses_fields(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete_with_artifacts")

    completed = run_cli(
        "report-completed",
        "--results-root",
        root,
        "--slo-ttft-ms",
        "500",
        "--slo-e2e-ms",
        "5000",
    )

    assert completed.returncode == 0, completed.stderr
    rec = json.loads((root / "report" / "operator_recommendation.json").read_text(encoding="utf-8"))
    cost_notes = rec["cost_notes"]
    reason = "not_proven — cost input not supplied"
    assert cost_notes["cost_per_million_completion_tokens_usd"] is None
    assert cost_notes["cost_per_useful_task"] is None
    assert cost_notes["claim_status"] == "not_proven"
    assert cost_notes["claim_status_by_field"]["cost_per_useful_task"] == reason


def write_sweep_run_dir(root: Path) -> Path:
    jobs = []
    for concurrency, ttft_ms, e2e_ms, success_rate in (
        (1, 100, 1000, 1.0),
        (2, 200, 2000, 0.98),
        (4, 600, 3000, 1.0),
    ):
        job_id = f"job-h200-c{concurrency}"
        jobs.append(
            {"job_id": job_id, "output_dir": f"jobs/{job_id}", "sku": "H200", "engine": "vllm"}
        )
        rows = [
            request_row(
                f"{job_id}-r{i}",
                success=i < round(success_rate * 10),
                completion_tokens=64,
                ttft_ms=ttft_ms,
                e2e_latency_ms=e2e_ms,
                concurrency=concurrency,
            )
            for i in range(10)
        ]
        write_job(
            root,
            job_id,
            rows,
            concurrency=concurrency,
            success_count=sum(1 for row in rows if row["success"]),
        )
    root.mkdir(parents=True, exist_ok=True)
    (root / "matrix_plan.json").write_text(
        json.dumps({"jobs": jobs, "schema_version": "inferguard-gmi-profile-summary/v1"}, indent=2),
        encoding="utf-8",
    )
    write_validation_report(root)
    return root


def write_run_dir(
    root: Path,
    rows: list[dict[str, Any]],
    *,
    concurrency: int,
    success_count: int,
    duration_seconds: float,
) -> Path:
    job_id = "job-h200-vllm"
    root.mkdir(parents=True, exist_ok=True)
    (root / "matrix_plan.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "job_id": job_id,
                        "output_dir": f"jobs/{job_id}",
                        "sku": "H200",
                        "engine": "vllm",
                    }
                ],
                "schema_version": "inferguard-gmi-profile-summary/v1",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_job(
        root,
        job_id,
        rows,
        concurrency=concurrency,
        success_count=success_count,
        duration_seconds=duration_seconds,
    )
    return root


def write_validation_report(root: Path, status: str = "live_complete") -> None:
    (root / "validation_report.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-validation-report/v1",
                "status": status,
                "jobs": [{"job_id": "job-h200-vllm", "status": status, "claim_status": "measured"}],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def write_job(
    root: Path,
    job_id: str,
    rows: list[dict[str, Any]],
    *,
    concurrency: int,
    success_count: int,
    duration_seconds: float = 10.0,
) -> None:
    job_dir = root / "jobs" / job_id
    request_dir = job_dir / "request_profile"
    metrics_dir = job_dir / "metrics"
    request_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "operator_profile.json").write_text(
        json.dumps({"sku": "H200", "gpu_count": 1, "engine": "vllm"}, indent=2),
        encoding="utf-8",
    )
    (request_dir / "requests_profile.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    successful = [row for row in rows if row["success"]]
    summary = {
        "schema_version": "inferguard-request-profile-summary/v1",
        "job_id": job_id,
        "workload_label": "cost-model-test",
        "engine": "vllm",
        "concurrency": concurrency,
        "request_count": len(rows),
        "success_count": success_count,
        "failure_count": max(len(rows) - success_count, 0),
        "success_rate": success_count / len(rows) if rows else 0,
        "duration_seconds": duration_seconds,
        "prompt_tokens_total": sum(int(row.get("prompt_tokens") or 0) for row in rows),
        "completion_tokens_total": sum(
            int(row.get("completion_tokens") or 0) for row in successful
        ),
        "ttft_ms": {
            "p50": percentile(successful, "ttft_ms", 50),
            "p95": percentile(successful, "ttft_ms", 95),
            "p99": percentile(successful, "ttft_ms", 99),
        },
        "e2e_latency_ms": {
            "p50": percentile(successful, "e2e_latency_ms", 50),
            "p95": percentile(successful, "e2e_latency_ms", 95),
            "p99": percentile(successful, "e2e_latency_ms", 99),
        },
        "claim_status": "measured",
    }
    (request_dir / "requests_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (metrics_dir / "metrics_summary.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-metrics-summary/v1",
                "duration_seconds": duration_seconds,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def request_row(
    request_id: str,
    *,
    success: bool,
    completion_tokens: int,
    ttft_ms: float | None,
    e2e_latency_ms: float,
    concurrency: int = 1,
) -> dict[str, Any]:
    return {
        "schema_version": "inferguard-request-profile/v1",
        "request_id": request_id,
        "job_id": "job-h200-vllm",
        "workload_label": "cost-model-test",
        "engine": "vllm",
        "concurrency": concurrency,
        "prompt_tokens": 128,
        "completion_tokens": completion_tokens,
        "ttft_ms": ttft_ms,
        "e2e_latency_ms": e2e_latency_ms,
        "success": success,
        "claim_status": "measured",
    }


def percentile(rows: list[dict[str, Any]], key: str, pct: int) -> float | None:
    values = sorted(float(row[key]) for row in rows if row.get(key) is not None)
    if not values:
        return None
    idx = min(len(values) - 1, max(0, round((pct / 100) * (len(values) - 1))))
    return values[idx]
