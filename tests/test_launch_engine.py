import json
import re
import subprocess
import sys
from pathlib import Path

from inferguard.launch_engine.vllm import build_vllm_command
from tests.fixtures.mock_sglang_server import start_mock_sglang_server
from tests.fixtures.mock_vllm_server import start_mock_servers

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"
LMCACHE_CONFIG = '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'


def test_external_validate_mock_vllm(tmp_path: Path) -> None:
    server = start_mock_servers("h100")
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "vllm",
            "--external-launch",
            "--endpoint-url",
            server.base_url,
            "--model-path",
            "mock-dsv4",
        )
    finally:
        server.teardown()

    assert completed.returncode == 0, completed.stderr
    healthcheck = _read_json(tmp_path / "launch" / "healthcheck.json")
    assert healthcheck["status"] == "external_validated"
    assert healthcheck["canary_completion"]["completion_tokens"] >= 1


def test_command_json_captures_state(tmp_path: Path) -> None:
    server = start_mock_servers("h100")
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "vllm",
            "--external-launch",
            "--endpoint-url",
            server.base_url,
            "--model-path",
            "mock-dsv4",
        )
    finally:
        server.teardown()

    assert completed.returncode == 0, completed.stderr
    command = _read_json(tmp_path / "launch" / "command.json")
    assert command["argv"][0] in {"vllm", "python"}
    assert command["env"]
    assert command["model_path"] is not None
    assert command["port"] is not None


def test_canary_failure_propagates(tmp_path: Path) -> None:
    server = start_mock_servers("h100", canary_fail=True)
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "vllm",
            "--external-launch",
            "--endpoint-url",
            server.base_url,
            "--model-path",
            "mock-dsv4",
        )
    finally:
        server.teardown()

    assert completed.returncode == 1
    healthcheck = _read_json(tmp_path / "launch" / "healthcheck.json")
    assert healthcheck["status"] == "failed"
    assert healthcheck["failure_reason"] is not None


def test_lmcache_kv_transfer_config(tmp_path: Path) -> None:
    server = start_mock_servers("h100")
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "vllm",
            "--external-launch",
            "--endpoint-url",
            server.base_url,
            "--model-path",
            "mock-dsv4",
            "--kv-transfer-config",
            LMCACHE_CONFIG,
        )
    finally:
        server.teardown()

    assert completed.returncode == 0, completed.stderr
    command = _read_json(tmp_path / "launch" / "command.json")
    assert LMCACHE_CONFIG in command["argv"]


def test_vllm_data_parallel_size_passes_through() -> None:
    argv = build_vllm_command("deepseek-ai/DeepSeek-V4-Pro", data_parallel_size=8)

    assert "--data-parallel-size" in argv
    assert argv[argv.index("--data-parallel-size") + 1] == "8"


def test_old_lmcache_connector_rejected(tmp_path: Path) -> None:
    server = start_mock_servers("h100")
    old_config = '{"kv_connector":"LMCacheConnector","kv_role":"kv_both"}'
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "vllm",
            "--external-launch",
            "--endpoint-url",
            server.base_url,
            "--model-path",
            "mock-dsv4",
            "--kv-transfer-config",
            old_config,
        )
    finally:
        server.teardown()

    assert completed.returncode != 0
    assert "LMCacheConnectorV1" in completed.stderr


def test_sglang_metrics_endpoint_after_launch(tmp_path: Path) -> None:
    server = start_mock_sglang_server()
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "sglang",
            "--external-launch",
            "--endpoint-url",
            server.base_url,
            "--model-path",
            "mock-sglang",
            "--enable-metrics",
            "--enable-cache-report",
        )
    finally:
        server.teardown()

    assert completed.returncode == 0, completed.stderr
    healthcheck = _read_json(tmp_path / "launch" / "healthcheck.json")
    assert healthcheck["metrics_endpoint_reachable"] is True


def test_sglang_no_enable_metrics_warns(tmp_path: Path) -> None:
    server = start_mock_sglang_server(no_metrics=True)
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "sglang",
            "--external-launch",
            "--endpoint-url",
            server.base_url,
            "--model-path",
            "mock-sglang",
        )
    finally:
        server.teardown()

    assert completed.returncode == 0, completed.stderr
    healthcheck = _read_json(tmp_path / "launch" / "healthcheck.json")
    command = _read_json(tmp_path / "launch" / "command.json")
    assert healthcheck["metrics_endpoint_reachable"] is False
    assert any("--enable-metrics" in warning for warning in healthcheck["warnings"])
    assert any("--enable-metrics" in warning for warning in command["warnings"])


def test_healthcheck_timeout(tmp_path: Path) -> None:
    server = start_mock_servers("h100", ready_after_seconds=999)
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "vllm",
            "--external-launch",
            "--endpoint-url",
            server.base_url,
            "--model-path",
            "mock-dsv4",
            "--healthcheck-timeout-seconds",
            "1",
        )
    finally:
        server.teardown()

    assert completed.returncode == 1
    healthcheck = _read_json(tmp_path / "launch" / "healthcheck.json")
    assert healthcheck["status"] == "failed"
    assert healthcheck["failure_reason"] == "healthcheck_timeout"


def test_engine_version_captured(tmp_path: Path) -> None:
    server = start_mock_servers("h100")
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "vllm",
            "--external-launch",
            "--endpoint-url",
            server.base_url,
            "--model-path",
            "mock-dsv4",
        )
    finally:
        server.teardown()

    assert completed.returncode == 0, completed.stderr
    engine_version = _read_json(tmp_path / "launch" / "engine_version.json")
    assert engine_version["version"] is not None
    assert engine_version["engine"] in {"vllm", "sglang"}


def test_stdout_summary_format(tmp_path: Path) -> None:
    server = start_mock_servers("h100")
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "vllm",
            "--external-launch",
            "--endpoint-url",
            server.base_url,
            "--model-path",
            "mock-dsv4",
        )
    finally:
        server.teardown()

    assert completed.returncode == 0, completed.stderr
    assert re.match(
        r"^inferguard launch-engine: engine=\w+ status=\w+ pid=\S+ port=\d+ healthcheck_ms=[\d.]+ first_token_ts=\S+\n$",
        completed.stdout,
    )


def test_external_no_log_files(tmp_path: Path) -> None:
    server = start_mock_servers("h100")
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "vllm",
            "--external-launch",
            "--endpoint-url",
            server.base_url,
            "--model-path",
            "mock-dsv4",
        )
    finally:
        server.teardown()

    assert completed.returncode == 0, completed.stderr
    launch_dir = tmp_path / "launch"
    assert not (launch_dir / "stdout.log").exists()
    assert not (launch_dir / "stderr.log").exists()
    assert (launch_dir / "command.json").exists()
    assert (launch_dir / "healthcheck.json").exists()
    assert (launch_dir / "engine_version.json").exists()


def _run_launch(output_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "launch-engine",
            "--output-dir",
            str(output_dir),
            *args,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
