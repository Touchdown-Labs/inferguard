import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_lmcache_slurm_matrix.py"


def test_expected_artifact_contract_includes_slurm_layer_outputs_and_reports(
    tmp_path: Path,
) -> None:
    out = tmp_path / "matrix"
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--dry-run", "--results-root", str(out), "--max-jobs", "2"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    contract = json.loads((out / "expected_artifact_contract.json").read_text(encoding="utf-8"))

    assert contract["schema_version"] == "inferguard-lmcache-slurm-artifact-contract/v1"
    assert "matrix_plan.json" in contract["matrix_level"]
    assert "expected_artifact_contract.json" in contract["matrix_level"]
    assert "sbatch/*.sbatch" in contract["matrix_level"]
    assert len(contract["per_job"]) == 2
    expected = "\n".join(contract["per_job"][0]["expected_paths"])
    for required in (
        "slurm-%j.out",
        "slurm-%j.err",
        "logs/job_stdout.log",
        "logs/job_stderr.log",
        "slurm_metadata.env",
        "topology.json",
        "repo_sha.txt",
        "component_versions.json",
        "raw/nvidia_smi.txt",
        "raw/nvidia_smi_topo.txt",
        "raw/ibv_devinfo.txt",
        "raw/nccl_smoke.txt",
        "logs/server.log",
        "inferguard_bench/summary.json",
        "inferguard_bench/metrics.jsonl",
        "inferguard_bench/requests.jsonl",
        "inferguard_bench/config.json",
    ):
        assert required in expected
    assert "inferred_without_engine_metrics" in contract["claim_boundary"]
