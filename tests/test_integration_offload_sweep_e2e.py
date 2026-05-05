import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.mock_vllm_server import start_mock_servers

WORKLOAD_CLASSES = [
    "coding-long",
    "agent-chat",
    "multi-agent-coding",
    "tool-heavy",
    "session-resume",
    "prefix-reuse",
    "kv-pressure",
]
NATIVE_ARTIFACTS = [
    "run.json",
    "config.json",
    "requests.jsonl",
    "metrics.jsonl",
    "summary.json",
    "report.md",
]
REPO_ROOT = Path(__file__).resolve().parents[1]
OFFLOAD_SWEEP_SCRIPT = REPO_ROOT / "scripts" / "run_offload_sweep.sh"
SOURCE_TRACE_ROOT = REPO_ROOT / "traces" / "isb1-dsv4-agent"


@pytest.mark.integration
def test_run_offload_sweep_e2e_against_extended_mock(tmp_path: Path) -> None:
    trace_dir = _build_mini_trace_pack(tmp_path)
    results_root = tmp_path / "offload-results"
    mock = start_mock_servers(
        "h200",
        enable_lmcache=True,
        enable_dynamo_kvbm=True,
        enable_sglang_hicache=True,
    )
    try:
        for offload_label in ("offload_off", "offload_cpu_32gb"):
            result = _run_offload_sweep(
                tmp_path,
                trace_dir,
                results_root,
                offload_label,
                mock.endpoint_url,
                mock.metrics_url,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            _assert_offload_outputs(results_root / offload_label)
    finally:
        mock.teardown()

    comparison = results_root / "cross-config-comparison.md"
    assert comparison.exists()
    comparison_text = comparison.read_text(encoding="utf-8")
    assert "| offload_off |" in comparison_text
    assert "| offload_cpu_32gb |" in comparison_text


def _run_offload_sweep(
    tmp_path: Path,
    trace_dir: Path,
    results_root: Path,
    offload_label: str,
    endpoint_url: str,
    metrics_url: str,
) -> subprocess.CompletedProcess[str]:
    inferguard_bin = _write_inferguard_shim(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "MODEL_NAME": "mock-dsv4",
            "ENDPOINT_URL": endpoint_url,
            "RIG_LABEL": "h200",
            "OFFLOAD_LABEL": offload_label,
            "TRACE_DIR": str(trace_dir),
            "RESULTS_ROOT": str(results_root),
            "CONCURRENCY": "1,2",
            "WARMUP_SECONDS": "1",
            "DURATION_SECONDS": "5",
            "OUTPUT_TOKENS": "32",
            "METRICS_URL": metrics_url,
            "INFERGUARD_BIN": str(inferguard_bin),
            "PYTHONPATH": f"{REPO_ROOT / 'src'}:{REPO_ROOT}:{env.get('PYTHONPATH', '')}",
        }
    )
    return subprocess.run(
        [_bash_executable(), str(OFFLOAD_SWEEP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )


def _bash_executable() -> str:
    for candidate in (
        Path("/opt/homebrew/bin/bash"),
        Path("/usr/local/bin/bash"),
        Path("/bin/bash"),
    ):
        if candidate.exists():
            return str(candidate)
    return "bash"


def _build_mini_trace_pack(tmp_path: Path) -> Path:
    trace_dir = tmp_path / "isb1-mini"
    trace_dir.mkdir()
    for workload_class in WORKLOAD_CLASSES:
        source_path = SOURCE_TRACE_ROOT / workload_class / f"{workload_class}.jsonl"
        line = next(
            source_line
            for source_line in source_path.read_text(encoding="utf-8").splitlines()
            if source_line.strip()
        )
        class_dir = trace_dir / workload_class
        class_dir.mkdir()
        (class_dir / f"{workload_class}.jsonl").write_text(line + "\n", encoding="utf-8")
    return trace_dir


def _write_inferguard_shim(tmp_path: Path) -> Path:
    shim = tmp_path / "inferguard-offload"
    shim.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "for index, arg in enumerate(sys.argv[:-1]):\n"
        "    if arg == '--duration-seconds' and sys.argv[index + 1] == '5':\n"
        "        sys.argv[index + 1] = '0.5'\n"
        "    if arg == '--warmup-seconds' and sys.argv[index + 1] == '1':\n"
        "        sys.argv[index + 1] = '0'\n"
        "from inferguard.cli import app\n"
        "app()\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return shim


def _assert_offload_outputs(config_results_root: Path) -> None:
    report_json = config_results_root / "inferguard_report" / "report.json"
    report_md = config_results_root / "inferguard_report" / "report.md"
    assert report_json.exists()
    assert report_md.exists()
    assert report_md.read_text(encoding="utf-8").strip()

    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["run_summary"]["total_cells"] >= len(WORKLOAD_CLASSES)
    assert report["artifact_manifest"]

    for workload_class in WORKLOAD_CLASSES:
        class_dir = config_results_root / workload_class
        assert class_dir.is_dir(), workload_class
        for artifact in NATIVE_ARTIFACTS:
            assert (class_dir / artifact).exists(), f"{workload_class}/{artifact}"
