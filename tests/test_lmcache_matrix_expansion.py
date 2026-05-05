import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_lmcache_slurm_matrix.py"


def _run_matrix(tmp_path: Path, *args: str) -> dict:
    out = tmp_path / "matrix"
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--dry-run", "--results-root", str(out), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads((out / "matrix_plan.json").read_text(encoding="utf-8"))


def test_default_matrix_expands_expected_job_count(tmp_path: Path) -> None:
    plan = _run_matrix(tmp_path, "--max-jobs", "1")

    # 3 hardware × (2 baseline engines × disabled + 2 LMCache engines × 7 enabled modes)
    # × 10 workloads × 6 context lengths × 6 concurrency levels × 2 arrival modes.
    assert plan["total_jobs_before_limit"] == 34560
    assert plan["total_jobs"] == 1


def test_matrix_filter_flags_skip_gb200_and_sglang_lmcache(tmp_path: Path) -> None:
    plan = _run_matrix(
        tmp_path,
        "--skip-gb200",
        "--skip-sglang-lmcache",
        "--context-lengths",
        "8192",
        "--concurrency",
        "1",
        "--arrival-mode",
        "poisson",
    )

    assert plan["total_jobs_before_limit"] == 180
    assert {job["hardware"] for job in plan["jobs"]} == {"h200_8gpu", "b200_8gpu"}
    assert "sglang_lmcache_optional" not in {job["engine"] for job in plan["jobs"]}
    assert {job["arrival_mode"] for job in plan["jobs"]} == {"poisson"}


def test_context_and_concurrency_overrides_replace_yaml_defaults(tmp_path: Path) -> None:
    plan = _run_matrix(
        tmp_path,
        "--context-lengths",
        "8192,32768",
        "--concurrency",
        "1,4",
        "--arrival-mode",
        "closed_loop",
        "--skip-gb200",
        "--skip-sglang-lmcache",
    )

    assert plan["filters"]["context_lengths"] == [8192, 32768]
    assert plan["filters"]["concurrency"] == [1, 4]
    assert plan["filters"]["arrival_modes"] == ["closed_loop"]
    assert {job["context_length"] for job in plan["jobs"]} == {8192, 32768}
    assert {job["concurrency"] for job in plan["jobs"]} == {1, 4}
    by_engine_mode = Counter((job["engine"], job["lmcache_mode"]) for job in plan["jobs"])
    assert by_engine_mode[("vllm_baseline", "disabled")] == 80
    assert by_engine_mode[("sglang_baseline", "disabled")] == 80
    assert by_engine_mode[("vllm_lmcache", "cpu_offload")] == 80
