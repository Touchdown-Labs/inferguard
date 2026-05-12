import json
import subprocess
import sys
from pathlib import Path

import pytest

from inferguard.launch_engine.sglang import (
    DEFAULT_SGLANG_CHUNKED_PREFILL_SIZE,
    build_sglang_command,
    sglang_launch_warnings,
)
from tests.fixtures.mock_sglang_server import start_mock_sglang_server

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"


def test_sglang_defaults_enable_cache_report() -> None:
    argv = build_sglang_command("deepseek-ai/DeepSeek-V4-Flash")

    assert "--enable-cache-report" in argv


def test_sglang_lmcache_and_kv_events_flags_are_source_backed() -> None:
    config = '{"publisher": "zmq", "topic": "kv-events"}'
    argv = build_sglang_command(
        "Qwen/Qwen3-8B",
        host="0.0.0.0",
        port=30000,
        enable_lmcache=True,
        kv_events_config=config,
    )

    assert argv[:7] == [
        "python",
        "-m",
        "sglang.launch_server",
        "--model-path",
        "Qwen/Qwen3-8B",
        "--host",
    ]
    assert argv[argv.index("--host") + 1] == "0.0.0.0"
    assert argv[argv.index("--port") + 1] == "30000"
    assert "--enable-lmcache" in argv
    assert argv[argv.index("--kv-events-config") + 1] == config


def test_b200_fp8_chunked_prefill_always_explicit() -> None:
    argv = build_sglang_command(
        "deepseek-ai/DeepSeek-V4-Pro",
        hardware="B200",
        quantization="fp8",
    )

    assert argv[argv.index("--chunked-prefill-size") + 1] == str(
        DEFAULT_SGLANG_CHUNKED_PREFILL_SIZE
    )
    assert "--quantization" in argv
    warnings = sglang_launch_warnings(hardware="B200", quantization="fp8")
    assert warnings
    assert "--chunked-prefill-size" in warnings[0]


def test_b200_fp8_cannot_disable_chunked_prefill() -> None:
    with pytest.raises(ValueError, match="chunked prefill"):
        build_sglang_command(
            "deepseek-ai/DeepSeek-V4-Pro",
            hardware="B200",
            quantization="fp8",
            chunked_prefill_size=-1,
        )


def test_launch_command_records_b200_fp8_warning(tmp_path: Path) -> None:
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
            "--hardware",
            "B200",
            "--quantization",
            "fp8",
        )
    finally:
        server.teardown()

    assert completed.returncode == 0, completed.stderr
    command = json.loads((tmp_path / "launch" / "command.json").read_text(encoding="utf-8"))
    assert command["argv"][command["argv"].index("--chunked-prefill-size") + 1] == str(
        DEFAULT_SGLANG_CHUNKED_PREFILL_SIZE
    )
    assert any("B200/FP8" in warning for warning in command["warnings"])


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
