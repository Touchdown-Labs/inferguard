import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_agentx_slurm_matrix.py"


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


def test_agentx_matrix_expands_gmi_hardware_and_contract(tmp_path: Path) -> None:
    plan = _run_matrix(
        tmp_path,
        "--context-buckets",
        "8192",
        "--concurrency",
        "1",
        "--cache-modes",
        "engine_prefix_cache",
        "--tenant-modes",
        "single_tenant",
    )

    assert plan["schema_version"] == "inferguard-agentx-slurm-matrix/v1"
    assert plan["total_jobs_before_limit"] == 5
    assert {job["hardware"] for job in plan["jobs"]} == {
        "b200_8gpu",
        "b300_8gpu",
        "gb200_nvl72",
    }
    assert {job["engine"] for job in plan["jobs"]} == {
        "dynamo_vllm_agentx",
        "sglang_agentx",
        "vllm_agentx",
    }
    assert {job["trace_source"] for job in plan["jobs"]} == {
        "semianalysisai/cc-traces-weka-042026"
    }

    contract = json.loads(
        (tmp_path / "matrix" / "expected_artifact_contract.json").read_text(encoding="utf-8")
    )
    assert contract["schema_version"] == "inferguard-agentx-slurm-artifact-contract/v1"
    assert "AgentX/WEKA claims require live" in contract["claim_boundary"]


def test_agentx_matrix_renders_sbatch_with_inferguard_bridge(tmp_path: Path) -> None:
    plan = _run_matrix(
        tmp_path,
        "--skip-gb200",
        "--context-buckets",
        "8192",
        "--concurrency",
        "1",
        "--cache-modes",
        "engine_prefix_cache",
        "--tenant-modes",
        "single_tenant",
    )
    assert plan["total_jobs"] == 4

    sbatch_files = sorted((tmp_path / "matrix" / "sbatch").glob("*.sbatch"))
    assert len(sbatch_files) == 4
    text = sbatch_files[0].read_text(encoding="utf-8")
    assert "export AGENTX_TRACE_SOURCE=semianalysisai/cc-traces-weka-042026" in text
    assert "submit_agentx_trace_replay.sbatch" in text
    assert "export AGENTX_MODEL=" in text
    completed = subprocess.run(["bash", "-n", str(sbatch_files[0])], text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
