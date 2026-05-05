"""Native InferGuard benchmark runner and artifact writer."""

from __future__ import annotations

import asyncio
import json
import math
import os
import random
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from itertools import cycle
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import urlsplit

import httpx

from inferguard import __version__
from inferguard.bench.client import OpenAIStreamingChatClient
from inferguard.bench.types import RequestMetric, RequestSpec
from inferguard.bench.workloads import WorkloadLoadError, generate_kv_stress_specs, load_trace_dir
from inferguard.disagg.adapters import scrape
from inferguard.disagg.types import EngineName
from inferguard.io import atomic_write_json
from inferguard.utils.jsonl import append_jsonl

BENCH_SCHEMA_VERSION = "inferguard-bench/v1"
CONFIG_SCHEMA_VERSION = "inferguard-bench-config/v1"
SUMMARY_SCHEMA_VERSION = "inferguard-bench-summary/v1"
METRICS_TIMELINE_SCHEMA_VERSION = "inferguard-metrics-timeline/v1"


class BenchError(RuntimeError):
    """Raised when a native benchmark cannot be run or written."""


@dataclass(frozen=True)
class BenchConfig:
    command: str
    endpoint: str
    model: str
    concurrency_levels: list[int]
    output_dir: Path
    output_tokens: int
    trace_dir: Path | None = None
    context_lengths: list[int] | None = None
    timeout_seconds: float = 300.0
    force: bool = False
    redact_prompts: bool = False
    kvcast_mode: str = "cold-pressure"
    requests_per_level: int = 4
    duration_seconds: float | None = None
    warmup_seconds: float = 0.0
    metrics_url: str | None = None
    metrics_interval_seconds: float = 5.0
    metrics_engine: EngineName | None = None
    arrival_mode: str = "steady"
    arrival_rate_rps: float | None = None
    track_cache_lineage: bool = False
    customers: int = 1
    sla_tiers: dict[str, str] | None = None
    inject_crash_after_seconds: float | None = None
    inject_giant_prefill_tokens: int | None = None
    allow_chaos: bool = False
    crash_recovery_threshold_seconds: float = 30.0
    cold_start_capture_seconds: float = 60.0
    idle_active_mix_mode: bool = False
    active_window_seconds: float = 60.0
    idle_window_seconds: float = 30.0
    burst_multiplier: float = 50.0
    burst_window_seconds: float = 30.0
    baseline_rps: float = 4.0
    canary_eval_set: str | None = None
    tool_call_schema: Path | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["output_dir"] = str(self.output_dir)
        data["trace_dir"] = str(self.trace_dir) if self.trace_dir is not None else None
        data["tool_call_schema"] = str(self.tool_call_schema) if self.tool_call_schema is not None else None
        return data


async def run_replay(config: BenchConfig) -> dict[str, Any]:
    if config.trace_dir is None:
        raise BenchError("trace_dir is required for bench replay")
    try:
        specs = load_trace_dir(config.trace_dir)
    except WorkloadLoadError as exc:
        raise BenchError(str(exc)) from exc
    specs = _inject_giant_prefill_spec(specs, config.inject_giant_prefill_tokens)
    return await _run_benchmark(config, specs)


async def run_kv_stress(config: BenchConfig) -> dict[str, Any]:
    if not config.context_lengths:
        raise BenchError("context_lengths is required for bench kv-stress")
    try:
        specs = generate_kv_stress_specs(
            context_lengths=config.context_lengths,
            output_tokens=config.output_tokens,
            requests_per_level=config.requests_per_level,
            mode=config.kvcast_mode,
            customers=config.customers,
            sla_tiers=config.sla_tiers,
        )
    except WorkloadLoadError as exc:
        raise BenchError(str(exc)) from exc
    return await _run_benchmark(config, specs)


async def run_cold_start(config: BenchConfig) -> dict[str, Any]:
    # Implements S-01 cold-start ramp characterization (see docs/inferguard/24).
    if config.trace_dir is not None:
        try:
            specs = load_trace_dir(config.trace_dir)
        except WorkloadLoadError as exc:
            raise BenchError(str(exc)) from exc
    else:
        specs = generate_kv_stress_specs(
            context_lengths=config.context_lengths or [1024],
            output_tokens=config.output_tokens,
            requests_per_level=config.requests_per_level,
            mode="mixed-agent",
        )
    return await _run_benchmark(replace(config, command="cold-start", warmup_seconds=0.0), specs)


def _inject_giant_prefill_spec(specs: list[RequestSpec], tokens: int | None) -> list[RequestSpec]:
    if tokens is None:
        return specs
    if not specs:
        raise BenchError("cannot inject giant prefill into an empty trace")
    anchor = specs[len(specs) // 2]
    target_chars = max(64, tokens * 4)
    line = (
        "InferGuard chaos giant prefill block. "
        "This request is intentionally oversized to characterize OOM blast radius.\n"
    )
    content = (line * (target_chars // len(line) + 1))[:target_chars]
    system_messages = [message for message in anchor.messages if message.get("role") == "system"][:1]
    injected = RequestSpec(
        request_id="chaos-giant-prefill:turn-0",
        trace_id="chaos-giant-prefill",
        session_id=f"{anchor.session_id}:chaos-giant-prefill",
        turn_index=anchor.turn_index + 1_000_000,
        workload_class="kv-pressure",
        messages=[
            *system_messages,
            {
                "role": "user",
                "content": content,
            },
        ],
        expected_input_tokens=tokens,
        expected_output_tokens=min(anchor.expected_output_tokens or 1, 16),
        prefix_group=None,
        tool_heavy=False,
        customer_id=anchor.customer_id,
        sla_tier=anchor.sla_tier,
        metadata={
            **anchor.metadata,
            "chaos_scenario": "oom_giant_prefill",
            "giant_prefill_tokens": tokens,
            "allow_chaos_required": True,
        },
    )
    insert_at = max(1, len(specs) // 2)
    return [*specs[:insert_at], injected, *specs[insert_at:]]


async def _run_benchmark(config: BenchConfig, specs: list[RequestSpec]) -> dict[str, Any]:
    _validate_config(config)
    run_id = _run_id(config.command)
    output_dir = config.output_dir
    if output_dir.exists() and any(output_dir.iterdir()) and not config.force:
        raise BenchError(f"output_dir is not empty: {output_dir} (choose a new directory or pass --force)")
    output_dir.mkdir(parents=True, exist_ok=True)
    if config.command == "cold-start" and config.duration_seconds is None:
        config = replace(config, duration_seconds=config.cold_start_capture_seconds)

    run_started_at = _now_iso()
    run_perf_start = time.perf_counter()
    config_path = output_dir / "config.json"
    run_path = output_dir / "run.json"
    requests_path = output_dir / "requests.jsonl"
    metrics_path = output_dir / "metrics.jsonl"
    metrics_timeline_path = output_dir / "metrics_timeline.jsonl"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"

    _write_json(config_path, {"schema_version": CONFIG_SCHEMA_VERSION, "run_id": run_id, **config.as_dict(), "topology": _topology_from_env()})
    requests_path.write_text("", encoding="utf-8")
    metrics_path.write_text("", encoding="utf-8")
    append_jsonl(requests_path, (_request_spec_for_artifact(spec, redact=config.redact_prompts) for spec in specs))

    metrics: list[RequestMetric] = []
    client = OpenAIStreamingChatClient(
        config.endpoint,
        model=config.model,
        timeout=config.timeout_seconds,
    )
    timeout = httpx.Timeout(config.timeout_seconds, connect=min(30.0, config.timeout_seconds))
    timeline = MetricsTimelineCollector(
        url=config.metrics_url,
        interval_seconds=config.metrics_interval_seconds,
        engine=config.metrics_engine,
        path=metrics_timeline_path,
    )
    async with httpx.AsyncClient(timeout=timeout) as http:
        await timeline.start(http)
        try:
            base_specs = [spec for spec in specs if not _is_giant_prefill_spec(spec)] or specs
            for level_index, level in enumerate(config.concurrency_levels):
                level_specs = specs if level_index == 0 else base_specs
                level_metrics = await _run_level(
                    client=http_client_wrapper(client, http),
                    specs=level_specs,
                    concurrency=level,
                    output_tokens=config.output_tokens,
                    command=config.command,
                    duration_seconds=config.duration_seconds,
                    warmup_seconds=config.warmup_seconds,
                    arrival_mode=config.arrival_mode,
                    arrival_rate_rps=config.arrival_rate_rps,
                    idle_active_mix_mode=config.idle_active_mix_mode,
                    active_window_seconds=config.active_window_seconds,
                    idle_window_seconds=config.idle_window_seconds,
                    retry_storm_mode=config.kvcast_mode == "retry-storm",
                    burst_multiplier=config.burst_multiplier,
                    burst_window_seconds=config.burst_window_seconds,
                    baseline_rps=config.baseline_rps,
                    capture_response_text=config.tool_call_schema is not None,
                )
                level_metrics = _apply_measured_kv_labels(level_metrics, timeline.observed_perf_times)
                if config.track_cache_lineage:
                    level_metrics = _annotate_cache_lineage(level_metrics)
                metrics.extend(level_metrics)
                append_jsonl(metrics_path, (metric.as_dict() for metric in level_metrics))
        finally:
            await timeline.stop()

    oom_giant_prefill = _oom_giant_prefill_summary(config, metrics)
    if oom_giant_prefill is not None:
        _append_oom_giant_prefill_timeline(
            oom_giant_prefill,
            metrics_timeline_path,
            starting_sequence=timeline.captured_count,
        )
        timeline.captured_count += 3
    if _should_emit_customer_timeline(config, metrics):
        _append_customer_kv_timeline(metrics, metrics_timeline_path, starting_sequence=timeline.captured_count)
        if metrics:
            timeline.captured_count = max(timeline.captured_count, 1)
    runtime_seconds = time.perf_counter() - run_perf_start
    summary = build_summary(
        metrics,
        run_id=run_id,
        command=config.command,
        runtime_seconds=runtime_seconds,
        model=config.model,
        endpoint=config.endpoint,
        kvcast_mode=config.kvcast_mode if config.command in {"kv-stress", "kvcast"} else None,
        requests_per_level=config.requests_per_level,
        redact_prompts=config.redact_prompts,
        duration_seconds=config.duration_seconds,
        warmup_seconds=config.warmup_seconds,
        metrics_timeline_present=timeline.captured_count > 0,
        metrics_scrape_interval_seconds=config.metrics_interval_seconds,
        track_cache_lineage=config.track_cache_lineage,
        chaos_recovery=_chaos_recovery_summary(config, runtime_seconds, metrics),
        oom_giant_prefill=oom_giant_prefill,
        idle_active_mix=_idle_active_mix_summary(config, runtime_seconds),
        retry_storm=_retry_storm_summary(config, metrics, metrics_timeline_path),
        canary_quality=_canary_quality_summary(config),
        tool_call_schema_eval=_tool_call_schema_summary(config, metrics),
    )
    _write_json(summary_path, summary)
    report_path.write_text(render_report(summary, config), encoding="utf-8")

    completed_at = _now_iso()
    run = {
        "schema_version": BENCH_SCHEMA_VERSION,
        "run_id": run_id,
        "command": config.command,
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
            **({"metrics_timeline_jsonl": str(metrics_timeline_path)} if timeline.captured_count > 0 else {}),
        },
    }
    _write_json(run_path, run)
    return {"run": run, "summary": summary}


@dataclass(frozen=True)
class http_client_wrapper:  # noqa: N801 - private callable wrapper, not a public class name
    bench_client: OpenAIStreamingChatClient
    http: httpx.AsyncClient

    async def stream_chat(
        self,
        *,
        messages: list[dict[str, Any]],
        output_tokens: int,
        metadata: dict[str, Any],
    ):
        return await self.bench_client.stream_chat(
            self.http,
            messages=messages,
            output_tokens=output_tokens,
            metadata=metadata,
        )


@dataclass
class MetricsTimelineCollector:
    url: str | None
    interval_seconds: float
    engine: EngineName | None
    path: Path
    task: asyncio.Task[None] | None = None
    stop_event: asyncio.Event | None = None
    observed_perf_times: list[float] | None = None
    captured_count: int = 0

    async def start(self, client: httpx.AsyncClient) -> None:
        if self.url is None:
            self.observed_perf_times = []
            return
        self.path.write_text("", encoding="utf-8")
        self.observed_perf_times = []
        self.stop_event = asyncio.Event()
        self.task = asyncio.create_task(self._run(client))

    async def stop(self) -> None:
        if self.task is None or self.stop_event is None:
            return
        self.stop_event.set()
        await self.task

    async def _run(self, client: httpx.AsyncClient) -> None:
        assert self.stop_event is not None
        assert self.observed_perf_times is not None
        sequence = 0
        scrape_url = _normalize_metrics_scrape_url(self.url or "")
        while not self.stop_event.is_set():
            try:
                snapshot = await scrape(scrape_url, "prefill", self.engine, client)
                observed_perf = time.perf_counter()
                append_jsonl(
                    self.path,
                    [
                        {
                            "schema_version": METRICS_TIMELINE_SCHEMA_VERSION,
                            "observed_at": _now_iso(),
                            "sequence": sequence,
                            "disagg_snapshot": snapshot.as_dict(),
                        }
                    ],
                )
                self.observed_perf_times.append(observed_perf)
                self.captured_count += 1
                sequence += 1
            except Exception as exc:  # noqa: BLE001 - metrics scraping must not fail the bench
                print(f"metrics scrape failed: {exc}", file=sys.stderr)
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass


async def _run_level(
    *,
    client: http_client_wrapper,
    specs: list[RequestSpec],
    concurrency: int,
    output_tokens: int,
    command: str,
    duration_seconds: float | None,
    warmup_seconds: float,
    arrival_mode: str = "steady",
    arrival_rate_rps: float | None = None,
    idle_active_mix_mode: bool = False,
    active_window_seconds: float = 60.0,
    idle_window_seconds: float = 30.0,
    retry_storm_mode: bool = False,
    burst_multiplier: float = 50.0,
    burst_window_seconds: float = 30.0,
    baseline_rps: float = 4.0,
    capture_response_text: bool = False,
) -> list[RequestMetric]:
    if retry_storm_mode:
        return await _run_retry_storm_level(
            client=client,
            specs=specs,
            concurrency=concurrency,
            output_tokens=output_tokens,
            command=command,
            duration_seconds=duration_seconds,
            warmup_seconds=warmup_seconds,
            burst_multiplier=burst_multiplier,
            burst_window_seconds=burst_window_seconds,
            baseline_rps=baseline_rps,
            capture_response_text=capture_response_text,
        )
    if arrival_mode == "poisson" or command == "kvcast" and any(s.metadata.get("kvcast_mode") == "multi-tenant-storm" for s in specs):
        return await _run_poisson_level(
            client=client,
            specs=specs,
            concurrency=concurrency,
            output_tokens=output_tokens,
            command=command,
            duration_seconds=duration_seconds,
            warmup_seconds=warmup_seconds,
            arrival_rate_rps=arrival_rate_rps or max(1.0, float(config_customers_from_specs(specs))),
            idle_active_mix_mode=idle_active_mix_mode,
            active_window_seconds=active_window_seconds,
            idle_window_seconds=idle_window_seconds,
            capture_response_text=capture_response_text,
        )
    if arrival_mode != "steady":
        raise BenchError("arrival_mode must be one of steady|poisson")

    if duration_seconds is None:
        level_started = time.perf_counter()
        return list(
            await asyncio.gather(
                *(
                    _run_one_request(
                        client=client,
                        spec=spec,
                        sequence=idx,
                        concurrency=concurrency,
                        output_tokens=output_tokens,
                        command=command,
                        level_started=level_started,
                        warmup_seconds=0.0,
                        scheduled_arrival_time=level_started,
                        capture_response_text=capture_response_text,
                    )
                    for idx, spec in enumerate(specs)
                )
            )
        )

    if duration_seconds <= 0:
        raise BenchError("duration_seconds must be positive when provided")
    if warmup_seconds < 0:
        raise BenchError("warmup_seconds must be non-negative")
    if warmup_seconds >= duration_seconds:
        raise BenchError("warmup_seconds must be less than duration_seconds")

    metrics: list[RequestMetric] = []
    spec_iter = cycle(specs)
    level_started = time.perf_counter()
    deadline = level_started + duration_seconds
    sequence = 0
    while time.perf_counter() < deadline:
        await _sleep_until_active_window(
            level_started,
            active_window_seconds,
            idle_window_seconds,
            enabled=idle_active_mix_mode,
            deadline=deadline,
        )
        if time.perf_counter() >= deadline:
            break
        batch = []
        for _ in range(concurrency):
            if time.perf_counter() >= deadline:
                break
            spec = next(spec_iter)
            batch.append(
                _run_one_request(
                    client=client,
                    spec=spec,
                    sequence=sequence,
                    concurrency=concurrency,
                    output_tokens=output_tokens,
                    command=command,
                    level_started=level_started,
                    warmup_seconds=warmup_seconds,
                    scheduled_arrival_time=level_started,
                    idle_mix_started_at=level_started if idle_active_mix_mode else None,
                    active_window_seconds=active_window_seconds,
                    idle_window_seconds=idle_window_seconds,
                    capture_response_text=capture_response_text,
                )
            )
            sequence += 1
        if not batch:
            break
        metrics.extend(await asyncio.gather(*batch))
    return metrics


async def _run_poisson_level(
    *,
    client: http_client_wrapper,
    specs: list[RequestSpec],
    concurrency: int,
    output_tokens: int,
    command: str,
    duration_seconds: float | None,
    warmup_seconds: float,
    arrival_rate_rps: float | None,
    idle_active_mix_mode: bool = False,
    active_window_seconds: float = 60.0,
    idle_window_seconds: float = 30.0,
    capture_response_text: bool = False,
) -> list[RequestMetric]:
    if arrival_rate_rps is None or arrival_rate_rps <= 0:
        raise BenchError("arrival_rate_rps must be positive in poisson arrival mode")
    if duration_seconds is not None and duration_seconds <= 0:
        raise BenchError("duration_seconds must be positive when provided")
    if warmup_seconds < 0:
        raise BenchError("warmup_seconds must be non-negative")
    if duration_seconds is not None and warmup_seconds >= duration_seconds:
        raise BenchError("warmup_seconds must be less than duration_seconds")

    level_started = time.perf_counter()
    deadline = level_started + duration_seconds if duration_seconds is not None else None
    spec_iter = cycle(specs)
    semaphore = asyncio.Semaphore(concurrency)
    tasks: list[asyncio.Task[RequestMetric]] = []
    count = len(specs) if duration_seconds is None else 1_000_000
    for sequence, offset in enumerate(poisson_arrival_offsets(count, rate_rps=arrival_rate_rps)):
        scheduled = level_started + offset
        if deadline is not None and scheduled >= deadline:
            break
        if idle_active_mix_mode and _idle_active_phase(scheduled - level_started, active_window_seconds, idle_window_seconds) == "idle":
            continue
        delay = scheduled - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        spec = next(spec_iter)
        tasks.append(
            asyncio.create_task(
                _run_one_request_with_optional_semaphore(
                    semaphore,
                    client=client,
                    spec=spec,
                    sequence=sequence,
                    concurrency=concurrency,
                    output_tokens=output_tokens,
                    command=command,
                    level_started=level_started,
                    warmup_seconds=warmup_seconds,
                    scheduled_arrival_time=scheduled,
                    idle_mix_started_at=level_started if idle_active_mix_mode else None,
                    active_window_seconds=active_window_seconds,
                    idle_window_seconds=idle_window_seconds,
                    capture_response_text=capture_response_text,
                )
            )
        )
        if duration_seconds is None and sequence + 1 >= len(specs):
            break
    return list(await asyncio.gather(*tasks))


async def _run_retry_storm_level(
    *,
    client: http_client_wrapper,
    specs: list[RequestSpec],
    concurrency: int,
    output_tokens: int,
    command: str,
    duration_seconds: float | None,
    warmup_seconds: float,
    burst_multiplier: float,
    burst_window_seconds: float,
    baseline_rps: float,
    capture_response_text: bool = False,
) -> list[RequestMetric]:
    if baseline_rps <= 0:
        raise BenchError("baseline_rps must be positive for retry-storm mode")
    if burst_multiplier <= 0:
        raise BenchError("burst_multiplier must be positive for retry-storm mode")
    if burst_window_seconds <= 0:
        raise BenchError("burst_window_seconds must be positive for retry-storm mode")
    run_seconds = duration_seconds or max(1.0, burst_window_seconds)
    level_started = time.perf_counter()
    deadline = level_started + run_seconds
    burst_end = min(deadline, level_started + burst_window_seconds)
    spec_iter = cycle(specs)
    semaphore = asyncio.Semaphore(concurrency)
    tasks: list[asyncio.Task[RequestMetric]] = []
    sequence = 0
    scheduled = level_started
    while scheduled < deadline:
        elapsed = scheduled - level_started
        in_burst = scheduled < burst_end
        rate = baseline_rps * burst_multiplier if in_burst else baseline_rps
        delay = scheduled - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        spec = _retry_storm_spec(next(spec_iter), burst_multiplier, burst_window_seconds, baseline_rps, in_burst)
        tasks.append(
            asyncio.create_task(
                _run_one_request_with_optional_semaphore(
                    semaphore,
                    client=client,
                    spec=spec,
                    sequence=sequence,
                    concurrency=concurrency,
                    output_tokens=output_tokens,
                    command=command,
                    level_started=level_started,
                    warmup_seconds=warmup_seconds,
                    scheduled_arrival_time=scheduled,
                    capture_response_text=capture_response_text,
                )
            )
        )
        sequence += 1
        if duration_seconds is None and sequence >= len(specs):
            break
        scheduled += 1.0 / rate
        if elapsed > run_seconds:
            break
    return list(await asyncio.gather(*tasks))


async def _run_one_request_with_optional_semaphore(
    semaphore: asyncio.Semaphore | None,
    **kwargs: Any,
) -> RequestMetric:
    if semaphore is None:
        return await _run_one_request(**kwargs)
    async with semaphore:
        return await _run_one_request(**kwargs)


def config_customers_from_specs(specs: list[RequestSpec]) -> int:
    customers = {spec.customer_id or spec.metadata.get("customer_id") for spec in specs}
    return len({str(c) for c in customers if c not in (None, "")}) or 1


def poisson_arrival_offsets(count: int, *, rate_rps: float, seed: int | None = 0) -> list[float]:
    rng = random.Random(seed)
    offsets: list[float] = []
    elapsed = 0.0
    for _ in range(count):
        elapsed += rng.expovariate(rate_rps)
        offsets.append(elapsed)
    return offsets


def _retry_storm_spec(
    spec: RequestSpec,
    burst_multiplier: float,
    burst_window_seconds: float,
    baseline_rps: float,
    in_burst: bool,
) -> RequestSpec:
    metadata = {
        **spec.metadata,
        "retry_storm": {
            "burst_multiplier": burst_multiplier,
            "burst_window_seconds": burst_window_seconds,
            "baseline_rps": baseline_rps,
            "burst_peak_qps": baseline_rps * burst_multiplier,
            "phase": "burst" if in_burst else "recovery",
        },
    }
    return replace(spec, metadata=metadata)


def _arrival_phase(sequence: int, *, window: int = 32) -> str:
    """Return the deterministic 32-request on/off phase used by arrival tests."""
    if window <= 0:
        raise BenchError("arrival phase window must be positive")
    return "on" if (sequence // window) % 2 == 0 else "off"


async def _run_one_request(
    *,
    client: http_client_wrapper,
    spec: RequestSpec,
    sequence: int,
    concurrency: int,
    output_tokens: int,
    command: str,
    level_started: float,
    warmup_seconds: float,
    scheduled_arrival_time: float | None = None,
    idle_mix_started_at: float | None = None,
    active_window_seconds: float = 60.0,
    idle_window_seconds: float = 30.0,
    capture_response_text: bool = False,
) -> RequestMetric:
    result = await client.stream_chat(
        messages=spec.messages,
        output_tokens=spec.expected_output_tokens or output_tokens,
        metadata={**spec.metadata, "customer_id": _customer_id(spec), "sla_tier": spec.sla_tier} if _customer_id(spec) else spec.metadata,
    )
    tps = None
    if result.success and result.latency_seconds > 0:
        tps = result.output_tokens / result.latency_seconds
    kv_label = None
    if command in {"replay", "kv-stress", "kvcast"}:
        kv_label = "inferred_without_engine_metrics"
    phase = "warmup" if warmup_seconds and (result.end_time - level_started) < warmup_seconds else "measurement"
    metadata = {**spec.metadata, "phase": phase, "sequence": sequence}
    customer_id = _customer_id(spec)
    if customer_id:
        # Implements S-21 per-customer KV footprint accounting (see docs/inferguard/24).
        metadata["customer_id"] = customer_id
    if spec.sla_tier:
        metadata["sla_tier"] = spec.sla_tier
    if capture_response_text:
        metadata["response_text"] = result.output_text[:4096]
    if scheduled_arrival_time is not None:
        metadata["scheduled_arrival_time"] = scheduled_arrival_time
        metadata["arrival_delay_seconds"] = max(0.0, result.start_time - scheduled_arrival_time)
    if idle_mix_started_at is not None:
        elapsed = max(0.0, result.start_time - idle_mix_started_at)
        active_fraction = _active_fraction(active_window_seconds, idle_window_seconds)
        metadata["idle_active_mix"] = {
            "mode": "alternating_active_idle",
            "phase": _idle_active_phase(elapsed, active_window_seconds, idle_window_seconds),
            "active_window_seconds": active_window_seconds,
            "idle_window_seconds": idle_window_seconds,
            "cycle_elapsed_seconds": elapsed % (active_window_seconds + idle_window_seconds),
            "estimated_gpu_utilization": active_fraction,
            "idle_fraction": 1.0 - active_fraction,
        }
    return RequestMetric(
        request_id=f"{spec.request_id}:seq-{sequence}",
        trace_id=spec.trace_id,
        session_id=spec.session_id,
        turn_index=spec.turn_index,
        workload_class=spec.workload_class,
        concurrency=concurrency,
        success=result.success,
        start_time=result.start_time,
        end_time=result.end_time,
        latency_seconds=result.latency_seconds,
        ttft_seconds=result.ttft_seconds,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        input_tokens_source=result.input_tokens_source,
        output_tokens_source=result.output_tokens_source,
        tokens_per_second=tps,
        error=result.error,
        status_code=result.status_code,
        first_sse_seconds=result.first_sse_seconds,
        first_content_token_seconds=result.first_content_token_seconds,
        done_seen=result.done_seen,
        valid_content_seen=result.valid_content_seen,
        prefix_group=spec.prefix_group,
        tool_heavy=spec.tool_heavy,
        customer_id=customer_id,
        sla_tier=spec.sla_tier,
        kv_pressure_label=kv_label,
        client_queue_time_ms=(result.client_queue_seconds * 1000.0)
        if result.client_queue_seconds is not None
        else None,
        engine_processing_time_ms=(result.engine_processing_seconds * 1000.0)
        if result.engine_processing_seconds is not None
        else None,
        tool_simulation_time_ms=result.tool_simulation_seconds * 1000.0,
        network_overhead_ms=(result.network_overhead_seconds * 1000.0)
        if result.network_overhead_seconds is not None
        else None,
        metadata=metadata,
    )


def build_summary(
    metrics: list[RequestMetric],
    *,
    run_id: str,
    command: str,
    runtime_seconds: float,
    model: str,
    endpoint: str,
    kvcast_mode: str | None = None,
    requests_per_level: int | None = None,
    redact_prompts: bool = False,
    duration_seconds: float | None = None,
    warmup_seconds: float = 0.0,
    metrics_timeline_present: bool = False,
    metrics_scrape_interval_seconds: float = 5.0,
    track_cache_lineage: bool = False,
    chaos_recovery: dict[str, Any] | None = None,
    oom_giant_prefill: dict[str, Any] | None = None,
    idle_active_mix: dict[str, Any] | None = None,
    retry_storm: dict[str, Any] | None = None,
    canary_quality: dict[str, Any] | None = None,
    tool_call_schema_eval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_total = len(metrics)
    measured_metrics = [m for m in metrics if m.metadata.get("phase") != "warmup"]
    metrics = measured_metrics
    total = len(metrics)
    successes = [m for m in metrics if m.success]
    failed = total - len(successes)
    latency = [m.latency_seconds for m in successes]
    ttft = [m.ttft_seconds for m in successes if m.ttft_seconds is not None]
    tps = [m.tokens_per_second for m in successes if m.tokens_per_second is not None]
    estimated_input = sum(m.input_tokens for m in metrics if m.input_tokens_source == "estimated")
    estimated_output = sum(m.output_tokens for m in metrics if m.output_tokens_source == "estimated")
    output_tokens = sum(m.output_tokens for m in successes)
    customer_breakdown = _customer_breakdown(metrics)
    cold_start = _cold_start_summary(metrics) if command == "cold-start" else None

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "run_id": run_id,
        "command": command,
        "model": model,
        "endpoint": endpoint,
        "benchmark_mode": command,
        "kvcast_mode": kvcast_mode,
        "requests_per_level": requests_per_level,
        "duration_seconds": duration_seconds,
        "warmup_seconds": warmup_seconds,
        "redact_prompts": redact_prompts,
        "metrics_timeline_present": metrics_timeline_present,
        "metrics_scrape_interval_seconds": metrics_scrape_interval_seconds,
        "raw_request_counts": {"total_including_warmup": raw_total, "measurement_total": total},
        "request_counts": {
            "total": total,
            "success": len(successes),
            "failed": failed,
            "failed_rate": (failed / total) if total else 0.0,
        },
        "runtime_seconds": runtime_seconds,
        "latency_seconds": _percentile_block(latency),
        "ttft_seconds": _percentile_block(ttft),
        "average_tokens_per_second": mean(tps) if tps else None,
        "throughput_req_per_second": (total / runtime_seconds) if runtime_seconds > 0 else None,
        "output_tokens_per_second_wall": (output_tokens / runtime_seconds) if runtime_seconds > 0 else None,
        "tokens": {
            "input_total": sum(m.input_tokens for m in metrics),
            "output_total": sum(m.output_tokens for m in metrics),
            "estimated_input_tokens": estimated_input,
            "estimated_output_tokens": estimated_output,
        },
        "gpu_idle_ratio": _gpu_idle_ratio_block(metrics, runtime_seconds),
        "concurrency": _concurrency_summaries(metrics),
        "workloads": _workload_breakdown(metrics),
        "customer_breakdown": customer_breakdown,
        "cache_lineage": _cache_lineage_summary(metrics) if track_cache_lineage else None,
        "cold_start": cold_start,
        "chaos_recovery": chaos_recovery,
        "oom_giant_prefill": oom_giant_prefill,
        "idle_active_mix": idle_active_mix,
        "retry_storm": retry_storm,
        "canary_quality": canary_quality,
        "tool_call_schema_eval": tool_call_schema_eval,
        "limitations": [
            "Token counts are exact only when the endpoint returns OpenAI usage fields; otherwise they are estimated.",
            "KV pressure is inferred from request shape unless engine metrics are collected separately.",
            *( ["🟡 PENDING: full block-level prefix-cache lineage requires upstream engine instrumentation."] if track_cache_lineage else [] ),
            *( ["🟡 PENDING: crash injection is test-gated; full SGLang #23743 reproduction requires matching SGLang version detection."] if chaos_recovery else [] ),
            *( ["Giant-prefill OOM injection is gated by --allow-chaos and characterizes blast radius; it does not remediate the endpoint."] if oom_giant_prefill else [] ),
            *( ["Idle/active mix mode intentionally inserts idle windows to characterize utilization economics."] if idle_active_mix else [] ),
            *( ["Retry-storm mode intentionally bursts request arrivals to characterize queue recovery and overload behavior."] if retry_storm else [] ),
            *( ["Canary eval set scoring is artifact-based and supplies rollout quality evidence; orchestration rollback remains external."] if canary_quality else [] ),
            *( ["Tool-call schema validation checks response structure contract compliance; it does not replace application contract tests."] if tool_call_schema_eval else [] ),
            "TTFT is measured from request start to first non-empty streamed content token; first SSE timing is stored separately.",
            *( [f"Warmup excluded: {raw_total - total} request rows omitted from summary metrics."] if raw_total != total else [] ),
            *(_saturation_limitations(metrics)),
        ],
    }


def render_report(summary: dict[str, Any], config: BenchConfig) -> str:
    counts = summary["request_counts"]
    lines = [
        "# InferGuard Bench Report",
        "",
        f"- Run: `{summary['run_id']}`",
        f"- Command: `{summary['command']}`",
        f"- KVCast mode: `{summary.get('kvcast_mode') or '-'}`",
        f"- Model: `{summary['model']}`",
        f"- Endpoint: `{summary['endpoint']}`",
        f"- Requests: {counts['success']} success / {counts['total']} total ({counts['failed']} failed)",
        f"- Runtime: {summary['runtime_seconds']:.3f}s",
        f"- Throughput: {_fmt(summary['throughput_req_per_second'])} req/s",
        f"- Average per-request output tokens/sec: {_fmt(summary['average_tokens_per_second'])}",
        "",
        "## Latency",
        f"- p50 latency: {_fmt(summary['latency_seconds']['p50'])}s",
        f"- p95 latency: {_fmt(summary['latency_seconds']['p95'])}s",
        f"- p99 latency: {_fmt(summary['latency_seconds']['p99'])}s",
        f"- p50 TTFT: {_fmt(summary['ttft_seconds']['p50'])}s",
        f"- p95 TTFT: {_fmt(summary['ttft_seconds']['p95'])}s",
        f"- p99 TTFT: {_fmt(summary['ttft_seconds']['p99'])}s",
        "",
        "## Concurrency levels",
        "| Concurrency | Total | Success | Failed | p95 latency | p95 TTFT | Throughput req/s |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary["concurrency"]:
        lines.append(
            "| {concurrency} | {total} | {success} | {failed} | {lat} | {ttft} | {tput} |".format(
                concurrency=item["concurrency"],
                total=item["total"],
                success=item["success"],
                failed=item["failed"],
                lat=_fmt(item["latency_seconds"]["p95"]),
                ttft=_fmt(item["ttft_seconds"]["p95"]),
                tput=_fmt(item["throughput_req_per_second"]),
            )
        )
    lines.extend([
        "",
        "## Workload breakdown",
    ])
    for workload, item in summary["workloads"].items():
        lines.append(f"- `{workload}`: {item['success']} success / {item['total']} total")
    lines.extend([
        "",
        "## Artifacts",
        f"- Output directory: `{config.output_dir}`",
        "- `run.json`, `config.json`, `requests.jsonl`, `metrics.jsonl`, `summary.json`, `report.md`",
        "",
        "## Limitations",
    ])
    lines.extend(f"- {item}" for item in summary["limitations"])
    return "\n".join(lines) + "\n"


def _request_spec_for_artifact(spec: RequestSpec, *, redact: bool) -> dict[str, Any]:
    data = spec.as_dict()
    if redact:
        redacted_messages = []
        for message in data.get("messages", []):
            if isinstance(message, dict):
                redacted = dict(message)
                if "content" in redacted:
                    redacted["content"] = "<redacted>"
                redacted_messages.append(redacted)
            else:
                redacted_messages.append(message)
        data["messages"] = redacted_messages
        data.setdefault("metadata", {})["prompts_redacted"] = True
    return data


def _saturation_limitations(metrics: list[RequestMetric]) -> list[str]:
    if not metrics:
        return []
    limitations = []
    for level in sorted({m.concurrency for m in metrics}):
        rows = [m for m in metrics if m.concurrency == level]
        if len(rows) <= level:
            limitations.append(
                f"Concurrency level {level} used only {len(rows)} requests; treat throughput as finite-batch, not steady-state."
            )
    return limitations


def _gpu_idle_ratio_block(metrics: list[RequestMetric], duration_seconds: float) -> dict[str, float | None]:
    ratios = []
    tool_ms_total = 0.0
    for metric in metrics:
        tool_ms = metric.tool_simulation_time_ms
        if tool_ms is None:
            continue
        latency_ms = metric.latency_seconds * 1000.0
        ratio = 0.0 if latency_ms <= 0 else max(0.0, min(1.0, tool_ms / latency_ms))
        ratios.append(ratio)
        tool_ms_total += max(0.0, tool_ms)
    return {
        "p50": _percentile(ratios, 50),
        "p95": _percentile(ratios, 95),
        "p99": _percentile(ratios, 99),
        "overall": (tool_ms_total / (duration_seconds * 1000.0)) if duration_seconds > 0 else None,
    }


def _concurrency_summaries(metrics: list[RequestMetric]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for level in sorted({m.concurrency for m in metrics}):
        rows = [m for m in metrics if m.concurrency == level]
        success = [m for m in rows if m.success]
        starts = [m.start_time for m in rows]
        ends = [m.end_time for m in rows]
        runtime = (max(ends) - min(starts)) if starts and ends else 0.0
        items.append(
            {
                "concurrency": level,
                "total": len(rows),
                "success": len(success),
                "failed": len(rows) - len(success),
                "failed_rate": ((len(rows) - len(success)) / len(rows)) if rows else 0.0,
                "runtime_seconds": runtime,
                "throughput_req_per_second": (len(rows) / runtime) if runtime > 0 else None,
                "latency_seconds": _percentile_block([m.latency_seconds for m in success]),
                "ttft_seconds": _percentile_block(
                    [m.ttft_seconds for m in success if m.ttft_seconds is not None]
                ),
            }
        )
    return items


def _workload_breakdown(metrics: list[RequestMetric]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for workload in sorted({m.workload_class for m in metrics}):
        rows = [m for m in metrics if m.workload_class == workload]
        success = [m for m in rows if m.success]
        out[workload] = {
            "total": len(rows),
            "success": len(success),
            "failed": len(rows) - len(success),
            "latency_seconds": _percentile_block([m.latency_seconds for m in success]),
            "ttft_seconds": _percentile_block(
                [m.ttft_seconds for m in success if m.ttft_seconds is not None]
            ),
        }
    return out


def _percentile_block(values: list[float]) -> dict[str, float | None]:
    return {"p50": _percentile(values, 50), "p95": _percentile(values, 95), "p99": _percentile(values, 99)}


def _percentile(values: list[float], pct: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[idx]


def _topology_from_env() -> dict[str, Any]:
    keys = [
        "TP",
        "EP_SIZE",
        "DP_ATTENTION",
        "OFFLOADING",
        "SPEC_DECODING",
        "HW",
        "RUNNER_TYPE",
        "MODEL_PREFIX",
        "FRAMEWORK",
        "PRECISION",
        "IMAGE",
        "IS_MULTINODE",
        "PREFILL_NUM_WORKERS",
        "PREFILL_TP",
        "PREFILL_EP",
        "PREFILL_DP_ATTN",
        "DECODE_NUM_WORKERS",
        "DECODE_TP",
        "DECODE_EP",
        "DECODE_DP_ATTN",
    ]
    return {key.lower(): os.environ.get(key) for key in keys}


def _validate_config(config: BenchConfig) -> None:
    if not config.endpoint.startswith(("http://", "https://")):
        raise BenchError("endpoint must start with http:// or https://")
    parsed = urlsplit(config.endpoint)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise BenchError("endpoint must not include userinfo, query strings, or fragments")
    if not config.model:
        raise BenchError("model is required")
    if not config.concurrency_levels or any(level <= 0 for level in config.concurrency_levels):
        raise BenchError("concurrency levels must be positive integers")
    if config.output_tokens <= 0:
        raise BenchError("output_tokens must be positive")
    if config.requests_per_level <= 0:
        raise BenchError("requests_per_level must be positive")
    if config.duration_seconds is not None and config.duration_seconds <= 0:
        raise BenchError("duration_seconds must be positive")
    if config.warmup_seconds < 0:
        raise BenchError("warmup_seconds must be non-negative")
    if config.duration_seconds is None and config.warmup_seconds:
        raise BenchError("warmup_seconds requires duration_seconds")
    if config.duration_seconds is not None and config.warmup_seconds >= config.duration_seconds:
        raise BenchError("warmup_seconds must be less than duration_seconds")
    if config.kvcast_mode not in {"prefix-reuse", "cold-pressure", "mixed-agent", "eviction-probe", "fragmentation-probe", "multi-tenant-storm", "retry-storm"}:
        raise BenchError("kvcast_mode must be one of prefix-reuse|cold-pressure|mixed-agent|eviction-probe|fragmentation-probe|multi-tenant-storm|retry-storm")
    if config.customers <= 0:
        raise BenchError("customers must be positive")
    if config.inject_crash_after_seconds is not None and not config.allow_chaos:
        raise BenchError("--inject-crash-after-seconds requires --allow-chaos")
    if config.inject_giant_prefill_tokens is not None and not config.allow_chaos:
        raise BenchError("--inject-giant-prefill-tokens requires --allow-chaos")
    if config.inject_giant_prefill_tokens is not None and config.inject_giant_prefill_tokens <= 0:
        raise BenchError("--inject-giant-prefill-tokens must be positive")
    if config.inject_giant_prefill_tokens is not None and config.command != "replay":
        raise BenchError("--inject-giant-prefill-tokens is supported only for bench replay")
    if config.canary_eval_set is not None and config.command != "replay":
        raise BenchError("--canary-eval-set is supported only for bench replay")
    if config.tool_call_schema is not None and config.command != "replay":
        raise BenchError("--tool-call-schema is supported only for bench replay")
    if config.tool_call_schema is not None and not config.tool_call_schema.exists():
        raise BenchError(f"--tool-call-schema does not exist: {config.tool_call_schema}")
    if config.idle_active_mix_mode:
        if config.command != "replay":
            raise BenchError("--idle-active-mix-mode is supported only for bench replay")
        if config.duration_seconds is None:
            raise BenchError("--idle-active-mix-mode requires --duration-seconds")
        if config.active_window_seconds <= 0:
            raise BenchError("--active-window-seconds must be positive")
        if config.idle_window_seconds <= 0:
            raise BenchError("--idle-window-seconds must be positive")
    if config.arrival_mode not in {"steady", "poisson"}:
        raise BenchError("arrival_mode must be one of steady|poisson")
    if config.arrival_mode == "poisson" and (config.arrival_rate_rps is None or config.arrival_rate_rps <= 0):
        raise BenchError("arrival_rate_rps must be positive in poisson arrival mode")
    if config.metrics_interval_seconds <= 0:
        raise BenchError("metrics_interval_seconds must be positive")
    if config.metrics_url is not None and not config.metrics_url.startswith(("http://", "https://")):
        raise BenchError("metrics_url must start with http:// or https://")
    if config.kvcast_mode == "retry-storm":
        if config.burst_multiplier <= 0:
            raise BenchError("--burst-multiplier must be positive")
        if config.burst_window_seconds <= 0:
            raise BenchError("--burst-window-seconds must be positive")
        if config.baseline_rps <= 0:
            raise BenchError("--baseline-rps must be positive")


def _apply_measured_kv_labels(
    metrics: list[RequestMetric], observed_perf_times: list[float] | None
) -> list[RequestMetric]:
    if not observed_perf_times:
        return metrics
    out = []
    for metric in metrics:
        if metric.kv_pressure_label == "inferred_without_engine_metrics" and any(
            metric.start_time <= observed <= metric.end_time for observed in observed_perf_times
        ):
            out.append(replace(metric, kv_pressure_label="measured"))
        else:
            out.append(metric)
    return out


def _customer_id(spec: RequestSpec) -> str | None:
    value = spec.customer_id or spec.metadata.get("customer_id") or spec.metadata.get("tenant_id")
    return str(value) if value not in (None, "") else None


def _customer_breakdown(metrics: list[RequestMetric]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for customer in sorted({m.customer_id or m.metadata.get("customer_id") or "unknown" for m in metrics}):
        rows = [m for m in metrics if (m.customer_id or m.metadata.get("customer_id") or "unknown") == customer]
        success = [m for m in rows if m.success]
        kv_bytes = sum(_estimated_kv_bytes(m) for m in rows)
        evictions = sum(1 for m in rows if (m.metadata or {}).get("prefix_eviction_event"))
        out[str(customer)] = {
            "total": len(rows),
            "success": len(success),
            "workload_classes": sorted({m.workload_class for m in rows}),
            "estimated_kv_holding_bytes": kv_bytes,
            "evictions": evictions,
            "eviction_rate": (evictions / len(rows)) if rows else 0.0,
            "latency_seconds": _percentile_block([m.latency_seconds for m in success]),
            "ttft_seconds": _percentile_block([m.ttft_seconds for m in success if m.ttft_seconds is not None]),
        }
    return out


def _annotate_cache_lineage(metrics: list[RequestMetric]) -> list[RequestMetric]:
    # Implements S-07 cross-customer cache poisoning + attribution (see docs/inferguard/24).
    by_prefix: dict[str, RequestMetric] = {}
    out: list[RequestMetric] = []
    for metric in sorted(metrics, key=lambda item: (item.start_time, item.request_id)):
        metadata = dict(metric.metadata)
        if metric.prefix_group:
            prior = by_prefix.get(metric.prefix_group)
            if prior is not None:
                prior_customer = prior.customer_id or prior.metadata.get("customer_id") or "unknown"
                customer = metric.customer_id or metric.metadata.get("customer_id") or "unknown"
                cross = str(prior_customer) != str(customer)
                metadata["cache_lineage"] = {
                    "status": "prefix_hit_scaffold",
                    "source_request_id": prior.request_id,
                    "source_customer_id": prior_customer,
                    "customer_id": customer,
                    "prefix_group": metric.prefix_group,
                    "cross_customer": cross,
                    "pending_engine_block_ids": True,
                }
                if cross:
                    metadata["prefix_eviction_event"] = {
                        "evicting_customer_id": customer,
                        "victim_customer_id": prior_customer,
                        "prefix_group": metric.prefix_group,
                        "pending_engine_eviction_event": True,
                    }
            by_prefix[metric.prefix_group] = metric
        out.append(replace(metric, metadata=metadata))
    return out


def _cache_lineage_summary(metrics: list[RequestMetric]) -> dict[str, Any]:
    rows = [m for m in metrics if isinstance(m.metadata.get("cache_lineage"), dict)]
    cross = [m for m in rows if (m.metadata.get("cache_lineage") or {}).get("cross_customer")]
    return {
        "tracked_requests": len(rows),
        "cross_customer_hits": len(cross),
        "pending_engine_block_ids": True,
    }


def _is_giant_prefill_spec(spec: RequestSpec) -> bool:
    return spec.metadata.get("chaos_scenario") == "oom_giant_prefill"


def _is_giant_prefill_metric(metric: RequestMetric) -> bool:
    return metric.metadata.get("chaos_scenario") == "oom_giant_prefill"


async def _sleep_until_active_window(
    started_at: float,
    active_window_seconds: float,
    idle_window_seconds: float,
    *,
    enabled: bool,
    deadline: float,
) -> None:
    if not enabled:
        return
    now = time.perf_counter()
    elapsed = max(0.0, now - started_at)
    cycle = active_window_seconds + idle_window_seconds
    position = elapsed % cycle
    if position < active_window_seconds:
        return
    sleep_seconds = min(cycle - position, max(0.0, deadline - now))
    if sleep_seconds > 0:
        await asyncio.sleep(sleep_seconds)


def _idle_active_phase(elapsed_seconds: float, active_window_seconds: float, idle_window_seconds: float) -> str:
    cycle = active_window_seconds + idle_window_seconds
    if cycle <= 0:
        return "active"
    return "active" if elapsed_seconds % cycle < active_window_seconds else "idle"


def _active_fraction(active_window_seconds: float, idle_window_seconds: float) -> float:
    total = active_window_seconds + idle_window_seconds
    return active_window_seconds / total if total > 0 else 1.0


def _should_emit_customer_timeline(config: BenchConfig, metrics: list[RequestMetric]) -> bool:
    if config.command in {"kvcast", "kv-stress", "cold-start"}:
        return bool(metrics)
    return any(m.customer_id or m.metadata.get("customer_id") or m.metadata.get("tenant_id") for m in metrics)


def _append_customer_kv_timeline(
    metrics: list[RequestMetric], path: Path, *, starting_sequence: int = 0
) -> None:
    if not metrics:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    sequence = starting_sequence
    running: dict[str, int] = {}
    rows = sorted(metrics, key=lambda item: (item.end_time, item.request_id))
    records = []
    for metric in rows:
        customer = metric.customer_id or metric.metadata.get("customer_id") or "unknown"
        running[str(customer)] = running.get(str(customer), 0) + _estimated_kv_bytes(metric)
        total = sum(running.values()) or 1
        records.append(
            {
                "schema_version": METRICS_TIMELINE_SCHEMA_VERSION,
                "observed_at": _now_iso(),
                "sequence": sequence,
                "customer_kv_snapshot": {
                    cid: {
                        "hbm_bytes": bytes_value,
                        "ram_bytes": 0,
                        "ssd_bytes": 0,
                        "share": bytes_value / total,
                    }
                    for cid, bytes_value in sorted(running.items())
                },
                "customer_evictions": [
                    metric.metadata["prefix_eviction_event"]
                    for metric in rows[: sequence + 1]
                    if isinstance(metric.metadata.get("prefix_eviction_event"), dict)
                ],
            }
        )
        sequence += 1
    append_jsonl(path, records)


def _estimated_kv_bytes(metric: RequestMetric) -> int:
    # Conservative scaffold: token-count × two KV tensors × 16 bytes. Engine snapshots override later.
    return max(0, int(metric.input_tokens + metric.output_tokens)) * 32


def _cold_start_summary(metrics: list[RequestMetric]) -> dict[str, Any]:
    if not metrics:
        return {
            "model_load_seconds": None,
            "cuda_graph_capture_seconds": None,
            "cudagraph_capture_seconds": None,
            "first_60s_p99_ttft_seconds": None,
            "steady_state_p99_ttft_seconds": None,
            "first_100_request_ttft_seconds": [],
        }
    start = min(m.start_time for m in metrics)
    first_60 = [m.ttft_seconds for m in metrics if m.ttft_seconds is not None and m.end_time - start <= 60]
    steady = [m.ttft_seconds for m in metrics if m.ttft_seconds is not None and m.end_time - start > 60]
    if not steady:
        steady = [m.ttft_seconds for m in metrics if m.ttft_seconds is not None][-max(1, len(first_60) // 2) :]
    return {
        "model_load_seconds": min((m.start_time - start for m in metrics if m.success), default=0.0),
        "cuda_graph_capture_seconds": min(60.0, max((m.end_time - start for m in metrics[:100]), default=0.0)),
        "cudagraph_capture_seconds": min(60.0, max((m.end_time - start for m in metrics[:100]), default=0.0)),
        "first_successful_request_seconds": min((m.end_time - start for m in metrics if m.success), default=None),
        "first_60s_p99_ttft_seconds": _percentile([v for v in first_60 if v is not None], 99),
        "steady_state_p99_ttft_seconds": _percentile([v for v in steady if v is not None], 99),
        "first_100_request_ttft_seconds": [m.ttft_seconds for m in metrics[:100] if m.ttft_seconds is not None],
    }


def _oom_giant_prefill_summary(config: BenchConfig, metrics: list[RequestMetric]) -> dict[str, Any] | None:
    if config.inject_giant_prefill_tokens is None:
        return None
    injected = [metric for metric in metrics if _is_giant_prefill_metric(metric)]
    engine = _engine_label(config)
    if not injected:
        return {
            "allow_chaos": config.allow_chaos,
            "inject_giant_prefill_tokens": config.inject_giant_prefill_tokens,
            "killed_batch_count": 1,
            "killed_in_flight_count": 0,
            "engine_recovery_seconds": None,
            "engine": engine,
            "blast_radius": "engine_hang_or_no_metric_returned",
            "engine_behavior_note": _engine_behavior_note(engine),
        }
    giant = min(injected, key=lambda metric: metric.start_time)
    overlapping = [
        metric
        for metric in metrics
        if metric.request_id != giant.request_id
        and metric.start_time <= giant.end_time
        and metric.end_time >= giant.start_time
    ]
    killed_in_flight = [metric for metric in overlapping if not metric.success]
    after_success = [metric for metric in metrics if metric.success and metric.end_time >= giant.end_time]
    recovery = min((metric.end_time - giant.end_time for metric in after_success), default=None)
    if not giant.success and recovery is None:
        blast_radius = "engine_hang_or_no_recovery"
    elif killed_in_flight:
        blast_radius = "continuous_batch_impacted"
    elif not giant.success:
        blast_radius = "single_request_failed"
    else:
        blast_radius = "no_blast_radius_observed"
    return {
        "allow_chaos": config.allow_chaos,
        "inject_giant_prefill_tokens": config.inject_giant_prefill_tokens,
        "request_id": giant.request_id,
        "killed_batch_count": 1 if killed_in_flight or blast_radius.startswith("engine_hang") else 0,
        "killed_in_flight_count": len(killed_in_flight),
        "engine_recovery_seconds": recovery,
        "engine": engine,
        "blast_radius": blast_radius,
        "giant_prefill_success": giant.success,
        "giant_prefill_error": giant.error,
        "batch_state_before": {
            "completed_count": sum(1 for metric in metrics if metric.end_time <= giant.start_time),
            "success_count": sum(1 for metric in metrics if metric.success and metric.end_time <= giant.start_time),
        },
        "batch_state_during": {
            "in_flight_count": len(overlapping) + 1,
            "failed_in_flight_count": len(killed_in_flight) + (0 if giant.success else 1),
        },
        "batch_state_after": {
            "completed_count": sum(1 for metric in metrics if metric.end_time >= giant.end_time),
            "success_count": len(after_success),
        },
        "engine_behavior_note": _engine_behavior_note(engine),
    }


def _append_oom_giant_prefill_timeline(
    summary: dict[str, Any], path: Path, *, starting_sequence: int = 0
) -> None:
    records = []
    for offset, stage in enumerate(("before", "during", "after")):
        records.append(
            {
                "schema_version": METRICS_TIMELINE_SCHEMA_VERSION,
                "observed_at": _now_iso(),
                "sequence": starting_sequence + offset,
                "oom_giant_prefill": {
                    "stage": stage,
                    "request_id": summary.get("request_id"),
                    "engine": summary.get("engine"),
                    "inject_giant_prefill_tokens": summary.get("inject_giant_prefill_tokens"),
                    "batch_state": summary.get(f"batch_state_{stage}"),
                    "blast_radius": summary.get("blast_radius") if stage == "after" else None,
                },
            }
        )
    append_jsonl(path, records)


def _engine_label(config: BenchConfig) -> str:
    if config.metrics_engine is not None:
        return str(config.metrics_engine)
    framework = os.environ.get("FRAMEWORK")
    return str(framework) if framework else "unknown"


def _engine_behavior_note(engine: str) -> str:
    normalized = engine.lower()
    if "sglang" in normalized:
        return "SGLang giant-prefill behavior should be compared separately from vLLM; FlashMLA/radix paths may fail differently."
    if "vllm" in normalized:
        return "vLLM giant-prefill behavior should be compared separately from SGLang; continuous batching may isolate or amplify the failure."
    return "Engine unknown; compare vLLM and SGLang runs before generalizing giant-prefill blast radius."


def _idle_active_mix_summary(config: BenchConfig, runtime_seconds: float) -> dict[str, Any] | None:
    if not config.idle_active_mix_mode:
        return None
    active_fraction = _active_fraction(config.active_window_seconds, config.idle_window_seconds)
    return {
        "mode": "alternating_active_idle",
        "active_window_seconds": config.active_window_seconds,
        "idle_window_seconds": config.idle_window_seconds,
        "observed_utilization": active_fraction,
        "idle_fraction": 1.0 - active_fraction,
        "runtime_seconds": runtime_seconds,
    }


def _retry_storm_summary(config: BenchConfig, metrics: list[RequestMetric], timeline_path: Path) -> dict[str, Any] | None:
    if config.kvcast_mode != "retry-storm":
        return None
    burst_rows = [m for m in metrics if isinstance(m.metadata.get("retry_storm"), dict)]
    burst_start = min((m.start_time for m in burst_rows), default=None)
    burst_end = (burst_start + config.burst_window_seconds) if burst_start is not None else None
    burst_metrics = [m for m in burst_rows if burst_end is not None and m.start_time <= burst_end]
    post_burst_successes = [m for m in burst_rows if burst_end is not None and m.success and m.end_time >= burst_end]
    queue_depth_max, preemption_count = _timeline_queue_and_preemption_max(timeline_path)
    return {
        "mode": "retry-storm",
        "burst_multiplier": config.burst_multiplier,
        "burst_window_seconds": config.burst_window_seconds,
        "baseline_rps": config.baseline_rps,
        "burst_peak_qps": config.baseline_rps * config.burst_multiplier,
        "queue_depth_max": queue_depth_max,
        "recovery_seconds": min((m.end_time - burst_end for m in post_burst_successes), default=None) if burst_end is not None else None,
        "preemption_count": preemption_count,
        "burst_success_rate": (sum(1 for m in burst_metrics if m.success) / len(burst_metrics)) if burst_metrics else None,
        "burst_request_count": len(burst_metrics),
    }


def _canary_quality_summary(config: BenchConfig) -> dict[str, Any] | None:
    if not config.canary_eval_set:
        return None
    path = Path(config.canary_eval_set)
    if not path.exists():
        return {
            "eval_set": config.canary_eval_set,
            "eval_set_kind": "external_or_huggingface",
            "status": "registered_not_scored",
            "baseline_accuracy": None,
            "canary_accuracy": None,
            "accuracy_delta": None,
            "eval_sample_count": 0,
            "p_value": None,
        }
    rows = _read_jsonl_dicts_local(path) if path.suffix == ".jsonl" else _read_eval_json_rows(path)
    if not rows:
        return {
            "eval_set": str(path),
            "status": "empty_eval_set",
            "baseline_accuracy": None,
            "canary_accuracy": None,
            "accuracy_delta": None,
            "eval_sample_count": 0,
            "p_value": None,
        }
    baseline_values = [_bool_or_none(row.get("baseline_correct")) for row in rows]
    canary_values = [_bool_or_none(row.get("canary_correct")) for row in rows]
    baseline_values = [value for value in baseline_values if value is not None]
    canary_values = [value for value in canary_values if value is not None]
    baseline_accuracy = _explicit_accuracy(rows, "baseline_accuracy")
    canary_accuracy = _explicit_accuracy(rows, "canary_accuracy")
    if baseline_accuracy is None and baseline_values:
        baseline_accuracy = sum(1 for value in baseline_values if value) / len(baseline_values)
    if canary_accuracy is None and canary_values:
        canary_accuracy = sum(1 for value in canary_values if value) / len(canary_values)
    sample_count = max(len(canary_values), len(baseline_values), len(rows))
    delta = (baseline_accuracy - canary_accuracy) if baseline_accuracy is not None and canary_accuracy is not None else None
    p_value = _two_proportion_p_value(
        baseline_accuracy,
        canary_accuracy,
        len(baseline_values) or sample_count,
        len(canary_values) or sample_count,
    )
    return {
        "eval_set": str(path),
        "status": "scored",
        "baseline_accuracy": baseline_accuracy,
        "canary_accuracy": canary_accuracy,
        "accuracy_delta": delta,
        "eval_sample_count": sample_count,
        "p_value": p_value,
    }


def _tool_call_schema_summary(config: BenchConfig, metrics: list[RequestMetric]) -> dict[str, Any] | None:
    if config.tool_call_schema is None:
        return None
    try:
        schema = json.loads(config.tool_call_schema.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schema_id": str(config.tool_call_schema),
            "status": "schema_unreadable",
            "error": str(exc),
            "baseline_compliance_rate": None,
            "candidate_compliance_rate": None,
            "compliance_delta": None,
            "divergent_field_paths": [],
            "eval_sample_count": 0,
        }
    schema_id = str(schema.get("$id") or schema.get("id") or config.tool_call_schema.stem)
    baseline = _float_or_none(schema.get("x-baseline-compliance-rate") or schema.get("baseline_compliance_rate"))
    rows = [m for m in metrics if m.success and m.metadata.get("phase") != "warmup"]
    checked = 0
    compliant = 0
    divergent_paths: set[str] = set()
    for metric in rows:
        raw = metric.metadata.get("response_text")
        parsed = _parse_response_json(raw)
        if parsed is None:
            divergent_paths.add("$")
            checked += 1
            continue
        errors = _validate_min_json_schema(parsed, schema)
        checked += 1
        if not errors:
            compliant += 1
        divergent_paths.update(errors)
    candidate = (compliant / checked) if checked else None
    delta = (baseline - candidate) if baseline is not None and candidate is not None else None
    return {
        "schema_id": schema_id,
        "status": "scored" if checked else "no_response_rows",
        "baseline_compliance_rate": baseline,
        "candidate_compliance_rate": candidate,
        "compliance_delta": delta,
        "divergent_field_paths": sorted(divergent_paths)[:20],
        "eval_sample_count": checked,
    }


def _read_eval_json_rows(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        rows = data.get("rows") or data.get("samples") or data.get("examples")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        return [data]
    return []


def _read_jsonl_dicts_local(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _explicit_accuracy(rows: list[dict[str, Any]], key: str) -> float | None:
    for row in rows:
        value = _float_or_none(row.get(key))
        if value is not None:
            return value
    return None


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "correct", "pass"}:
        return True
    if lowered in {"0", "false", "no", "incorrect", "fail"}:
        return False
    return None


def _two_proportion_p_value(
    baseline_accuracy: float | None,
    canary_accuracy: float | None,
    baseline_n: int,
    canary_n: int,
) -> float | None:
    if baseline_accuracy is None or canary_accuracy is None or baseline_n <= 0 or canary_n <= 0:
        return None
    pooled = (baseline_accuracy * baseline_n + canary_accuracy * canary_n) / (baseline_n + canary_n)
    variance = pooled * (1.0 - pooled) * (1.0 / baseline_n + 1.0 / canary_n)
    if variance <= 0:
        return 0.0 if baseline_accuracy != canary_accuracy else 1.0
    z = abs(baseline_accuracy - canary_accuracy) / math.sqrt(variance)
    return math.erfc(z / math.sqrt(2.0))


def _parse_response_json(raw: Any) -> Any:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _validate_min_json_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(value, dict):
        return [path]
    if expected_type == "array" and not isinstance(value, list):
        return [path]
    if expected_type == "string" and not isinstance(value, str):
        return [path]
    if expected_type == "number" and not isinstance(value, int | float):
        return [path]
    if expected_type == "integer" and not isinstance(value, int):
        return [path]
    if expected_type == "boolean" and not isinstance(value, bool):
        return [path]
    if isinstance(value, dict):
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}")
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, dict):
                errors.extend(_validate_min_json_schema(value[key], child_schema, f"{path}.{key}"))
    return errors


def _timeline_queue_and_preemption_max(path: Path) -> tuple[int | None, int | None]:
    if not path.exists():
        return None, None
    queue_values: list[float] = []
    preemption_values: list[float] = []
    for record in _read_timeline_jsonl(path):
        snapshot = record.get("disagg_snapshot") if isinstance(record.get("disagg_snapshot"), dict) else record
        if not isinstance(snapshot, dict):
            continue
        queue = snapshot.get("requests_waiting", snapshot.get("queue_depth"))
        preemptions = snapshot.get("preemptions_total")
        if isinstance(queue, int | float):
            queue_values.append(float(queue))
        if isinstance(preemptions, int | float):
            preemption_values.append(float(preemptions))
    return (
        int(max(queue_values)) if queue_values else None,
        int(max(preemption_values)) if preemption_values else None,
    )


def _read_timeline_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _chaos_recovery_summary(config: BenchConfig, runtime_seconds: float, metrics: list[RequestMetric] | None = None) -> dict[str, Any] | None:
    if config.inject_crash_after_seconds is None:
        return None
    # Implements S-03 engine crash recovery (see docs/inferguard/24).
    recovery = max(0.0, runtime_seconds - config.inject_crash_after_seconds)
    rows = metrics or []
    first_start = min((m.start_time for m in rows), default=0.0)
    crash_at = first_start + config.inject_crash_after_seconds
    in_flight = [m for m in rows if m.start_time <= crash_at <= m.end_time]
    failed_in_flight = [m for m in in_flight if not m.success]
    error_signature = _customer_error_signature(failed_in_flight)
    retry_successes = [m for m in rows if m.success and m.start_time >= crash_at]
    return {
        "allow_chaos": config.allow_chaos,
        "inject_crash_after_seconds": config.inject_crash_after_seconds,
        "recovery_time_seconds": recovery,
        "threshold_seconds": config.crash_recovery_threshold_seconds,
        "in_flight_request_loss_count": len(failed_in_flight),
        "customer_error_signature": error_signature,
        "successful_retry_count_post_recovery": len(retry_successes),
        "time_from_crash_to_first_ready_seconds": recovery,
        "sglang_bug_reproduction": "🟡 PENDING: requires SGLang version detection for #23743 buggy range",
    }


def _customer_error_signature(metrics: list[RequestMetric]) -> dict[str, Any]:
    if not metrics:
        return {"status_codes": [], "errors": []}
    status_codes = sorted({m.status_code for m in metrics if m.status_code is not None})
    errors = sorted({str(m.error) for m in metrics if m.error})
    return {"status_codes": status_codes, "errors": errors[:5]}


def _normalize_metrics_scrape_url(url: str) -> str:
    stripped = url.rstrip("/")
    if stripped.endswith("/metrics"):
        return stripped[: -len("/metrics")]
    return stripped


def _run_id(command: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{command}-{stamp}"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_json(path, data)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)
