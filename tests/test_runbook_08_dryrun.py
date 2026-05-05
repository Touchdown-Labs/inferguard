import os
import subprocess
import sys
import zipfile
from pathlib import Path


def test_runbook_08_dryrun_script_emits_packet(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    results_root = tmp_path / "runbook08-dryrun"
    env = {
        **os.environ,
        "PYTHON_BIN": sys.executable,
        "INFERGUARD_BIN": f"{sys.executable} -m inferguard.cli",
        "RESULTS_ROOT": str(results_root),
        "RUN_ID": "pytest-runbook-08-dryrun",
    }

    completed = subprocess.run(
        [str(repo_root / "scripts" / "dryrun_runbook_08.sh")],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=int(os.environ.get("INFERGUARD_RUNBOOK_DRYRUN_TEST_TIMEOUT", "180")),
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (results_root / "inferguard_report" / "report.json").exists()
    assert (results_root / "inferguard_report" / "operator_brief.md").exists()
    assert (
        results_root / "compare" / "vllm-coding-long-native-vs-lmcache" / "compare.json"
    ).exists()
    packet_index = results_root / "packets" / "packet_index.csv"
    assert packet_index.exists()
    packets = sorted((results_root / "packets").glob("private-repro_*.zip"))
    assert packets
    with zipfile.ZipFile(packets[0]) as zf:
        names = set(zf.namelist())
    assert "manifest.json" in names
    assert "README.md" in names
    assert any(name.endswith("operator_brief.md") for name in names)
