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
from datetime import UTC, datetime
from pathlib import Path

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
MP_EVENT_BUS_QUEUE_SIZE = 10000
MP_METRICS_SAMPLE_RATE = 1.0

VLLM_BASE_URL = f"http://127.0.0.1:{VLLM_PORT}"
VLLM_HEALTH_URL = f"{VLLM_BASE_URL}/health"
VLLM_METRICS_URL = f"{VLLM_BASE_URL}/metrics"
LMCACHE_HTTP_BASE_URL = f"http://127.0.0.1:{LMCACHE_HTTP_PORT}"
LMCACHE_HEALTH_URL = f"{LMCACHE_HTTP_BASE_URL}/api/healthcheck"
LMCACHE_METRICS_URL = f"http://127.0.0.1:{LMCACHE_PROMETHEUS_PORT}/metrics"

INFERGUARD_PACKAGE = (
    "inferguard @ "
    "git+https://github.com/Touchdown-Labs/inferguard.git@"
    "cf1d669ad5eabcffd6eac25b903f9f348f8b6308"
)

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
        INFERGUARD_PACKAGE,
    )
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


def _curl_to_file(url: str, path: Path, log_path: Path, *, timeout: int = 30) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_best_effort(["curl", "-fsS", url, "-o", str(path)], log_path, timeout=timeout)
    return result == 0


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


def _launch_lmcache(run_dir: Path) -> tuple[subprocess.Popen[str], object]:
    log_handle = (run_dir / "lmcache.log").open("w", encoding="utf-8")
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
        "8",
        "--eviction-policy",
        "LRU",
        "--prometheus-port",
        str(LMCACHE_PROMETHEUS_PORT),
        "--event-bus-queue-size",
        str(MP_EVENT_BUS_QUEUE_SIZE),
        "--metrics-sample-rate",
        str(MP_METRICS_SAMPLE_RATE),
        "--trace-level",
        "storage",
        "--trace-output",
        str(run_dir / "lmcache_trace.lct"),
        "--lookup-hash-log-dir",
        str(run_dir / "lookup_hashes"),
        "--lookup-hash-log-rotation-interval",
        "21600",
        "--lookup-hash-log-rotation-max-size",
        "104857600",
        "--lookup-hash-log-max-files",
        "10",
    ]
    (run_dir / "lmcache_command.json").write_text(
        json.dumps(cmd, indent=2) + "\n",
        encoding="utf-8",
    )
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=subprocess.STDOUT, text=True)
    return proc, log_handle


def _launch_vllm(run_dir: Path) -> tuple[subprocess.Popen[str], object]:
    log_handle = (run_dir / "vllm.log").open("w", encoding="utf-8")
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
    cmd = [
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
    (run_dir / "vllm_command.json").write_text(json.dumps(cmd, indent=2) + "\n", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=subprocess.STDOUT, text=True)
    return proc, log_handle


def _capture_safe_http(run_dir: Path) -> None:
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
    for filename, path in endpoints.items():
        _curl_to_file(f"{LMCACHE_HTTP_BASE_URL}{path}", run_dir / "http" / filename, log_path)


def _capture_metrics(run_dir: Path, suffix: str) -> None:
    log_path = run_dir / "capture.log"
    _curl_to_file(VLLM_METRICS_URL, run_dir / f"vllm_metrics_{suffix}.prom", log_path)
    _curl_to_file(LMCACHE_METRICS_URL, run_dir / f"lmcache_metrics_{suffix}.prom", log_path)


def _drive_traffic(run_dir: Path) -> None:
    script = r"""
import json
import sys
import time
import urllib.request

base_url, model = sys.argv[1], sys.argv[2]
prefix = "InferGuard LMCache Packet A repeated-prefix validation. " * 220
for idx in range(10):
    prompt = prefix + f"\nRequest variant {idx % 2}: summarize the observability evidence."
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "max_tokens": 96,
        "temperature": 0,
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
        ["python3", "-c", script, VLLM_BASE_URL, MODEL],
        run_dir / "traffic.log",
        timeout=30 * 60,
        check=True,
    )


def _run_inferguard_packet(run_dir: Path) -> None:
    packet_dir = run_dir / "lmcache-packet"
    commands_log = run_dir / "inferguard_commands.log"
    collect_cmd = [
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
        "--engine-log-file",
        str(run_dir / "vllm.log"),
        "--lmcache-log-file",
        str(run_dir / "lmcache.log"),
        "--lmcache-trace-file",
        str(run_dir / "lmcache_trace.lct"),
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
    _run_best_effort(collect_cmd, commands_log, timeout=180)

    compat_cmd = [
        "inferguard",
        "lmcache-compat",
        "--engine-metrics-file",
        str(run_dir / "vllm_metrics_loaded.prom"),
        "--lmcache-metrics-file",
        str(run_dir / "lmcache_metrics_loaded.prom"),
        "--lmcache-http-evidence-file",
        str(packet_dir / "lmcache_http_evidence.json"),
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
        "--json",
    ]
    _run_best_effort(compat_cmd, commands_log, timeout=180)

    coverage_cmd = [
        "inferguard",
        "observability-coverage",
        "--engine-metrics-file",
        str(run_dir / "vllm_metrics_loaded.prom"),
        "--lmcache-metrics-file",
        str(run_dir / "lmcache_metrics_loaded.prom"),
        "--lmcache-http-evidence-file",
        str(packet_dir / "lmcache_http_evidence.json"),
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
    _run_best_effort(coverage_cmd, commands_log, timeout=180)

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


def _write_summary_and_index(run_dir: Path) -> None:
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
    required = [
        "env.txt",
        "vllm.log",
        "lmcache.log",
        "vllm_metrics_empty.prom",
        "lmcache_metrics_empty.prom",
        "vllm_metrics_loaded.prom",
        "lmcache_metrics_loaded.prom",
        "lmcache_trace.lct",
        "lmcache-packet/packet_manifest.json",
        "lmcache-packet/lmcache_http_evidence.json",
        "lmcache-packet/lmcache_log_evidence.json",
        "lmcache-packet/lmcache_trace_evidence.json",
        "lmcache_compat_report.json",
        "observability_coverage.json",
        "diagnose-bottleneck/bottleneck_diagnosis.json",
        "artifact_index.json",
    ]
    lines = [
        "# Packet A LMCache MP Modal Lab Summary",
        "",
        f"- Model: `{MODEL}`",
        "- Architecture: standalone `lmcache server` plus vLLM `LMCacheMPConnector`.",
        f"- Output directory: `{run_dir}`",
        "",
        "## Required Artifacts",
        "",
    ]
    lines.extend(f"- [{'x' if (run_dir / rel).exists() else ' '}] `{rel}`" for rel in required)
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- LMCache and vLLM health failures raise immediately before traffic is sent.",
            "- Individual capture and InferGuard command failures are logged and do not stop later captures.",
            "- L2 is intentionally not configured for Packet A L1-only evidence.",
            "",
        ]
    )
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _terminate(proc: subprocess.Popen[str] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=30)


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_a() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = OUT_ROOT / "packet-a" / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    lmcache_proc: subprocess.Popen[str] | None = None
    vllm_proc: subprocess.Popen[str] | None = None
    handles: list[object] = []
    try:
        _write_env_snapshot(run_dir)
        lmcache_proc, lmcache_handle = _launch_lmcache(run_dir)
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
        _drive_traffic(run_dir)
        _capture_metrics(run_dir, "loaded")
        _capture_safe_http(run_dir)
        _run_inferguard_packet(run_dir)
        _write_summary_and_index(run_dir)
    finally:
        _terminate(vllm_proc)
        _terminate(lmcache_proc)
        for handle in handles:
            try:
                handle.close()
            except Exception:
                pass
        _write_summary_and_index(run_dir)
        try:
            volume.commit()
        except Exception as exc:
            print(f"Modal volume commit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return str(run_dir)


@app.local_entrypoint()
def main() -> None:
    print(run_packet_a.remote())
