"""Typer-based CLI entrypoint for InferGuard diagnostics and benchmarks."""
# ruff: noqa: UP007  # Typer/click in this test matrix cannot parse PEP 604 unions in CLI signatures.

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from inferguard import __version__
from inferguard.analyze import (
    AnalyzeError,
    AnalyzeOptions,
    CompareError,
    CompareOptions,
    analyze_results,
    compare_runs,
    exit_code_for_report,
    render_plots,
)
from inferguard.analyze.exporters import emit_agentx_shape
from inferguard.bench import (
    AgentXReplayConfig,
    BenchConfig,
    BenchError,
    UpstreamBenchConfig,
    run_agentx_replay,
    run_cold_start,
    run_kv_stress,
    run_replay,
    run_upstream,
)
from inferguard.bench.tokenizer import estimate_text_tokens
from inferguard.bundle.emitter import BundleEmitError, emit_bundle
from inferguard.config import HTTP_TIMEOUT_SECONDS
from inferguard.disagg.adapters import scrape
from inferguard.disagg.detect import evaluate
from inferguard.disagg.types import DisaggFinding, DisaggStatus, EngineName
from inferguard.harness.agent_trace import AgentTracer
from inferguard.harness.cluster_daemon import ClusterDaemon
from inferguard.harness.daemon import DEFAULT_DAEMON_PORT, Daemon
from inferguard.harness.telemetry import NEVER_COLLECTED_KEYS, TelemetryClient, default_config_dir
from inferguard.io import (
    atomic_write_json,
    flush_jsonl_streams,
    terminate_registered_processes,
    write_registered_partial_results,
)
from inferguard.preflight import check_hma_offload_compat, check_tokenizer_mismatch
from inferguard.profile import (
    ProfileError,
    ProfileLiveOptions,
    run_profile_live,
    run_profile_retro,
)
from inferguard.profile.retro import ProfileRetroError
from inferguard.profile.types import ProfileFinding
from inferguard.router import classify_run_dir, render_verdict_markdown
from inferguard.router.classify import RouterClassifyError
from inferguard.schemas.telemetry import TelemetryValidationError, load_telemetry_payload
from inferguard.workload import analyze_workload_dir, render_fingerprint_markdown
from inferguard.workload.profile import WorkloadAnalyzeError

ZERO_TELEMETRY_MESSAGE = (
    "No telemetry. No network calls outside endpoints you pass via flags. "
    "Verified: see oss/inferguard/docs/telemetry/v0/POSTURE.md."
)
AGENT_FRAMEWORKS = {"langgraph", "crewai", "autogen", "claude_code", "cursor_sdk", "raw_openai"}

app = typer.Typer(
    help="InferGuard — read-only disaggregated-serving diagnostics.",
    add_completion=False,
    invoke_without_command=True,
)
disagg_app = typer.Typer(
    no_args_is_help=True,
    help="Disaggregated serving diagnostics.",
    add_completion=False,
)
bench_app = typer.Typer(
    no_args_is_help=True,
    help="OpenAI-compatible endpoint benchmarks.",
    add_completion=False,
)
profile_app = typer.Typer(
    no_args_is_help=True,
    help="Live endpoint profiler for existing /metrics traffic.",
    add_completion=False,
)
agent_app = typer.Typer(
    no_args_is_help=True,
    help="Agent trace harness commands.",
    add_completion=False,
)
daemon_app = typer.Typer(
    no_args_is_help=True,
    help="Local harness daemon sidecar.",
    add_completion=False,
)
telemetry_app = typer.Typer(
    no_args_is_help=True,
    help="Local-only telemetry consent and payload audit commands.",
    add_completion=False,
)
workload_app = typer.Typer(
    no_args_is_help=True,
    help="Pre-flight workload fingerprinting.",
    add_completion=False,
)
router_app = typer.Typer(
    no_args_is_help=True,
    help="Rule-based execution-path routing.",
    add_completion=False,
)
app.add_typer(disagg_app, name="disagg")
app.add_typer(bench_app, name="bench")
app.add_typer(profile_app, name="profile")
app.add_typer(agent_app, name="agent")
app.add_typer(daemon_app, name="daemon")
app.add_typer(telemetry_app, name="telemetry")
app.add_typer(workload_app, name="workload")
app.add_typer(router_app, name="router")

_SIGNAL_HANDLERS_INSTALLED = False
_SIGNAL_ALREADY_HANDLED = False


def install_signal_handlers() -> None:
    """Install InferGuard's shared SIGINT/SIGTERM cleanup handler once."""

    global _SIGNAL_HANDLERS_INSTALLED
    if _SIGNAL_HANDLERS_INSTALLED:
        return
    try:
        signal.signal(signal.SIGINT, _shared_shutdown_handler)
        signal.signal(signal.SIGTERM, _shared_shutdown_handler)
    except ValueError:
        # signal.signal only works in the main thread. CLI entrypoints run there;
        # library imports from worker threads should remain harmless.
        return
    _SIGNAL_HANDLERS_INSTALLED = True


def _shared_shutdown_handler(signum: int, _frame: Optional[object]) -> None:
    """Flush live artifacts, emit partial summaries, terminate engines, then exit."""

    global _SIGNAL_ALREADY_HANDLED
    exit_code = 130 if signum == signal.SIGINT else 128 + int(signum)
    if _SIGNAL_ALREADY_HANDLED:
        os._exit(exit_code)  # noqa: SLF001 - second signal means immediate shutdown
    _SIGNAL_ALREADY_HANDLED = True
    try:
        flush_jsonl_streams()
        written = write_registered_partial_results(signum)
        terminate_registered_processes(grace_seconds=5.0)
        if written:
            typer.echo(
                "InferGuard interrupted; wrote partial results: "
                + ", ".join(str(path) for path in written),
                err=True,
            )
    finally:
        raise SystemExit(exit_code)


install_signal_handlers()


@app.command("preflight")
def preflight_cmd(
    model: Annotated[
        str,
        typer.Option("--model", help="Model family or HF id for compatibility checks."),
    ] = "deepseek-ai/DeepSeek-V4-Pro",
    engine: Annotated[
        str,
        typer.Option("--engine", help="Engine hint: vllm, sglang, dynamo, lmcache, llm-d, or auto."),
    ] = "vllm",
    kv_offloading_backend: Annotated[
        Optional[str],
        typer.Option("--kv-offloading-backend", help="KV offload backend, e.g. native when OFFLOADING=cpu."),
    ] = None,
    disable_hybrid_kv_cache_manager: Annotated[
        bool,
        typer.Option(
            "--disable-hybrid-kv-cache-manager/--no-disable-hybrid-kv-cache-manager",
            help="Whether the serving launch disables the hybrid KV cache manager.",
        ),
    ] = False,
    config: Annotated[
        Optional[Path],
        typer.Option("--config", help="Optional config.json/run config containing topology/preflight fields."),
    ] = None,
    detect_tokenizer_mismatch: Annotated[
        bool,
        typer.Option("--detect-tokenizer-mismatch", help="Probe client/server tokenizer-count drift before rollout."),
    ] = False,
    endpoint: Annotated[
        Optional[str],
        typer.Option("--endpoint", help="Optional OpenAI-compatible /v1/chat/completions endpoint for tokenizer probe."),
    ] = None,
    sample_text: Annotated[
        str,
        typer.Option("--sample-text", help="Known text sent for tokenizer-mismatch probing."),
    ] = "Hello world\nThis is a test of tokenization.",
    client_tokenizer: Annotated[
        str,
        typer.Option("--client-tokenizer", help="Client tokenizer label/version used for preflight evidence."),
    ] = "inferguard-estimator",
    server_tokenizer: Annotated[
        Optional[str],
        typer.Option("--server-tokenizer", help="Optional server tokenizer label/version used for preflight evidence."),
    ] = None,
    client_token_count: Annotated[
        Optional[int],
        typer.Option("--client-token-count", help="Optional explicit client token count for tokenizer probe/testing."),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
) -> None:
    """Run read-only launch compatibility checks before a benchmark."""
    status: dict[str, object] = {
        "engine": None if engine == "auto" else _validated_engine(engine),
        "kv_offloading_backend": kv_offloading_backend,
        "disable_hybrid_kv_cache_manager": disable_hybrid_kv_cache_manager,
    }
    tokenizer_probe: dict[str, object] = {
        "enabled": detect_tokenizer_mismatch,
        "client_tokenizer": client_tokenizer,
        "server_tokenizer": server_tokenizer,
        "sample_text_length": len(sample_text),
        "client_prompt_tokens": client_token_count,
        "server_prompt_tokens": None,
    }
    if config is not None:
        try:
            loaded = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            typer.echo(f"could not read --config: {exc}", err=True)
            raise typer.Exit(code=3) from exc
        if isinstance(loaded, dict):
            topology = loaded.get("topology") if isinstance(loaded.get("topology"), dict) else {}
            status.update(
                {
                    "engine": loaded.get("framework") or topology.get("framework") or status.get("engine"),
                    "kv_offloading_backend": loaded.get("kv_offloading_backend")
                    or topology.get("kv_offloading_backend")
                    or ("native" if str(topology.get("offloading") or "").lower() == "cpu" else status.get("kv_offloading_backend")),
                    "disable_hybrid_kv_cache_manager": loaded.get("disable_hybrid_kv_cache_manager")
                    if loaded.get("disable_hybrid_kv_cache_manager") is not None
                    else topology.get("disable_hybrid_kv_cache_manager", status.get("disable_hybrid_kv_cache_manager")),
                }
            )
            model = str(loaded.get("model") or model)
            probe = loaded.get("tokenizer_mismatch") or loaded.get("tokenizer_probe")
            if isinstance(probe, dict):
                detect_tokenizer_mismatch = detect_tokenizer_mismatch or bool(probe.get("enabled", True))
                tokenizer_probe.update(
                    {
                        "enabled": detect_tokenizer_mismatch,
                        "client_tokenizer": probe.get("client_tokenizer") or tokenizer_probe["client_tokenizer"],
                        "server_tokenizer": probe.get("server_tokenizer") or tokenizer_probe["server_tokenizer"],
                        "client_prompt_tokens": probe.get("client_prompt_tokens")
                        or probe.get("client_token_count")
                        or tokenizer_probe["client_prompt_tokens"],
                        "server_prompt_tokens": probe.get("server_prompt_tokens")
                        or probe.get("usage_prompt_tokens")
                        or tokenizer_probe["server_prompt_tokens"],
                        "sample_text_length": probe.get("sample_text_length") or tokenizer_probe["sample_text_length"],
                    }
                )
    findings = check_hma_offload_compat(status, model)
    if detect_tokenizer_mismatch:
        if tokenizer_probe.get("client_prompt_tokens") is None:
            tokenizer_probe["client_prompt_tokens"] = client_token_count or estimate_text_tokens(sample_text)
        if tokenizer_probe.get("server_prompt_tokens") is None and endpoint:
            try:
                tokenizer_probe["server_prompt_tokens"] = asyncio.run(
                    _probe_server_prompt_tokens(
                        endpoint=endpoint,
                        model=model,
                        sample_text=sample_text,
                        timeout=HTTP_TIMEOUT_SECONDS,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - preflight must report probe setup failures cleanly
                findings.append(
                    DisaggFinding(
                        code="endpoint_unreachable",
                        severity="critical",
                        message=f"Tokenizer mismatch probe failed: {exc}",
                        evidence={"endpoint": endpoint, "probe": "tokenizer_mismatch"},
                    )
                )
        findings.extend(
            check_tokenizer_mismatch(
                client_tokenizer=str(tokenizer_probe.get("client_tokenizer") or client_tokenizer),
                server_tokenizer=(
                    str(tokenizer_probe.get("server_tokenizer"))
                    if tokenizer_probe.get("server_tokenizer") is not None
                    else server_tokenizer
                ),
                client_prompt_tokens=tokenizer_probe.get("client_prompt_tokens"),
                server_prompt_tokens=tokenizer_probe.get("server_prompt_tokens"),
                sample_text_length=int(tokenizer_probe.get("sample_text_length") or len(sample_text)),
            )
        )
    payload = {
        "schema_version": "inferguard-preflight/v1",
        "model": model,
        "status": status,
        "tokenizer_probe": tokenizer_probe if detect_tokenizer_mismatch else None,
        "findings": [finding.as_dict() for finding in findings],
    }
    if json_out:
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    elif findings:
        for finding in findings:
            typer.echo(f"{finding.severity.upper()} {finding.code}: {finding.message}")
    else:
        typer.echo("OK — no preflight findings.")
    raise typer.Exit(code=_exit_code_for_findings(findings))


@app.command("analyze")
def analyze_cmd(
    results_dir: Annotated[Path, typer.Argument(help="Directory containing benchmark artifacts.")],
    output_dir: Annotated[
        Optional[Path],
        typer.Option("--output-dir", help="Destination for generated reports."),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: json, md, or both."),
    ] = "both",
    fail_on: Annotated[
        str,
        typer.Option("--fail-on", help="Exit threshold: never, warning, or critical."),
    ] = "critical",
    strict: Annotated[
        bool,
        typer.Option("--strict/--best-effort", help="Fail on missing required artifacts."),
    ] = False,
    timeline_glob: Annotated[
        str,
        typer.Option("--timeline-glob", help="Discovery pattern for timeline JSONL files."),
    ] = "**/inferguard_timeline.jsonl",
    cost_per_gpu_hour: Annotated[
        Optional[float],
        typer.Option("--cost-per-gpu-hour", help="GPU-hour cost for cost-per-task accounting."),
    ] = None,
    gpus: Annotated[
        Optional[int],
        typer.Option("--gpus", help="GPU count for cost-per-task accounting."),
    ] = None,
    operator_brief: Annotated[
        Optional[bool],
        typer.Option("--operator-brief/--no-operator-brief", help="Emit operator_brief.{json,md}; defaults on when --gpus is provided."),
    ] = None,
    cost_currency: Annotated[
        str,
        typer.Option("--cost-currency", help="Currency label for cost output."),
    ] = "USD",
    plots: Annotated[
        bool,
        typer.Option("--plots", help="After report writes, render SVG plots into <output-dir>/plots/."),
    ] = False,
    emit_agentx_shape_dir: Annotated[
        Optional[Path],
        typer.Option("--emit-agentx-shape", help="Write per-cell agg_*.json files in AgentX/InferenceX shape."),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Also print the generated JSON report to stdout."),
    ] = False,
) -> None:
    """Analyze an existing result directory without launching benchmarks."""
    if output_format not in {"json", "md", "both"}:
        raise typer.BadParameter("--format must be one of json|md|both")
    if fail_on not in {"never", "warning", "critical"}:
        raise typer.BadParameter("--fail-on must be one of never|warning|critical")
    destination = output_dir or (results_dir / "inferguard_report")
    emit_operator_brief = operator_brief if operator_brief is not None else gpus is not None
    try:
        report = analyze_results(
            results_dir,
            AnalyzeOptions(
                output_dir=destination,
                output_format=output_format,
                strict=strict,
                timeline_glob=timeline_glob,
                cost_per_gpu_hour=cost_per_gpu_hour,
                gpus=gpus,
                cost_currency=cost_currency,
                operator_brief=emit_operator_brief,
            ),
        )
    except AnalyzeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except OSError as exc:
        typer.echo(f"report writing failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    if plots:
        try:
            render_plots(report, destination / "plots")
        except ImportError as exc:
            typer.echo(
                f"plot rendering requires matplotlib: {exc}\n"
                "Install with: pip install 'inferguard[plot]'",
                err=True,
            )
            raise typer.Exit(code=3) from exc
    if emit_agentx_shape_dir is not None:
        emit_agentx_shape(report, emit_agentx_shape_dir)
    if json_out:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    raise typer.Exit(code=exit_code_for_report(report, fail_on))



@workload_app.command("analyze")
def workload_analyze_cmd(
    log_dir: Annotated[Path, typer.Argument(help="Directory containing OpenAI-style JSONL logs.")],
    source_format: Annotated[
        str,
        typer.Option("--format", help="Input format. Currently: openai-jsonl."),
    ] = "openai-jsonl",
    emit: Annotated[
        Optional[Path],
        typer.Option("--emit", help="Write workload fingerprint JSON."),
    ] = None,
    emit_md: Annotated[
        Optional[Path],
        typer.Option("--emit-md", help="Write human-readable workload report markdown."),
    ] = None,
    privacy_class: Annotated[
        str,
        typer.Option("--privacy-class", help="public, private, or regulated."),
    ] = "public",
    latency_sensitivity: Annotated[
        str,
        typer.Option("--latency-sensitivity", help="tight, loose, or batch."),
    ] = "loose",
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Print fingerprint JSON to stdout."),
    ] = False,
) -> None:
    """Generate a pre-flight workload fingerprint without launching benchmarks."""
    try:
        fingerprint = analyze_workload_dir(
            log_dir,
            source_format=source_format,
            privacy_class=privacy_class,
            latency_sensitivity=latency_sensitivity,
        )
        if emit is not None:
            emit.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(emit, fingerprint.as_dict())
        if emit_md is not None:
            emit_md.parent.mkdir(parents=True, exist_ok=True)
            emit_md.write_text(render_fingerprint_markdown(fingerprint), encoding="utf-8")
    except (OSError, WorkloadAnalyzeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    if json_out or emit is None:
        sys.stdout.write(json.dumps(fingerprint.as_dict(), indent=2, sort_keys=True) + "\n")
    raise typer.Exit(code=0)


@router_app.command("classify")
def router_classify_cmd(
    run_dir: Annotated[Path, typer.Argument(help="Directory containing InferGuard or AgentX artifacts.")],
    workload_fingerprint: Annotated[
        Optional[Path],
        typer.Option("--workload-fingerprint", help="Fingerprint JSON from `inferguard workload analyze`."),
    ] = None,
    slo: Annotated[
        Optional[str],
        typer.Option("--slo", help="Comma-separated SLOs, e.g. p95_ttft_ms=1000,error_rate_max=0.01."),
    ] = None,
    hardware_fleet: Annotated[
        Optional[str],
        typer.Option("--hardware-fleet", help="Comma-separated hardware labels, e.g. h200,b200,gb200."),
    ] = None,
    emit: Annotated[
        Optional[Path],
        typer.Option("--emit", help="Write router verdict JSON."),
    ] = None,
    emit_md: Annotated[
        Optional[Path],
        typer.Option("--emit-md", help="Write router verdict markdown."),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Print verdict JSON to stdout."),
    ] = False,
) -> None:
    """Classify bottlenecks and rank execution paths from run artifacts."""
    try:
        verdict = classify_run_dir(
            run_dir,
            workload_fingerprint_path=workload_fingerprint,
            slo=_parse_float_kv_csv(slo, "--slo"),
            hardware_fleet=_parse_string_csv(hardware_fleet),
        )
        if emit is not None:
            emit.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(emit, verdict.as_dict())
        if emit_md is not None:
            emit_md.parent.mkdir(parents=True, exist_ok=True)
            emit_md.write_text(render_verdict_markdown(verdict), encoding="utf-8")
    except (OSError, RouterClassifyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    if json_out or emit is None:
        sys.stdout.write(json.dumps(verdict.as_dict(), indent=2, sort_keys=True) + "\n")
    raise typer.Exit(code=0)


@app.command("emit-bundle")
def emit_bundle_cmd(
    verdict: Annotated[Path, typer.Argument(help="Router verdict JSON from `inferguard router classify`.")],
    output_dir: Annotated[
        Path,
        typer.Option("--output", help="Destination bundle directory."),
    ],
    target: Annotated[
        str,
        typer.Option("--target", help="Bundle target. Currently: slurm."),
    ] = "slurm",
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Print bundle manifest JSON to stdout."),
    ] = False,
) -> None:
    """Emit a deployment bundle from a router verdict."""
    try:
        manifest = emit_bundle(verdict, output_dir, target=target)
    except (OSError, BundleEmitError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    if json_out:
        sys.stdout.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    else:
        typer.echo(f"Wrote InferGuard deployment bundle to {output_dir}.")
    raise typer.Exit(code=0)


@profile_app.command("live")
def profile_live_cmd(
    endpoint: Annotated[
        str,
        typer.Option("--endpoint", help="Serving endpoint base URL or /metrics URL to observe."),
    ],
    duration: Annotated[
        float,
        typer.Option("--duration", help="Sampling window in seconds."),
    ] = 60.0,
    interval: Annotated[
        float,
        typer.Option("--interval", help="Seconds between /metrics scrapes."),
    ] = 2.0,
    engine: Annotated[
        str,
        typer.Option("--engine", help="Engine hint: auto, vllm, sglang, dynamo, lmcache, llm-d."),
    ] = "auto",
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory for profile.jsonl/profile_summary.json/profile.md."),
    ] = Path("inferguard_profile_live"),
    output_format: Annotated[
        str,
        typer.Option("--format", help="Streaming output format: table or json."),
    ] = "table",
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="HTTP timeout per metrics scrape (seconds)."),
    ] = HTTP_TIMEOUT_SECONDS,
) -> None:
    """Observe an existing endpoint without generating traffic."""
    try:
        result = asyncio.run(
            run_profile_live(
                ProfileLiveOptions(
                    endpoint=endpoint,
                    duration_seconds=duration,
                    interval_seconds=interval,
                    engine=_validated_engine(engine),
                    output_dir=output_dir,
                    timeout_seconds=timeout,
                    output_format=output_format,
                ),
                emit=typer.echo,
            )
        )
    except ProfileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except OSError as exc:
        typer.echo(f"profile artifact writing failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    summary = result["summary"]
    if output_format == "table":
        typer.echo(f"Wrote InferGuard profile artifacts to {output_dir}.")
    raise typer.Exit(code=_exit_code_for_findings(summary.findings))


@profile_app.command("retro")
def profile_retro_cmd(
    input_path: Annotated[
        Path,
        typer.Argument(help="Existing profile.jsonl or metrics timeline JSONL file."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory for profile_summary.json/profile.md."),
    ] = Path("inferguard_profile_retro"),
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Print summary JSON to stdout."),
    ] = False,
) -> None:
    """Summarize an existing profile/timeline JSONL file."""
    try:
        summary = run_profile_retro(input_path, output_dir)
    except (ProfileRetroError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    if json_out:
        sys.stdout.write(json.dumps(summary.as_dict(), indent=2, sort_keys=True) + "\n")
    else:
        typer.echo(f"Wrote InferGuard retro profile artifacts to {output_dir}.")
    raise typer.Exit(code=_exit_code_for_findings(summary.findings))


@bench_app.command("replay")
def bench_replay_cmd(
    endpoint: Annotated[
        str,
        typer.Option("--endpoint", help="OpenAI-compatible /v1/chat/completions endpoint."),
    ],
    model: Annotated[str, typer.Option("--model", help="Model name sent in chat requests.")],
    trace_dir: Annotated[
        Path,
        typer.Option("--trace-dir", help="Directory containing InferGuard trace JSONL files."),
    ],
    concurrency: Annotated[
        str,
        typer.Option("--concurrency", help="Comma-separated concurrency levels, e.g. 1,4,8,16,32."),
    ] = "1,4,8,16,32",
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory for run.json/config.json/JSONL/summary/report."),
    ] = Path("inferguard_bench_replay"),
    output_tokens: Annotated[
        int,
        typer.Option("--output-tokens", help="Fallback max output tokens when trace does not specify expected_output_tokens."),
    ] = 512,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="HTTP timeout per request in seconds."),
    ] = 300.0,
    duration_seconds: Annotated[
        Optional[float],
        typer.Option("--duration-seconds", help="Run each concurrency level for this many seconds instead of one finite pass."),
    ] = None,
    warmup_seconds: Annotated[
        float,
        typer.Option("--warmup-seconds", help="Exclude this many initial seconds per level from summary metrics."),
    ] = 0.0,
    metrics_url: Annotated[
        Optional[str],
        typer.Option("--metrics-url", help="Optional engine metrics URL to scrape during the bench."),
    ] = None,
    metrics_interval: Annotated[
        float,
        typer.Option("--metrics-interval", help="Seconds between engine metrics scrapes."),
    ] = 5.0,
    metrics_engine: Annotated[
        str,
        typer.Option("--metrics-engine", help="Engine hint for metrics detection: auto, vllm, sglang, dynamo, llm-d."),
    ] = "auto",
    force: Annotated[
        bool,
        typer.Option("--force", help="Allow writing into a non-empty output directory; known artifact files may be overwritten."),
    ] = False,
    redact_prompts: Annotated[
        bool,
        typer.Option("--redact-prompts", help="Replace prompt content with <redacted> in requests.jsonl."),
    ] = False,
    track_cache_lineage: Annotated[
        bool,
        typer.Option("--track-cache-lineage", help="Track request-level prefix-cache lineage scaffold."),
    ] = False,
    idle_active_mix_mode: Annotated[
        bool,
        typer.Option("--idle-active-mix-mode", help="Alternate active request windows with idle windows for S-14 cost economics."),
    ] = False,
    active_window_seconds: Annotated[
        float,
        typer.Option("--active-window-seconds", help="Active traffic window length for --idle-active-mix-mode."),
    ] = 60.0,
    idle_window_seconds: Annotated[
        float,
        typer.Option("--idle-window-seconds", help="Idle traffic window length for --idle-active-mix-mode."),
    ] = 30.0,
    inject_giant_prefill_tokens: Annotated[
        Optional[int],
        typer.Option("--inject-giant-prefill-tokens", help="Inject one oversized prefill request; requires --allow-chaos."),
    ] = None,
    allow_chaos: Annotated[
        bool,
        typer.Option("--allow-chaos", help="Allow chaos-mode replay injections."),
    ] = False,
    canary_eval_set: Annotated[
        Optional[str],
        typer.Option("--canary-eval-set", help="Held-out eval set path or HuggingFace dataset id for canary quality scoring."),
    ] = None,
    tool_call_schema: Annotated[
        Optional[Path],
        typer.Option("--tool-call-schema", help="JSON schema describing expected tool-call response format."),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Print summary JSON to stdout."),
    ] = False,
) -> None:
    """Replay trace JSONL records against a streaming chat-completions endpoint."""
    config = BenchConfig(
        command="replay",
        endpoint=endpoint,
        model=model,
        trace_dir=trace_dir,
        concurrency_levels=_parse_int_csv(concurrency, "--concurrency"),
        output_dir=output_dir,
        output_tokens=output_tokens,
        timeout_seconds=timeout,
        duration_seconds=duration_seconds,
        warmup_seconds=warmup_seconds,
        metrics_url=metrics_url,
        metrics_interval_seconds=metrics_interval,
        metrics_engine=_validated_metrics_engine(metrics_engine),
        force=force,
        redact_prompts=redact_prompts,
        track_cache_lineage=track_cache_lineage,
        idle_active_mix_mode=idle_active_mix_mode,
        active_window_seconds=active_window_seconds,
        idle_window_seconds=idle_window_seconds,
        inject_giant_prefill_tokens=inject_giant_prefill_tokens,
        allow_chaos=allow_chaos,
        canary_eval_set=canary_eval_set,
        tool_call_schema=tool_call_schema,
    )
    _run_bench(config, run_replay, json_out=json_out)


@bench_app.command("upstream")
def bench_upstream_cmd(
    engine: Annotated[
        str,
        typer.Argument(help="Upstream engine to run: vllm or sglang."),
    ],
    profile: Annotated[
        str,
        typer.Option("--profile", help="Profile: vLLM random|sharegpt|prefix-repetition|sonnet; SGLang random."),
    ],
    model: Annotated[str, typer.Option("--model", help="Model name passed to the upstream bench.")],
    endpoint: Annotated[
        str,
        typer.Option("--endpoint", help="Engine endpoint base URL, e.g. http://localhost:8000."),
    ] = "http://localhost:8000",
    num_prompts: Annotated[
        int,
        typer.Option("--num-prompts", help="Number of prompts passed to the upstream bench."),
    ] = 100,
    request_rate: Annotated[
        Optional[float],
        typer.Option("--request-rate", help="Optional upstream request-rate limit."),
    ] = None,
    dataset_path: Annotated[
        Optional[Path],
        typer.Option("--dataset-path", help="Optional upstream dataset path for dataset-backed profiles."),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory for run/config/requests/metrics/summary artifacts."),
    ] = Path("inferguard_bench_upstream"),
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Subprocess timeout in seconds."),
    ] = 300.0,
    enable_radix_cache: Annotated[
        Optional[bool],
        typer.Option(
            "--enable-radix-cache/--disable-radix-cache",
            help="Set SGLANG_ENABLE_RADIX_CACHE=1/0 for SGLang upstream runs.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Allow writing into a non-empty output directory."),
    ] = False,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Print summary JSON to stdout."),
    ] = False,
) -> None:
    """Run vLLM/SGLang native benchmark CLIs and normalize their artifacts."""
    if engine not in {"vllm", "sglang"}:
        raise typer.BadParameter("engine must be vllm or sglang")
    if num_prompts <= 0:
        raise typer.BadParameter("--num-prompts must be positive")
    if timeout <= 0:
        raise typer.BadParameter("--timeout must be positive")
    if request_rate is not None and request_rate <= 0:
        raise typer.BadParameter("--request-rate must be positive")
    config = UpstreamBenchConfig(
        engine=engine,  # type: ignore[arg-type]
        profile=profile,
        model=model,
        endpoint=endpoint,
        output_dir=output_dir,
        num_prompts=num_prompts,
        request_rate=request_rate,
        timeout_seconds=timeout,
        dataset_path=dataset_path,
        force=force,
        enable_radix_cache=enable_radix_cache,
    )
    _run_upstream_bench(config, json_out=json_out)


@bench_app.command("compare")
def bench_compare_cmd(
    run_a_dir: Annotated[
        Path,
        typer.Argument(help="First InferGuard bench run directory."),
    ],
    run_b_dir: Annotated[
        Path,
        typer.Argument(help="Second InferGuard bench run directory."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory for compare.json and compare.md."),
    ] = Path("inferguard_bench_compare"),
    label_a: Annotated[
        Optional[str],
        typer.Option("--label-a", help="Display label for the first run, e.g. vllm."),
    ] = None,
    label_b: Annotated[
        Optional[str],
        typer.Option("--label-b", help="Display label for the second run, e.g. sglang."),
    ] = None,
    min_identity_overlap: Annotated[
        float,
        typer.Option("--min-identity-overlap", help="Required trace_id+turn_index overlap ratio; must be > this value."),
    ] = 0.50,
    strict_identity: Annotated[
        bool,
        typer.Option("--strict-identity", help="Fail instead of warning when trace identity overlap is too low."),
    ] = False,
    cost_per_gpu_hour: Annotated[
        Optional[float],
        typer.Option("--cost-per-gpu-hour", help="Optional GPU-hour cost for cost-per-task deltas."),
    ] = None,
    gpus: Annotated[
        Optional[int],
        typer.Option("--gpus", help="GPU count for cost-per-task deltas."),
    ] = None,
    blue_green: Annotated[
        bool,
        typer.Option("--blue-green", help="Treat run A as blue/baseline and run B as green/candidate; emit rollout p99 regression findings."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Allow overwriting compare artifacts in a non-empty output directory."),
    ] = False,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Print compare JSON to stdout."),
    ] = False,
) -> None:
    """Compare two bench run directories for cross-engine parity."""
    options = CompareOptions(
        output_dir=output_dir,
        label_a=label_a,
        label_b=label_b,
        min_identity_overlap=min_identity_overlap,
        strict_identity=strict_identity,
        cost_per_gpu_hour=cost_per_gpu_hour,
        gpus=gpus,
        blue_green=blue_green,
        force=force,
    )
    _run_compare(run_a_dir, run_b_dir, options, json_out=json_out)


@bench_app.command("agentx-replay")
def bench_agentx_replay_cmd(
    endpoint: Annotated[
        str,
        typer.Option("--endpoint", help="OpenAI-compatible API endpoint base URL."),
    ],
    model: Annotated[str, typer.Option("--model", help="Model label for InferGuard artifacts.")],
    trace_source: Annotated[
        str,
        typer.Option("--trace-source", help="Hugging Face dataset name or local trace directory."),
    ],
    concurrency: Annotated[
        int,
        typer.Option("--concurrency", help="AgentX concurrent users; used for start-users and max-users."),
    ] = 1,
    duration_seconds: Annotated[
        int,
        typer.Option("--duration-seconds", help="AgentX replay duration in seconds; warns below 900s/15min."),
    ] = 1800,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory for InferGuard AgentX replay artifacts."),
    ] = Path("inferguard_bench_agentx_replay"),
    tester_path: Annotated[
        Optional[Path],
        typer.Option("--tester-path", help="Path to trace_replay_tester.py or a kv-cache-tester checkout."),
    ] = None,
    allow_network_clone: Annotated[
        bool,
        typer.Option("--allow-network-clone", help="Clone kv-cache-tester into ~/.cache/inferguard/agentx-tester if missing."),
    ] = False,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Print summary JSON to stdout."),
    ] = False,
) -> None:
    """Run AgentX trace replay and convert detailed_results.csv to InferGuard artifacts."""
    if concurrency <= 0:
        raise typer.BadParameter("--concurrency must be a positive integer")
    if duration_seconds <= 0:
        raise typer.BadParameter("--duration-seconds must be a positive integer")
    config = AgentXReplayConfig(
        endpoint=endpoint,
        model=model,
        trace_source=trace_source,
        concurrency=concurrency,
        duration_seconds=duration_seconds,
        output_dir=output_dir,
        tester_path=tester_path,
        allow_network_clone=allow_network_clone,
    )
    _run_agentx_bench(config, json_out=json_out)


@bench_app.command("kv-stress")
def bench_kv_stress_cmd(
    endpoint: Annotated[
        str,
        typer.Option("--endpoint", help="OpenAI-compatible /v1/chat/completions endpoint."),
    ],
    model: Annotated[str, typer.Option("--model", help="Model name sent in chat requests.")],
    context_lengths: Annotated[
        str,
        typer.Option("--context-lengths", help="Comma-separated approximate input token targets."),
    ] = "8192,32768,65536,131072,524288,1048576",
    concurrency: Annotated[
        str,
        typer.Option("--concurrency", help="Comma-separated concurrency levels, e.g. 1,4,8,16."),
    ] = "1,4,8,16",
    output_tokens: Annotated[
        int,
        typer.Option("--output-tokens", help="Max streamed output tokens per request."),
    ] = 512,
    mode: Annotated[
        str,
        typer.Option("--mode", help="KVCast mode: cold-pressure, prefix-reuse, mixed-agent, eviction-probe, or fragmentation-probe."),
    ] = "cold-pressure",
    requests_per_level: Annotated[
        int,
        typer.Option("--requests-per-level", help="Synthetic requests generated per context length."),
    ] = 4,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory for run.json/config.json/JSONL/summary/report."),
    ] = Path("inferguard_bench_kv_stress"),
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="HTTP timeout per request in seconds."),
    ] = 300.0,
    duration_seconds: Annotated[
        Optional[float],
        typer.Option("--duration-seconds", help="Run each concurrency level for this many seconds instead of one finite pass."),
    ] = None,
    warmup_seconds: Annotated[
        float,
        typer.Option("--warmup-seconds", help="Exclude this many initial seconds per level from summary metrics."),
    ] = 0.0,
    metrics_url: Annotated[
        Optional[str],
        typer.Option("--metrics-url", help="Optional engine metrics URL to scrape during the bench."),
    ] = None,
    metrics_interval: Annotated[
        float,
        typer.Option("--metrics-interval", help="Seconds between engine metrics scrapes."),
    ] = 5.0,
    metrics_engine: Annotated[
        str,
        typer.Option("--metrics-engine", help="Engine hint for metrics detection: auto, vllm, sglang, dynamo, llm-d."),
    ] = "auto",
    force: Annotated[
        bool,
        typer.Option("--force", help="Allow writing into a non-empty output directory; known artifact files may be overwritten."),
    ] = False,
    redact_prompts: Annotated[
        bool,
        typer.Option("--redact-prompts", help="Replace prompt content with <redacted> in requests.jsonl."),
    ] = False,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Print summary JSON to stdout."),
    ] = False,
) -> None:
    """Generate synthetic KVCast prompts and infer cache pressure from request shape."""
    config = BenchConfig(
        command="kv-stress",
        endpoint=endpoint,
        model=model,
        context_lengths=_parse_int_csv(context_lengths, "--context-lengths"),
        concurrency_levels=_parse_int_csv(concurrency, "--concurrency"),
        output_dir=output_dir,
        output_tokens=output_tokens,
        timeout_seconds=timeout,
        duration_seconds=duration_seconds,
        warmup_seconds=warmup_seconds,
        metrics_url=metrics_url,
        metrics_interval_seconds=metrics_interval,
        metrics_engine=_validated_metrics_engine(metrics_engine),
        force=force,
        redact_prompts=redact_prompts,
        kvcast_mode=_validated_kvcast_mode(mode),
        requests_per_level=requests_per_level,
    )
    _run_bench(config, run_kv_stress, json_out=json_out)


@bench_app.command("kvcast")
def bench_kvcast_cmd(
    endpoint: Annotated[
        str,
        typer.Option("--endpoint", help="OpenAI-compatible /v1/chat/completions endpoint."),
    ],
    model: Annotated[str, typer.Option("--model", help="Model name sent in chat requests.")],
    context_lengths: Annotated[
        str,
        typer.Option("--context-lengths", help="Comma-separated approximate input token targets."),
    ] = "8192,32768,65536,131072,524288,1048576",
    concurrency: Annotated[
        str,
        typer.Option("--concurrency", help="Comma-separated concurrency levels, e.g. 1,4,8,16."),
    ] = "1,4,8,16",
    mode: Annotated[
        str,
        typer.Option("--mode", help="KVCast mode: cold-pressure, prefix-reuse, mixed-agent, eviction-probe, fragmentation-probe, multi-tenant-storm, or retry-storm."),
    ] = "cold-pressure",
    output_tokens: Annotated[
        int,
        typer.Option("--output-tokens", help="Max streamed output tokens per request."),
    ] = 512,
    requests_per_level: Annotated[
        int,
        typer.Option("--requests-per-level", help="Synthetic requests generated per context length."),
    ] = 4,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory for run.json/config.json/JSONL/summary/report."),
    ] = Path("inferguard_bench_kvcast"),
    timeout: Annotated[float, typer.Option("--timeout", help="HTTP timeout per request in seconds.")] = 300.0,
    duration_seconds: Annotated[
        Optional[float],
        typer.Option("--duration-seconds", help="Run each concurrency level for this many seconds instead of one finite pass."),
    ] = None,
    warmup_seconds: Annotated[
        float,
        typer.Option("--warmup-seconds", help="Exclude this many initial seconds per level from summary metrics."),
    ] = 0.0,
    arrival_mode: Annotated[
        str,
        typer.Option("--arrival-mode", help="Arrival scheduler: steady or poisson."),
    ] = "steady",
    arrival_rate_rps: Annotated[
        Optional[float],
        typer.Option("--arrival-rate-rps", help="Mean request arrivals per second for --arrival-mode poisson."),
    ] = None,
    metrics_url: Annotated[
        Optional[str],
        typer.Option("--metrics-url", help="Optional engine metrics URL to scrape during the bench."),
    ] = None,
    metrics_interval: Annotated[
        float,
        typer.Option("--metrics-interval", help="Seconds between engine metrics scrapes."),
    ] = 5.0,
    metrics_engine: Annotated[
        str,
        typer.Option("--metrics-engine", help="Engine hint for metrics detection: auto, vllm, sglang, dynamo, llm-d."),
    ] = "auto",
    force: Annotated[
        bool,
        typer.Option("--force", help="Allow writing into a non-empty output directory; known artifact files may be overwritten."),
    ] = False,
    redact_prompts: Annotated[
        bool,
        typer.Option("--redact-prompts", help="Replace prompt content with <redacted> in requests.jsonl."),
    ] = False,
    customers: Annotated[
        int,
        typer.Option("--customers", help="Customer count for --mode multi-tenant-storm."),
    ] = 1,
    sla_tiers: Annotated[
        Optional[str],
        typer.Option("--sla-tiers", help="Comma-separated SLA tier policies, e.g. premium=p99<2s,standard=p99<5s."),
    ] = None,
    track_cache_lineage: Annotated[
        bool,
        typer.Option("--track-cache-lineage", help="Track request-level prefix-cache lineage scaffold."),
    ] = False,
    burst_multiplier: Annotated[
        float,
        typer.Option("--burst-multiplier", help="Retry-storm burst QPS multiplier over --baseline-rps."),
    ] = 50.0,
    burst_window_seconds: Annotated[
        float,
        typer.Option("--burst-window-seconds", help="Retry-storm burst duration in seconds."),
    ] = 30.0,
    baseline_rps: Annotated[
        float,
        typer.Option("--baseline-rps", help="Retry-storm baseline request rate before/after burst."),
    ] = 4.0,
    inject_crash_after_seconds: Annotated[
        Optional[float],
        typer.Option("--inject-crash-after-seconds", help="Test-only crash injection delay; requires --allow-chaos."),
    ] = None,
    allow_chaos: Annotated[
        bool,
        typer.Option("--allow-chaos", help="Allow test-only crash injection scaffolding."),
    ] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Print summary JSON to stdout.")] = False,
) -> None:
    """Run KVCast synthetic cache stress modes."""
    config = BenchConfig(
        command="kvcast",
        endpoint=endpoint,
        model=model,
        context_lengths=_parse_int_csv(context_lengths, "--context-lengths"),
        concurrency_levels=_parse_int_csv(concurrency, "--concurrency"),
        output_dir=output_dir,
        output_tokens=output_tokens,
        timeout_seconds=timeout,
        duration_seconds=duration_seconds,
        warmup_seconds=warmup_seconds,
        arrival_mode=_validated_arrival_mode(arrival_mode),
        arrival_rate_rps=arrival_rate_rps,
        metrics_url=metrics_url,
        metrics_interval_seconds=metrics_interval,
        metrics_engine=_validated_metrics_engine(metrics_engine),
        force=force,
        redact_prompts=redact_prompts,
        kvcast_mode=_validated_kvcast_mode(mode),
        requests_per_level=requests_per_level,
        customers=customers,
        sla_tiers=_parse_sla_tiers(sla_tiers),
        track_cache_lineage=track_cache_lineage,
        inject_crash_after_seconds=inject_crash_after_seconds,
        allow_chaos=allow_chaos,
        burst_multiplier=burst_multiplier,
        burst_window_seconds=burst_window_seconds,
        baseline_rps=baseline_rps,
    )
    _run_bench(config, run_kv_stress, json_out=json_out)

@bench_app.command("cold-start")
def bench_cold_start_cmd(
    endpoint: Annotated[str, typer.Option("--endpoint", help="OpenAI-compatible /v1/chat/completions endpoint.")],
    model: Annotated[str, typer.Option("--model", help="Model name sent in chat requests.")],
    trace_dir: Annotated[Optional[Path], typer.Option("--trace-dir", help="Optional InferGuard trace JSONL directory.")] = None,
    output_dir: Annotated[Path, typer.Option("--output-dir", help="Directory for cold-start artifacts.")] = Path("inferguard_bench_cold_start"),
    capture_seconds: Annotated[float, typer.Option("--capture-seconds", help="Cold-start capture window from process spawn/readiness.")] = 60.0,
    context_lengths: Annotated[str, typer.Option("--context-lengths", help="Synthetic context lengths when --trace-dir is omitted.")] = "1024",
    concurrency: Annotated[str, typer.Option("--concurrency", help="Comma-separated concurrency levels.")] = "1",
    output_tokens: Annotated[int, typer.Option("--output-tokens", help="Max streamed output tokens per request.")] = 64,
    metrics_url: Annotated[Optional[str], typer.Option("--metrics-url", help="Optional engine metrics URL to scrape during cold start.")] = None,
    metrics_interval: Annotated[float, typer.Option("--metrics-interval", help="Seconds between engine metrics scrapes.")] = 5.0,
    metrics_engine: Annotated[str, typer.Option("--metrics-engine", help="Engine hint for metrics detection: auto, vllm, sglang, dynamo, llm-d.")] = "auto",
    force: Annotated[bool, typer.Option("--force", help="Allow writing into a non-empty output directory.")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Print summary JSON to stdout.")] = False,
) -> None:
    """Capture first-60s cold-start ramp from endpoint readiness."""
    config = BenchConfig(
        command="cold-start",
        endpoint=endpoint,
        model=model,
        trace_dir=trace_dir,
        context_lengths=_parse_int_csv(context_lengths, "--context-lengths"),
        concurrency_levels=_parse_int_csv(concurrency, "--concurrency"),
        output_dir=output_dir,
        output_tokens=output_tokens,
        duration_seconds=capture_seconds,
        cold_start_capture_seconds=capture_seconds,
        metrics_url=metrics_url,
        metrics_interval_seconds=metrics_interval,
        metrics_engine=_validated_metrics_engine(metrics_engine),
        force=force,
    )
    _run_bench(config, run_cold_start, json_out=json_out)



@app.command("validate-completed")
def validate_completed_cmd(
    results_root: Annotated[
        Path,
        typer.Option("--results-root", help="Run directory to validate."),
    ] = ...,
    matrix_plan: Annotated[
        Optional[Path],
        typer.Option("--matrix-plan", help="Override matrix_plan.json location."),
    ] = None,
    artifact_contract: Annotated[
        Optional[Path],
        typer.Option("--artifact-contract", help="Override expected_artifact_contract.json location."),
    ] = None,
    output_dir: Annotated[
        Optional[Path],
        typer.Option("--output-dir", help="Output directory for validation artifacts."),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Return non-zero unless the run is live_complete."),
    ] = False,
    label_overrides: Annotated[
        Optional[Path],
        typer.Option("--label-overrides", help="JSON {claim_id: claim_status} for human-reviewed downgrades."),
    ] = None,
    json_only: Annotated[
        bool,
        typer.Option("--json-only", help="Skip markdown rendering."),
    ] = False,
) -> None:
    """Validate completed runs before any publishability or operator claim."""
    from inferguard.validate import validate_run
    from inferguard.validate.render import render_validation_markdown

    root = results_root
    plan_path = matrix_plan or root / "matrix_plan.json"
    contract_path = artifact_contract or root / "expected_artifact_contract.json"
    target = output_dir or root
    target.mkdir(parents=True, exist_ok=True)
    report = validate_run(
        root,
        contract=contract_path,
        plan=plan_path,
        overrides=label_overrides,
    )
    _phase_bc_write_json(target / "validation_report.json", report.to_dict())
    if not json_only:
        (target / "validation_report.md").write_text(
            render_validation_markdown(report),
            encoding="utf-8",
        )
    summary = report.summary
    typer.echo(
        "inferguard validate-completed: "
        f"status={report.status} "
        f"jobs={len(report.jobs)} "
        f"live={summary.get('live_complete', 0)} "
        f"synthetic={summary.get('synthetic_only', 0)} "
        f"incomplete={summary.get('live_incomplete', 0)} "
        f"missing={summary.get('missing_required_artifacts', 0)}"
    )
    if strict and report.status != "live_complete":
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


@app.command("request-profile")
def request_profile_cmd(
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Output directory for request-profile artifacts."),
    ] = ...,
    endpoint_url: Annotated[
        str,
        typer.Option("--endpoint", help="OpenAI-compatible chat-completions endpoint."),
    ] = ...,
    model: Annotated[
        str,
        typer.Option("--model", help="Model name sent in profile requests."),
    ] = ...,
    input_jsonl: Annotated[
        Path,
        typer.Option("--input-jsonl", help="JSONL request/profile input file."),
    ] = ...,
    concurrency: Annotated[
        Optional[str],
        typer.Option("--concurrency", help="Closed-loop concurrency level."),
    ] = None,
    timeout_seconds: Annotated[
        float,
        typer.Option("--timeout-seconds", help="HTTP timeout per request."),
    ] = 300.0,
    arrival_mode: Annotated[
        Optional[str],
        typer.Option("--arrival-mode", help="Arrival mode: closed_loop or poisson."),
    ] = None,
    rate_rps: Annotated[
        Optional[float],
        typer.Option("--rate-rps", help="Poisson arrival rate in requests per second."),
    ] = None,
    max_requests: Annotated[
        Optional[int],
        typer.Option("--max-requests", help="Maximum request rows to issue."),
    ] = None,
    api_key: Annotated[
        Optional[str],
        typer.Option("--api-key", help="Optional bearer token for the endpoint."),
    ] = None,
    stream: Annotated[
        bool,
        typer.Option("--stream", help="Use streaming chat completions."),
    ] = False,
    include_usage: Annotated[
        bool,
        typer.Option("--include-usage", help="Request OpenAI stream usage when streaming."),
    ] = False,
    continuous_usage_stats: Annotated[
        bool,
        typer.Option("--continuous-usage-stats", help="Request continuous usage stats when supported."),
    ] = False,
    workload_label: Annotated[
        Optional[str],
        typer.Option("--workload-label", help="Workload label stamped into artifacts."),
    ] = None,
    job_id: Annotated[
        Optional[str],
        typer.Option("--job-id", help="Optional job id stamped into artifacts."),
    ] = None,
    seed: Annotated[
        int,
        typer.Option("--seed", help="Deterministic scheduler seed."),
    ] = 0,
    engine: Annotated[
        Optional[str],
        typer.Option("--engine", help="Engine label stamped into artifacts."),
    ] = None,
    model_profile: Annotated[
        Optional[str],
        typer.Option("--model-profile", help="Model architecture/profile label."),
    ] = None,
) -> None:
    """Profile per-request TTFT, TPOT, E2E latency, and failures."""
    from inferguard.request_profile import format_stdout_summary, profile_endpoint

    if concurrency is not None and int(concurrency) <= 0:
        raise typer.BadParameter("--concurrency must be positive")
    if arrival_mode not in {None, "closed_loop", "poisson"}:
        raise typer.BadParameter("--arrival-mode must be one of closed_loop|poisson")
    if arrival_mode == "poisson" and (rate_rps is None or rate_rps <= 0):
        raise typer.BadParameter("--rate-rps is required when --arrival-mode=poisson")
    if max_requests is not None and max_requests <= 0:
        raise typer.BadParameter("--max-requests must be positive")
    summary = profile_endpoint(
        endpoint=endpoint_url,
        model=model,
        input_jsonl=input_jsonl,
        output_dir=output_dir,
        concurrency=int(concurrency or 1),
        timeout_seconds=timeout_seconds,
        arrival_mode=arrival_mode or "closed_loop",
        rate_rps=rate_rps,
        max_requests=max_requests,
        api_key=api_key,
        stream=stream,
        include_usage=include_usage,
        continuous_usage_stats=continuous_usage_stats,
        workload_label=workload_label or "default",
        job_id=job_id,
        seed=seed,
        engine=engine or "vllm",
        model_profile=model_profile,
    )
    typer.echo(format_stdout_summary(summary))
    raise typer.Exit(code=0)


@app.command("collect-metrics")
def collect_metrics_cmd(
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Output directory for metrics artifacts."),
    ] = ...,
    engine: Annotated[
        str,
        typer.Option("--engine", help="Engine: vllm, sglang, lmcache, or dynamo-sglang."),
    ] = ...,
    engine_metrics_url: Annotated[
        str,
        typer.Option("--engine-metrics-url", help="Serving-engine Prometheus metrics URL."),
    ] = ...,
    dcgm_metrics_url: Annotated[
        Optional[str],
        typer.Option("--dcgm-metrics-url", help="DCGM exporter Prometheus metrics URL."),
    ] = None,
    duration_seconds: Annotated[
        int,
        typer.Option("--duration-seconds", help="Collection duration in seconds."),
    ] = ...,
    interval_seconds: Annotated[
        float,
        typer.Option("--interval-seconds", help="Engine scrape interval in seconds."),
    ] = 1.0,
    dcgm_interval_seconds: Annotated[
        float,
        typer.Option("--dcgm-interval-seconds", help="DCGM timestamp window in seconds."),
    ] = 5.0,
    lmcache_metrics_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-metrics-url", help="Optional LMCache metrics URL."),
    ] = None,
    label_job_id: Annotated[
        Optional[str],
        typer.Option("--label-job-id", help="Job id label for normalized metrics."),
    ] = None,
    label_engine_version: Annotated[
        Optional[str],
        typer.Option("--label-engine-version", help="Engine version label for normalized metrics."),
    ] = None,
    label_hardware: Annotated[
        Optional[str],
        typer.Option("--label-hardware", help="Hardware label for normalized metrics."),
    ] = None,
    keep_raw_samples: Annotated[
        bool,
        typer.Option("--keep-raw-samples", help="Keep raw Prometheus samples alongside normalized timelines."),
    ] = False,
) -> None:
    """Collect normalized engine and GPU metric timelines for live evidence."""
    from inferguard.collect_metrics import CollectMetricsOptions, collect_metrics

    if engine not in {"vllm", "sglang", "lmcache", "dynamo-sglang"}:
        raise typer.BadParameter("--engine must be one of vllm|sglang|lmcache|dynamo-sglang")
    if duration_seconds <= 0:
        raise typer.BadParameter("--duration-seconds must be a positive integer for collect-metrics")
    if interval_seconds <= 0:
        raise typer.BadParameter("--interval-seconds must be positive for collect-metrics")
    if dcgm_metrics_url and dcgm_interval_seconds <= 0:
        raise typer.BadParameter("--dcgm-interval-seconds must be positive for collect-metrics")
    collect_metrics(
        CollectMetricsOptions(
            engine=engine,
            engine_metrics_url=engine_metrics_url,
            dcgm_metrics_url=dcgm_metrics_url,
            duration_seconds=float(duration_seconds),
            output_dir=output_dir,
            interval_seconds=interval_seconds,
            dcgm_interval_seconds=dcgm_interval_seconds,
            lmcache_metrics_url=lmcache_metrics_url,
            label_job_id=label_job_id,
            label_engine_version=label_engine_version,
            label_hardware=label_hardware,
            keep_raw_samples=keep_raw_samples,
        )
    )
    raise typer.Exit(code=0)


@app.command("lmcache-compat")
def lmcache_compat_cmd(
    engine_metrics_url: Annotated[
        Optional[str],
        typer.Option("--engine-metrics-url", help="Optional vLLM/SGLang Prometheus metrics URL."),
    ] = None,
    lmcache_metrics_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-metrics-url", help="Optional LMCache Prometheus metrics URL."),
    ] = None,
    engine_metrics_file: Annotated[
        Optional[Path],
        typer.Option("--engine-metrics-file", help="Optional saved engine metrics scrape."),
    ] = None,
    lmcache_metrics_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-metrics-file", help="Optional saved LMCache metrics scrape."),
    ] = None,
    lmcache_http_evidence_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-http-evidence-file", help="Optional LMCache HTTP evidence JSON."),
    ] = None,
    lmcache_log_evidence_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-log-evidence-file", help="Optional LMCache log evidence JSON."),
    ] = None,
    lmcache_trace_evidence_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-trace-evidence-file", help="Optional LMCache .lct trace evidence JSON."),
    ] = None,
    lmcache_otel_evidence_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-otel-evidence-file", help="Optional LMCache OTel evidence JSON."),
    ] = None,
    lmcache_trace_replay_evidence_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-trace-replay-evidence-file", help="Optional LMCache trace replay evidence JSON."),
    ] = None,
    lmcache_lookup_hash_evidence_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-lookup-hash-evidence-file", help="Optional LMCache lookup-hash evidence JSON."),
    ] = None,
    lmcache_cacheblend_boundary_evidence_file: Annotated[
        Optional[Path],
        typer.Option(
            "--lmcache-cacheblend-boundary-evidence-file",
            help="Optional CacheBlend boundary lifecycle evidence JSONL.",
        ),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", help="Optional JSON report path."),
    ] = None,
    expect_mode: Annotated[
        str,
        typer.Option("--expect-mode", help="Expected LMCache mode: auto, mp, or embedded."),
    ] = "auto",
    l2_configured: Annotated[
        bool,
        typer.Option("--l2-configured", help="Treat MP L2 metric families as expected."),
    ] = False,
    mp_prometheus_port: Annotated[
        Optional[int],
        typer.Option("--mp-prometheus-port", help="LMCache MP Prometheus port from launch/config."),
    ] = None,
    mp_event_bus_queue_size: Annotated[
        Optional[int],
        typer.Option("--mp-event-bus-queue-size", help="LMCache MP EventBus queue size from launch/config."),
    ] = None,
    mp_metrics_sample_rate: Annotated[
        Optional[float],
        typer.Option("--mp-metrics-sample-rate", help="LMCache MP metrics sample rate from launch/config."),
    ] = None,
    mp_service_instance_id: Annotated[
        Optional[str],
        typer.Option("--mp-service-instance-id", help="LMCache MP service instance id from launch/config."),
    ] = None,
    mp_observability_disabled: Annotated[
        bool,
        typer.Option(
            "--mp-observability-disabled/--mp-observability-enabled",
            help="Whether LMCache MP was launched with --disable-observability.",
        ),
    ] = False,
    mp_metrics_disabled: Annotated[
        bool,
        typer.Option(
            "--mp-metrics-disabled/--mp-metrics-enabled",
            help="Whether LMCache MP was launched with --disable-metrics.",
        ),
    ] = False,
    mp_logging_disabled: Annotated[
        bool,
        typer.Option(
            "--mp-logging-disabled/--mp-logging-enabled",
            help="Whether LMCache MP was launched with --disable-logging.",
        ),
    ] = False,
    mp_tracing_enabled: Annotated[
        bool,
        typer.Option(
            "--mp-tracing-enabled/--mp-tracing-disabled",
            help="Whether LMCache MP tracing was launched with --enable-tracing.",
        ),
    ] = False,
    mp_trace_recording_enabled: Annotated[
        bool,
        typer.Option(
            "--mp-trace-recording-enabled/--mp-trace-recording-disabled",
            help="Whether LMCache MP trace recording was launched with --trace-level storage.",
        ),
    ] = False,
    fail_on: Annotated[
        str,
        typer.Option(
            "--fail-on",
            help="Exit nonzero on: never, mode-mismatch, or missing-required.",
        ),
    ] = "never",
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Emit the full compatibility report as JSON."),
    ] = False,
) -> None:
    """Report LMCache embedded/MP and vLLM KV-observability compatibility."""
    from inferguard.compat import (
        build_compat_report_from_paths,
        build_compat_report_from_urls,
        write_compat_report,
    )

    valid_modes = {"auto", "mp", "embedded"}
    valid_fail_on = {"never", "mode-mismatch", "missing-required"}
    if expect_mode not in valid_modes:
        raise typer.BadParameter("--expect-mode must be one of auto|mp|embedded")
    if fail_on not in valid_fail_on:
        raise typer.BadParameter("--fail-on must be one of never|mode-mismatch|missing-required")
    if not any(
        [
            engine_metrics_url,
            lmcache_metrics_url,
            engine_metrics_file,
            lmcache_metrics_file,
            lmcache_http_evidence_file,
            lmcache_log_evidence_file,
            lmcache_trace_evidence_file,
            lmcache_otel_evidence_file,
            lmcache_trace_replay_evidence_file,
            lmcache_lookup_hash_evidence_file,
            lmcache_cacheblend_boundary_evidence_file,
        ]
    ):
        raise typer.BadParameter(
            "pass at least one of --engine-metrics-url, --lmcache-metrics-url, "
            "--engine-metrics-file, --lmcache-metrics-file, or an evidence file"
        )
    if mp_metrics_sample_rate is not None and not (0 < mp_metrics_sample_rate <= 1.0):
        raise typer.BadParameter("--mp-metrics-sample-rate must be in (0, 1.0]")
    if mp_event_bus_queue_size is not None and mp_event_bus_queue_size < 0:
        raise typer.BadParameter("--mp-event-bus-queue-size must be non-negative")
    if mp_prometheus_port is not None and not (0 < mp_prometheus_port <= 65535):
        raise typer.BadParameter("--mp-prometheus-port must be a valid TCP port")
    mp_observability = {
        "prometheus_port": mp_prometheus_port,
        "event_bus_queue_size": mp_event_bus_queue_size,
        "metrics_sample_rate": mp_metrics_sample_rate,
        "service_instance_id": mp_service_instance_id,
        "observability_disabled": mp_observability_disabled,
        "metrics_disabled": mp_metrics_disabled,
        "logging_disabled": mp_logging_disabled,
        "tracing_enabled": mp_tracing_enabled,
        "trace_recording_enabled": mp_trace_recording_enabled,
    }
    if engine_metrics_url or lmcache_metrics_url:
        report = build_compat_report_from_urls(
            engine_metrics_url=engine_metrics_url,
            lmcache_metrics_url=lmcache_metrics_url,
            expect_mode=expect_mode,
            l2_configured=l2_configured,
            mp_observability=mp_observability,
            lmcache_http_evidence_file=lmcache_http_evidence_file,
            lmcache_log_evidence_file=lmcache_log_evidence_file,
            lmcache_trace_evidence_file=lmcache_trace_evidence_file,
            lmcache_otel_evidence_file=lmcache_otel_evidence_file,
            lmcache_trace_replay_evidence_file=lmcache_trace_replay_evidence_file,
            lmcache_lookup_hash_evidence_file=lmcache_lookup_hash_evidence_file,
            lmcache_cacheblend_boundary_evidence_file=lmcache_cacheblend_boundary_evidence_file,
        )
    else:
        report = build_compat_report_from_paths(
            engine_metrics_file=engine_metrics_file,
            lmcache_metrics_file=lmcache_metrics_file,
            expect_mode=expect_mode,
            l2_configured=l2_configured,
            mp_observability=mp_observability,
            lmcache_http_evidence_file=lmcache_http_evidence_file,
            lmcache_log_evidence_file=lmcache_log_evidence_file,
            lmcache_trace_evidence_file=lmcache_trace_evidence_file,
            lmcache_otel_evidence_file=lmcache_otel_evidence_file,
            lmcache_trace_replay_evidence_file=lmcache_trace_replay_evidence_file,
            lmcache_lookup_hash_evidence_file=lmcache_lookup_hash_evidence_file,
            lmcache_cacheblend_boundary_evidence_file=lmcache_cacheblend_boundary_evidence_file,
        )
    if output is not None:
        write_compat_report(report, output)
    exit_code = _lmcache_compat_exit_code(report, fail_on)
    if json_out:
        typer.echo(json.dumps(report, indent=2, sort_keys=True))
        raise typer.Exit(code=exit_code)
    table = Table(title="InferGuard LMCache Observability Compatibility")
    table.add_column("Surface")
    table.add_column("Status")
    table.add_column("Families")
    table.add_column("Populated")
    table.add_column("Zero")
    table.add_column("Missing")
    table.add_column("N/A")
    for surface, row in sorted(report["surfaces"].items()):
        table.add_row(
            surface,
            str(row["status"]),
            str(row["family_count"]),
            str(row["populated"]),
            str(row["zero"]),
            str(row["missing"]),
            str(row.get("not_applicable", 0)),
        )
    Console().print(table)
    typer.echo(
        f"detected_mode={report.get('detected_mode')} "
        f"expect_mode={report.get('expect_mode')} "
        f"failure_reasons={len(report.get('failure_reasons') or [])} "
        f"upstream_questions={len(report.get('upstream_questions') or [])}"
    )
    if output is not None:
        typer.echo(f"wrote {output}")
    raise typer.Exit(code=exit_code)


def _lmcache_compat_exit_code(report: dict[str, Any], fail_on: str) -> int:
    if fail_on == "never":
        return 0
    failures = list(report.get("failure_reasons") or [])
    if fail_on == "mode-mismatch":
        return 1 if any(item.get("code") == "lmcache_mode_mismatch" for item in failures) else 0
    if fail_on == "missing-required":
        return 1 if failures else 0
    return 0


@app.command("collect-lmcache")
def collect_lmcache_cmd(
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Output directory for the LMCache evidence packet."),
    ] = ...,
    engine_metrics_url: Annotated[
        Optional[str],
        typer.Option("--engine-metrics-url", help="Optional serving-engine Prometheus metrics URL."),
    ] = None,
    lmcache_metrics_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-metrics-url", help="Optional LMCache Prometheus metrics URL."),
    ] = None,
    engine_metrics_file: Annotated[
        Optional[Path],
        typer.Option("--engine-metrics-file", help="Optional saved engine Prometheus scrape."),
    ] = None,
    lmcache_metrics_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-metrics-file", help="Optional saved LMCache Prometheus scrape."),
    ] = None,
    lmcache_http_base_url: Annotated[
        Optional[str],
        typer.Option(
            "--lmcache-http-base-url",
            help="Optional LMCache MP HTTP base URL; fetches safe read-only endpoints.",
        ),
    ] = None,
    lmcache_http_thread_name: Annotated[
        Optional[str],
        typer.Option(
            "--lmcache-http-thread-name",
            help="Optional periodic thread name to fetch from /periodic-threads/{thread_name}.",
        ),
    ] = None,
    lmcache_health_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-health-url", help="Optional LMCache MP HTTP healthcheck URL."),
    ] = None,
    lmcache_health_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-health-file", help="Optional saved LMCache MP healthcheck response."),
    ] = None,
    lmcache_status_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-status-url", help="Optional LMCache MP HTTP status URL."),
    ] = None,
    lmcache_status_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-status-file", help="Optional saved LMCache MP status response."),
    ] = None,
    lmcache_conf_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-conf-url", help="Optional LMCache MP /conf URL."),
    ] = None,
    lmcache_conf_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-conf-file", help="Optional saved LMCache MP /conf response."),
    ] = None,
    lmcache_threads_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-threads-url", help="Optional LMCache MP /threads URL."),
    ] = None,
    lmcache_threads_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-threads-file", help="Optional saved LMCache MP /threads response."),
    ] = None,
    lmcache_periodic_threads_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-periodic-threads-url", help="Optional LMCache MP /periodic-threads URL."),
    ] = None,
    lmcache_periodic_threads_file: Annotated[
        Optional[Path],
        typer.Option(
            "--lmcache-periodic-threads-file",
            help="Optional saved LMCache MP /periodic-threads response.",
        ),
    ] = None,
    lmcache_periodic_thread_url: Annotated[
        Optional[str],
        typer.Option(
            "--lmcache-periodic-thread-url",
            help="Optional LMCache MP /periodic-threads/{thread_name} URL.",
        ),
    ] = None,
    lmcache_periodic_thread_file: Annotated[
        Optional[Path],
        typer.Option(
            "--lmcache-periodic-thread-file",
            help="Optional saved LMCache MP /periodic-threads/{thread_name} response.",
        ),
    ] = None,
    lmcache_periodic_threads_health_url: Annotated[
        Optional[str],
        typer.Option(
            "--lmcache-periodic-threads-health-url",
            help="Optional LMCache MP /periodic-threads-health URL.",
        ),
    ] = None,
    lmcache_periodic_threads_health_file: Annotated[
        Optional[Path],
        typer.Option(
            "--lmcache-periodic-threads-health-file",
            help="Optional saved LMCache MP /periodic-threads-health response.",
        ),
    ] = None,
    lmcache_version_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-version-url", help="Optional LMCache MP /version URL."),
    ] = None,
    lmcache_version_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-version-file", help="Optional saved LMCache MP /version response."),
    ] = None,
    lmcache_lmc_version_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-lmc-version-url", help="Optional LMCache MP /lmc_version URL."),
    ] = None,
    lmcache_lmc_version_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-lmc-version-file", help="Optional saved LMCache MP /lmc_version response."),
    ] = None,
    lmcache_commit_id_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-commit-id-url", help="Optional LMCache MP /commit_id URL."),
    ] = None,
    lmcache_commit_id_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-commit-id-file", help="Optional saved LMCache MP /commit_id response."),
    ] = None,
    lmcache_quota_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-quota-url", help="Optional LMCache MP GET /api/quota URL."),
    ] = None,
    lmcache_quota_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-quota-file", help="Optional saved LMCache MP GET /api/quota response."),
    ] = None,
    engine_log_file: Annotated[
        Optional[Path],
        typer.Option("--engine-log-file", help="Optional engine log file to copy into the packet."),
    ] = None,
    lmcache_log_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-log-file", help="Optional LMCache log file to copy into the packet."),
    ] = None,
    lmcache_trace_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-trace-file", help="Optional LMCache MP .lct trace recording file."),
    ] = None,
    lmcache_otel_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-otel-file", help="Optional JSONL export of LMCache OTel spans."),
    ] = None,
    lmcache_trace_replay_output: Annotated[
        Optional[Path],
        typer.Option(
            "--lmcache-trace-replay-output",
            help="Optional LMCache trace replay output file or directory to copy and parse if supported.",
        ),
    ] = None,
    lmcache_lookup_hash_path: Annotated[
        Optional[Path],
        typer.Option(
            "--lmcache-lookup-hash-path",
            help="Optional lookup_hashes_*.jsonl file or lookup-hash directory to copy and parse if supported.",
        ),
    ] = None,
    expect_mode: Annotated[
        str,
        typer.Option("--expect-mode", help="Expected LMCache mode: auto, mp, or embedded."),
    ] = "auto",
    l2_configured: Annotated[
        bool,
        typer.Option("--l2-configured", help="Treat MP L2 metric families as expected."),
    ] = False,
    timeout_seconds: Annotated[
        float,
        typer.Option("--timeout-seconds", help="HTTP timeout per scrape."),
    ] = 10.0,
    mp_prometheus_port: Annotated[
        Optional[int],
        typer.Option("--mp-prometheus-port", help="LMCache MP Prometheus port from launch/config."),
    ] = None,
    mp_event_bus_queue_size: Annotated[
        Optional[int],
        typer.Option("--mp-event-bus-queue-size", help="LMCache MP EventBus queue size from launch/config."),
    ] = None,
    mp_metrics_sample_rate: Annotated[
        Optional[float],
        typer.Option("--mp-metrics-sample-rate", help="LMCache MP metrics sample rate from launch/config."),
    ] = None,
    mp_service_instance_id: Annotated[
        Optional[str],
        typer.Option("--mp-service-instance-id", help="LMCache MP service instance id from launch/config."),
    ] = None,
    mp_observability_disabled: Annotated[
        bool,
        typer.Option(
            "--mp-observability-disabled/--mp-observability-enabled",
            help="Whether LMCache MP was launched with --disable-observability.",
        ),
    ] = False,
    mp_metrics_disabled: Annotated[
        bool,
        typer.Option(
            "--mp-metrics-disabled/--mp-metrics-enabled",
            help="Whether LMCache MP was launched with --disable-metrics.",
        ),
    ] = False,
    mp_logging_disabled: Annotated[
        bool,
        typer.Option(
            "--mp-logging-disabled/--mp-logging-enabled",
            help="Whether LMCache MP was launched with --disable-logging.",
        ),
    ] = False,
    mp_tracing_enabled: Annotated[
        bool,
        typer.Option(
            "--mp-tracing-enabled/--mp-tracing-disabled",
            help="Whether LMCache MP tracing was launched with --enable-tracing.",
        ),
    ] = False,
    mp_trace_recording_enabled: Annotated[
        bool,
        typer.Option(
            "--mp-trace-recording-enabled/--mp-trace-recording-disabled",
            help="Whether LMCache MP trace recording was launched with --trace-level storage.",
        ),
    ] = False,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Emit the packet manifest as JSON."),
    ] = False,
) -> None:
    """Collect raw LMCache/vLLM evidence plus a compatibility report."""
    from inferguard.lmcache_packet import LmcachePacketOptions, collect_lmcache_packet

    valid_modes = {"auto", "mp", "embedded"}
    if expect_mode not in valid_modes:
        raise typer.BadParameter("--expect-mode must be one of auto|mp|embedded")
    if timeout_seconds <= 0:
        raise typer.BadParameter("--timeout-seconds must be positive")
    if mp_metrics_sample_rate is not None and not (0 < mp_metrics_sample_rate <= 1.0):
        raise typer.BadParameter("--mp-metrics-sample-rate must be in (0, 1.0]")
    if mp_event_bus_queue_size is not None and mp_event_bus_queue_size < 0:
        raise typer.BadParameter("--mp-event-bus-queue-size must be non-negative")
    if mp_prometheus_port is not None and not (0 < mp_prometheus_port <= 65535):
        raise typer.BadParameter("--mp-prometheus-port must be a valid TCP port")
    if not any(
        [
            engine_metrics_url,
            lmcache_metrics_url,
            engine_metrics_file,
            lmcache_metrics_file,
            lmcache_health_url,
            lmcache_health_file,
            lmcache_status_url,
            lmcache_status_file,
            lmcache_http_base_url,
            lmcache_conf_url,
            lmcache_conf_file,
            lmcache_threads_url,
            lmcache_threads_file,
            lmcache_periodic_threads_url,
            lmcache_periodic_threads_file,
            lmcache_periodic_thread_url,
            lmcache_periodic_thread_file,
            lmcache_periodic_threads_health_url,
            lmcache_periodic_threads_health_file,
            lmcache_version_url,
            lmcache_version_file,
            lmcache_lmc_version_url,
            lmcache_lmc_version_file,
            lmcache_commit_id_url,
            lmcache_commit_id_file,
            lmcache_quota_url,
            lmcache_quota_file,
            engine_log_file,
            lmcache_log_file,
            lmcache_trace_file,
            lmcache_otel_file,
            lmcache_trace_replay_output,
            lmcache_lookup_hash_path,
        ]
    ):
        raise typer.BadParameter("pass at least one URL or file input to collect")
    manifest = collect_lmcache_packet(
        LmcachePacketOptions(
            output_dir=output_dir,
            engine_metrics_url=engine_metrics_url,
            lmcache_metrics_url=lmcache_metrics_url,
            engine_metrics_file=engine_metrics_file,
            lmcache_metrics_file=lmcache_metrics_file,
            lmcache_http_base_url=lmcache_http_base_url,
            lmcache_http_thread_name=lmcache_http_thread_name,
            lmcache_health_url=lmcache_health_url,
            lmcache_health_file=lmcache_health_file,
            lmcache_status_url=lmcache_status_url,
            lmcache_status_file=lmcache_status_file,
            lmcache_conf_url=lmcache_conf_url,
            lmcache_conf_file=lmcache_conf_file,
            lmcache_threads_url=lmcache_threads_url,
            lmcache_threads_file=lmcache_threads_file,
            lmcache_periodic_threads_url=lmcache_periodic_threads_url,
            lmcache_periodic_threads_file=lmcache_periodic_threads_file,
            lmcache_periodic_thread_url=lmcache_periodic_thread_url,
            lmcache_periodic_thread_file=lmcache_periodic_thread_file,
            lmcache_periodic_threads_health_url=lmcache_periodic_threads_health_url,
            lmcache_periodic_threads_health_file=lmcache_periodic_threads_health_file,
            lmcache_version_url=lmcache_version_url,
            lmcache_version_file=lmcache_version_file,
            lmcache_lmc_version_url=lmcache_lmc_version_url,
            lmcache_lmc_version_file=lmcache_lmc_version_file,
            lmcache_commit_id_url=lmcache_commit_id_url,
            lmcache_commit_id_file=lmcache_commit_id_file,
            lmcache_quota_url=lmcache_quota_url,
            lmcache_quota_file=lmcache_quota_file,
            engine_log_file=engine_log_file,
            lmcache_log_file=lmcache_log_file,
            lmcache_trace_file=lmcache_trace_file,
            lmcache_otel_file=lmcache_otel_file,
            lmcache_trace_replay_output=lmcache_trace_replay_output,
            lmcache_lookup_hash_path=lmcache_lookup_hash_path,
            expect_mode=expect_mode,
            l2_configured=l2_configured,
            timeout_seconds=timeout_seconds,
            mp_observability={
                "prometheus_port": mp_prometheus_port,
                "event_bus_queue_size": mp_event_bus_queue_size,
                "metrics_sample_rate": mp_metrics_sample_rate,
                "service_instance_id": mp_service_instance_id,
                "observability_disabled": mp_observability_disabled,
                "metrics_disabled": mp_metrics_disabled,
                "logging_disabled": mp_logging_disabled,
                "tracing_enabled": mp_tracing_enabled,
                "trace_recording_enabled": mp_trace_recording_enabled,
            },
        )
    )
    if json_out:
        typer.echo(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        typer.echo(
            "inferguard collect-lmcache: "
            f"detected_mode={manifest.get('detected_mode')} "
            f"claim_status={manifest.get('claim_status')} "
            f"artifacts={len(manifest.get('artifacts') or {})} "
            f"errors={len(manifest.get('scrape_errors') or [])} "
            f"output_dir={output_dir}"
        )
    raise typer.Exit(code=0)


@app.command("observability-coverage")
def observability_coverage_cmd(
    engine_metrics_url: Annotated[
        Optional[str],
        typer.Option("--engine-metrics-url", help="Optional vLLM/SGLang Prometheus metrics URL."),
    ] = None,
    lmcache_metrics_url: Annotated[
        Optional[str],
        typer.Option("--lmcache-metrics-url", help="Optional LMCache Prometheus metrics URL."),
    ] = None,
    engine_metrics_file: Annotated[
        Optional[Path],
        typer.Option("--engine-metrics-file", help="Optional saved vLLM/SGLang metrics scrape."),
    ] = None,
    lmcache_metrics_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-metrics-file", help="Optional saved LMCache metrics scrape."),
    ] = None,
    lmcache_http_evidence_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-http-evidence-file", help="Optional LMCache HTTP evidence JSON."),
    ] = None,
    lmcache_log_evidence_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-log-evidence-file", help="Optional LMCache log evidence JSON."),
    ] = None,
    lmcache_trace_evidence_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-trace-evidence-file", help="Optional LMCache .lct trace evidence JSON."),
    ] = None,
    lmcache_otel_evidence_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-otel-evidence-file", help="Optional LMCache OTel evidence JSON."),
    ] = None,
    lmcache_trace_replay_evidence_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-trace-replay-evidence-file", help="Optional LMCache trace replay evidence JSON."),
    ] = None,
    lmcache_lookup_hash_evidence_file: Annotated[
        Optional[Path],
        typer.Option("--lmcache-lookup-hash-evidence-file", help="Optional LMCache lookup-hash evidence JSON."),
    ] = None,
    lmcache_cacheblend_boundary_evidence_file: Annotated[
        Optional[Path],
        typer.Option(
            "--lmcache-cacheblend-boundary-evidence-file",
            help="Optional CacheBlend boundary lifecycle evidence JSONL.",
        ),
    ] = None,
    expected_engine: Annotated[
        str,
        typer.Option("--expected-engine", help="Expected engine: auto, vllm, or sglang."),
    ] = "auto",
    expect_lmcache_mode: Annotated[
        str,
        typer.Option("--expect-lmcache-mode", help="Expected LMCache mode: auto, mp, or embedded."),
    ] = "auto",
    external_cache_configured: Annotated[
        bool,
        typer.Option("--external-cache-configured", help="Require external prefix/KV cache families."),
    ] = False,
    cpu_offload_configured: Annotated[
        bool,
        typer.Option("--cpu-offload-configured", help="Require vLLM CPU offload metric families."),
    ] = False,
    l2_configured: Annotated[
        bool,
        typer.Option("--l2-configured", help="Require LMCache MP L2 metric families."),
    ] = False,
    disaggregated_or_external_cache: Annotated[
        bool,
        typer.Option(
            "--disaggregated-or-external-cache",
            help="Require KV transfer families for disaggregated/external-cache paths.",
        ),
    ] = False,
    timeout_seconds: Annotated[
        float,
        typer.Option("--timeout-seconds", help="HTTP timeout per scrape."),
    ] = 10.0,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", help="Optional JSON report path."),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Emit the full coverage report as JSON."),
    ] = False,
) -> None:
    """Report observability family coverage across vLLM, SGLang, and LMCache."""
    from inferguard.observability_coverage import (
        build_observability_coverage_report_from_paths,
        build_observability_coverage_report_from_urls,
        dumps_report,
        write_observability_coverage_report,
    )

    if expected_engine not in {"auto", "vllm", "sglang"}:
        raise typer.BadParameter("--expected-engine must be one of auto|vllm|sglang")
    if expect_lmcache_mode not in {"auto", "mp", "embedded"}:
        raise typer.BadParameter("--expect-lmcache-mode must be one of auto|mp|embedded")
    if timeout_seconds <= 0:
        raise typer.BadParameter("--timeout-seconds must be positive")
    if not any(
        [
            engine_metrics_url,
            lmcache_metrics_url,
            engine_metrics_file,
            lmcache_metrics_file,
            lmcache_http_evidence_file,
            lmcache_log_evidence_file,
            lmcache_trace_evidence_file,
            lmcache_otel_evidence_file,
            lmcache_trace_replay_evidence_file,
            lmcache_lookup_hash_evidence_file,
            lmcache_cacheblend_boundary_evidence_file,
        ]
    ):
        raise typer.BadParameter(
            "pass at least one of --engine-metrics-url, --lmcache-metrics-url, "
            "--engine-metrics-file, --lmcache-metrics-file, or an evidence file"
        )
    kwargs = {
        "expected_engine": expected_engine,
        "expect_lmcache_mode": expect_lmcache_mode,
        "external_cache_configured": external_cache_configured,
        "cpu_offload_configured": cpu_offload_configured,
        "l2_configured": l2_configured,
        "disaggregated_or_external_cache": disaggregated_or_external_cache,
    }
    if engine_metrics_url or lmcache_metrics_url:
        report = build_observability_coverage_report_from_urls(
            engine_metrics_url=engine_metrics_url,
            lmcache_metrics_url=lmcache_metrics_url,
            timeout_seconds=timeout_seconds,
            lmcache_http_evidence_file=lmcache_http_evidence_file,
            lmcache_log_evidence_file=lmcache_log_evidence_file,
            lmcache_trace_evidence_file=lmcache_trace_evidence_file,
            lmcache_otel_evidence_file=lmcache_otel_evidence_file,
            lmcache_trace_replay_evidence_file=lmcache_trace_replay_evidence_file,
            lmcache_lookup_hash_evidence_file=lmcache_lookup_hash_evidence_file,
            lmcache_cacheblend_boundary_evidence_file=lmcache_cacheblend_boundary_evidence_file,
            **kwargs,
        )
    else:
        report = build_observability_coverage_report_from_paths(
            engine_metrics_file=engine_metrics_file,
            lmcache_metrics_file=lmcache_metrics_file,
            lmcache_http_evidence_file=lmcache_http_evidence_file,
            lmcache_log_evidence_file=lmcache_log_evidence_file,
            lmcache_trace_evidence_file=lmcache_trace_evidence_file,
            lmcache_otel_evidence_file=lmcache_otel_evidence_file,
            lmcache_trace_replay_evidence_file=lmcache_trace_replay_evidence_file,
            lmcache_lookup_hash_evidence_file=lmcache_lookup_hash_evidence_file,
            lmcache_cacheblend_boundary_evidence_file=lmcache_cacheblend_boundary_evidence_file,
            **kwargs,
        )
    if output is not None:
        write_observability_coverage_report(report, output)
    if json_out:
        typer.echo(dumps_report(report))
    else:
        table = Table(title="InferGuard Observability Coverage")
        table.add_column("Surface")
        table.add_column("Status")
        table.add_column("Families")
        table.add_column("Populated")
        table.add_column("Zero")
        table.add_column("Missing")
        table.add_column("N/A")
        for surface, row in sorted(report["surfaces"].items()):
            table.add_row(
                surface,
                str(row["status"]),
                str(row["family_count"]),
                str(row["populated"]),
                str(row["zero"]),
                str(row["missing"]),
                str(row.get("not_applicable", 0)),
            )
        Console().print(table)
        typer.echo(
            f"detected_engines={','.join(report.get('detected_engines') or []) or 'unknown'} "
            f"detected_lmcache_mode={report.get('detected_lmcache_mode')} "
            f"coverage_gaps={len(report.get('coverage_gaps') or [])}"
        )
        if output is not None:
            typer.echo(f"wrote {output}")
    raise typer.Exit(code=0)


@app.command("agentx-ingest")
@app.command("ingest-agentx")
def agentx_ingest_cmd(
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Output directory for canonical InferGuard artifacts."),
    ] = ...,
    agentx_results_dir: Annotated[
        Optional[Path],
        typer.Option("--agentx-results-dir", help="AgentX result directory containing metadata and CSV output."),
    ] = None,
    agentx_result: Annotated[
        Optional[Path],
        typer.Option("--agentx-result", help="Single AgentX detailed result CSV."),
    ] = None,
    job_id: Annotated[
        Optional[str],
        typer.Option("--job-id", help="Optional job id stamped into artifacts."),
    ] = None,
    engine: Annotated[
        Optional[str],
        typer.Option("--engine", help="Engine label stamped into artifacts."),
    ] = None,
    workload_label: Annotated[
        Optional[str],
        typer.Option("--workload-label", help="Workload label stamped into artifacts."),
    ] = None,
    model_profile: Annotated[
        Optional[str],
        typer.Option("--model-profile", help="Model architecture/profile label."),
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option("--model", help="Fallback model/profile label for single CSV ingest."),
    ] = None,
    concurrency: Annotated[
        Optional[str],
        typer.Option("--concurrency", help="Concurrency label for single CSV ingest."),
    ] = None,
) -> None:
    """Convert AgentX result CSV outputs into canonical InferGuard schemas."""
    from inferguard.agentx_adapter import (
        convert_agentx_result_to_canonical,
        ingest_agentx_results_dir,
    )

    if agentx_results_dir is None and agentx_result is None:
        raise typer.BadParameter("--agentx-results-dir or --agentx-result is required for ingest-agentx")
    if agentx_results_dir is not None and agentx_result is not None:
        raise typer.BadParameter("provide only one of --agentx-results-dir or --agentx-result")
    if agentx_results_dir is not None:
        try:
            artifacts = ingest_agentx_results_dir(
                agentx_results_dir,
                output_dir=output_dir,
                job_id=job_id,
                engine=engine,
                workload_label=workload_label,
            )
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
    else:
        metadata = {
            "output_dir": str(output_dir),
            "job_id": job_id,
            "engine": engine or "vllm",
            "workload_label": workload_label or "agentx-replay",
            "model_profile": model_profile or model,
            "concurrency": int(concurrency or 1),
        }
        artifacts = convert_agentx_result_to_canonical(agentx_result, metadata)
    typer.echo(artifacts.summary.summary_line())
    raise typer.Exit(code=0 if artifacts.summary.status == "ingested" else 1)


@app.command("launch-engine")
def launch_engine_cmd(
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Output directory for launch artifacts."),
    ] = ...,
    engine: Annotated[
        str,
        typer.Option("--engine", help="Engine: vllm, sglang, lmcache, or dynamo-sglang."),
    ] = ...,
    external_launch: Annotated[
        bool,
        typer.Option("--external-launch", help="Validate an already-launched endpoint instead of spawning."),
    ] = False,
    endpoint_url: Annotated[
        Optional[str],
        typer.Option("--endpoint-url", "--endpoint", help="Endpoint URL for external-launch or healthcheck."),
    ] = None,
    model_path: Annotated[
        Optional[str],
        typer.Option("--model-path", help="Model path or id passed to the serving engine."),
    ] = None,
    host: Annotated[
        Optional[str],
        typer.Option("--host", help="Engine bind host."),
    ] = None,
    port: Annotated[
        Optional[int],
        typer.Option("--port", help="Engine bind port."),
    ] = None,
    tensor_parallel_size: Annotated[
        int,
        typer.Option("--tensor-parallel-size", help="Tensor parallel size."),
    ] = 1,
    pipeline_parallel_size: Annotated[
        int,
        typer.Option("--pipeline-parallel-size", help="Pipeline parallel size."),
    ] = 1,
    data_parallel_size: Annotated[
        int,
        typer.Option("--data-parallel-size", help="Data parallel size."),
    ] = 1,
    max_model_len: Annotated[
        Optional[int],
        typer.Option("--max-model-len", help="Maximum model context length."),
    ] = None,
    gpu_memory_utilization: Annotated[
        float,
        typer.Option("--gpu-memory-utilization", help="vLLM GPU memory utilization."),
    ] = 0.9,
    mem_fraction_static: Annotated[
        float,
        typer.Option("--mem-fraction-static", help="SGLang static memory fraction."),
    ] = 0.9,
    enable_prefix_caching: Annotated[
        bool,
        typer.Option("--enable-prefix-caching", help="Enable prefix caching when supported."),
    ] = False,
    enable_chunked_prefill: Annotated[
        bool,
        typer.Option("--enable-chunked-prefill", help="Enable chunked prefill when supported."),
    ] = False,
    chunked_prefill_size: Annotated[
        Optional[int],
        typer.Option("--chunked-prefill-size", help="Chunked prefill size."),
    ] = None,
    enable_cache_report: Annotated[
        bool,
        typer.Option("--enable-cache-report", help="Enable engine cache reporting flags."),
    ] = False,
    enable_metrics: Annotated[
        bool,
        typer.Option("--enable-metrics", help="Enable engine metrics flags."),
    ] = False,
    kv_cache_dtype: Annotated[
        Optional[str],
        typer.Option("--kv-cache-dtype", help="KV cache dtype."),
    ] = None,
    quantization: Annotated[
        Optional[str],
        typer.Option("--quantization", help="Quantization mode."),
    ] = None,
    hardware: Annotated[
        Optional[str],
        typer.Option("--hardware", help="Hardware label for launch warnings."),
    ] = None,
    kv_transfer_config: Annotated[
        Optional[str],
        typer.Option("--kv-transfer-config", help="KV transfer configuration JSON/string."),
    ] = None,
    healthcheck_timeout_seconds: Annotated[
        int,
        typer.Option("--healthcheck-timeout-seconds", help="Healthcheck timeout in seconds."),
    ] = 600,
    healthcheck_prompt: Annotated[
        str,
        typer.Option("--healthcheck-prompt", help="Healthcheck canary prompt."),
    ] = "Hello, are you up?",
    canary_completion_tokens: Annotated[
        int,
        typer.Option("--canary-completion-tokens", help="Healthcheck canary completion tokens."),
    ] = 16,
    extra_args: Annotated[
        Optional[str],
        typer.Option("--extra-args", help="Extra engine CLI arguments."),
    ] = None,
) -> None:
    """Launch or validate a vLLM, SGLang, LMCache, or Dynamo-SGLang engine."""
    from inferguard.launch_engine import launch

    if engine not in {"vllm", "sglang", "lmcache", "dynamo-sglang"}:
        raise typer.BadParameter(
            '--engine must be one of: "vllm", "sglang", "lmcache", "dynamo-sglang" for launch-engine'
        )
    if external_launch and not endpoint_url:
        raise typer.BadParameter("--endpoint-url is required with --external-launch")
    if not external_launch and not model_path:
        raise typer.BadParameter("--model-path is required unless --external-launch is set")
    if healthcheck_timeout_seconds < 0:
        raise typer.BadParameter("--healthcheck-timeout-seconds must be non-negative")
    if canary_completion_tokens <= 0:
        raise typer.BadParameter("--canary-completion-tokens must be positive")
    host_value = host or "0.0.0.0"  # nosec B104 - engine launch defaults to externally reachable serving.
    selected_port = port
    if selected_port is None and not external_launch:
        selected_port = 8000 if engine in {"vllm", "lmcache"} else 30000
    outcome = launch(
        engine=engine,
        output_dir=output_dir,
        external_launch=external_launch,
        endpoint_url=endpoint_url,
        model_path=model_path,
        host=host_value,
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
        kv_transfer_config=kv_transfer_config,
        healthcheck_timeout_seconds=healthcheck_timeout_seconds,
        healthcheck_prompt=healthcheck_prompt,
        canary_completion_tokens=canary_completion_tokens,
        extra_args=extra_args,
    )
    typer.echo(outcome.summary_line())
    raise typer.Exit(code=outcome.return_code)


@app.command("diagnose-bottleneck")
def diagnose_bottleneck_cmd(
    job_dir: Annotated[
        Path,
        typer.Option("--job-dir", help="Completed job directory to diagnose."),
    ] = ...,
    validation_report: Annotated[
        Optional[Path],
        typer.Option("--validation-report", help="Optional validation report path."),
    ] = None,
    rule_config: Annotated[
        Optional[Path],
        typer.Option("--rule-config", help="Optional bottleneck rule config."),
    ] = None,
    output_dir: Annotated[
        Optional[Path],
        typer.Option("--output-dir", help="Output directory for diagnosis artifacts."),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Return non-zero when evidence is insufficient."),
    ] = False,
    json_only: Annotated[
        bool,
        typer.Option("--json-only", help="Skip markdown rendering."),
    ] = False,
) -> None:
    """Diagnose one completed job into a bottleneck verdict."""
    from inferguard.diagnose_bottleneck import diagnose, write_diagnosis

    diagnosis = diagnose(
        job_dir,
        validation_report=validation_report,
        rule_config=rule_config,
    )
    target = output_dir or job_dir / "diagnosis"
    write_diagnosis(diagnosis, target, json_only=json_only)
    typer.echo(diagnosis.summary_line())
    if strict and diagnosis.to_dict()["verdict"] == "not_enough_evidence":
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


@app.command("classify-failures")
def classify_failures_cmd(
    job_dir: Annotated[
        Path,
        typer.Option("--job-dir", help="Completed or failed job directory to classify."),
    ] = ...,
    regex_config: Annotated[
        Optional[Path],
        typer.Option("--regex-config", help="Optional regex classification config."),
    ] = None,
    max_failures: Annotated[
        int,
        typer.Option("--max-failures", help="Maximum ranked failures to emit."),
    ] = 20,
    output_dir: Annotated[
        Optional[Path],
        typer.Option("--output-dir", help="Output directory for classification artifacts."),
    ] = None,
    json_only: Annotated[
        bool,
        typer.Option("--json-only", help="Skip markdown rendering."),
    ] = False,
) -> None:
    """Classify failed job evidence into operator-actionable failure classes."""
    from inferguard.classify_failures import (
        classify,
        format_stdout_summary,
        write_failure_classification,
    )

    if max_failures <= 0:
        raise typer.BadParameter("--max-failures must be positive")
    target = output_dir or job_dir / "diagnosis"
    report = classify(
        job_dir,
        regex_config=regex_config,
        max_failures=max_failures,
    )
    write_failure_classification(report, target, write_markdown=not json_only)
    typer.echo(format_stdout_summary(report))
    raise typer.Exit(code=0)


@app.command("report-completed")
def report_completed_cmd(
    results_root: Annotated[
        Path,
        typer.Option("--results-root", help="Completed run root to summarize."),
    ] = ...,
    output_dir: Annotated[
        Optional[Path],
        typer.Option("--output-dir", help="Output directory for recommendation artifacts."),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Return non-zero when recommendation evidence is insufficient."),
    ] = False,
    json_only: Annotated[
        bool,
        typer.Option("--json-only", help="Skip markdown rendering."),
    ] = False,
    cost_input: Annotated[
        Optional[Path],
        typer.Option("--cost-input", help='JSON {"<sku>": <usd_per_gpu_hour>} for cost claims.'),
    ] = None,
    workload_fingerprint: Annotated[
        Optional[Path],
        typer.Option("--workload-fingerprint", help="Optional WorkloadFingerprint JSON."),
    ] = None,
    slo: Annotated[
        Optional[Path],
        typer.Option("--slo", help="Optional SLO JSON."),
    ] = None,
    useful_task_definition: Annotated[
        Optional[Path],
        typer.Option("--useful-task-definition", help="Optional useful-task criteria JSON."),
    ] = None,
    useful_task_min_tokens: Annotated[
        int,
        typer.Option("--useful-task-min-tokens", help="Minimum completion tokens for a useful task."),
    ] = 1,
    useful_task_slo_ttft_ms: Annotated[
        Optional[float],
        typer.Option("--useful-task-slo-ttft-ms", help="Useful-task TTFT SLO in milliseconds."),
    ] = None,
    slo_ttft_ms: Annotated[
        Optional[float],
        typer.Option("--slo-ttft-ms", help="TTFT SLO in milliseconds."),
    ] = None,
    slo_e2e_ms: Annotated[
        Optional[float],
        typer.Option("--slo-e2e-ms", help="E2E latency SLO in milliseconds."),
    ] = None,
    slo_success_rate: Annotated[
        float,
        typer.Option("--slo-success-rate", help="Success-rate SLO."),
    ] = 0.95,
    success_rate_floor: Annotated[
        float,
        typer.Option("--success-rate-floor", help="Compatibility alias for --slo-success-rate."),
    ] = 0.95,
) -> None:
    """Build a refusal-gated operator recommendation from completed evidence."""
    from inferguard.report_completed import RecommendationOptions, build_recommendation
    from inferguard.report_completed.render import render_markdown

    if useful_task_min_tokens < 0:
        raise typer.BadParameter("--useful-task-min-tokens must be non-negative")
    selected_success_rate = success_rate_floor if success_rate_floor != 0.95 else slo_success_rate
    if selected_success_rate < 0 or selected_success_rate > 1:
        raise typer.BadParameter("--slo-success-rate must be between 0 and 1")
    rec = build_recommendation(
        results_root,
        RecommendationOptions(
            cost_input=cost_input,
            workload_fingerprint=workload_fingerprint,
            slo=slo,
            useful_task_definition=useful_task_definition,
            useful_task_min_tokens=useful_task_min_tokens,
            useful_task_slo_ttft_ms=useful_task_slo_ttft_ms,
            slo_ttft_ms=slo_ttft_ms,
            slo_e2e_ms=slo_e2e_ms,
            slo_success_rate=selected_success_rate,
        ),
    )
    target = output_dir or _phase_bc_default_report_completed_output_dir(results_root)
    target.mkdir(parents=True, exist_ok=True)
    _phase_bc_write_json(target / "operator_recommendation.json", rec.to_dict())
    if not json_only:
        (target / "operator_recommendation.md").write_text(render_markdown(rec), encoding="utf-8")
    sku = rec.best_gpu_sku.get("value") or "null"
    engine = rec.best_engine.get("value") or "null"
    bottleneck = rec.bottleneck.get("verdict") or "not_enough_evidence"
    claim = rec.claim_status if rec.claim_status != "synthetic" else "not_proven"
    typer.echo(
        "inferguard report-completed: "
        f"status={rec.executive_verdict_status} "
        f"sku={sku} "
        f"engine={engine} "
        f"bottleneck={bottleneck} "
        f"claim={claim}"
    )
    if strict and (
        rec.executive_verdict == "not_enough_evidence"
        or rec.executive_verdict_status == "not_enough_evidence"
    ):
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


@app.command("compute-cost")
def compute_cost_cmd(
    results_root: Annotated[
        Path,
        typer.Option("--results-root", help="Completed run root to price."),
    ] = ...,
    cost_input: Annotated[
        Path,
        typer.Option("--cost-input", help='JSON {"<sku>": <usd_per_gpu_hour>} for cost claims.'),
    ] = ...,
    output_dir: Annotated[
        Optional[Path],
        typer.Option("--output-dir", help="Output directory for cost artifacts."),
    ] = None,
    json_only: Annotated[
        bool,
        typer.Option("--json-only", help="Skip markdown rendering."),
    ] = False,
    slo: Annotated[
        Optional[Path],
        typer.Option("--slo", help="Optional SLO JSON."),
    ] = None,
    useful_task_definition: Annotated[
        Optional[Path],
        typer.Option("--useful-task-definition", help="Optional useful-task criteria JSON."),
    ] = None,
    useful_task_min_tokens: Annotated[
        int,
        typer.Option("--useful-task-min-tokens", help="Minimum completion tokens for a useful task."),
    ] = 1,
    useful_task_slo_ttft_ms: Annotated[
        Optional[float],
        typer.Option("--useful-task-slo-ttft-ms", help="Useful-task TTFT SLO in milliseconds."),
    ] = None,
    slo_ttft_ms: Annotated[
        Optional[float],
        typer.Option("--slo-ttft-ms", help="TTFT SLO in milliseconds."),
    ] = None,
    slo_e2e_ms: Annotated[
        Optional[float],
        typer.Option("--slo-e2e-ms", help="E2E latency SLO in milliseconds."),
    ] = None,
    slo_success_rate: Annotated[
        float,
        typer.Option("--slo-success-rate", help="Success-rate SLO."),
    ] = 0.95,
    success_rate_floor: Annotated[
        float,
        typer.Option("--success-rate-floor", help="Compatibility alias for --slo-success-rate."),
    ] = 0.95,
) -> None:
    """Compute cost-per-useful-task and safe concurrency from run evidence."""
    from inferguard.cost_model import compute_cost
    from inferguard.cost_model.render import render_cost_markdown

    if useful_task_min_tokens < 0:
        raise typer.BadParameter("--useful-task-min-tokens must be non-negative")
    selected_success_rate = success_rate_floor if success_rate_floor != 0.95 else slo_success_rate
    if selected_success_rate < 0 or selected_success_rate > 1:
        raise typer.BadParameter("--slo-success-rate must be between 0 and 1")
    report = compute_cost(
        results_root,
        cost_input,
        slo,
        useful_task_definition=useful_task_definition,
        useful_task_min_tokens=useful_task_min_tokens,
        useful_task_slo_ttft_ms=useful_task_slo_ttft_ms,
        slo_ttft_ms=slo_ttft_ms,
        slo_e2e_ms=slo_e2e_ms,
        slo_success_rate=selected_success_rate,
    )
    target = output_dir or results_root
    target.mkdir(parents=True, exist_ok=True)
    _phase_bc_write_json(target / "cost_report.json", report.to_dict())
    if not json_only:
        (target / "cost_report.md").write_text(render_cost_markdown(report), encoding="utf-8")
    envelope = report.safe_concurrency_envelope
    typer.echo(
        "inferguard compute-cost: "
        f"cost_per_m_completion_usd={_summary_money(report.cost_per_million_completion_tokens_usd)} "
        f"cost_per_useful_task_usd={_summary_nullable(report.cost_per_useful_task_usd)} "
        f"safe_concurrency={_summary_nullable(envelope.safe_concurrency)} "
        f"claim={report.claim_status}"
    )
    raise typer.Exit(code=0)


@app.command("find-cliffs")
def find_cliffs_cmd(
    results_root: Annotated[
        Path,
        typer.Option("--results-root", help="Completed sweep root to analyze."),
    ] = ...,
    output_dir: Annotated[
        Optional[Path],
        typer.Option("--output-dir", help="Output directory for capacity cliff artifacts."),
    ] = None,
    cliffs: Annotated[
        Optional[str],
        typer.Option("--cliffs", help="Comma-separated capacity cliff subset; default is all."),
    ] = None,
    ttft_p99_floor_ms: Annotated[
        float,
        typer.Option("--ttft-p99-floor-ms", help="TTFT p99 floor in milliseconds."),
    ] = 1000.0,
    success_rate_floor: Annotated[
        float,
        typer.Option("--success-rate-floor", help="Minimum acceptable success rate."),
    ] = 0.95,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Return non-zero when any cliff lacks enough evidence."),
    ] = False,
    json_only: Annotated[
        bool,
        typer.Option("--json-only", help="Skip markdown rendering."),
    ] = False,
) -> None:
    """Find capacity cliffs across completed sweep evidence."""
    from inferguard.find_cliffs import (
        FindCliffsOptions,
        find_cliffs,
        format_stdout_summary,
        write_capacity_cliffs,
    )
    from inferguard.find_cliffs.types import CAPACITY_CLIFF_NAMES

    if ttft_p99_floor_ms <= 0:
        raise typer.BadParameter("--ttft-p99-floor-ms must be positive")
    if not 0 < success_rate_floor <= 1:
        raise typer.BadParameter("--success-rate-floor must be > 0 and <= 1")
    cliff_names = CAPACITY_CLIFF_NAMES
    if cliffs:
        cliff_names = tuple(name.strip() for name in cliffs.split(",") if name.strip())
    capacity = find_cliffs(
        results_root,
        FindCliffsOptions(
            cliffs=cliff_names,
            ttft_p99_floor_ms=ttft_p99_floor_ms,
            success_rate_floor=success_rate_floor,
        ),
    )
    target = output_dir or results_root
    write_capacity_cliffs(capacity, target, write_markdown=not json_only)
    typer.echo(format_stdout_summary(capacity))
    if strict and any(cliff.reasoning.startswith("not_enough_evidence") for cliff in capacity.cliffs):
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


def _phase_bc_default_report_completed_output_dir(results_root: Path) -> Path:
    plan_path = results_root / "matrix_plan.json"
    plan = _phase_bc_load_json(plan_path) if plan_path.exists() else {}
    jobs = plan.get("jobs") if isinstance(plan.get("jobs"), list) else []
    if len(jobs) == 1 and isinstance(jobs[0], dict):
        raw = jobs[0].get("output_dir") or Path("jobs") / str(jobs[0].get("job_id") or "unknown")
        job_dir = Path(str(raw))
        if not job_dir.is_absolute():
            job_dir = results_root / job_dir
        return job_dir / "report"
    return results_root / "report"


def _phase_bc_load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _phase_bc_write_json(path: Path, data: dict) -> None:
    atomic_write_json(path, data)


def _summary_money(value: object) -> str:
    if isinstance(value, int | float):
        return f"{float(value):.6f}"
    return "0.000000"


def _summary_nullable(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


@app.command("simulate-gpu")
def simulate_gpu_cmd(
    results_root: Annotated[
        Optional[Path],
        typer.Option("--results-root", help="Run directory where matrix and synthetic GPU artifacts will be written."),
    ] = None,
    plan: Annotated[
        Optional[Path],
        typer.Option("--plan", help="Existing matrix_plan.json to simulate. Preserves the legacy gmi_gpu_mimic.py flag."),
    ] = None,
    gpu_profiles: Annotated[
        Optional[Path],
        typer.Option("--gpu-profiles", "--gpu-mimic-profile", help="Optional GPU mimic profile catalog JSON."),
    ] = None,
    provider: Annotated[str, typer.Option("--provider", help="Provider profile. Currently only gmi.")] = "gmi",
    cluster_profile: Annotated[
        Optional[Path],
        typer.Option("--cluster-profile", help="Optional standalone JSON/YAML cluster profile."),
    ] = None,
    stage: Annotated[str, typer.Option("--stage", help="Matrix stage label.")] = "single-node-smoke",
    max_jobs: Annotated[int, typer.Option("--max-jobs", help="Maximum jobs to render into the synthetic matrix.")] = 1,
    hardware: Annotated[str, typer.Option("--hardware", help="Hardware alias: h100, h200, b200, b300, gb200, or gb300.")] = "b200",
    engine: Annotated[str, typer.Option("--engine", help="Engine alias: vllm or sglang.")] = "vllm",
    model_profile: Annotated[
        str,
        typer.Option("--model-profile", help="Model profile alias, e.g. dsv4-pro or deepseek_v4_pro."),
    ] = "dsv4-pro",
    workload: Annotated[str, typer.Option("--workload", help="Workload alias, e.g. long_context_chat.")] = "long_context_chat",
    context_lengths: Annotated[
        Optional[str],
        typer.Option("--context-lengths", help="Comma-separated context lengths. Defaults to 8192."),
    ] = None,
    concurrency: Annotated[
        Optional[str],
        typer.Option("--concurrency", help="Comma-separated concurrency levels. Defaults to 1."),
    ] = None,
    arrival_mode: Annotated[str, typer.Option("--arrival-mode", help="Arrival mode label.")] = "closed_loop",
) -> None:
    """Generate synthetic GPU/Slurm artifacts for local bundle smoke testing."""
    from inferguard.synthetic import SIMULATION_MODE, simulate_from_options, simulate_results

    try:
        if plan is not None:
            summary = simulate_results(plan, gpu_profiles)
        else:
            if results_root is None:
                raise typer.BadParameter("--results-root is required when --plan is not supplied")
            summary = simulate_from_options(
                results_root=results_root,
                hardware=hardware,
                model_profile=model_profile,
                workload=workload,
                engine=engine,
                provider=provider,
                cluster_profile=cluster_profile,
                stage=stage,
                max_jobs=max_jobs,
                context_lengths=context_lengths,
                concurrency=concurrency,
                arrival_mode=arrival_mode,
                gpu_profiles_path=gpu_profiles,
            )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    sys.stdout.write(json.dumps({"simulation_summary": summary["jobs"], "mode": SIMULATION_MODE}, indent=2) + "\n")
    raise typer.Exit(code=0)


@app.command("serve-mimic")
def serve_mimic_cmd(
    host: Annotated[str, typer.Option("--host", help="Bind host for the synthetic endpoint.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Bind port for the synthetic endpoint.")] = 8000,
    model: Annotated[
        Optional[str],
        typer.Option("--model", help="Model id returned by the OpenAI-compatible endpoint."),
    ] = None,
    model_profile: Annotated[
        Optional[str],
        typer.Option("--model-profile", help="Fallback model id/profile label."),
    ] = None,
) -> None:
    """Serve a tiny fake OpenAI-compatible endpoint for synthetic smoke tests."""
    from inferguard.synthetic import serve_synthetic_endpoint

    serve_synthetic_endpoint(host, port, model or model_profile or "synthetic-gmi-model")


@app.callback(invoke_without_command=True)
def _main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", help="Print version and exit.", is_eager=True
    ),
) -> None:
    if version:
        typer.echo(f"inferguard {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@disagg_app.command("status")
def disagg_status_cmd(
    prefill: str = typer.Option(..., "--prefill", help="Prefill endpoint base URL."),
    decode: str = typer.Option(..., "--decode", help="Decode endpoint base URL."),
    transfer: Optional[str] = typer.Option(
        None, "--transfer", help="Optional transfer-layer metrics URL."
    ),
    engine: str = typer.Option(
        "auto",
        "--engine",
        help="Engine hint: auto, vllm, sglang, dynamo, llm-d.",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of a table."
    ),
    timeout: float = typer.Option(
        HTTP_TIMEOUT_SECONDS, "--timeout", help="HTTP timeout per scrape (seconds)."
    ),
) -> None:
    """Scrape prefill + decode (+ optional transfer) and print findings."""
    engine_arg = _validated_engine(engine)
    status = asyncio.run(
        _collect(
            prefill=prefill,
            decode=decode,
            transfer=transfer,
            engine=engine_arg,
            timeout=timeout,
        )
    )
    if json_out:
        sys.stdout.write(json.dumps(status.as_dict(), indent=2) + "\n")
    else:
        _render_table(status)
    raise typer.Exit(code=_exit_code(status))


@agent_app.command(
    "trace",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def agent_trace_cmd(
    ctx: typer.Context,
    framework: Annotated[
        str,
        typer.Option(
            "--framework",
            help="Agent framework: langgraph, crewai, autogen, claude_code, cursor_sdk, raw_openai.",
        ),
    ] = "raw_openai",
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Directory for agent-trace/v1 JSONL output."),
    ] = Path("inferguard_agent_trace"),
    save_prompts: Annotated[
        bool,
        typer.Option(
            "--save-prompts/--no-save-prompts",
            help="Write prompt text to prompts-local.jsonl for local debugging only.",
        ),
    ] = False,
    rig_label: Annotated[
        Optional[str],
        typer.Option("--rig-label", help="Optional rig label: h100, h200, b200, gb200, auto."),
    ] = None,
) -> None:
    """Wrap a subprocess and emit a local ``agent-trace/v1`` JSONL file."""

    command = list(ctx.args)
    if not command:
        raise typer.BadParameter(
            "subprocess argv is required; pass it after options, e.g. "
            "`inferguard agent trace --output-dir traces -- python agent.py`"
        )
    tracer = AgentTracer(
        output_dir=output_dir,
        framework=_validated_agent_framework(framework),
        save_prompts=save_prompts,
        rig_label=rig_label,
    )
    try:
        result = tracer.trace_subprocess(command)
    except PermissionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except OSError as exc:
        typer.echo(f"agent trace subprocess failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    typer.echo(f"Wrote agent trace to {result.trace_path}")
    raise typer.Exit(code=result.returncode)


@daemon_app.command("start")
def daemon_start_cmd(
    port: Annotated[
        int,
        typer.Option("--port", help="Loopback Prometheus metrics port."),
    ] = DEFAULT_DAEMON_PORT,
    host: Annotated[
        Optional[str],
        typer.Option("--host", help="Metrics bind host; cluster leaders default to 0.0.0.0."),
    ] = None,
    watch_dir: Annotated[
        Optional[Path],
        typer.Option("--watch-dir", help="Directory containing agent-trace/v1 JSONL files."),
    ] = None,
    prometheus: Annotated[
        bool,
        typer.Option("--prometheus/--no-prometheus", help="Expose loopback /metrics endpoint."),
    ] = True,
    leader: Annotated[
        bool,
        typer.Option("--leader", help="Run as a cluster fan-in leader and merge follower ranks."),
    ] = False,
    follower: Annotated[
        Optional[str],
        typer.Option("--follower", help="Run as a cluster follower and POST snapshots to LEADER_URL."),
    ] = None,
    cluster_token: Annotated[
        Optional[Path],
        typer.Option("--cluster-token", help="Path to operator-generated cluster bearer token."),
    ] = None,
) -> None:
    """Start the foreground harness daemon sidecar."""

    if leader and follower is not None:
        raise typer.BadParameter("--leader and --follower are mutually exclusive")
    if leader and not prometheus:
        raise typer.BadParameter("--leader requires --prometheus so followers can register")
    bind_host = host or ("0.0.0.0" if leader else "127.0.0.1")  # nosec B104 - leader must accept follower nodes.
    daemon = Daemon()
    cluster: Optional[ClusterDaemon] = None
    seen: set[Path] = set()
    loaded = _daemon_record_watch_dir(daemon, watch_dir, seen)
    try:
        if leader:
            cluster = ClusterDaemon.leader(daemon=daemon, token_path=cluster_token)
            metrics_url = cluster.start_server(host=bind_host, port=port)
        else:
            metrics_url = (
                daemon.start_metrics_server(
                    host=bind_host,
                    port=port,
                    allow_remote=follower is not None and bind_host not in {"127.0.0.1", "localhost", "::1"},
                )
                if prometheus
                else None
            )
            if follower is not None:
                cluster = ClusterDaemon.follower(
                    leader_url=follower,
                    daemon=daemon,
                    token_path=cluster_token,
                )
                cluster.start_follower()
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        typer.echo(f"daemon cluster startup failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    _write_daemon_state(
        {
            "pid": os.getpid(),
            "port": port,
            "host": bind_host,
            "watch_dir": str(watch_dir) if watch_dir else None,
            "prometheus": prometheus,
            "metrics_url": metrics_url,
            "cluster_mode": "leader" if leader else ("follower" if follower else None),
            "leader_url": follower,
            "started_at_epoch": time.time(),
        }
    )
    typer.echo(f"InferGuard daemon started in foreground (pid {os.getpid()}).")
    if leader:
        typer.echo("Cluster mode: leader (merged /metrics and follower fan-in enabled).")
    if follower is not None:
        typer.echo(f"Cluster mode: follower (pushing snapshots to {follower}).")
    if watch_dir is not None:
        typer.echo(f"Loaded {loaded} event(s) from {watch_dir}.")
    if metrics_url is not None:
        typer.echo(f"Prometheus metrics: {metrics_url}")
    else:
        sys.stdout.write(json.dumps(daemon.snapshot().as_dict(), indent=2, sort_keys=True) + "\n")
        _clear_daemon_state()
        raise typer.Exit()
    try:
        while True:
            time.sleep(5)
            _daemon_record_watch_dir(daemon, watch_dir, seen)
    except KeyboardInterrupt:
        typer.echo("InferGuard daemon stopping.")
    finally:
        if cluster is not None:
            cluster.stop()
        daemon.stop_metrics_server()
        _clear_daemon_state()


@daemon_app.command("stop")
def daemon_stop_cmd(
    port: Annotated[int, typer.Option("--port", help="Expected daemon port.")] = DEFAULT_DAEMON_PORT,
    watch_dir: Annotated[
        Optional[Path],
        typer.Option("--watch-dir", help="Expected watch directory."),
    ] = None,
    prometheus: Annotated[
        bool,
        typer.Option("--prometheus/--no-prometheus", help="Expected Prometheus state."),
    ] = True,
) -> None:
    """Stop the recorded foreground daemon process when possible."""

    state = _read_daemon_state()
    if state is None:
        typer.echo("InferGuard daemon is not marked running.")
        return
    expected = {"port": port, "watch_dir": str(watch_dir) if watch_dir else None, "prometheus": prometheus}
    pid = state.get("pid")
    if isinstance(pid, int) and pid != os.getpid():
        command_text = _process_command(pid)
        if _looks_like_inferguard_daemon(command_text):
            try:
                os.kill(pid, signal.SIGTERM)
                typer.echo(f"Sent SIGTERM to InferGuard daemon pid {pid}.")
            except ProcessLookupError:
                typer.echo(f"No live process found for recorded daemon pid {pid}; clearing state.")
            except PermissionError as exc:
                typer.echo(f"Could not stop recorded daemon pid {pid}: {exc}", err=True)
                raise typer.Exit(code=3) from exc
        else:
            typer.echo(
                f"Recorded pid {pid} no longer looks like `inferguard daemon start`; "
                "clearing stale state without sending a signal."
            )
    else:
        typer.echo("Recorded daemon pid is missing or current process; clearing state only.")
    if any(state.get(key) != value for key, value in expected.items()):
        typer.echo("Note: supplied flags did not exactly match the recorded daemon state.")
    _clear_daemon_state()


@daemon_app.command("status")
def daemon_status_cmd(
    port: Annotated[int, typer.Option("--port", help="Daemon port to report.")] = DEFAULT_DAEMON_PORT,
    watch_dir: Annotated[
        Optional[Path],
        typer.Option("--watch-dir", help="Optionally load trace files before reporting status."),
    ] = None,
    prometheus: Annotated[
        bool,
        typer.Option("--prometheus/--no-prometheus", help="Prometheus endpoint expectation."),
    ] = True,
) -> None:
    """Print daemon state and a one-shot local snapshot."""

    daemon = Daemon()
    loaded = _daemon_record_watch_dir(daemon, watch_dir, set())
    status = {
        "recorded_state": _read_daemon_state(),
        "requested": {
            "port": port,
            "watch_dir": str(watch_dir) if watch_dir else None,
            "prometheus": prometheus,
        },
        "loaded_events": loaded,
        "snapshot": daemon.snapshot().as_dict(),
    }
    sys.stdout.write(json.dumps(status, indent=2, sort_keys=True) + "\n")


@telemetry_app.command("status")
def telemetry_status_cmd() -> None:
    """Show local telemetry state without contacting the network."""

    client = TelemetryClient()
    status = client.status()
    pending = _pending_payloads(status.uploads_pending_dir)
    typer.echo(ZERO_TELEMETRY_MESSAGE)
    typer.echo(f"state: {status.state.value}")
    typer.echo(f"hard_disabled: {_bool_text(status.hard_disabled)}")
    typer.echo(f"consent_token_present: {_bool_text(status.consent_token_present)}")
    typer.echo(f"pending_payloads: {len(pending)}")
    typer.echo(f"config_dir: {status.config_dir}")
    typer.echo(f"uploads_pending_dir: {status.uploads_pending_dir}")
    typer.echo(
        "env_overrides: "
        f"INFERGUARD_TELEMETRY={os.environ.get('INFERGUARD_TELEMETRY', '<unset>')} "
        f"(disabled is a hard override); DO_NOT_TRACK={os.environ.get('DO_NOT_TRACK', '<unset>')} "
        "(1 is a hard override)"
    )


@telemetry_app.command("enable")
def telemetry_enable_cmd(
    consent_token: Annotated[
        str,
        typer.Option("--consent-token", help="Consent token issued out-of-band by Touchdown."),
    ],
) -> None:
    """Enable local telemetry spooling after explicit consent."""

    client = TelemetryClient()
    client.enable_pending_consent()
    try:
        status = client.grant_consent(consent_token)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if status.hard_disabled:
        typer.echo(
            "Telemetry remains disabled because DO_NOT_TRACK=1 or "
            "INFERGUARD_TELEMETRY=disabled is set."
        )
        raise typer.Exit(code=1)
    typer.echo(f"Telemetry enabled with consent. Token written to {client.consent_path}.")


@telemetry_app.command("disable")
def telemetry_disable_cmd() -> None:
    """Disable telemetry, delete the consent token, and clear local state."""

    client = TelemetryClient()
    client.disable(delete_pending=False)
    token_deleted = _unlink_if_exists(client.consent_path)
    state_deleted = _unlink_if_exists(client.state_path)
    typer.echo(
        "Telemetry disabled. "
        f"consent_token_deleted={_bool_text(token_deleted)} "
        f"state_cleared={_bool_text(state_deleted)}"
    )


@telemetry_app.command("log")
def telemetry_log_cmd(
    limit: Annotated[int, typer.Option("--limit", help="Maximum recent events to show.")] = 50,
) -> None:
    """Show recent local telemetry events and pending payload files."""

    client = TelemetryClient()
    ring = client.log_tail(limit)
    pending = _pending_payloads(client.uploads_pending_dir)[-limit:]
    if not ring and not pending:
        typer.echo("No telemetry events in local ring buffer or uploads-pending directory.")
        return
    sys.stdout.write(
        json.dumps(
            {"ring_buffer": ring, "pending_payloads": pending},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


@telemetry_app.command("verify-payload")
def telemetry_verify_payload_cmd(
    path: Annotated[Path, typer.Argument(help="Payload-pending JSON file or directory.")],
) -> None:
    """Render the exact local-only telemetry payload that would be uploaded."""

    payload_path = _resolve_payload_path(path)
    try:
        raw_payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        typer.echo(f"{payload_path}: invalid JSON: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    blocked = _blocked_key_paths(raw_payload)
    if blocked:
        typer.echo(
            "Payload contains never-collected sensitive field(s): " + ", ".join(blocked),
            err=True,
        )
        raise typer.Exit(code=3)
    try:
        payload = load_telemetry_payload(payload_path).as_dict()
    except TelemetryValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    client = TelemetryClient()
    output = {
        "local_only": True,
        "payload_path": str(payload_path),
        "upload_permitted_by_current_policy": client.can_upload(),
        "blocked_by_do_not_track": os.environ.get("DO_NOT_TRACK") == "1",
        "blocked_by_inferguard_telemetry_disabled": os.environ.get(
            "INFERGUARD_TELEMETRY", ""
        ).strip().lower()
        in {"disabled", "0", "false", "off"},
        "dropped_fields": [],
        "payload": payload,
    }
    sys.stdout.write(json.dumps(output, indent=2, sort_keys=True) + "\n")


# --- core async flow --------------------------------------------------------


async def _collect(
    *,
    prefill: str,
    decode: str,
    transfer: Optional[str],
    engine: Optional[EngineName],
    timeout: float,
) -> DisaggStatus:
    import httpx

    async with httpx.AsyncClient(timeout=timeout) as client:
        targets = [
            scrape(prefill, "prefill", engine, client),
            scrape(decode, "decode", engine, client),
        ]
        if transfer:
            targets.append(scrape(transfer, "transfer", engine, client))
        results = await asyncio.gather(*targets)

    prefill_snap = results[0]
    decode_snap = results[1]
    transfer_snap = results[2] if transfer else None
    status = DisaggStatus(
        prefill=prefill_snap,
        decode=decode_snap,
        transfer=transfer_snap,
    )
    findings = evaluate(status)
    return DisaggStatus(
        prefill=prefill_snap,
        decode=decode_snap,
        transfer=transfer_snap,
        findings=findings,
    )


async def _probe_server_prompt_tokens(
    *,
    endpoint: str,
    model: str,
    sample_text: str,
    timeout: float,
) -> Optional[int]:
    import httpx

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": sample_text}],
        "max_tokens": 1,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    prompt_tokens: Optional[int] = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", endpoint, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    line = line[len("data:") :].strip()
                if not line or line == "[DONE]":
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                usage = chunk.get("usage")
                if isinstance(usage, dict) and isinstance(usage.get("prompt_tokens"), int):
                    prompt_tokens = usage["prompt_tokens"]
    return prompt_tokens


# --- rendering --------------------------------------------------------------


def _render_table(status: DisaggStatus) -> None:
    console = Console()
    table = Table(show_header=True, header_style="bold")
    table.add_column("role")
    table.add_column("engine")
    table.add_column("connector")
    table.add_column("running")
    table.add_column("waiting")
    table.add_column("kv_usage")
    table.add_column("ttft(ms)")
    table.add_column("tpot(ms)")
    table.add_column("status")
    for snap in _iter(status):
        table.add_row(
            snap.endpoint.role,
            snap.endpoint.engine,
            snap.endpoint.connector or "-",
            _str(snap.requests_running),
            _str(snap.requests_waiting),
            _pct(snap.kv_cache_usage),
            _ms(snap.ttft_avg_seconds),
            _ms(snap.tpot_avg_seconds),
            snap.scrape_error or "ok",
        )
    console.print(table)

    if status.findings:
        console.print()
        console.print("[bold]Findings[/bold]")
        for f in status.findings:
            style = {"info": "dim", "warning": "yellow", "critical": "red"}[f.severity]
            console.print(f"[{style}]{f.severity.upper()}[/{style}] {f.code}: {f.message}")
    else:
        console.print()
        console.print("[green]OK[/green] — no findings.")


def _iter(status: DisaggStatus):
    yield status.prefill
    yield status.decode
    if status.transfer is not None:
        yield status.transfer


def _str(v: int | Optional[float]) -> str:
    return "-" if v is None else str(v)


def _pct(v: Optional[float]) -> str:
    return "-" if v is None else f"{v * 100:.0f}%" if v <= 1.0 else f"{v:.0f}"


def _ms(v: Optional[float]) -> str:
    return "-" if v is None else f"{v * 1000:.0f}"


# --- helpers ----------------------------------------------------------------


def _validated_engine(raw: str) -> Optional[EngineName]:
    if raw == "auto":
        return None
    if raw in ("vllm", "sglang", "dynamo", "lmcache", "llm-d"):
        return raw  # type: ignore[return-value]
    raise typer.BadParameter(
        f"--engine must be one of auto|vllm|sglang|dynamo|lmcache|llm-d (got {raw!r})"
    )


def _exit_code(status: DisaggStatus) -> int:
    return _exit_code_for_findings(status.findings)


def _exit_code_for_findings(findings: list[DisaggFinding | ProfileFinding]) -> int:
    if not findings:
        return 0
    severities = {f.severity for f in findings}
    if "critical" in severities:
        return 2
    if "warning" in severities:
        return 1
    return 0


def _validated_agent_framework(raw: str) -> str:
    if raw in AGENT_FRAMEWORKS:
        return raw
    allowed = "|".join(sorted(AGENT_FRAMEWORKS))
    raise typer.BadParameter(f"--framework must be one of {allowed} (got {raw!r})")


def _daemon_state_path() -> Path:
    return default_config_dir() / "daemon-state.json"


def _write_daemon_state(state: dict[str, object]) -> None:
    path = _daemon_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, state)


def _read_daemon_state() -> dict[str, object] | None:
    path = _daemon_state_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _clear_daemon_state() -> None:
    _unlink_if_exists(_daemon_state_path())


def _process_command(pid: int) -> str:
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _looks_like_inferguard_daemon(command_text: str) -> bool:
    lowered = command_text.lower()
    return "inferguard" in lowered and "daemon" in lowered and "start" in lowered


def _daemon_record_watch_dir(daemon: Daemon, watch_dir: Optional[Path], seen: set[Path]) -> int:
    if watch_dir is None:
        return 0
    if not watch_dir.exists() or not watch_dir.is_dir():
        raise typer.BadParameter(f"--watch-dir must be an existing directory (got {watch_dir})")
    count = 0
    for path in sorted(watch_dir.glob("*.jsonl")):
        marker = path.resolve()
        if marker in seen:
            continue
        try:
            count += daemon.record_agent_trace_file(path)
        except (OSError, ValueError) as exc:
            typer.echo(f"Skipping invalid trace file {path}: {exc}", err=True)
            continue
        seen.add(marker)
    return count


def _pending_payloads(directory: Path) -> list[dict[str, object]]:
    if not directory.exists():
        return []
    payloads: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime):
        payload_kind: Optional[str] = None
        schema_version: Optional[str] = None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if isinstance(raw, dict):
            payload_kind = raw.get("payload_kind") if isinstance(raw.get("payload_kind"), str) else None
            schema_version = (
                raw.get("schema_version") if isinstance(raw.get("schema_version"), str) else None
            )
        payloads.append(
            {
                "path": str(path),
                "payload_kind": payload_kind,
                "schema_version": schema_version,
            }
        )
    return payloads


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _unlink_if_exists(path: Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def _resolve_payload_path(path: Path) -> Path:
    if path.is_file():
        return path
    if not path.exists():
        raise typer.BadParameter(f"payload path does not exist: {path}")
    search_dir = path / "uploads-pending" if (path / "uploads-pending").is_dir() else path
    candidates = sorted(search_dir.glob("*.json"), key=lambda item: item.stat().st_mtime)
    if not candidates:
        raise typer.BadParameter(f"no pending payload JSON files found under {path}")
    return candidates[-1]


def _blocked_key_paths(value: object, *, prefix: str = "$") -> list[str]:
    if isinstance(value, dict):
        blocked: list[str] = []
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if _is_never_collected_key(str(key)):
                blocked.append(path)
            blocked.extend(_blocked_key_paths(item, prefix=path))
        return blocked
    if isinstance(value, list):
        blocked = []
        for index, item in enumerate(value):
            blocked.extend(_blocked_key_paths(item, prefix=f"{prefix}[{index}]"))
        return blocked
    return []


def _is_never_collected_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return normalized in NEVER_COLLECTED_KEYS or normalized.endswith("_api_key")


def _validated_kvcast_mode(raw: str) -> str:
    if raw in {"cold-pressure", "prefix-reuse", "mixed-agent", "eviction-probe", "fragmentation-probe", "multi-tenant-storm", "retry-storm"}:
        return raw
    raise typer.BadParameter("--mode must be one of cold-pressure|prefix-reuse|mixed-agent|eviction-probe|fragmentation-probe|multi-tenant-storm|retry-storm")


def _parse_sla_tiers(raw: Optional[str]) -> dict[str, str] | None:
    if raw in (None, ""):
        return None
    tiers: dict[str, str] = {}
    for part in raw.split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise typer.BadParameter("--sla-tiers entries must be name=policy")
        name, policy = part.split("=", 1)
        tiers[name.strip()] = policy.strip()
    return tiers or None


def _validated_arrival_mode(raw: str) -> str:
    if raw in {"steady", "poisson"}:
        return raw
    raise typer.BadParameter("--arrival-mode must be one of steady|poisson")


def _validated_metrics_engine(raw: str) -> Optional[EngineName]:
    if raw == "auto":
        return None
    if raw in ("vllm", "sglang", "dynamo", "lmcache", "llm-d"):
        return raw  # type: ignore[return-value]
    raise typer.BadParameter(
        f"--metrics-engine must be one of auto|vllm|sglang|dynamo|lmcache|llm-d (got {raw!r})"
    )

def _parse_int_csv(raw: str, option_name: str) -> list[int]:
    try:
        values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError as exc:
        raise typer.BadParameter(f"{option_name} must be a comma-separated list of integers") from exc
    if not values or any(value <= 0 for value in values):
        raise typer.BadParameter(f"{option_name} values must be positive integers")
    return values



def _parse_string_csv(raw: Optional[str]) -> list[str]:
    if raw in (None, ""):
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_float_kv_csv(raw: Optional[str], option_name: str) -> dict[str, float]:
    if raw in (None, ""):
        return {}
    parsed: dict[str, float] = {}
    for part in raw.split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise typer.BadParameter(f"{option_name} entries must be key=value")
        key, value = part.split("=", 1)
        try:
            parsed[key.strip()] = float(value.strip())
        except ValueError as exc:
            raise typer.BadParameter(f"{option_name} value for {key.strip()} must be numeric") from exc
    return parsed


def _run_compare(run_a_dir: Path, run_b_dir: Path, options: CompareOptions, *, json_out: bool) -> None:
    try:
        report = compare_runs(run_a_dir, run_b_dir, options)
    except CompareError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except OSError as exc:
        typer.echo(f"compare artifact writing failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    if json_out:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    else:
        typer.echo(f"Wrote InferGuard compare artifacts to {options.output_dir}.")
    severities = {finding.get("severity") for finding in report.get("findings", [])}
    raise typer.Exit(code=2 if "critical" in severities else 0)


def _run_bench(config: BenchConfig, func, *, json_out: bool) -> None:
    try:
        result = asyncio.run(func(config))
    except BenchError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except OSError as exc:
        typer.echo(f"benchmark artifact writing failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    _finish_bench(result, config.output_dir, json_out=json_out)


def _run_agentx_bench(config: AgentXReplayConfig, *, json_out: bool) -> None:
    try:
        result = run_agentx_replay(config)
    except BenchError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except OSError as exc:
        typer.echo(f"benchmark artifact writing failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    _finish_bench(result, config.output_dir, json_out=json_out)


def _run_upstream_bench(config: UpstreamBenchConfig, *, json_out: bool) -> None:
    try:
        result = run_upstream(config)
    except BenchError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except OSError as exc:
        typer.echo(f"benchmark artifact writing failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    _finish_bench(result, config.output_dir, json_out=json_out)


def _finish_bench(result: dict, output_dir: Path, *, json_out: bool) -> None:
    counts = result["summary"]["request_counts"]
    if json_out:
        sys.stdout.write(json.dumps(result["summary"], indent=2, sort_keys=True) + "\n")
    else:
        typer.echo(
            f"Wrote InferGuard bench artifacts to {output_dir} "
            f"({counts['success']}/{counts['total']} succeeded)."
        )
    raise typer.Exit(code=2 if counts["total"] and counts["success"] == 0 else 0)


if __name__ == "__main__":  # pragma: no cover
    app()
