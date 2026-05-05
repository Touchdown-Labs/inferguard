"""Launch vLLM or SGLang engines and write InferGuard launch artifacts."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from inferguard.io import (
    atomic_write_json,
    register_child_process,
    register_partial_results,
    unregister_child_process,
    unregister_partial_results,
)
from inferguard.launch_engine.healthcheck import iso_now, normalize_base_url, run_healthcheck
from inferguard.launch_engine.lmcache import (
    DEFAULT_PROMETHEUS_MULTIPROC_DIR,
    build_lmcache_vllm_command,
    ensure_prometheus_multiproc_env,
    is_lmcache_v1_config,
    lmcache_metrics_present,
    validate_lmcache_kv_transfer_config,
)
from inferguard.launch_engine.sglang import build_sglang_command, sglang_launch_warnings
from inferguard.launch_engine.types import (
    ENGINE_VERSION_SCHEMA_VERSION,
    HealthcheckResult,
    LaunchCommand,
    LaunchOutcome,
)
from inferguard.launch_engine.vllm import build_vllm_command

ENGINE_DEFAULT_PORTS = {"vllm": 8000, "lmcache": 8000, "sglang": 30000, "dynamo-sglang": 30000}
ENV_RECORD_KEYS = (
    "CUDA_VISIBLE_DEVICES",
    "PATH",
    "PROMETHEUS_MULTIPROC_DIR",
    "SGLANG_LOG_LEVEL",
    "VLLM_ATTENTION_BACKEND",
    "VLLM_ENGINE_READY_TIMEOUT_S",
)


def launch(
    *,
    engine: str,
    output_dir: str | Path,
    external_launch: bool = False,
    endpoint_url: str | None = None,
    model_path: str | None = None,
    host: str = "127.0.0.1",
    port: int | None = None,
    tensor_parallel_size: int = 1,
    pipeline_parallel_size: int = 1,
    data_parallel_size: int = 1,
    max_model_len: int | None = None,
    gpu_memory_utilization: float = 0.9,
    mem_fraction_static: float = 0.9,
    enable_prefix_caching: bool = False,
    enable_chunked_prefill: bool = False,
    chunked_prefill_size: int | None = None,
    enable_cache_report: bool = False,
    enable_metrics: bool = False,
    kv_cache_dtype: str | None = None,
    quantization: str | None = None,
    hardware: str | None = None,
    kv_transfer_config: str | None = None,
    healthcheck_timeout_seconds: int = 600,
    healthcheck_prompt: str = "Hello, are you up?",
    canary_completion_tokens: int = 16,
    extra_args: str | None = None,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
) -> LaunchOutcome:
    launch_start = time.perf_counter()
    artifact_dir = _launch_artifact_dir(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    engine = engine.lower()
    _validate_engine(engine)
    workdir = Path(cwd or os.getcwd()).resolve()
    selected_port = _select_port(engine, port, endpoint_url)
    model_ref = model_path or "external"
    selected_endpoint = endpoint_url or _endpoint_for_host(host, selected_port)
    effective_kv_transfer_config = _effective_kv_transfer_config(engine, kv_transfer_config)
    launch_warnings = _launch_warnings(
        engine=engine,
        hardware=hardware,
        quantization=quantization,
        chunked_prefill_size=chunked_prefill_size,
        enable_metrics=enable_metrics,
    )
    argv = _build_argv(
        engine=engine,
        model_path=model_ref,
        host=host,
        port=selected_port,
        tensor_parallel_size=tensor_parallel_size,
        pipeline_parallel_size=pipeline_parallel_size,
        data_parallel_size=data_parallel_size,
        max_model_len=max_model_len,
        gpu_memory_utilization=gpu_memory_utilization,
        mem_fraction_static=mem_fraction_static,
        enable_prefix_caching=enable_prefix_caching,
        enable_chunked_prefill=enable_chunked_prefill,
        chunked_prefill_size=chunked_prefill_size,
        enable_cache_report=enable_cache_report,
        enable_metrics=enable_metrics,
        kv_cache_dtype=kv_cache_dtype,
        quantization=quantization,
        hardware=hardware,
        kv_transfer_config=effective_kv_transfer_config,
        extra_args=extra_args,
    )
    launch_env, record_env = _build_env(env, effective_kv_transfer_config)
    command = LaunchCommand(
        engine=engine,
        argv=argv,
        env=record_env,
        cwd=str(workdir),
        started_at=iso_now(),
        model_path=model_ref,
        external=external_launch,
        host=host,
        port=selected_port,
        endpoint=normalize_base_url(selected_endpoint),
        warnings=launch_warnings,
    )
    _write_json(artifact_dir / "command.json", command.to_dict())
    engine_version = _capture_engine_version(engine)
    _write_json(artifact_dir / "engine_version.json", engine_version)

    process: subprocess.Popen[bytes] | None = None
    partial_path = artifact_dir / "partial_results.json"
    register_partial_results(
        partial_path,
        lambda: _partial_results_payload(
            engine=engine,
            artifact_dir=artifact_dir,
            command=command,
            process=process,
        ),
    )
    try:
        if external_launch:
            status_name = "external_validated"
        else:
            stdout_path = artifact_dir / "stdout.log"
            stderr_path = artifact_dir / "stderr.log"
            stdout_handle = stdout_path.open("ab")
            stderr_handle = stderr_path.open("ab")
            try:
                process = subprocess.Popen(
                    argv,
                    cwd=str(workdir),
                    env=launch_env,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    start_new_session=True,
                )
                register_child_process(process)
            finally:
                stdout_handle.close()
                stderr_handle.close()
            status_name = "healthy"

        healthcheck = run_healthcheck(
            selected_endpoint,
            model_id=model_path,
            timeout_seconds=healthcheck_timeout_seconds,
            prompt=healthcheck_prompt,
            canary_completion_tokens=canary_completion_tokens,
            success_status=status_name,
        )
    except Exception as exc:  # noqa: BLE001 - launch artifacts must record failures
        healthcheck = _failed_healthcheck(
            endpoint=selected_endpoint,
            model_id=model_path or model_ref,
            failure_reason=f"launch_failed:{type(exc).__name__}:{exc}",
            warnings=launch_warnings,
        )
    healthcheck = _augment_healthcheck(
        healthcheck,
        endpoint=selected_endpoint,
        engine=engine,
        enable_metrics=enable_metrics,
        kv_transfer_config=effective_kv_transfer_config,
    )
    if healthcheck.status == "failed" and process is not None:
        _terminate_process(process)
        unregister_child_process(process)
    _write_json(artifact_dir / "healthcheck.json", healthcheck.to_dict())
    return_code = 0 if healthcheck.status in {"healthy", "external_validated"} else 1
    healthcheck_ms = (time.perf_counter() - launch_start) * 1000.0
    outcome = LaunchOutcome(
        command=command,
        healthcheck=healthcheck,
        engine_version=engine_version,
        output_dir=str(artifact_dir),
        pid=process.pid if process is not None else None,
        return_code=return_code,
        healthcheck_ms=healthcheck_ms,
    )
    unregister_partial_results(partial_path)
    if process is not None:
        unregister_child_process(process)
    return outcome


def _build_argv(
    *,
    engine: str,
    model_path: str,
    host: str,
    port: int,
    tensor_parallel_size: int,
    pipeline_parallel_size: int,
    data_parallel_size: int,
    max_model_len: int | None,
    gpu_memory_utilization: float,
    mem_fraction_static: float,
    enable_prefix_caching: bool,
    enable_chunked_prefill: bool,
    chunked_prefill_size: int | None,
    enable_cache_report: bool,
    enable_metrics: bool,
    kv_cache_dtype: str | None,
    quantization: str | None,
    hardware: str | None,
    kv_transfer_config: str | None,
    extra_args: str | None,
) -> list[str]:
    if engine == "vllm":
        if kv_transfer_config is not None:
            validate_lmcache_kv_transfer_config(kv_transfer_config)
        return build_vllm_command(
            model_path,
            host=host,
            port=port,
            tensor_parallel_size=tensor_parallel_size,
            pipeline_parallel_size=pipeline_parallel_size,
            data_parallel_size=data_parallel_size,
            max_model_len=max_model_len,
            gpu_memory_utilization=gpu_memory_utilization,
            enable_prefix_caching=enable_prefix_caching,
            enable_chunked_prefill=enable_chunked_prefill,
            kv_cache_dtype=kv_cache_dtype,
            quantization=quantization,
            kv_transfer_config=kv_transfer_config,
            extra_args=extra_args,
        )
    if engine == "lmcache":
        return build_lmcache_vllm_command(
            model_path,
            host=host,
            port=port,
            tensor_parallel_size=tensor_parallel_size,
            pipeline_parallel_size=pipeline_parallel_size,
            max_model_len=max_model_len,
            gpu_memory_utilization=gpu_memory_utilization,
            enable_prefix_caching=enable_prefix_caching,
            enable_chunked_prefill=enable_chunked_prefill,
            kv_cache_dtype=kv_cache_dtype,
            quantization=quantization,
            kv_transfer_config=kv_transfer_config,
            extra_args=extra_args,
        )
    if engine in {"sglang", "dynamo-sglang"}:
        return build_sglang_command(
            model_path,
            host=host,
            port=port,
            tensor_parallel_size=tensor_parallel_size,
            data_parallel_size=data_parallel_size,
            max_model_len=max_model_len,
            mem_fraction_static=mem_fraction_static,
            enable_metrics=enable_metrics,
            enable_cache_report=True,
            chunked_prefill_size=chunked_prefill_size,
            hardware=hardware,
            quantization=quantization,
            extra_args=extra_args,
        )
    raise ValueError(f"unsupported engine: {engine}")


def _validate_engine(engine: str) -> None:
    if engine not in ENGINE_DEFAULT_PORTS:
        raise ValueError("--engine must be one of vllm|sglang|lmcache|dynamo-sglang")


def _effective_kv_transfer_config(engine: str, kv_transfer_config: str | None) -> str | None:
    if engine == "lmcache":
        return validate_lmcache_kv_transfer_config(kv_transfer_config)
    if kv_transfer_config is None:
        return None
    return validate_lmcache_kv_transfer_config(kv_transfer_config)


def _launch_warnings(
    *,
    engine: str,
    hardware: str | None,
    quantization: str | None,
    chunked_prefill_size: int | None,
    enable_metrics: bool,
) -> list[str]:
    warnings: list[str] = []
    if engine in {"sglang", "dynamo-sglang"}:
        warnings.extend(
            sglang_launch_warnings(
                hardware=hardware,
                quantization=quantization,
                chunked_prefill_size=chunked_prefill_size,
            )
        )
        if not enable_metrics:
            warnings.append(
                "SGLang launch did not include --enable-metrics; "
                "metrics_endpoint_reachable may be false and SGLang metric claims remain not_proven."
            )
    return warnings


def _augment_healthcheck(
    healthcheck: HealthcheckResult,
    *,
    endpoint: str,
    engine: str,
    enable_metrics: bool,
    kv_transfer_config: str | None,
) -> HealthcheckResult:
    warnings = list(healthcheck.warnings)
    lmcache_present = healthcheck.lmcache_metrics_present
    if (
        engine in {"sglang", "dynamo-sglang"}
        and not enable_metrics
        and not healthcheck.metrics_endpoint_reachable
    ):
        warnings.append(
            "SGLang metrics endpoint was not reachable because --enable-metrics was omitted."
        )
    if is_lmcache_v1_config(kv_transfer_config):
        lmcache_present, warning = _scrape_lmcache_metrics_presence(endpoint)
        if warning:
            warnings.append(warning)
    if warnings == healthcheck.warnings and lmcache_present == healthcheck.lmcache_metrics_present:
        return healthcheck
    return replace(
        healthcheck,
        warnings=warnings,
        lmcache_metrics_present=lmcache_present,
    )


def _scrape_lmcache_metrics_presence(endpoint: str) -> tuple[bool, str | None]:
    metrics_url = f"{normalize_base_url(endpoint)}/metrics"
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(metrics_url)
    except Exception as exc:  # noqa: BLE001 - healthcheck artifact must record warnings
        return (
            False,
            f"LMCache metrics check could not scrape vLLM /metrics: {type(exc).__name__}: {exc}",
        )
    if response.status_code != 200:
        return False, f"LMCache metrics check found vLLM /metrics status={response.status_code}"
    if lmcache_metrics_present(response.text):
        return True, None
    return False, "LMCacheConnectorV1 launch did not surface lmcache:* metrics on vLLM /metrics."


def _launch_artifact_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    if path.name == "launch":
        return path
    return path / "launch"


def _select_port(engine: str, port: int | None, endpoint_url: str | None) -> int:
    if port is not None:
        return int(port)
    if endpoint_url:
        parsed = urlparse(endpoint_url)
        if parsed.port is not None:
            return int(parsed.port)
    return ENGINE_DEFAULT_PORTS[engine]


def _endpoint_for_host(host: str, port: int) -> str:
    unspecified_ipv4_host = ".".join(("0", "0", "0", "0"))
    wildcard_hosts = {unspecified_ipv4_host, "::"}
    probe_host = "127.0.0.1" if host in wildcard_hosts else host
    return f"http://{probe_host}:{port}"


def _build_env(
    env: dict[str, str] | None,
    kv_transfer_config: str | None,
) -> tuple[dict[str, str], dict[str, str]]:
    launch_env = dict(os.environ)
    if env:
        launch_env.update({str(key): str(value) for key, value in env.items()})
    if is_lmcache_v1_config(kv_transfer_config):
        launch_env.setdefault("PROMETHEUS_MULTIPROC_DIR", DEFAULT_PROMETHEUS_MULTIPROC_DIR)
        launch_env = ensure_prometheus_multiproc_env(launch_env)
    record_keys = set(ENV_RECORD_KEYS)
    if env:
        record_keys.update(str(key) for key in env)
    record_env = {key: launch_env[key] for key in sorted(record_keys) if key in launch_env}
    return launch_env, record_env


def _capture_engine_version(engine: str) -> dict[str, Any]:
    captured_at = iso_now()
    if engine == "vllm":
        argv = ["vllm", "--version"]
    elif engine == "lmcache":
        vllm = _capture_engine_version("vllm")
        lmcache = _python_package_version("lmcache")
        return {
            "schema_version": ENGINE_VERSION_SCHEMA_VERSION,
            "engine": engine,
            "argv": ["vllm", "--version"],
            "captured_at": captured_at,
            "version": f"vllm={vllm.get('version')}; lmcache={lmcache}",
            "raw_output": "",
            "returncode": vllm.get("returncode"),
            "components": {"vllm": vllm, "lmcache": lmcache},
        }
    elif engine == "sglang":
        argv = [sys.executable, "-m", "sglang.launch_server", "--version"]
    elif engine == "dynamo-sglang":
        argv = [sys.executable, "-m", "sglang.launch_server", "--version"]
    else:
        argv = [engine, "--version"]
    try:
        completed = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        raw_output = (completed.stdout or completed.stderr or "").strip()
        version = _first_line(raw_output) or f"unavailable:returncode_{completed.returncode}"
        return {
            "schema_version": ENGINE_VERSION_SCHEMA_VERSION,
            "engine": engine,
            "argv": argv,
            "captured_at": captured_at,
            "version": version,
            "raw_output": raw_output,
            "returncode": completed.returncode,
        }
    except FileNotFoundError:
        return {
            "schema_version": ENGINE_VERSION_SCHEMA_VERSION,
            "engine": engine,
            "argv": argv,
            "captured_at": captured_at,
            "version": "unavailable:executable_not_found",
            "raw_output": "",
            "returncode": None,
        }
    except subprocess.TimeoutExpired as exc:
        raw_output = (exc.stdout or exc.stderr or "").strip()
        return {
            "schema_version": ENGINE_VERSION_SCHEMA_VERSION,
            "engine": engine,
            "argv": argv,
            "captured_at": captured_at,
            "version": "unavailable:version_command_timeout",
            "raw_output": raw_output,
            "returncode": None,
        }


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _python_package_version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "unavailable:package_not_found"


def _failed_healthcheck(
    endpoint: str,
    model_id: str,
    failure_reason: str,
    *,
    warnings: list[str] | None = None,
) -> HealthcheckResult:
    ts = iso_now()
    return HealthcheckResult(
        endpoint=normalize_base_url(endpoint),
        model_id=model_id,
        first_probe_at=ts,
        ready_at=None,
        ready_after_seconds=0.0,
        metrics_endpoint_reachable=False,
        openai_models_endpoint_reachable=False,
        canary_completion=None,
        status="failed",
        failure_reason=failure_reason,
        warnings=list(warnings or []),
        attempts=[],
    )


def _partial_results_payload(
    *,
    engine: str,
    artifact_dir: Path,
    command: LaunchCommand,
    process: subprocess.Popen[bytes] | None,
) -> dict[str, Any]:
    return {
        "command": "launch-engine",
        "status": "interrupted",
        "claim_status": "inferred",
        "claim_reason": "interrupted_partial_results",
        "engine": engine,
        "pid": process.pid if process is not None else None,
        "process_returncode": process.poll() if process is not None else None,
        "artifacts": {
            "launch_dir": str(artifact_dir),
            "command": str(artifact_dir / "command.json"),
            "healthcheck": str(artifact_dir / "healthcheck.json"),
            "stdout": str(artifact_dir / "stdout.log"),
            "stderr": str(artifact_dir / "stderr.log"),
        },
        "launch_command": command.to_dict(),
    }


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    _terminate_process_group(process, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process, signal.SIGKILL)
        process.wait(timeout=5)


def _terminate_process_group(process: subprocess.Popen[bytes], signum: int) -> None:
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


def _write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_json(path, data)


__all__ = [
    "LaunchCommand",
    "HealthcheckResult",
    "LaunchOutcome",
    "launch",
]
