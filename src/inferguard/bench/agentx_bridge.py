"""AgentX trace replay bridge for InferGuard bench artifacts."""

from __future__ import annotations

import csv
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inferguard import __version__
from inferguard.bench.runner import BenchError, build_summary
from inferguard.bench.types import RequestMetric
from inferguard.io import atomic_write_json
from inferguard.utils.jsonl import append_jsonl

AGENTX_SCHEMA_VERSION = "inferguard-bench-agentx/v1"
AGENTX_CONFIG_SCHEMA_VERSION = "inferguard-bench-agentx-config/v1"
KV_CACHE_TESTER_URL = "https://github.com/callanjfox/kv-cache-tester.git"
KV_CACHE_TESTER_BRANCH = "agentx-minimized"
DEFAULT_TESTER_CACHE_DIR = Path.home() / ".cache" / "inferguard" / "agentx-tester"
MIN_RECOMMENDED_DURATION_SECONDS = 900


@dataclass(frozen=True)
class AgentXReplayConfig:
    endpoint: str
    model: str
    trace_source: str
    concurrency: int
    duration_seconds: int
    output_dir: Path
    tester_path: Path | None = None
    allow_network_clone: bool = False

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["output_dir"] = str(self.output_dir)
        data["tester_path"] = str(self.tester_path) if self.tester_path is not None else None
        return data


def run_agentx_replay(config: AgentXReplayConfig) -> dict[str, Any]:
    """Run Cam's AgentX trace replay tester and emit InferGuard artifacts."""
    _validate_config(config)
    run_id = _run_id()
    output_dir = config.output_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise BenchError(f"output_dir is not empty: {output_dir} (choose a new directory)")
    output_dir.mkdir(parents=True, exist_ok=True)

    tester_script = _resolve_tester_script(config.tester_path, config.allow_network_clone)
    trace_replay_dir = output_dir / "trace_replay"
    trace_replay_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / "agentx_replay_stdout.log"
    stderr_path = output_dir / "agentx_replay_stderr.log"
    config_path = output_dir / "config.json"
    run_path = output_dir / "run.json"
    requests_path = output_dir / "requests.jsonl"
    metrics_path = output_dir / "metrics.jsonl"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"

    warning = None
    if config.duration_seconds < MIN_RECOMMENDED_DURATION_SECONDS:
        warning = (
            "AgentX replay duration is below the recommended 900s/15min steady-state minimum; "
            "results should be treated as a smoke run."
        )
        print(f"WARNING: {warning}", file=sys.stderr)

    command = _build_command(config, tester_script, trace_replay_dir, output_dir / "metrics")
    run_started_at = _now_iso()
    run_perf_start = time.perf_counter()
    _write_json(
        config_path,
        {
            "schema_version": AGENTX_CONFIG_SCHEMA_VERSION,
            "run_id": run_id,
            **config.as_dict(),
            "tester_script": str(tester_script),
            "external_repo": {
                "url": KV_CACHE_TESTER_URL,
                "branch": KV_CACHE_TESTER_BRANCH,
                "auto_clone_cache_dir": str(DEFAULT_TESTER_CACHE_DIR),
                "network_clone_allowed": config.allow_network_clone,
            },
            "command": command,
            "warning": warning,
        },
    )

    with (
        stdout_path.open("w", encoding="utf-8") as stdout,
        stderr_path.open("w", encoding="utf-8") as stderr,
    ):
        completed = subprocess.run(
            command, cwd=str(tester_script.parent), stdout=stdout, stderr=stderr, check=False
        )
    if completed.returncode != 0:
        raise BenchError(
            f"AgentX trace replay tester failed with exit code {completed.returncode}; "
            f"see {stderr_path} and {stdout_path}"
        )

    detailed_path = trace_replay_dir / "detailed_results.csv"
    if not detailed_path.exists():
        raise BenchError(f"AgentX replay did not produce expected CSV: {detailed_path}")
    server_metrics_path = _find_server_metrics(output_dir, trace_replay_dir)
    rows = _read_csv(detailed_path)
    metrics = [_metric_from_row(row, config.concurrency) for row in rows]

    requests_path.write_text("", encoding="utf-8")
    metrics_path.write_text("", encoding="utf-8")
    append_jsonl(requests_path, (_request_artifact(row) for row in rows))
    append_jsonl(metrics_path, (metric.as_dict() for metric in metrics))

    runtime_seconds = time.perf_counter() - run_perf_start
    summary = build_summary(
        metrics,
        run_id=run_id,
        command="agentx-replay",
        runtime_seconds=runtime_seconds,
        model=config.model,
        endpoint=config.endpoint,
        duration_seconds=config.duration_seconds,
        metrics_timeline_present=server_metrics_path is not None,
    )
    summary["schema_family"] = AGENTX_SCHEMA_VERSION
    summary["agentx"] = {
        "trace_source": config.trace_source,
        "concurrency": config.concurrency,
        "duration_seconds": config.duration_seconds,
        "detailed_results_csv": str(detailed_path),
        "metrics_server_metrics_csv": str(server_metrics_path) if server_metrics_path else None,
        "warning": warning,
    }
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, warning), encoding="utf-8")

    completed_at = _now_iso()
    run = {
        "schema_version": AGENTX_SCHEMA_VERSION,
        "run_id": run_id,
        "command": "agentx-replay",
        "started_at": run_started_at,
        "completed_at": completed_at,
        "runtime_seconds": runtime_seconds,
        "inferguard_version": __version__,
        "artifacts": {
            "config_json": str(config_path),
            "requests_jsonl": str(requests_path),
            "metrics_jsonl": str(metrics_path),
            "summary_json": str(summary_path),
            "report_md": str(report_path),
            "agentx_detailed_results_csv": str(detailed_path),
            "agentx_stdout_log": str(stdout_path),
            "agentx_stderr_log": str(stderr_path),
            **(
                {"agentx_metrics_server_metrics_csv": str(server_metrics_path)}
                if server_metrics_path
                else {}
            ),
        },
    }
    _write_json(run_path, run)
    return {"run": run, "summary": summary}


def _validate_config(config: AgentXReplayConfig) -> None:
    if not config.endpoint:
        raise BenchError("endpoint is required")
    if not config.model:
        raise BenchError("model is required")
    if not config.trace_source:
        raise BenchError("trace_source is required")
    if config.concurrency <= 0:
        raise BenchError("concurrency must be a positive integer")
    if config.duration_seconds <= 0:
        raise BenchError("duration_seconds must be a positive integer")


def _resolve_tester_script(tester_path: Path | None, allow_network_clone: bool) -> Path:
    root_or_script = tester_path or DEFAULT_TESTER_CACHE_DIR
    if not root_or_script.exists():
        if tester_path is not None:
            raise BenchError(f"tester_path does not exist: {tester_path}")
        if not allow_network_clone:
            raise BenchError(
                f"AgentX tester repo not found at {DEFAULT_TESTER_CACHE_DIR}. "
                "Pass --tester-path to a checked-out kv-cache-tester repo or pass "
                "--allow-network-clone to clone the external repo."
            )
        _clone_tester(DEFAULT_TESTER_CACHE_DIR)
    script = _find_tester_script(root_or_script)
    if script is None:
        raise BenchError(
            f"could not find trace_replay_tester.py under {root_or_script}; "
            "pass --tester-path to the script or kv-cache-tester repo root"
        )
    return script


def _clone_tester(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    completed = subprocess.run(
        [
            "git",
            "clone",
            "--branch",
            KV_CACHE_TESTER_BRANCH,
            "--depth",
            "1",
            KV_CACHE_TESTER_URL,
            str(destination),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise BenchError(
            f"failed to clone AgentX tester repo into {destination}: {completed.stderr.strip()}"
        )


def _find_tester_script(root_or_script: Path) -> Path | None:
    if root_or_script.is_file() and root_or_script.name == "trace_replay_tester.py":
        return root_or_script
    candidates = [
        root_or_script / "trace_replay_tester.py",
        root_or_script / "utils" / "trace-replay" / "trace_replay_tester.py",
    ]
    return next((path for path in candidates if path.exists()), None)


def _build_command(
    config: AgentXReplayConfig,
    tester_script: Path,
    trace_replay_dir: Path,
    metrics_prefix: Path,
) -> list[str]:
    command = [
        "python3",
        str(tester_script),
        "--api-endpoint",
        config.endpoint,
        "--start-users",
        str(config.concurrency),
        "--max-users",
        str(config.concurrency),
        "--test-duration",
        str(config.duration_seconds),
        "--output-dir",
        str(trace_replay_dir),
        "--metrics-output-prefix",
        str(metrics_prefix),
        "--timing-strategy",
        "original",
        "--recycle",
    ]
    source = Path(config.trace_source).expanduser()
    if source.exists():
        command.extend(["--trace-directory", str(source)])
    else:
        command.extend(["--hf-dataset", config.trace_source])
    return command


def _find_server_metrics(output_dir: Path, trace_replay_dir: Path) -> Path | None:
    candidates = [
        output_dir / "metrics_server_metrics.csv",
        trace_replay_dir / "metrics_server_metrics.csv",
    ]
    return next((path for path in candidates if path.exists()), None)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _metric_from_row(row: dict[str, str], concurrency: int) -> RequestMetric:
    success = _bool(row.get("success"))
    start = _float(row.get("request_start_time")) or 0.0
    end = _float(row.get("request_complete_time")) or start
    latency = _float(row.get("ttlt"))
    if latency is None and end >= start:
        latency = end - start
    output_tokens = _int(row.get("output_tokens_actual")) or 0
    tps = output_tokens / latency if success and latency and latency > 0 else None
    error = row.get("error_message") or None
    return RequestMetric(
        request_id=f"agentx:{row.get('trace_id', 'unknown')}:{row.get('user_id', 'user')}:{row.get('request_idx', '0')}",
        trace_id=row.get("trace_id") or "unknown",
        session_id=row.get("user_id") or row.get("trace_id") or "unknown",
        turn_index=_int(row.get("request_idx")) or 0,
        workload_class="agentic-coding",
        concurrency=concurrency,
        success=success,
        start_time=start,
        end_time=end,
        latency_seconds=latency or 0.0,
        ttft_seconds=_float(row.get("ttft")),
        input_tokens=_int(row.get("input_tokens")) or 0,
        output_tokens=output_tokens,
        input_tokens_source="server_authoritative",
        output_tokens_source="server_authoritative",
        tokens_per_second=tps,
        error=error,
        kv_pressure_label="agentx_theoretical_cache_blocks",
        metadata={
            "source": "agentx_replay",
            "phase": "measurement",
            "output_tokens_expected": _int(row.get("output_tokens_expected")),
            "itl_seconds": _float(row.get("itl")),
            "cache_hit_blocks": _int(row.get("cache_hit_blocks")) or 0,
            "cache_miss_blocks": _int(row.get("cache_miss_blocks")) or 0,
            "request_type": row.get("request_type"),
        },
    )


def _request_artifact(row: dict[str, str]) -> dict[str, Any]:
    return {
        "request_id": f"agentx:{row.get('trace_id', 'unknown')}:{row.get('user_id', 'user')}:{row.get('request_idx', '0')}",
        "trace_id": row.get("trace_id") or "unknown",
        "session_id": row.get("user_id") or row.get("trace_id") or "unknown",
        "turn_index": _int(row.get("request_idx")) or 0,
        "workload_class": "agentic-coding",
        "expected_input_tokens": _int(row.get("input_tokens")),
        "expected_output_tokens": _int(row.get("output_tokens_expected")),
        "metadata": {
            "source": "agentx_detailed_results_csv",
            "request_start_time": _float(row.get("request_start_time")),
            "request_complete_time": _float(row.get("request_complete_time")),
            "cache_hit_blocks": _int(row.get("cache_hit_blocks")) or 0,
            "cache_miss_blocks": _int(row.get("cache_miss_blocks")) or 0,
        },
    }


def _bool(value: str | None) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


def _float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def _render_report(summary: dict[str, Any], warning: str | None) -> str:
    counts = summary["request_counts"]
    lines = [
        "# InferGuard AgentX replay bench report",
        "",
        f"- Run ID: `{summary['run_id']}`",
        f"- Model: `{summary['model']}`",
        f"- Endpoint: `{summary['endpoint']}`",
        f"- Requests: {counts['success']}/{counts['total']} succeeded",
        f"- Duration: {summary.get('duration_seconds')} seconds configured",
    ]
    if warning:
        lines.append(f"- Warning: {warning}")
    return "\n".join(lines) + "\n"


def _run_id() -> str:
    return "bench-agentx-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_json(path, data)
