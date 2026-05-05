import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from inferguard.find_cliffs import find_cliffs
from inferguard.find_cliffs.types import CAPACITY_CLIFF_NAMES, CAPACITY_CLIFFS_SCHEMA_VERSION

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sweep_dirs"


def copy_fixture(
    tmp_path: Path, name: str, *, validation_status: str | None = "live_complete"
) -> Path:
    src = FIXTURES / name
    dst = tmp_path / name
    shutil.copytree(src, dst)
    if validation_status is not None:
        (dst / "validation_report.json").write_text(
            json.dumps(
                {
                    "schema_version": "inferguard-validation-report/v1",
                    "status": validation_status,
                    "jobs": [
                        {
                            "job_id": path.name,
                            "status": validation_status,
                            "claim_status": "measured",
                        }
                        for path in sorted((dst / "jobs").iterdir())
                        if path.is_dir()
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return dst


def capacity(root: Path) -> dict:
    return find_cliffs(root).to_dict()


def cliff(data: dict, name: str) -> dict:
    return next(item for item in data["cliffs"] if item["name"] == name)


def run_find_cliffs(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "find-cliffs",
            "--results-root",
            str(root),
            *extra,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_no_cliff_observed(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "no_cliff")
    data = capacity(root)

    assert data["summary"]["max_concurrency"] is None
    target = cliff(data, "max_concurrency_before_p99_cliff")
    assert target["claim_status"] == "not_proven"
    assert target["value"] is None


def test_p99_cliff_detected(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "concurrency_p99_sweep")
    data = capacity(root)

    assert data["summary"]["max_concurrency"] == 8
    target = cliff(data, "max_concurrency_before_p99_cliff")
    assert target["claim_status"] == "measured"
    assert target["evidence_paths"]


def test_measured_cliffs_require_live_complete_validation(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "concurrency_p99_sweep", validation_status=None)
    data = capacity(root)

    assert data["claim_status"] == "inferred"
    assert data["claim_reason"].startswith("validation_report.status is not live_complete")
    assert cliff(data, "max_concurrency_before_p99_cliff")["claim_status"] == "inferred"


def test_oom_cliff(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "context_oom_sweep")
    data = capacity(root)

    assert data["summary"]["max_concurrency"] == 16
    target = cliff(data, "max_concurrency_before_p99_cliff")
    assert "oom" in target["reasoning"].lower()
    context = cliff(data, "max_context_before_oom")
    assert context["claim_status"] == "measured"
    assert data["summary"]["max_context"] == 65536


def test_two_point_sweep_insufficient(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "two_points")
    data = capacity(root)

    assert all(item["claim_status"] == "not_proven" for item in data["cliffs"])


def test_kv_saturation_threshold(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "kv_saturation_sweep")
    data = capacity(root)

    assert data["summary"]["kv_saturation_concurrency"] is not None
    target = cliff(data, "kv_saturation_point")
    assert target["claim_status"] == "measured"
    assert target["value"] == 4


def test_truncated_job_json_downgrades_without_crash(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "concurrency_p99_sweep")
    (root / "jobs" / "cell-c8" / "request_profile" / "requests_summary.json").write_text(
        '{"request_count": 8, "ttft_ms": [',
        encoding="utf-8",
    )

    data = capacity(root)

    assert data["schema_version"] == CAPACITY_CLIFFS_SCHEMA_VERSION
    assert all(item["claim_status"] in {"measured", "not_proven"} for item in data["cliffs"])


def test_schema_version_locked(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "concurrency_p99_sweep")
    completed = run_find_cliffs(root)

    assert completed.returncode == 0, completed.stderr
    data = json.loads((root / "capacity_cliffs.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == CAPACITY_CLIFFS_SCHEMA_VERSION


def test_stdout_summary_format(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "concurrency_p99_sweep")
    completed = run_find_cliffs(root)

    assert completed.returncode == 0, completed.stderr
    assert re.match(
        r"^inferguard find-cliffs: cliffs_found=\d+ max_concurrency=\S+ max_context=\S+ claim=\w+\n$",
        completed.stdout,
    )


def test_supporting_curve_present(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "context_oom_sweep")
    data = capacity(root)

    assert all(
        len(item["supporting_curve"]) >= 2
        for item in data["cliffs"]
        if item["claim_status"] == "measured"
    )


def test_six_locked_cliffs_exactly(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "concurrency_p99_sweep")
    data = capacity(root)

    assert tuple(item["name"] for item in data["cliffs"]) == CAPACITY_CLIFF_NAMES


def test_queue_explosion_point(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "queue_explosion_sweep")
    data = capacity(root)

    assert data["summary"]["queue_explosion_concurrency"] == 8
    assert cliff(data, "queue_explosion_point")["claim_status"] == "measured"


def test_decode_collapse_point(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "decode_collapse_sweep")
    data = capacity(root)

    assert data["summary"]["decode_collapse_concurrency"] == 4
    assert cliff(data, "decode_collapse_point")["claim_status"] == "measured"


def test_throughput_plateau(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "throughput_plateau_sweep")
    data = capacity(root)

    assert data["summary"]["throughput_plateau_tokens_per_sec"] is not None
    assert cliff(data, "throughput_plateau")["claim_status"] == "measured"


def test_incomplete_sweep_partial_not_proven(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "incomplete_sweep")
    data = capacity(root)

    assert all(item["claim_status"] == "not_proven" for item in data["cliffs"])
    assert all("not_enough_evidence" in item["reasoning"] for item in data["cliffs"])
