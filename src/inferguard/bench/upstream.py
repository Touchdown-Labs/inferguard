"""Engine-native upstream benchmark wrapper.

This module shells out to upstream engine benchmark CLIs, captures their output,
and writes an InferGuard-compatible artifact bundle for later analysis.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from inferguard import __version__
from inferguard.bench.runner import BenchError
from inferguard.io import atomic_write_json

UPSTREAM_RUN_SCHEMA_VERSION = "inferguard-bench-upstream/v1"
UPSTREAM_CONFIG_SCHEMA_VERSION = "inferguard-bench-upstream-config/v1"
SUMMARY_SCHEMA_VERSION = "inferguard-bench-summary/v1"
METRIC_SCHEMA_VERSION = "inferguard-bench-metric/v1"
REQUEST_SCHEMA_VERSION = "inferguard-bench-spec/v1"

Engine = Literal["vllm", "sglang"]

VLLM_PROFILES = {"random", "sharegpt", "prefix-repetition", "sonnet"}
SGLANG_PROFILES = {"random"}


@dataclass(frozen=True)
class UpstreamBenchConfig:
    engine: Engine
    profile: str
    model: str
    endpoint: str
    output_dir: Path
    num_prompts: int = 100
    request_rate: float | None = None
    timeout_seconds: float = 300.0
    dataset_path: Path | None = None
    force: bool = False
    enable_radix_cache: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["output_dir"] = str(self.output_dir)
        data["dataset_path"] = str(self.dataset_path) if self.dataset_path is not None else None
        return data


def run_upstream(config: UpstreamBenchConfig) -> dict[str, Any]:
    """Run an upstream engine benchmark and write InferGuard artifacts."""
    _validate_config(config)
    run_id = _run_id(f"upstream-{config.engine}-{config.profile}")
    output_dir = config.output_dir
    if output_dir.exists() and any(output_dir.iterdir()) and not config.force:
        raise BenchError(
            f"output_dir is not empty: {output_dir} (choose a new directory or pass --force)"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    started_at = _now_iso()
    started_perf = time.perf_counter()
    command = _build_command(config)
    env = _build_env(config)

    completed = subprocess.run(  # noqa: S603 - explicit user-facing wrapper around upstream CLIs
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=config.timeout_seconds,
        env=env,
    )
    runtime_seconds = time.perf_counter() - started_perf
    completed_at = _now_iso()

    stdout_path = output_dir / "upstream_stdout.txt"
    stderr_path = output_dir / "upstream_stderr.txt"
    upstream_json_path = output_dir / "upstream.json"
    requests_path = output_dir / "requests.jsonl"
    metrics_path = output_dir / "metrics.jsonl"
    summary_path = output_dir / "summary.json"
    config_path = output_dir / "config.json"
    run_path = output_dir / "run.json"

    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    upstream_data = (
        _parse_json_payload(completed.stdout) or _parse_json_payload(completed.stderr) or {}
    )
    _write_json(upstream_json_path, upstream_data)
    _write_json(
        config_path,
        {
            "schema_version": UPSTREAM_CONFIG_SCHEMA_VERSION,
            "run_id": run_id,
            "command": "upstream",
            "subprocess_args": command,
            **config.as_dict(),
        },
    )

    requests = _extract_requests(upstream_data)
    _write_requests(requests_path, requests)
    metric_rows = _metric_rows(upstream_data, config, run_id, completed.returncode, runtime_seconds)
    _write_jsonl(metrics_path, metric_rows)
    summary = _summary(
        upstream_data, config, run_id, completed.returncode, runtime_seconds, metric_rows
    )
    _write_json(summary_path, summary)

    run = {
        "schema_version": UPSTREAM_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "command": "upstream",
        "engine": config.engine,
        "profile": config.profile,
        "started_at": started_at,
        "completed_at": completed_at,
        "runtime_seconds": runtime_seconds,
        "inferguard_version": __version__,
        "subprocess": {
            "args": command,
            "returncode": completed.returncode,
        },
        "artifacts": {
            "config_json": str(config_path),
            "requests_jsonl": str(requests_path),
            "metrics_jsonl": str(metrics_path),
            "summary_json": str(summary_path),
            "upstream_json": str(upstream_json_path),
            "upstream_stdout_txt": str(stdout_path),
            "upstream_stderr_txt": str(stderr_path),
        },
    }
    _write_json(run_path, run)
    if completed.returncode != 0:
        raise BenchError(
            f"upstream {config.engine} benchmark failed with exit code {completed.returncode}; "
            f"artifacts written to {output_dir}"
        )
    return {"run": run, "summary": summary}


def _validate_config(config: UpstreamBenchConfig) -> None:
    if config.engine == "vllm" and config.profile not in VLLM_PROFILES:
        raise BenchError("vLLM --profile must be one of random|sharegpt|prefix-repetition|sonnet")
    if config.engine == "sglang" and config.profile not in SGLANG_PROFILES:
        raise BenchError("SGLang --profile must be random")
    if config.num_prompts <= 0:
        raise BenchError("--num-prompts must be positive")
    if config.timeout_seconds <= 0:
        raise BenchError("--timeout must be positive")
    if config.request_rate is not None and config.request_rate <= 0:
        raise BenchError("--request-rate must be positive when provided")
    if not config.endpoint.startswith(("http://", "https://")):
        raise BenchError("endpoint must start with http:// or https://")


def _build_command(config: UpstreamBenchConfig) -> list[str]:
    if config.engine == "vllm":
        dataset_name = (
            "prefix_repetition" if config.profile == "prefix-repetition" else config.profile
        )
        command = [
            "vllm",
            "bench",
            "serve",
            "--backend",
            "openai-chat",
            "--base-url",
            config.endpoint.rstrip("/"),
            "--model",
            config.model,
            "--dataset-name",
            dataset_name,
            "--num-prompts",
            str(config.num_prompts),
            "--save-result",
        ]
    else:
        parsed = urlsplit(config.endpoint)
        host = parsed.hostname or "localhost"
        port = str(parsed.port or (443 if parsed.scheme == "https" else 80))
        command = [
            "python3",
            "-m",
            "sglang.bench_serving",
            "--backend",
            "sglang",
            "--host",
            host,
            "--port",
            port,
            "--model",
            config.model,
            "--dataset-name",
            config.profile,
            "--num-prompts",
            str(config.num_prompts),
        ]
    if config.dataset_path is not None:
        command.extend(["--dataset-path", str(config.dataset_path)])
    if config.request_rate is not None:
        command.extend(["--request-rate", str(config.request_rate)])
    return command


def _build_env(config: UpstreamBenchConfig) -> dict[str, str]:
    env = os.environ.copy()
    if config.engine == "sglang" and config.enable_radix_cache is not None:
        env["SGLANG_ENABLE_RADIX_CACHE"] = "1" if config.enable_radix_cache else "0"
    return env


def _parse_json_payload(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else {"payload": payload}
    except json.JSONDecodeError:
        pass
    start = stripped.rfind("{")
    while start != -1:
        try:
            payload = json.loads(stripped[start:])
            return payload if isinstance(payload, dict) else {"payload": payload}
        except json.JSONDecodeError:
            start = stripped.rfind("{", 0, start)
    return None


def _extract_requests(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("request_outputs", "requests", "per_request"):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _metric_rows(
    data: dict[str, Any],
    config: UpstreamBenchConfig,
    run_id: str,
    returncode: int,
    runtime_seconds: float,
) -> list[dict[str, Any]]:
    total = _int_first(
        data, "num_requests", "total_num_prompts", "num_prompts", default=config.num_prompts
    )
    success = (
        0 if returncode else _int_first(data, "successful_requests", "completed", default=total)
    )
    failed = max(total - success, 0)
    row = {
        "schema_version": METRIC_SCHEMA_VERSION,
        "run_id": run_id,
        "trace_id": f"upstream-{config.profile}",
        "request_id": f"{run_id}-aggregate",
        "workload_class": f"upstream-{config.profile}",
        "concurrency": _int_first(data, "max_concurrency", "concurrency", default=1),
        "success": success > 0 and returncode == 0,
        "start_time": 0.0,
        "end_time": runtime_seconds,
        "latency_seconds": _seconds_first(data, "p99_e2el_ms", "p99_latency_ms", "mean_e2el_ms"),
        "ttft_seconds": _seconds_first(data, "p99_ttft_ms", "mean_ttft_ms"),
        "input_tokens": _int_first(data, "total_input_tokens", "input_tokens", default=0),
        "output_tokens": _int_first(data, "total_output_tokens", "output_tokens", default=0),
        "input_tokens_source": "upstream",
        "output_tokens_source": "upstream",
        "error": None if returncode == 0 else f"upstream_exit_{returncode}",
        "metadata": {"engine": config.engine, "profile": config.profile, "failed_requests": failed},
    }
    return [row]


def _summary(
    data: dict[str, Any],
    config: UpstreamBenchConfig,
    run_id: str,
    returncode: int,
    runtime_seconds: float,
    metric_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    total = _int_first(
        data, "num_requests", "total_num_prompts", "num_prompts", default=config.num_prompts
    )
    success = (
        0 if returncode else _int_first(data, "successful_requests", "completed", default=total)
    )
    failed = max(total - success, 0)
    input_total = _int_first(data, "total_input_tokens", "input_tokens", default=0)
    output_total = _int_first(data, "total_output_tokens", "output_tokens", default=0)
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "run_id": run_id,
        "command": "upstream",
        "model": config.model,
        "endpoint": config.endpoint,
        "benchmark_mode": "upstream",
        "engine": config.engine,
        "profile": config.profile,
        "kvcast_mode": None,
        "requests_per_level": None,
        "duration_seconds": None,
        "warmup_seconds": 0.0,
        "redact_prompts": False,
        "metrics_timeline_present": False,
        "metrics_scrape_interval_seconds": None,
        "raw_request_counts": {"total_including_warmup": total, "measurement_total": total},
        "request_counts": {
            "total": total,
            "success": success,
            "failed": failed,
            "failed_rate": (failed / total) if total else 0.0,
        },
        "runtime_seconds": runtime_seconds,
        "latency_seconds": {
            "p50": _seconds_first(data, "median_e2el_ms", "median_latency_ms", "mean_e2el_ms"),
            "p95": _seconds_first(data, "p95_e2el_ms", "p95_latency_ms", "mean_e2el_ms"),
            "p99": _seconds_first(data, "p99_e2el_ms", "p99_latency_ms", "mean_e2el_ms"),
        },
        "ttft_seconds": {
            "p50": _seconds_first(data, "median_ttft_ms", "mean_ttft_ms"),
            "p95": _seconds_first(data, "p95_ttft_ms", "mean_ttft_ms"),
            "p99": _seconds_first(data, "p99_ttft_ms", "mean_ttft_ms"),
        },
        "average_tokens_per_second": _float_first(data, "mean_output_throughput"),
        "throughput_req_per_second": _float_first(data, "request_throughput"),
        "output_tokens_per_second_wall": _float_first(data, "output_throughput"),
        "tokens": {
            "input_total": input_total,
            "output_total": output_total,
            "estimated_input_tokens": 0,
            "estimated_output_tokens": 0,
        },
        "concurrency": [
            {
                "concurrency": metric_rows[0]["concurrency"] if metric_rows else 1,
                "total": total,
                "success": success,
                "failed": failed,
                "latency_seconds": {
                    "p50": _seconds_first(
                        data, "median_e2el_ms", "median_latency_ms", "mean_e2el_ms"
                    ),
                    "p95": _seconds_first(data, "p95_e2el_ms", "p95_latency_ms", "mean_e2el_ms"),
                    "p99": _seconds_first(data, "p99_e2el_ms", "p99_latency_ms", "mean_e2el_ms"),
                },
                "ttft_seconds": {
                    "p50": _seconds_first(data, "median_ttft_ms", "mean_ttft_ms"),
                    "p95": _seconds_first(data, "p95_ttft_ms", "mean_ttft_ms"),
                    "p99": _seconds_first(data, "p99_ttft_ms", "mean_ttft_ms"),
                },
                "throughput_req_per_second": _float_first(data, "request_throughput"),
            }
        ],
        "workloads": {
            f"upstream-{config.profile}": {"total": total, "success": success, "failed": failed}
        },
        "limitations": [
            "Upstream engine-native benchmark output is normalized from the engine CLI JSON/stdout payload.",
            "Per-request rows are present only when the upstream engine emits request-level records.",
        ],
    }


def _write_requests(path: Path, rows: list[dict[str, Any]]) -> None:
    normalized = []
    for idx, row in enumerate(rows):
        normalized.append(
            {
                "schema_version": REQUEST_SCHEMA_VERSION,
                "trace_id": str(row.get("trace_id") or f"upstream-{idx}"),
                "session_id": str(row.get("session_id") or "upstream"),
                "turn_index": int(row.get("turn_index") or idx),
                "workload_class": str(row.get("workload_class") or "upstream"),
                "messages": row.get("messages") or [],
                "metadata": row,
            }
        )
    _write_jsonl(path, normalized)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )


def _int_first(data: dict[str, Any], *keys: str, default: int) -> int:
    for key in keys:
        value = data.get(key)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return default


def _float_first(data: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _seconds_first(data: dict[str, Any], *keys: str) -> float | None:
    value = _float_first(data, *keys)
    return None if value is None else value / 1000.0


def _run_id(command: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{command}-{stamp}"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_json(path, data)
