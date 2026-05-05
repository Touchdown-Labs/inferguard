import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from inferguard.io import (
    atomic_write_json,
    atomic_write_text,
    register_child_process,
    register_partial_results,
    reset_runtime_registries_for_tests,
)


def test_atomic_write_json_happy_path(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"

    atomic_write_json(path, {"b": 2, "a": 1})

    assert path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'


def test_atomic_write_replace_failure_keeps_original(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "artifact.txt"
    path.write_text("original", encoding="utf-8")

    def crash_before_replace(_tmp: str, _target: Path) -> None:
        raise RuntimeError("simulated SIGKILL before os.replace")

    monkeypatch.setattr("inferguard.io.os.replace", crash_before_replace)

    with pytest.raises(RuntimeError, match="simulated SIGKILL"):
        atomic_write_text(path, "new-value")

    assert path.read_text(encoding="utf-8") == "original"


def test_atomic_write_parent_missing_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        atomic_write_json(tmp_path / "missing" / "artifact.json", {"ok": True})


def test_atomic_write_permission_denied(tmp_path: Path) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root can write through permission-denied directories")
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(PermissionError):
            atomic_write_json(locked / "artifact.json", {"ok": True})
    finally:
        locked.chmod(0o700)


def test_shared_signal_handler_writes_partial_and_terminates_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import inferguard.cli as cli

    reset_runtime_registries_for_tests()
    monkeypatch.setattr(cli, "_SIGNAL_ALREADY_HANDLED", False)
    partial_path = tmp_path / "partial_results.json"
    register_partial_results(partial_path, lambda: {"command": "unit-test", "rows": 2})
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    register_child_process(child)
    try:
        with pytest.raises(SystemExit) as exc:
            cli._shared_shutdown_handler(signal.SIGTERM, None)
        assert exc.value.code == 143
        assert child.poll() is not None
        payload = partial_path.read_text(encoding="utf-8")
        assert '"claim_status": "inferred"' in payload
        assert '"signal": "SIGTERM"' in payload
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        reset_runtime_registries_for_tests()
        monkeypatch.setattr(cli, "_SIGNAL_ALREADY_HANDLED", False)


def test_shared_signal_handler_reaps_child_process_group(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import inferguard.cli as cli

    reset_runtime_registries_for_tests()
    monkeypatch.setattr(cli, "_SIGNAL_ALREADY_HANDLED", False)
    pidfile = tmp_path / "pids.txt"
    script = tmp_path / "parent.py"
    script.write_text(
        "\n".join(
            [
                "import os, pathlib, subprocess, sys, time",
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])",
                f"pathlib.Path({str(pidfile)!r}).write_text(f'{{os.getpid()}}\\n{{child.pid}}\\n')",
                "while True:",
                "    time.sleep(1)",
            ]
        ),
        encoding="utf-8",
    )
    parent = subprocess.Popen([sys.executable, str(script)], start_new_session=True)
    register_child_process(parent)
    try:
        deadline = time.time() + 5
        while not pidfile.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert pidfile.exists()
        parent_pid, child_pid = [int(line) for line in pidfile.read_text(encoding="utf-8").splitlines()]
        assert parent_pid == parent.pid

        with pytest.raises(SystemExit) as exc:
            cli._shared_shutdown_handler(signal.SIGTERM, None)

        assert exc.value.code == 143
        assert _pid_exited(parent_pid)
        assert _pid_exited(child_pid)
    finally:
        for pid in (parent.pid,):
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        reset_runtime_registries_for_tests()
        monkeypatch.setattr(cli, "_SIGNAL_ALREADY_HANDLED", False)


def _pid_exited(pid: int, *, timeout_seconds: float = 5.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False
