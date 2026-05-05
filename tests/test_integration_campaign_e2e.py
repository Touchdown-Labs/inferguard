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
RIG_PROFILES = ["h200", "b200", "gb200"]
NATIVE_ARTIFACTS = [
    "run.json",
    "config.json",
    "requests.jsonl",
    "metrics.jsonl",
    "summary.json",
    "report.md",
]
REPO_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_SCRIPT = REPO_ROOT / "scripts" / "run_isb1_campaign.sh"
SOURCE_TRACE_ROOT = REPO_ROOT / "traces" / "isb1-dsv4-agent"


@pytest.mark.integration
@pytest.mark.parametrize("rig_profile", RIG_PROFILES)
def test_run_isb1_campaign_e2e_against_multi_rig_mock(tmp_path: Path, rig_profile: str) -> None:
    trace_dir = _build_mini_trace_pack(tmp_path)
    results_root = tmp_path / f"results-{rig_profile}"
    mock = start_mock_servers(rig_profile)
    try:
        if rig_profile == "gb200":
            assert mock.decode_url is not None
            assert mock.decode_metrics_url is not None
            # v0.4 campaign wiring accepts one ENDPOINT_URL only. v0.5 should pass both
            # prefill and decode endpoints for true disaggregated GB200/Dynamo-vLLM runs.
        result = _run_campaign(tmp_path, trace_dir, results_root, rig_profile, mock.endpoint_url)
    finally:
        mock.teardown()

    assert result.returncode == 0, result.stdout + result.stderr
    _assert_campaign_outputs(results_root)


@pytest.mark.integration
def test_run_isb1_campaign_allows_one_partial_workload_failure(tmp_path: Path) -> None:
    trace_dir = _build_mini_trace_pack(tmp_path)
    results_root = tmp_path / "results-partial-failure"
    mock = start_mock_servers("h200")
    mock.simulate_failure_for_workload("kv-pressure")
    try:
        result = _run_campaign(tmp_path, trace_dir, results_root, "h200", mock.endpoint_url)
    finally:
        mock.teardown()

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "| kv-pressure | failed |" in output

    report = json.loads(
        (results_root / "inferguard_report" / "report.json").read_text(encoding="utf-8")
    )
    kv_cell_ids = {
        item["cell_id"]
        for item in report["artifact_manifest"]
        if item.get("cell_id") and "kv-pressure" in item.get("path", "")
    }
    kv_findings = [
        finding for finding in report["findings"] if finding.get("cell_id") in kv_cell_ids
    ]
    assert {finding["code"] for finding in kv_findings} & {
        "partial_run",
        "invalid_run_no_successful_requests",
    }


def _run_campaign(
    tmp_path: Path,
    trace_dir: Path,
    results_root: Path,
    rig_profile: str,
    endpoint_url: str,
) -> subprocess.CompletedProcess[str]:
    inferguard_bin = _write_inferguard_shim(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "MODEL_NAME": "mock-dsv4",
            "ENDPOINT_URL": endpoint_url,
            "RIG_LABEL": rig_profile,
            "TRACE_DIR": str(trace_dir),
            "RESULTS_ROOT": str(results_root),
            "CONCURRENCY": "1,2",
            "WARMUP_SECONDS": "1",
            "DURATION_SECONDS": "5",
            "OUTPUT_TOKENS": "32",
            "INFERGUARD_BIN": str(inferguard_bin),
            "PYTHONPATH": f"{REPO_ROOT / 'src'}:{REPO_ROOT}:{env.get('PYTHONPATH', '')}",
        }
    )
    return subprocess.run(
        [_bash_executable(), str(CAMPAIGN_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
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
    shim = tmp_path / "inferguard"
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


def _assert_campaign_outputs(results_root: Path) -> None:
    report_md = results_root / "inferguard_report" / "report.md"
    assert report_md.exists()
    assert report_md.read_text(encoding="utf-8").strip()

    for workload_class in WORKLOAD_CLASSES:
        class_dir = results_root / workload_class
        assert class_dir.is_dir(), workload_class
        for artifact in NATIVE_ARTIFACTS:
            assert (class_dir / artifact).exists(), f"{workload_class}/{artifact}"
