"""Crash-safe IO helpers and runtime shutdown registries for InferGuard."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import tempfile
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

PARTIAL_RESULTS_SCHEMA_VERSION = "inferguard-partial-results/v1"
LOGGER = logging.getLogger(__name__)

_RUNTIME_LOCK = threading.RLock()
_JSONL_STREAMS: list[TextIO] = []
_PARTIAL_RESULT_PRODUCERS: dict[Path, Callable[[], dict[str, Any]]] = {}
_CHILD_PROCESSES: list[subprocess.Popen[Any]] = []


def atomic_write_text(path: str | Path, text: str) -> None:
    """Write text via fsync + same-directory atomic replace.

    The parent directory must already exist. That is intentional: callers decide
    when creating directories is valid, while this helper only guarantees the
    destination file is either the previous complete file or the new complete
    file after a crash between temp-write and replace.
    """

    target = Path(path)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            delete=False,
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, target)
        _fsync_directory(target.parent)
    except Exception:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
        raise


def atomic_write_json(path: str | Path, obj: Any) -> None:
    """Atomically write a sorted, indented JSON artifact with a trailing newline."""

    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def load_json_object(
    path: str | Path | None, *, logger: logging.Logger | None = None
) -> dict[str, Any] | None:
    """Best-effort JSON object reader used by operator-facing report paths.

    Truncated JSON, missing files, non-UTF8 content, and non-object payloads are
    downgraded to ``None`` instead of raising through CLI publishability gates.
    """

    if path is None:
        return None
    source = Path(path)
    if not source.exists():
        return None
    log = logger or LOGGER
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.warning("could not read JSON object %s: %s", source, exc)
        return None
    if not isinstance(data, dict):
        log.warning("expected JSON object in %s; got %s", source, type(data).__name__)
        return None
    return data


def register_jsonl_stream(handle: TextIO) -> None:
    """Register an open JSONL stream for best-effort signal-time flushing."""

    with _RUNTIME_LOCK:
        if handle not in _JSONL_STREAMS:
            _JSONL_STREAMS.append(handle)


def unregister_jsonl_stream(handle: TextIO) -> None:
    """Remove a JSONL stream from the signal-time flush registry."""

    with _RUNTIME_LOCK:
        if handle in _JSONL_STREAMS:
            _JSONL_STREAMS.remove(handle)


def flush_jsonl_streams() -> None:
    """Best-effort flush/fsync for registered JSONL streams."""

    with _RUNTIME_LOCK:
        streams = list(_JSONL_STREAMS)
    for handle in streams:
        try:
            handle.flush()
            os.fsync(handle.fileno())
        except Exception as exc:  # noqa: BLE001 - shutdown path must be best-effort
            LOGGER.warning("could not flush JSONL stream during shutdown: %s", exc)


def register_partial_results(path: str | Path, producer: Callable[[], dict[str, Any]]) -> None:
    """Register a ``partial_results.json`` producer for signal-time emission."""

    with _RUNTIME_LOCK:
        _PARTIAL_RESULT_PRODUCERS[Path(path)] = producer


def unregister_partial_results(path: str | Path) -> None:
    """Remove a partial-results producer."""

    with _RUNTIME_LOCK:
        _PARTIAL_RESULT_PRODUCERS.pop(Path(path), None)


def write_registered_partial_results(signum: int | None = None) -> list[Path]:
    """Write all registered partial-result summaries and return written paths."""

    with _RUNTIME_LOCK:
        producers = list(_PARTIAL_RESULT_PRODUCERS.items())
    written: list[Path] = []
    for path, producer in producers:
        try:
            payload = producer()
        except Exception as exc:  # noqa: BLE001 - shutdown path must still emit a record
            payload = {"producer_error": f"{type(exc).__name__}: {exc}"}
        if not isinstance(payload, dict):
            payload = {"producer_error": f"producer returned {type(payload).__name__}"}
        payload = _partial_payload(payload, signum=signum)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(path, payload)
            written.append(path)
        except Exception as exc:  # noqa: BLE001 - shutdown path must be best-effort
            LOGGER.warning("could not write partial results %s: %s", path, exc)
    return written


def register_child_process(process: subprocess.Popen[Any]) -> None:
    """Register a spawned engine process for signal-time termination."""

    with _RUNTIME_LOCK:
        if process not in _CHILD_PROCESSES:
            _CHILD_PROCESSES.append(process)


def unregister_child_process(process: subprocess.Popen[Any]) -> None:
    """Remove a spawned engine process from the termination registry."""

    with _RUNTIME_LOCK:
        if process in _CHILD_PROCESSES:
            _CHILD_PROCESSES.remove(process)


def terminate_registered_processes(*, grace_seconds: float = 5.0) -> None:
    """Best-effort SIGTERM→SIGKILL cleanup for registered child processes."""

    with _RUNTIME_LOCK:
        processes = list(_CHILD_PROCESSES)
    for process in processes:
        try:
            if process.poll() is None:
                _terminate_process_group(process, signal.SIGTERM)
                try:
                    process.wait(timeout=grace_seconds)
                except subprocess.TimeoutExpired:
                    _terminate_process_group(process, signal.SIGKILL)
                    process.wait(timeout=grace_seconds)
        except Exception as exc:  # noqa: BLE001 - shutdown path must be best-effort
            LOGGER.warning("could not terminate child process during shutdown: %s", exc)
        finally:
            unregister_child_process(process)


def reset_runtime_registries_for_tests() -> None:
    """Clear shutdown registries for unit tests."""

    with _RUNTIME_LOCK:
        _JSONL_STREAMS.clear()
        _PARTIAL_RESULT_PRODUCERS.clear()
        _CHILD_PROCESSES.clear()


def _partial_payload(payload: dict[str, Any], *, signum: int | None) -> dict[str, Any]:
    result = dict(payload)
    result.setdefault("schema_version", PARTIAL_RESULTS_SCHEMA_VERSION)
    result.setdefault("status", "interrupted")
    if result.get("claim_status") not in {"measured", "inferred", "synthetic", "not_proven"}:
        result["claim_status"] = "inferred"
        result.setdefault("claim_reason", "interrupted_partial_results")
    result.setdefault(
        "generated_at",
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    if signum is not None:
        result["signal"] = _signal_name(signum)
        result["exit_code"] = 128 + int(signum)
    return result


def _signal_name(signum: int) -> str:
    try:
        return signal.Signals(signum).name
    except ValueError:
        return f"SIG{signum}"


def _terminate_process_group(process: subprocess.Popen[Any], signum: int) -> None:
    try:
        pgid = os.getpgid(process.pid)
    except ProcessLookupError:
        return
    if pgid != os.getpgid(0):
        os.killpg(pgid, signum)
    elif signum == signal.SIGTERM:
        process.terminate()
    else:
        process.kill()


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


__all__ = [
    "PARTIAL_RESULTS_SCHEMA_VERSION",
    "atomic_write_json",
    "atomic_write_text",
    "flush_jsonl_streams",
    "load_json_object",
    "register_child_process",
    "register_jsonl_stream",
    "register_partial_results",
    "reset_runtime_registries_for_tests",
    "terminate_registered_processes",
    "unregister_child_process",
    "unregister_jsonl_stream",
    "unregister_partial_results",
    "write_registered_partial_results",
]
