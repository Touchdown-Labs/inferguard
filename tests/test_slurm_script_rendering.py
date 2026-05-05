import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_lmcache_slurm_matrix.py"
SLURM_DIR = REPO_ROOT / "scripts" / "slurm"


def test_slurm_scripts_parse_with_bash_n() -> None:
    scripts = sorted(SLURM_DIR.glob("*.sh")) + sorted(SLURM_DIR.glob("*.sbatch"))
    assert len(scripts) >= 7
    for script in scripts:
        completed = subprocess.run(["bash", "-n", str(script)], text=True, capture_output=True, check=False)
        assert completed.returncode == 0, f"{script}: {completed.stderr}"


def test_matrix_runner_renders_sbatch_without_unexpanded_required_variables(tmp_path: Path) -> None:
    out = tmp_path / "matrix"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--dry-run",
            "--results-root",
            str(out),
            "--max-jobs",
            "4",
            "--context-lengths",
            "8192",
            "--concurrency",
            "1",
            "--arrival-mode",
            "closed_loop",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    plan = json.loads((out / "matrix_plan.json").read_text(encoding="utf-8"))
    assert plan["total_jobs"] == 4
    sbatch_files = sorted((out / "sbatch").glob("*.sbatch"))
    assert len(sbatch_files) == 4
    for path in sbatch_files:
        text = path.read_text(encoding="utf-8")
        assert "${LMCACHE_SLURM_PARTITION" not in text
        assert "${LMCACHE_SLURM_ACCOUNT" not in text
        assert "export LMCACHE_MODEL_PATH=" in text
        assert "submit_lmcache_kv_stress.sbatch" in text
        completed = subprocess.run(["bash", "-n", str(path)], text=True, capture_output=True, check=False)
        assert completed.returncode == 0, f"{path}: {completed.stderr}"
