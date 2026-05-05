from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from inferguard.classify_failures import classify, format_stdout_summary
from inferguard.classify_failures.types import FAILURE_CLASSIFICATION_SCHEMA_VERSION

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"


def _report(path: Path) -> dict:
    return classify(path).to_dict()


def test_no_failures_clean_run() -> None:
    report = _report(FIXTURES / "run_dirs" / "live_complete")

    assert report["failures"] == []
    assert report["top_class"] == "none"
    assert report["claim_status"] == "measured"


def test_oom_classified() -> None:
    report = _report(FIXTURES / "failure_logs" / "oom")

    assert report["top_class"] == "oom_hbm_exhaustion"
    assert report["failures"][0]["confidence"] >= 0.6


def test_nccl_classified() -> None:
    report = _report(FIXTURES / "failure_logs" / "nccl")

    assert report["top_class"] == "nccl_error"


def test_rdma_inactive() -> None:
    report = _report(FIXTURES / "failure_logs" / "rdma")

    assert report["top_class"] == "rdma_inactive"


def test_healthcheck_failure() -> None:
    report = _report(FIXTURES / "run_dirs" / "failed_launch")

    assert report["top_class"] == "endpoint_healthcheck_failure"


def test_unknown_class_preserved() -> None:
    report = _report(FIXTURES / "failure_logs" / "unknown")

    assert report["failures"][0]["class"] == "not_enough_evidence"
    assert report["failures"][0]["evidence_excerpt"] != ""


def test_multi_failure_ranked() -> None:
    report = _report(FIXTURES / "failure_logs" / "oom_plus_nccl.stderr")

    assert report["failures"][0]["confidence"] >= report["failures"][1]["confidence"]


def test_schema_version_locked() -> None:
    report = _report(FIXTURES / "failure_logs" / "oom")

    assert report["schema_version"] == FAILURE_CLASSIFICATION_SCHEMA_VERSION


def test_stdout_summary_format() -> None:
    report = classify(FIXTURES / "failure_logs" / "oom")
    stdout = format_stdout_summary(report) + "\n"

    assert re.match(
        r"^inferguard classify-failures: failures=\d+ top_class=\S+ claim=\w+\n$", stdout
    )


def test_xid_evidence_attached() -> None:
    report = _report(FIXTURES / "run_dirs" / "cuda_error_with_xid")

    assert any(
        "DCGM_FI_DEV_XID_ERRORS" in str(path) for path in report["failures"][0]["evidence_paths"]
    )


def test_cli_writes_artifacts(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "classify-failures",
            "--job-dir",
            str(FIXTURES / "failure_logs" / "oom"),
            "--output-dir",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "failure_classification.json").exists()
    assert (tmp_path / "failure_classification.md").exists()
    assert re.match(
        r"^inferguard classify-failures: failures=\d+ top_class=\S+ claim=\w+\n$",
        completed.stdout,
    )
