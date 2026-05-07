#!/usr/bin/env python3
"""Modal H100 lab for Packet A LMCache MP observability capture.

Exact run command:
    modal run scripts/lmcache_mp_modal_packet_lab.py

Outputs are written to the persistent Modal volume mounted at /out, under
/out/packet-a/<timestamp>/.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import modal

APP_NAME = "lmcache-mp-lab"
VOLUME_NAME = "lmcache-mp-lab"
OUT_ROOT = Path("/out")

MODEL = "Qwen/Qwen3-8B"
MODEL_MAX_LEN = 16384
VLLM_PORT = 8000
LMCACHE_HOST = "127.0.0.1"
LMCACHE_ZMQ_PORT = 6555
LMCACHE_HTTP_PORT = 8080
LMCACHE_PROMETHEUS_PORT = 9090
OTLP_HTTP_PORT = 4318
MP_EVENT_BUS_QUEUE_SIZE = 10000
MP_METRICS_SAMPLE_RATE = 1.0
LMCACHE_L1_SIZE_GB = "8"

VLLM_BASE_URL = f"http://127.0.0.1:{VLLM_PORT}"
VLLM_HEALTH_URL = f"{VLLM_BASE_URL}/health"
VLLM_METRICS_URL = f"{VLLM_BASE_URL}/metrics"
LMCACHE_HTTP_BASE_URL = f"http://127.0.0.1:{LMCACHE_HTTP_PORT}"
LMCACHE_HEALTH_URL = f"{LMCACHE_HTTP_BASE_URL}/api/healthcheck"
LMCACHE_METRICS_URL = f"http://127.0.0.1:{LMCACHE_PROMETHEUS_PORT}/metrics"
LMCACHE_TRACE_FILE = "lmcache_trace.lct"
LMCACHE_OTEL_FILE = "lmcache_otel.jsonl"
TRACE_REPLAY_DIR = "trace-replay"
LOOKUP_HASH_DIR = "lookup_hashes"
L2_CONFIG_FILE = "lmcache_l2_config.json"

REPO_ROOT = Path(__file__).resolve().parents[1]
MODAL_INFERGUARD_SOURCE = "/opt/inferguard"
MODAL_INFERGUARD_FILES = ("pyproject.toml", "README.md", "LICENSE")
MODAL_INFERGUARD_PACKAGE_DIR = "src/inferguard"
INFERGUARD_LOCAL_INSTALL_COMMAND = f"python -m pip install -e {MODAL_INFERGUARD_SOURCE}"

volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("curl", "git")
    .pip_install(
        "vllm",
        "lmcache",
        "hf-transfer",
        "huggingface-hub",
        "nvidia-cuda-runtime-cu12",
    )
    .add_local_file(
        local_path=str(REPO_ROOT / "pyproject.toml"),
        remote_path=f"{MODAL_INFERGUARD_SOURCE}/pyproject.toml",
        copy=True,
    )
    .add_local_file(
        local_path=str(REPO_ROOT / "README.md"),
        remote_path=f"{MODAL_INFERGUARD_SOURCE}/README.md",
        copy=True,
    )
    .add_local_file(
        local_path=str(REPO_ROOT / "LICENSE"),
        remote_path=f"{MODAL_INFERGUARD_SOURCE}/LICENSE",
        copy=True,
    )
    .add_local_dir(
        local_path=str(REPO_ROOT / MODAL_INFERGUARD_PACKAGE_DIR),
        remote_path=f"{MODAL_INFERGUARD_SOURCE}/{MODAL_INFERGUARD_PACKAGE_DIR}",
        copy=True,
    )
    .run_commands(INFERGUARD_LOCAL_INSTALL_COMMAND)
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            "HF_HOME": "/out/hf-cache",
            "VLLM_CACHE_ROOT": "/out/vllm-cache",
            "PYTHONHASHSEED": "0",
            "LMCACHE_USE_EXPERIMENTAL": "True",
            "LMCACHE_LOCAL_CPU": "True",
            "LMCACHE_MAX_LOCAL_CPU_SIZE": "8.0",
            "LMCACHE_CHUNK_SIZE": "256",
            "VLLM_USE_FLASHINFER_SAMPLER": "0",
            "VLLM_USE_DEEP_GEMM": "0",
            "VLLM_DEEP_GEMM_WARMUP": "skip",
            "VLLM_SKIP_DEEP_GEMM_WARMUP": "1",
            "LD_LIBRARY_PATH": (
                "/usr/local/lib/python3.11/site-packages/nvidia/cuda_runtime/lib"
            ),
        }
    )
)

app = modal.App(APP_NAME, image=image)


@dataclass(frozen=True)
class PacketSpec:
    packet_id: str
    name: str
    workload: str
    l2_configured: bool = False
    l2_adapter: str | None = None
    enable_otel: bool = False
    enable_cache_salt: bool = False
    eviction_policy: str = "LRU"
    extra_required_artifacts: tuple[str, ...] = ()
    extra_optional_artifacts: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)


PACKETS: dict[str, PacketSpec] = {
    "a": PacketSpec(
        packet_id="a",
        name="Packet A MP L1 smoke",
        workload="smoke",
        notes=("L2 is intentionally not configured for Packet A L1-only evidence.",),
    ),
    "b": PacketSpec(
        packet_id="b",
        name="Packet B MP sampled lifecycle",
        workload="reuse_eviction",
        notes=("Metrics sample rate is pinned to 1.0; workload mixes repeated prefixes and eviction pressure.",),
    ),
    "c": PacketSpec(
        packet_id="c",
        name="Packet C MP L2 fs adapter",
        workload="l2_reuse",
        l2_configured=True,
        l2_adapter="fs",
        extra_required_artifacts=(L2_CONFIG_FILE,),
        notes=("Local fs L2 config is written into the run directory and reported with --l2-configured.",),
    ),
    "d": PacketSpec(
        packet_id="d",
        name="Packet D MP OTel tracing",
        workload="otel_reuse",
        enable_otel=True,
        extra_required_artifacts=(LMCACHE_OTEL_FILE, "lmcache-packet/lmcache_otel_evidence.json"),
        notes=("A local OTLP/HTTP collector captures spans to lmcache_otel.jsonl and reports --mp-tracing-enabled.",),
    ),
    "e": PacketSpec(
        packet_id="e",
        name="Packet E trace replay",
        workload="trace_replay",
        notes=("Trace replay artifacts are required for this gate and are wired into compat and coverage reports.",),
    ),
    "f": PacketSpec(
        packet_id="f",
        name="Packet F cache_salt and IsolatedLRU",
        workload="cache_salt_isolated_lru",
        enable_cache_salt=True,
        eviction_policy="IsolatedLRU",
        notes=(
            "Uses tenant cache_salt request fields when vLLM/LMCache accept them; "
            "IsolatedLRU launch support is upstream-version dependent.",
        ),
    ),
}


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
        if text and not text.endswith("\n"):
            handle.write("\n")


def _run(
    cmd: list[str],
    log_path: Path,
    *,
    timeout: int,
    check: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    _append(log_path, f"$ {_quote_cmd(cmd)}\n")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=check,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        _append(log_path, output)
        _append(log_path, f"TIMEOUT after {timeout}s\n")
        raise
    _append(log_path, result.stdout or "")
    _append(log_path, f"exit_code={result.returncode}\n")
    return result


def _run_best_effort(cmd: list[str], log_path: Path, *, timeout: int) -> int:
    try:
        return _run(cmd, log_path, timeout=timeout).returncode
    except Exception as exc:
        _append(log_path, f"ERROR: {type(exc).__name__}: {exc}\n")
        return 1


def _run_required(cmd: list[str], log_path: Path, *, timeout: int) -> None:
    result = _run(cmd, log_path, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"required command failed with exit code {result.returncode}: {_quote_cmd(cmd)}")


def _curl_to_file(url: str, path: Path, log_path: Path, *, timeout: int = 30) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_best_effort(["curl", "-fsS", url, "-o", str(path)], log_path, timeout=timeout)
    return result == 0


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _wait_for_http(
    url: str,
    log_path: Path,
    *,
    label: str,
    max_wait_seconds: int,
    proc: subprocess.Popen[str] | None,
) -> None:
    deadline = time.monotonic() + max_wait_seconds
    attempt = 0
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"{label} exited before health passed with code {proc.returncode}")
        attempt += 1
        result = _run_best_effort(["curl", "-fsS", url], log_path, timeout=30)
        if result == 0:
            _append(log_path, f"{label} health passed after {attempt} attempts\n")
            return
        time.sleep(10)
    raise RuntimeError(f"{label} did not become healthy at {url}")


def _quote_cmd(cmd: list[str]) -> str:
    return " ".join(json.dumps(part) if any(char.isspace() for char in part) else part for part in cmd)


def _write_env_snapshot(run_dir: Path) -> None:
    env_path = run_dir / "env.txt"
    _run_best_effort(["nvidia-smi"], env_path, timeout=30)
    _run_best_effort(["python3", "-V"], env_path, timeout=30)
    _run_best_effort(["pip", "freeze"], env_path, timeout=60)
    safe_env = {}
    blocked = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")
    for key, value in sorted(os.environ.items()):
        safe_env[key] = "<redacted>" if any(marker in key.upper() for marker in blocked) else value
    (run_dir / "env.redacted.json").write_text(
        json.dumps(safe_env, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _get_packet(packet: str) -> PacketSpec:
    key = packet.lower().removeprefix("packet-")
    if key not in PACKETS:
        raise ValueError(f"unknown packet {packet!r}; expected one of {', '.join(sorted(PACKETS))}")
    return PACKETS[key]


def _build_lmcache_command(run_dir: Path, spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    cmd = [
        "lmcache",
        "server",
        "--host",
        LMCACHE_HOST,
        "--port",
        str(LMCACHE_ZMQ_PORT),
        "--http-port",
        str(LMCACHE_HTTP_PORT),
        "--l1-size-gb",
        LMCACHE_L1_SIZE_GB,
        "--eviction-policy",
        spec.eviction_policy,
        "--prometheus-port",
        str(LMCACHE_PROMETHEUS_PORT),
        "--event-bus-queue-size",
        str(MP_EVENT_BUS_QUEUE_SIZE),
        "--metrics-sample-rate",
        str(MP_METRICS_SAMPLE_RATE),
        "--trace-level",
        "storage",
        "--trace-output",
        str(run_dir / LMCACHE_TRACE_FILE),
        "--lookup-hash-log-dir",
        str(run_dir / LOOKUP_HASH_DIR),
        "--lookup-hash-log-rotation-interval",
        "21600",
        "--lookup-hash-log-rotation-max-size",
        "104857600",
        "--lookup-hash-log-max-files",
        "10",
    ]
    if spec.enable_otel:
        cmd.extend(["--enable-tracing"])
    return cmd


def _write_l2_config(run_dir: Path, spec: PacketSpec) -> Path | None:
    if not spec.l2_configured:
        return None
    l2_dir = run_dir / "l2-fs"
    l2_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "adapter": spec.l2_adapter or "fs",
        "path": str(l2_dir),
        "claim_status": "runner_configured_unvalidated_until_modal_packet_runs",
        "notes": [
            "This file is the runner-owned L2 evidence contract.",
            "If the installed LMCache version expects different L2 config keys, "
            "update this file before running Packet C.",
        ],
    }
    config_path = run_dir / L2_CONFIG_FILE
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return config_path


def _build_lmcache_env(run_dir: Path, spec: PacketSpec | None = None) -> dict[str, str]:
    spec = spec or PACKETS["a"]
    env: dict[str, str] = {}
    l2_config_path = run_dir / L2_CONFIG_FILE
    if spec.l2_configured:
        env.update(
            {
                "LMCACHE_CONFIG_FILE": str(l2_config_path),
                "LMCACHE_L2_ADAPTER": spec.l2_adapter or "fs",
                "LMCACHE_L2_PATH": str(run_dir / "l2-fs"),
            }
        )
    if spec.enable_otel:
        endpoint = f"http://127.0.0.1:{OTLP_HTTP_PORT}"
        env.update(
            {
                "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": f"{endpoint}/v1/traces",
                "OTEL_TRACES_EXPORTER": "otlp",
                "OTEL_SERVICE_NAME": f"lmcache-mp-packet-{spec.packet_id}",
            }
        )
    return env


def _launch_lmcache(run_dir: Path, spec: PacketSpec | None = None) -> tuple[subprocess.Popen[str], object]:
    spec = spec or PACKETS["a"]
    log_handle = (run_dir / "lmcache.log").open("w", encoding="utf-8")
    _write_l2_config(run_dir, spec)
    cmd = _build_lmcache_command(run_dir, spec)
    env_update = _build_lmcache_env(run_dir, spec)
    (run_dir / "lmcache_command.json").write_text(
        json.dumps(cmd, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "lmcache_env.json").write_text(
        json.dumps(env_update, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(env_update)
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=subprocess.STDOUT, text=True, env=env)
    return proc, log_handle


def _build_vllm_command() -> list[str]:
    kv_transfer_config = {
        "kv_connector": "LMCacheMPConnector",
        "kv_role": "kv_both",
        "kv_load_failure_policy": "recompute",
        "kv_connector_extra_config": {
            "lmcache.mp.host": f"tcp://{LMCACHE_HOST}",
            "lmcache.mp.port": LMCACHE_ZMQ_PORT,
            "lmcache.mp.mq_timeout": 10,
        },
    }
    return [
        "vllm",
        "serve",
        MODEL,
        "--kv-transfer-config",
        json.dumps(kv_transfer_config, separators=(",", ":")),
        "--disable-hybrid-kv-cache-manager",
        "--max-model-len",
        str(MODEL_MAX_LEN),
        "--gpu-memory-utilization",
        "0.80",
        "--port",
        str(VLLM_PORT),
    ]


def _launch_vllm(run_dir: Path) -> tuple[subprocess.Popen[str], object]:
    log_handle = (run_dir / "vllm.log").open("w", encoding="utf-8")
    cmd = _build_vllm_command()
    (run_dir / "vllm_command.json").write_text(json.dumps(cmd, indent=2) + "\n", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=subprocess.STDOUT, text=True)
    return proc, log_handle


def _capture_safe_http(run_dir: Path) -> dict[str, dict[str, object]]:
    log_path = run_dir / "capture.log"
    endpoints = {
        "root.txt": "/",
        "healthcheck.json": "/api/healthcheck",
        "status.json": "/api/status",
        "conf.json": "/conf",
        "version.txt": "/version",
        "lmc_version.txt": "/lmc_version",
        "commit_id.txt": "/commit_id",
        "quota.json": "/api/quota",
        "threads.json": "/threads",
        "periodic_threads.json": "/periodic-threads",
        "periodic_threads_health.json": "/periodic-threads-health",
    }
    results: dict[str, dict[str, object]] = {}
    for filename, path in endpoints.items():
        target = run_dir / "http" / filename
        ok = _curl_to_file(f"{LMCACHE_HTTP_BASE_URL}{path}", target, log_path)
        results[filename] = {"path": path, "ok": ok, "bytes": target.stat().st_size if target.exists() else 0}

    thread_name = _discover_periodic_thread_name(run_dir / "http" / "periodic_threads.json")
    if thread_name:
        filename = "periodic_thread.json"
        path = f"/periodic-threads/{thread_name}"
        target = run_dir / "http" / filename
        ok = _curl_to_file(f"{LMCACHE_HTTP_BASE_URL}{path}", target, log_path)
        results[filename] = {"path": path, "ok": ok, "bytes": target.stat().st_size if target.exists() else 0}

    (run_dir / "http" / "capture_manifest.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return results


def _discover_periodic_thread_name(path: Path) -> str | None:
    payload = _read_json(path)
    if isinstance(payload, list) and payload:
        return str(payload[0])
    if not isinstance(payload, dict):
        return None
    for key in ("periodic_threads", "threads"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict) and first.get("name"):
                return str(first["name"])
    return None


def _capture_metrics(run_dir: Path, suffix: str) -> None:
    log_path = run_dir / "capture.log"
    _curl_to_file(VLLM_METRICS_URL, run_dir / f"vllm_metrics_{suffix}.prom", log_path)
    _curl_to_file(LMCACHE_METRICS_URL, run_dir / f"lmcache_metrics_{suffix}.prom", log_path)


def _build_trace_replay_command(run_dir: Path, spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    replay_dir = run_dir / TRACE_REPLAY_DIR
    return [
        "lmcache",
        "trace",
        "replay",
        str(run_dir / LMCACHE_TRACE_FILE),
        "--output-dir",
        str(replay_dir),
        "--json",
        "--jsonl-out",
        str(replay_dir / "trace_replay.jsonl"),
        "--l1-size-gb",
        LMCACHE_L1_SIZE_GB,
        "--eviction-policy",
        spec.eviction_policy,
        "--disable-metrics",
    ]


def _run_trace_replay(run_dir: Path, spec: PacketSpec | None = None) -> None:
    trace_path = run_dir / LMCACHE_TRACE_FILE
    replay_dir = run_dir / TRACE_REPLAY_DIR
    log_path = run_dir / "trace_replay.log"
    if not trace_path.exists() or trace_path.stat().st_size == 0:
        _append(log_path, f"SKIP: missing or empty {trace_path}\n")
        return

    replay_dir.mkdir(parents=True, exist_ok=True)
    _run_required(
        ["lmcache", "trace", "info", str(trace_path)],
        replay_dir / "trace_info.txt",
        timeout=120,
    )
    _run_required(_build_trace_replay_command(run_dir, spec), log_path, timeout=10 * 60)


def _start_otel_collector(run_dir: Path) -> tuple[subprocess.Popen[str], object]:
    log_handle = (run_dir / "otel_collector.log").open("w", encoding="utf-8")
    otel_path = run_dir / LMCACHE_OTEL_FILE
    script = r"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

out = sys.argv[1]
port = int(sys.argv[2])

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length", "0") or "0")
        body = self.rfile.read(length)
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "path": self.path,
                "content_type": self.headers.get("content-type"),
                "body_preview": body.decode("utf-8", errors="replace")[:20000],
                "body_bytes": len(body),
            }) + "\n")
        self.send_response(200)
        self.end_headers()

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""
    proc = subprocess.Popen(
        ["python3", "-c", script, str(otel_path), str(OTLP_HTTP_PORT)],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, log_handle


def _drive_traffic(run_dir: Path, spec: PacketSpec | None = None) -> None:
    spec = spec or PACKETS["a"]
    requests = {
        "smoke": 10,
        "reuse_eviction": 36,
        "l2_reuse": 24,
        "otel_reuse": 16,
        "trace_replay": 20,
        "cache_salt_isolated_lru": 24,
    }.get(spec.workload, 10)
    script = r"""
import json
import sys
import time
import urllib.request

base_url = sys.argv[1]
model = sys.argv[2]
workload = sys.argv[3]
requests = int(sys.argv[4])
cache_salt_enabled = sys.argv[5] == "1"
shared_prefix = "InferGuard LMCache MP shared repeated-prefix validation. " * 220
eviction_prefix = "InferGuard LMCache MP eviction pressure unique block. " * 180
for idx in range(requests):
    if workload in {"reuse_eviction", "cache_salt_isolated_lru"} and idx % 3 == 2:
        prefix = eviction_prefix + (f" unique-window-{idx} " * 256)
    else:
        prefix = shared_prefix
    prompt = prefix + f"\nRequest variant {idx % 4}: summarize the observability evidence."
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "max_tokens": 96,
        "temperature": 0,
        **({"cache_salt": f"tenant-{idx % 2}"} if cache_salt_enabled else {}),
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url + "/v1/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        print(resp.status, resp.read(512).decode("utf-8", errors="replace"))
    time.sleep(1)
"""
    _run(
        [
            "python3",
            "-c",
            script,
            VLLM_BASE_URL,
            MODEL,
            spec.workload,
            str(requests),
            "1" if spec.enable_cache_salt else "0",
        ],
        run_dir / "traffic.log",
        timeout=30 * 60,
        check=True,
    )


def _maybe_add_existing(cmd: list[str], flag: str, path: Path) -> None:
    if path.exists():
        cmd.extend([flag, str(path)])


def _build_collect_lmcache_cmd(run_dir: Path, spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    packet_dir = run_dir / "lmcache-packet"
    cmd = [
        "inferguard",
        "collect-lmcache",
        "--output-dir",
        str(packet_dir),
        "--engine-metrics-file",
        str(run_dir / "vllm_metrics_loaded.prom"),
        "--lmcache-metrics-file",
        str(run_dir / "lmcache_metrics_loaded.prom"),
        "--lmcache-http-base-url",
        LMCACHE_HTTP_BASE_URL,
        "--lmcache-health-file",
        str(run_dir / "http" / "healthcheck.json"),
        "--lmcache-status-file",
        str(run_dir / "http" / "status.json"),
        "--lmcache-conf-file",
        str(run_dir / "http" / "conf.json"),
        "--lmcache-threads-file",
        str(run_dir / "http" / "threads.json"),
        "--lmcache-periodic-threads-file",
        str(run_dir / "http" / "periodic_threads.json"),
        "--lmcache-periodic-threads-health-file",
        str(run_dir / "http" / "periodic_threads_health.json"),
        "--lmcache-version-file",
        str(run_dir / "http" / "version.txt"),
        "--lmcache-lmc-version-file",
        str(run_dir / "http" / "lmc_version.txt"),
        "--lmcache-commit-id-file",
        str(run_dir / "http" / "commit_id.txt"),
        "--lmcache-quota-file",
        str(run_dir / "http" / "quota.json"),
        "--engine-log-file",
        str(run_dir / "vllm.log"),
        "--lmcache-log-file",
        str(run_dir / "lmcache.log"),
        "--lmcache-trace-file",
        str(run_dir / LMCACHE_TRACE_FILE),
        "--expect-mode",
        "mp",
        "--mp-prometheus-port",
        str(LMCACHE_PROMETHEUS_PORT),
        "--mp-event-bus-queue-size",
        str(MP_EVENT_BUS_QUEUE_SIZE),
        "--mp-metrics-sample-rate",
        str(MP_METRICS_SAMPLE_RATE),
        "--mp-trace-recording-enabled",
        "--json",
    ]
    if spec.l2_configured:
        cmd.append("--l2-configured")
    if spec.enable_otel:
        cmd.append("--mp-tracing-enabled")
    _maybe_add_existing(cmd, "--lmcache-periodic-thread-file", run_dir / "http" / "periodic_thread.json")
    _maybe_add_existing(cmd, "--lmcache-otel-file", run_dir / LMCACHE_OTEL_FILE)
    _maybe_add_existing(cmd, "--lmcache-trace-replay-output", run_dir / TRACE_REPLAY_DIR)
    _maybe_add_existing(cmd, "--lmcache-lookup-hash-path", run_dir / LOOKUP_HASH_DIR)
    return cmd


def _build_lmcache_compat_cmd(run_dir: Path, spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    packet_dir = run_dir / "lmcache-packet"
    cmd = [
        "inferguard",
        "lmcache-compat",
        "--engine-metrics-file",
        str(run_dir / "vllm_metrics_loaded.prom"),
        "--lmcache-metrics-file",
        str(run_dir / "lmcache_metrics_loaded.prom"),
        "--lmcache-http-evidence-file",
        str(packet_dir / "lmcache_http_evidence.json"),
        "--lmcache-log-evidence-file",
        str(packet_dir / "lmcache_log_evidence.json"),
        "--lmcache-trace-evidence-file",
        str(packet_dir / "lmcache_trace_evidence.json"),
        "--expect-mode",
        "mp",
        "--mp-prometheus-port",
        str(LMCACHE_PROMETHEUS_PORT),
        "--mp-event-bus-queue-size",
        str(MP_EVENT_BUS_QUEUE_SIZE),
        "--mp-metrics-sample-rate",
        str(MP_METRICS_SAMPLE_RATE),
        "--mp-trace-recording-enabled",
        "--output",
        str(run_dir / "lmcache_compat_report.json"),
        "--fail-on",
        "missing-required",
        "--json",
    ]
    if spec.l2_configured:
        cmd.append("--l2-configured")
    if spec.enable_otel:
        cmd.append("--mp-tracing-enabled")
    _maybe_add_existing(cmd, "--lmcache-trace-replay-evidence-file", packet_dir / "lmcache_trace_replay_evidence.json")
    _maybe_add_existing(cmd, "--lmcache-lookup-hash-evidence-file", packet_dir / "lmcache_lookup_hash_evidence.json")
    _maybe_add_existing(cmd, "--lmcache-otel-evidence-file", packet_dir / "lmcache_otel_evidence.json")
    return cmd


def _build_observability_coverage_cmd(run_dir: Path, spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    packet_dir = run_dir / "lmcache-packet"
    cmd = [
        "inferguard",
        "observability-coverage",
        "--engine-metrics-file",
        str(run_dir / "vllm_metrics_loaded.prom"),
        "--lmcache-metrics-file",
        str(run_dir / "lmcache_metrics_loaded.prom"),
        "--lmcache-http-evidence-file",
        str(packet_dir / "lmcache_http_evidence.json"),
        "--lmcache-log-evidence-file",
        str(packet_dir / "lmcache_log_evidence.json"),
        "--lmcache-trace-evidence-file",
        str(packet_dir / "lmcache_trace_evidence.json"),
        "--expected-engine",
        "vllm",
        "--expect-lmcache-mode",
        "mp",
        "--external-cache-configured",
        "--output",
        str(run_dir / "observability_coverage.json"),
        "--json",
    ]
    if spec.l2_configured:
        cmd.append("--l2-configured")
    _maybe_add_existing(cmd, "--lmcache-trace-replay-evidence-file", packet_dir / "lmcache_trace_replay_evidence.json")
    _maybe_add_existing(cmd, "--lmcache-lookup-hash-evidence-file", packet_dir / "lmcache_lookup_hash_evidence.json")
    _maybe_add_existing(cmd, "--lmcache-otel-evidence-file", packet_dir / "lmcache_otel_evidence.json")
    return cmd


def _run_inferguard_packet(run_dir: Path, spec: PacketSpec | None = None) -> None:
    spec = spec or PACKETS["a"]
    commands_log = run_dir / "inferguard_commands.log"
    _run_required(_build_collect_lmcache_cmd(run_dir, spec), commands_log, timeout=180)
    _run_required(_build_lmcache_compat_cmd(run_dir, spec), commands_log, timeout=180)
    _run_required(_build_observability_coverage_cmd(run_dir, spec), commands_log, timeout=180)

    job_dir = run_dir / "inferguard-job"
    collect_metrics_cmd = [
        "inferguard",
        "collect-metrics",
        "--output-dir",
        str(job_dir / "metrics"),
        "--engine",
        "vllm",
        "--engine-metrics-url",
        VLLM_METRICS_URL,
        "--lmcache-metrics-url",
        LMCACHE_METRICS_URL,
        "--duration-seconds",
        "30",
        "--interval-seconds",
        "5",
        "--keep-raw-samples",
    ]
    _run_best_effort(collect_metrics_cmd, commands_log, timeout=120)
    if (run_dir / "lmcache_compat_report.json").exists():
        (job_dir / "metrics").mkdir(parents=True, exist_ok=True)
        shutil.copy2(run_dir / "lmcache_compat_report.json", job_dir / "metrics" / "lmcache_compat_report.json")
    diagnose_cmd = [
        "inferguard",
        "diagnose-bottleneck",
        "--job-dir",
        str(job_dir),
        "--output-dir",
        str(run_dir / "diagnose-bottleneck"),
    ]
    _run_best_effort(diagnose_cmd, commands_log, timeout=120)


REQUIRED_ARTIFACTS = [
    "env.txt",
    "env.redacted.json",
    "vllm.log",
    "lmcache.log",
    "lmcache_command.json",
    "vllm_command.json",
    "http/capture_manifest.json",
    "vllm_metrics_empty.prom",
    "lmcache_metrics_empty.prom",
    "vllm_metrics_loaded.prom",
    "lmcache_metrics_loaded.prom",
    LMCACHE_TRACE_FILE,
    "trace-replay/trace_info.txt",
    "lmcache-packet/packet_manifest.json",
    "lmcache-packet/lmcache_http_evidence.json",
    "lmcache-packet/lmcache_log_evidence.json",
    "lmcache-packet/lmcache_trace_evidence.json",
    "lmcache-packet/lmcache_trace_replay_evidence.json",
    "lmcache_compat_report.json",
    "observability_coverage.json",
    "artifact_index.json",
]

OPTIONAL_ARTIFACTS = [
    "lmcache_env.json",
    "http/periodic_thread.json",
    L2_CONFIG_FILE,
    LMCACHE_OTEL_FILE,
    "lmcache-packet/lmcache_otel_evidence.json",
    "lmcache-packet/lmcache_lookup_hash_evidence.json",
    "trace-replay/trace_replay.jsonl",
    "diagnose-bottleneck/bottleneck_diagnosis.json",
]


def _missing_artifacts(run_dir: Path, rel_paths: list[str], *, require_nonempty: bool) -> list[str]:
    missing = []
    for rel in rel_paths:
        path = run_dir / rel
        if not path.exists():
            missing.append(rel)
        elif require_nonempty and path.is_file() and path.stat().st_size == 0:
            missing.append(f"{rel} (empty)")
    return missing


def _required_artifacts(spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    return [*REQUIRED_ARTIFACTS, *spec.extra_required_artifacts]


def _optional_artifacts(spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    return [*OPTIONAL_ARTIFACTS, *spec.extra_optional_artifacts]


def _validate_required_artifacts(run_dir: Path, spec: PacketSpec | None = None) -> None:
    spec = spec or PACKETS["a"]
    _write_summary_and_index(run_dir)
    missing = _missing_artifacts(run_dir, _required_artifacts(spec), require_nonempty=True)
    if missing:
        raise RuntimeError(f"Packet {spec.packet_id.upper()} missing required artifacts: " + ", ".join(missing))


def _write_summary_and_index(run_dir: Path, spec: PacketSpec | None = None) -> None:
    spec = spec or PACKETS["a"]
    artifact_index = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file():
            artifact_index.append(
                {
                    "path": str(path.relative_to(run_dir)),
                    "bytes": path.stat().st_size,
                }
            )
    (run_dir / "artifact_index.json").write_text(
        json.dumps(artifact_index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    required_artifacts = _required_artifacts(spec)
    optional_artifacts = _optional_artifacts(spec)
    missing_required = _missing_artifacts(run_dir, required_artifacts, require_nonempty=True)
    missing_optional = _missing_artifacts(run_dir, optional_artifacts, require_nonempty=True)
    lines = [
        f"# Packet {spec.packet_id.upper()} LMCache MP Modal Lab Summary",
        "",
        f"- Gate: {spec.name}",
        f"- Model: `{MODEL}`",
        "- Architecture: standalone `lmcache server` plus vLLM `LMCacheMPConnector`.",
        f"- Workload: `{spec.workload}`",
        f"- L2 configured: `{spec.l2_configured}`",
        f"- OTel enabled: `{spec.enable_otel}`",
        f"- Eviction policy: `{spec.eviction_policy}`",
        f"- Output directory: `{run_dir}`",
        "",
        "## Required Artifacts",
        "",
    ]
    lines.extend(_artifact_checkbox(run_dir, rel) for rel in required_artifacts)
    lines.extend(
        [
            "",
            "## Optional / Conditional Artifacts",
            "",
        ]
    )
    lines.extend(_artifact_checkbox(run_dir, rel) for rel in optional_artifacts)
    if missing_required:
        lines.extend(["", "## Missing Required", ""])
        lines.extend(f"- `{rel}`" for rel in missing_required)
    if missing_optional:
        lines.extend(["", "## Missing Optional / Conditional", ""])
        lines.extend(f"- `{rel}`" for rel in missing_optional)
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- LMCache and vLLM health failures raise immediately before traffic is sent.",
            "- InferGuard packet, compatibility, and coverage commands are required and fail the run on nonzero exit.",
            "- Safe LMCache HTTP endpoint captures are recorded in `http/capture_manifest.json`; "
            "destructive endpoints are not called.",
        ]
    )
    lines.extend(f"- {note}" for note in spec.notes)
    lines.append("")
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _artifact_checkbox(run_dir: Path, rel: str) -> str:
    marker = "x" if not _missing_artifacts(run_dir, [rel], require_nonempty=True) else " "
    return f"- [{marker}] `{rel}`"


def _terminate(proc: subprocess.Popen[str] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=30)


def _close_handles(handles: list[object]) -> None:
    while handles:
        handle = handles.pop()
        try:
            handle.close()
        except Exception:
            pass


def _run_packet(spec: PacketSpec) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = OUT_ROOT / f"packet-{spec.packet_id}" / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    lmcache_proc: subprocess.Popen[str] | None = None
    vllm_proc: subprocess.Popen[str] | None = None
    otel_proc: subprocess.Popen[str] | None = None
    handles: list[object] = []
    try:
        _write_env_snapshot(run_dir)
        if spec.enable_otel:
            otel_proc, otel_handle = _start_otel_collector(run_dir)
            handles.append(otel_handle)
        lmcache_proc, lmcache_handle = _launch_lmcache(run_dir, spec)
        handles.append(lmcache_handle)
        _wait_for_http(
            LMCACHE_HEALTH_URL,
            run_dir / "health.log",
            label="LMCache HTTP",
            max_wait_seconds=180,
            proc=lmcache_proc,
        )
        _wait_for_http(
            LMCACHE_METRICS_URL,
            run_dir / "health.log",
            label="LMCache Prometheus",
            max_wait_seconds=180,
            proc=lmcache_proc,
        )
        _capture_safe_http(run_dir)

        vllm_proc, vllm_handle = _launch_vllm(run_dir)
        handles.append(vllm_handle)
        _wait_for_http(
            VLLM_HEALTH_URL,
            run_dir / "health.log",
            label="vLLM",
            max_wait_seconds=30 * 60,
            proc=vllm_proc,
        )
        _capture_metrics(run_dir, "empty")
        _drive_traffic(run_dir, spec)
        _capture_metrics(run_dir, "loaded")
        _capture_safe_http(run_dir)
        _run_trace_replay(run_dir, spec)
        _run_inferguard_packet(run_dir, spec)
        _validate_required_artifacts(run_dir, spec)
    finally:
        _terminate(vllm_proc)
        _terminate(lmcache_proc)
        _terminate(otel_proc)
        _close_handles(handles)
        _write_summary_and_index(run_dir, spec)
        try:
            volume.commit()
        except Exception as exc:
            print(f"Modal volume commit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return str(run_dir)


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_a() -> str:
    return _run_packet(PACKETS["a"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_b() -> str:
    return _run_packet(PACKETS["b"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_c() -> str:
    return _run_packet(PACKETS["c"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_d() -> str:
    return _run_packet(PACKETS["d"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_e() -> str:
    return _run_packet(PACKETS["e"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_f() -> str:
    return _run_packet(PACKETS["f"])


@app.local_entrypoint()
def main(packet: str = "a") -> None:
    key = _get_packet(packet).packet_id
    runners = {
        "a": run_packet_a,
        "b": run_packet_b,
        "c": run_packet_c,
        "d": run_packet_d,
        "e": run_packet_e,
        "f": run_packet_f,
    }
    print(runners[key].remote())
