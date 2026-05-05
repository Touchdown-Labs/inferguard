import json
import subprocess
import sys
from pathlib import Path

import pytest

from inferguard.collect_metrics.normalize import normalize_engine_sample
from inferguard.launch_engine.lmcache import (
    LMCACHE_KV_TRANSFER_CONFIG,
    build_lmcache_vllm_command,
    lmcache_env,
    lmcache_metrics_present,
    validate_lmcache_kv_transfer_config,
)
from tests.fixtures.mock_vllm_server import start_mock_servers

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lmcache_metrics"


def test_lmcache_builder_uses_v1_connector_only() -> None:
    argv = build_lmcache_vllm_command("deepseek-ai/DeepSeek-V4-Flash")

    assert "--kv-transfer-config" in argv
    assert LMCACHE_KV_TRANSFER_CONFIG in argv
    with pytest.raises(ValueError, match="LMCacheConnectorV1"):
        validate_lmcache_kv_transfer_config('{"kv_connector":"LMCacheConnector"}')


def test_prometheus_multiproc_dir_set_before_launch(tmp_path: Path) -> None:
    multiproc_dir = tmp_path / "lmcache-prom"
    env = lmcache_env({"PROMETHEUS_MULTIPROC_DIR": str(multiproc_dir)})

    assert env["PROMETHEUS_MULTIPROC_DIR"] == str(multiproc_dir)
    assert multiproc_dir.exists()


def test_launch_engine_lmcache_records_multiproc_env_and_metrics_present(tmp_path: Path) -> None:
    server = start_mock_servers("h100", enable_lmcache=True)
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "lmcache",
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
    healthcheck = _read_json(tmp_path / "launch" / "healthcheck.json")
    assert command["env"]["PROMETHEUS_MULTIPROC_DIR"]
    assert any("LMCacheConnectorV1" in item for item in command["argv"])
    assert healthcheck["lmcache_metrics_present"] is True
    assert not healthcheck["warnings"]


def test_launch_engine_lmcache_warns_when_metrics_missing(tmp_path: Path) -> None:
    server = start_mock_servers("h100", enable_lmcache=False)
    try:
        completed = _run_launch(
            tmp_path,
            "--engine",
            "lmcache",
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
    assert healthcheck["lmcache_metrics_present"] is False
    assert any("lmcache:*" in warning for warning in healthcheck["warnings"])


def test_real_shaped_lmcache_prometheus_smoke() -> None:
    text = (FIXTURES / "with_multiproc_shim.prom").read_text(encoding="utf-8")
    parsed = normalize_engine_sample("lmcache", text)

    assert lmcache_metrics_present(text) is True
    assert parsed["groups"]["lmcache"]["connector"] == "LMCacheConnectorV1"
    assert parsed["groups"]["lmcache"]["retrieve_hit_rate"] == 0.8


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
