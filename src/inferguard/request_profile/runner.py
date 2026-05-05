"""Runner for OpenAI-compatible per-request profiling."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Callable, cast

import httpx

from inferguard.bench.client import OpenAIStreamingChatClient
from inferguard.bench.runner import BenchError, poisson_arrival_offsets
from inferguard.bench.tokenizer import estimate_messages_tokens
from inferguard.bench.types import RequestMetric, RequestSpec
from inferguard.io import (
    atomic_write_json,
    atomic_write_text,
    register_jsonl_stream,
    register_partial_results,
    unregister_jsonl_stream,
    unregister_partial_results,
)
from inferguard.request_profile.types import (
    ArrivalMode,
    ClaimStatus,
    EngineName,
    ErrorType,
    RequestProfileOptions,
    RequestProfileRow,
    RequestProfileSummary,
    TokenSource,
)

_PROFILE_NAMESPACE = uuid.UUID("f72cf08c-386e-4eca-a252-b40b5333ad40")
_ALLOWED_ENGINES = {"vllm", "sglang", "lmcache", "dynamo-sglang", "agentx-replay"}


def profile_endpoint(
    *,
    endpoint: str,
    model: str,
    input_jsonl: str | Path,
    output_dir: str | Path,
    concurrency: int = 1,
    timeout_seconds: float = 300.0,
    arrival_mode: ArrivalMode = "closed_loop",
    rate_rps: float | None = None,
    max_requests: int | None = None,
    api_key: str | None = None,
    stream: bool = False,
    include_usage: bool = False,
    continuous_usage_stats: bool = False,
    workload_label: str = "default",
    job_id: str | None = None,
    seed: int = 0,
    engine: str = "vllm",
    model_profile: str | None = None,
) -> RequestProfileSummary:
    """Profile an OpenAI-compatible chat-completions endpoint and write artifacts."""

    options = RequestProfileOptions(
        endpoint=endpoint,
        model=model,
        input_jsonl=str(input_jsonl),
        output_dir=str(output_dir),
        concurrency=concurrency,
        timeout_seconds=timeout_seconds,
        arrival_mode=arrival_mode,
        rate_rps=rate_rps,
        max_requests=max_requests,
        api_key=api_key,
        stream=stream,
        include_usage=include_usage,
        continuous_usage_stats=continuous_usage_stats,
        workload_label=workload_label,
        job_id=job_id,
        seed=seed,
        engine=_engine(engine),
        model_profile=model_profile,
    )
    return run_request_profile(options)


def run_request_profile(options: RequestProfileOptions) -> RequestProfileSummary:
    """Run the request profiler and return the emitted summary contract."""

    opts = _normalized_options(options)
    input_path = Path(opts.input_jsonl)
    output_dir = Path(opts.output_dir)
    specs = _load_request_specs(input_path)
    if opts.max_requests is not None:
        specs = specs[: opts.max_requests]
    if not specs:
        raise BenchError("input_jsonl did not contain any request specs")

    output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = output_dir / "requests_profile.jsonl"
    summary_path = output_dir / "requests_summary.json"
    job_id = opts.job_id or str(uuid.uuid4())
    wall_start = datetime.now(UTC)
    perf_start = time.perf_counter()
    run_options = replace(opts, job_id=job_id)
    rows: list[RequestProfileRow] = []
    partial_path = output_dir / "partial_results.json"

    def partial_payload() -> dict[str, Any]:
        return _partial_results_payload(
            rows,
            options=run_options,
            rows_path=rows_path,
            summary_path=summary_path,
        )

    def record_metric(metric: RequestMetric) -> None:
        row = _row_from_metric(
            metric,
            spec=specs[int(metric.metadata["sequence"])],
            options=run_options,
            wall_start=wall_start,
            perf_start=perf_start,
        )
        rows.append(row)
        rows_handle.write(json.dumps(row.to_dict(), sort_keys=True) + "\n")
        rows_handle.flush()

    atomic_write_text(rows_path, "")
    register_partial_results(partial_path, partial_payload)
    try:
        with rows_path.open("a", encoding="utf-8") as rows_handle:
            register_jsonl_stream(rows_handle)
            try:
                asyncio.run(_profile_requests(opts, specs, on_metric=record_metric))
            finally:
                unregister_jsonl_stream(rows_handle)
    finally:
        unregister_partial_results(partial_path)

    summary = _summary_from_rows(rows, options=run_options)
    atomic_write_json(summary_path, summary.to_dict())
    return summary


def format_stdout_summary(summary: RequestProfileSummary) -> str:
    """Return the locked one-line CLI summary for PRD §4.2.2."""

    return (
        "inferguard request-profile: "
        f"requests={summary.request_count} "
        f"success={summary.success_count} "
        f"failures={summary.failure_count} "
        f"ttft_p50={_number(summary.ttft_ms.get('p50'))} "
        f"ttft_p95={_number(summary.ttft_ms.get('p95'))} "
        f"tpot_p50={_number(summary.tpot_ms.get('p50'))} "
        f"e2e_p99={_number(summary.e2e_latency_ms.get('p99'))} "
        f"tokens_per_sec={_number(summary.tokens_per_sec_aggregate)}"
    )


def _partial_results_payload(
    rows: list[RequestProfileRow],
    *,
    options: RequestProfileOptions,
    rows_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    successes = sum(1 for row in rows if row.success)
    return {
        "command": "request-profile",
        "status": "interrupted",
        "claim_status": "inferred",
        "claim_reason": "interrupted_partial_results",
        "job_id": options.job_id,
        "workload_label": options.workload_label,
        "engine": options.engine,
        "model_profile": options.model_profile or options.model,
        "request_count": len(rows),
        "success_count": successes,
        "failure_count": len(rows) - successes,
        "artifacts": {
            "requests_profile": str(rows_path),
            "requests_summary": str(summary_path),
        },
    }


def _normalized_options(options: RequestProfileOptions) -> RequestProfileOptions:
    if options.concurrency <= 0:
        raise BenchError("concurrency must be positive")
    if options.timeout_seconds <= 0:
        raise BenchError("timeout_seconds must be positive")
    if options.arrival_mode not in {"closed_loop", "poisson"}:
        raise BenchError("arrival_mode must be one of closed_loop|poisson")
    if options.arrival_mode == "poisson" and (options.rate_rps is None or options.rate_rps <= 0):
        raise BenchError("rate_rps must be positive when arrival_mode=poisson")
    if options.max_requests is not None and options.max_requests <= 0:
        raise BenchError("max_requests must be positive when provided")
    return replace(
        options,
        api_key=options.api_key or os.environ.get("OPENAI_API_KEY"),
        engine=_engine(options.engine),
        workload_label=options.workload_label or "default",
    )


def _engine(value: str) -> EngineName:
    normalized = value.strip().lower()
    if normalized not in _ALLOWED_ENGINES:
        raise BenchError("engine must be one of vllm|sglang|lmcache|dynamo-sglang|agentx-replay")
    return cast(EngineName, normalized)


async def _profile_requests(
    options: RequestProfileOptions,
    specs: list[RequestSpec],
    *,
    on_metric: Callable[[RequestMetric], None] | None = None,
) -> list[RequestMetric]:
    timeout = httpx.Timeout(options.timeout_seconds, connect=min(30.0, options.timeout_seconds))
    client = OpenAIStreamingChatClient(
        options.endpoint,
        model=options.model,
        timeout=options.timeout_seconds,
        api_key=options.api_key,
        stream=options.stream,
        include_usage=options.include_usage,
        continuous_usage_stats=options.continuous_usage_stats,
    )
    async with httpx.AsyncClient(timeout=timeout) as http:
        if options.arrival_mode == "poisson":
            return await _run_poisson(client, http, specs, options, on_metric=on_metric)
        return await _run_closed_loop(client, http, specs, options, on_metric=on_metric)


async def _run_closed_loop(
    client: OpenAIStreamingChatClient,
    http: httpx.AsyncClient,
    specs: list[RequestSpec],
    options: RequestProfileOptions,
    *,
    on_metric: Callable[[RequestMetric], None] | None = None,
) -> list[RequestMetric]:
    queue: asyncio.Queue[tuple[int, RequestSpec]] = asyncio.Queue()
    for sequence, spec in enumerate(specs):
        queue.put_nowait((sequence, spec))
    level_started = time.perf_counter()
    results: list[RequestMetric] = []
    lock = asyncio.Lock()

    async def worker() -> None:
        while True:
            try:
                sequence, spec = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            metric = await _run_one_request(
                client,
                http,
                spec,
                sequence=sequence,
                options=options,
                level_started=level_started,
                scheduled_arrival_time=level_started,
            )
            async with lock:
                results.append(metric)
                if on_metric is not None:
                    on_metric(metric)
            queue.task_done()

    await asyncio.gather(*(worker() for _ in range(options.concurrency)))
    return sorted(results, key=lambda item: int(item.metadata["sequence"]))


async def _run_poisson(
    client: OpenAIStreamingChatClient,
    http: httpx.AsyncClient,
    specs: list[RequestSpec],
    options: RequestProfileOptions,
    *,
    on_metric: Callable[[RequestMetric], None] | None = None,
) -> list[RequestMetric]:
    rate = options.rate_rps or 1.0
    level_started = time.perf_counter()
    semaphore = asyncio.Semaphore(options.concurrency)
    tasks: list[asyncio.Task[RequestMetric]] = []
    for sequence, offset in enumerate(
        poisson_arrival_offsets(len(specs), rate_rps=rate, seed=options.seed)
    ):
        scheduled = level_started + offset
        delay = scheduled - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        spec = specs[sequence]
        tasks.append(
            asyncio.create_task(
                _run_one_request_with_semaphore(
                    semaphore,
                    client,
                    http,
                    spec,
                    sequence=sequence,
                    options=options,
                    level_started=level_started,
                    scheduled_arrival_time=scheduled,
                    on_metric=on_metric,
                )
            )
        )
    return sorted(await asyncio.gather(*tasks), key=lambda item: int(item.metadata["sequence"]))


async def _run_one_request_with_semaphore(
    semaphore: asyncio.Semaphore,
    client: OpenAIStreamingChatClient,
    http: httpx.AsyncClient,
    spec: RequestSpec,
    *,
    sequence: int,
    options: RequestProfileOptions,
    level_started: float,
    scheduled_arrival_time: float,
    on_metric: Callable[[RequestMetric], None] | None = None,
) -> RequestMetric:
    async with semaphore:
        metric = await _run_one_request(
            client,
            http,
            spec,
            sequence=sequence,
            options=options,
            level_started=level_started,
            scheduled_arrival_time=scheduled_arrival_time,
        )
        if on_metric is not None:
            on_metric(metric)
        return metric


async def _run_one_request(
    client: OpenAIStreamingChatClient,
    http: httpx.AsyncClient,
    spec: RequestSpec,
    *,
    sequence: int,
    options: RequestProfileOptions,
    level_started: float,
    scheduled_arrival_time: float,
) -> RequestMetric:
    result = await client.stream_chat(
        http,
        messages=spec.messages,
        output_tokens=spec.expected_output_tokens or _metadata_int(spec.metadata, "max_tokens") or 16,
        metadata=_request_metadata(spec),
    )
    tokens_per_second = None
    if result.success and result.latency_seconds > 0:
        tokens_per_second = result.output_tokens / result.latency_seconds
    metadata = {
        **spec.metadata,
        "phase": "measurement",
        "sequence": sequence,
        "scheduled_arrival_time": scheduled_arrival_time,
        "arrival_delay_seconds": max(0.0, result.start_time - scheduled_arrival_time),
        "cached_tokens": result.cached_tokens,
        "content_token_offsets_seconds": list(result.content_token_offsets_seconds),
        "streaming": options.stream,
    }
    return RequestMetric(
        request_id=f"{spec.request_id}:seq-{sequence}",
        trace_id=spec.trace_id,
        session_id=spec.session_id,
        turn_index=spec.turn_index,
        workload_class=spec.workload_class,
        concurrency=options.concurrency,
        success=result.success,
        start_time=result.start_time,
        end_time=result.end_time,
        latency_seconds=result.latency_seconds,
        ttft_seconds=result.ttft_seconds,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        input_tokens_source=result.input_tokens_source,
        output_tokens_source=result.output_tokens_source,
        tokens_per_second=tokens_per_second,
        error=result.error,
        status_code=result.status_code,
        first_sse_seconds=result.first_sse_seconds,
        first_content_token_seconds=result.first_content_token_seconds,
        done_seen=result.done_seen,
        valid_content_seen=result.valid_content_seen,
        prefix_group=spec.prefix_group,
        tool_heavy=spec.tool_heavy,
        customer_id=spec.customer_id,
        sla_tier=spec.sla_tier,
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


def _row_from_metric(
    metric: RequestMetric,
    *,
    spec: RequestSpec,
    options: RequestProfileOptions,
    wall_start: datetime,
    perf_start: float,
) -> RequestProfileRow:
    prompt_source = _prompt_source(metric.input_tokens_source)
    cached_tokens = _metadata_int(metric.metadata, "cached_tokens")
    cached_status = _cached_tokens_claim_status(cached_tokens, spec)
    claim_status = _row_claim_status(prompt_source, cached_status)
    claim_status_per_field: dict[str, ClaimStatus] = {
        "prompt_tokens": "measured" if prompt_source == "server" else claim_status,
        "completion_tokens": "measured" if metric.output_tokens_source == "api_usage" else claim_status,
        "cached_tokens": cached_status,
    }
    ttft_ms = metric.ttft_seconds * 1000.0 if metric.ttft_seconds is not None else None
    e2e_ms = metric.latency_seconds * 1000.0
    decoder_seconds = _decoder_seconds(metric)
    tpot_ms = (decoder_seconds * 1000.0 / metric.output_tokens) if metric.output_tokens > 0 else None
    content_offsets = [float(item) for item in metric.metadata.get("content_token_offsets_seconds") or []]
    itl_ms = [
        (right - left) * 1000.0 for left, right in zip(content_offsets, content_offsets[1:], strict=False)
    ]
    if not itl_ms and tpot_ms is not None and options.stream:
        itl_ms = [tpot_ms]
    error_type = _error_type(metric)
    return RequestProfileRow(
        request_id=str(uuid.uuid5(_PROFILE_NAMESPACE, f"{options.job_id}:{metric.request_id}")),
        job_id=str(options.job_id),
        workload_label=options.workload_label,
        model_profile=options.model_profile or options.model,
        engine=options.engine,
        context_length=spec.expected_input_tokens or metric.input_tokens,
        concurrency=metric.concurrency,
        prompt_tokens=metric.input_tokens,
        completion_tokens=metric.output_tokens,
        prompt_tokens_source=prompt_source,
        send_ts=_iso_from_perf(wall_start, perf_start, metric.start_time),
        first_token_ts=_iso_from_perf(wall_start, perf_start, metric.start_time + metric.ttft_seconds)
        if options.stream and metric.ttft_seconds is not None
        else None,
        done_ts=_iso_from_perf(wall_start, perf_start, metric.end_time),
        ttft_ms=ttft_ms if options.stream else None,
        e2e_latency_ms=e2e_ms,
        tpot_ms=tpot_ms,
        inter_token_latency_ms_p50=_percentile(itl_ms, 50),
        inter_token_latency_ms_p95=_percentile(itl_ms, 95),
        decode_tokens_per_sec=(metric.output_tokens / decoder_seconds)
        if decoder_seconds > 0 and metric.output_tokens > 0
        else None,
        streaming=options.stream,
        success=metric.success,
        http_status=metric.status_code,
        error_type=error_type,
        error_message=metric.error if error_type is not None else None,
        cached_tokens=cached_tokens,
        claim_status=claim_status,
        raw_response_ref=None,
        claim_status_per_field=claim_status_per_field,
    )


def _summary_from_rows(
    rows: list[RequestProfileRow],
    *,
    options: RequestProfileOptions,
) -> RequestProfileSummary:
    successes = [row for row in rows if row.success]
    failures = [row for row in rows if not row.success]
    prompt_total = sum(row.prompt_tokens for row in rows)
    completion_total = sum(row.completion_tokens for row in rows)
    runtime_seconds = _wall_runtime_seconds(rows)
    decode_tps = [row.decode_tokens_per_sec for row in successes if row.decode_tokens_per_sec is not None]
    return RequestProfileSummary(
        job_id=str(options.job_id),
        workload_label=options.workload_label,
        engine=options.engine,
        concurrency=options.concurrency,
        request_count=len(rows),
        success_count=len(successes),
        failure_count=len(failures),
        ttft_ms=_percentile_block([row.ttft_ms for row in successes if row.ttft_ms is not None]),
        tpot_ms=_percentile_block([row.tpot_ms for row in successes if row.tpot_ms is not None]),
        e2e_latency_ms=_percentile_block([row.e2e_latency_ms for row in successes]),
        decode_tokens_per_sec={
            "p50": _percentile(decode_tps, 50),
            "p95": _percentile(decode_tps, 95),
            "mean": mean(decode_tps) if decode_tps else None,
        },
        prompt_tokens_total=prompt_total,
        completion_tokens_total=completion_total,
        tokens_per_sec_aggregate=(completion_total / runtime_seconds) if runtime_seconds > 0 else None,
        failure_breakdown=dict(Counter(row.error_type or "unknown" for row in failures)),
        claim_status=_summary_claim_status(rows),
        success_rate=(len(successes) / len(rows)) if rows else 0.0,
    )


def _load_request_specs(path: Path) -> list[RequestSpec]:
    if not path.exists():
        raise BenchError(f"input_jsonl does not exist: {path}")
    specs: list[RequestSpec] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BenchError(f"invalid JSONL at {path}:{line_no}: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise BenchError(f"expected JSON object at {path}:{line_no}")
        specs.append(_spec_from_json(data, line_no=line_no))
    return specs


def _spec_from_json(data: dict[str, Any], *, line_no: int) -> RequestSpec:
    request = data.get("request") if isinstance(data.get("request"), dict) else {}
    messages = data.get("messages")
    if not isinstance(messages, list):
        messages = request.get("messages")
    if not isinstance(messages, list):
        raise BenchError(f"request spec line {line_no} is missing messages")
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    max_tokens = (
        _first_int(data, "max_tokens", "expected_output_tokens")
        or _first_int(request, "max_tokens", "expected_output_tokens")
        or 16
    )
    merged_metadata = {
        **metadata,
        "input_schema_version": data.get("schema_version"),
        "max_tokens": max_tokens,
    }
    workload_class = str(data.get("workload_class") or metadata.get("workload_class") or "openai-chat")
    expected_input = _first_int(data, "expected_input_tokens", "context_length", "prompt_tokens") or _first_int(
        request, "expected_input_tokens", "context_length", "prompt_tokens"
    )
    expected_output = _first_int(data, "expected_output_tokens", "max_tokens") or _first_int(
        request, "expected_output_tokens", "max_tokens"
    )
    request_id = str(data.get("request_id") or f"input-line-{line_no}")
    trace_id = str(data.get("trace_id") or request_id)
    return RequestSpec(
        request_id=request_id,
        trace_id=trace_id,
        session_id=str(data.get("session_id") or trace_id),
        turn_index=_first_int(data, "turn_index") or line_no - 1,
        workload_class=workload_class,
        messages=[message for message in messages if isinstance(message, dict)],
        expected_input_tokens=expected_input,
        expected_output_tokens=expected_output,
        prefix_group=str(data.get("prefix_group")) if data.get("prefix_group") else None,
        tool_heavy=bool(data.get("tool_heavy") or metadata.get("tool_heavy") or False),
        customer_id=str(metadata.get("customer_id")) if metadata.get("customer_id") else None,
        sla_tier=str(metadata.get("sla_tier")) if metadata.get("sla_tier") else None,
        metadata=merged_metadata,
    )


def _first_int(data: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        parsed = _int_or_none(data.get(key))
        if parsed is not None:
            return parsed
    return None


def _metadata_int(metadata: dict[str, Any], key: str) -> int | None:
    return _int_or_none(metadata.get(key))


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _request_metadata(spec: RequestSpec) -> dict[str, Any]:
    metadata = dict(spec.metadata)
    if spec.customer_id:
        metadata["customer_id"] = spec.customer_id
    if spec.sla_tier:
        metadata["sla_tier"] = spec.sla_tier
    return metadata


def _prompt_source(source: str) -> TokenSource:
    if source == "api_usage":
        return "server"
    try:
        estimate_messages_tokens([])
    except Exception:
        return "estimated"
    return "tokenizer"


def _row_claim_status(prompt_source: TokenSource, cached_status: ClaimStatus) -> ClaimStatus:
    if prompt_source == "estimated":
        return "not_proven"
    if prompt_source == "tokenizer" or cached_status == "inferred":
        return "inferred"
    return "measured"


def _cached_tokens_claim_status(cached_tokens: int | None, spec: RequestSpec) -> ClaimStatus:
    if cached_tokens is None:
        return "not_proven"
    if cached_tokens == 0 and _speculative_algorithm_enabled(spec):
        return "inferred"
    return "measured"


def _speculative_algorithm_enabled(spec: RequestSpec) -> bool:
    env_keys = (
        "INFERGUARD_SPECULATIVE_ALGORITHM",
        "SGLANG_SPECULATIVE_ALGORITHM",
        "SPECULATIVE_ALGORITHM",
    )
    if any(os.environ.get(key) for key in env_keys):
        return True
    metadata = spec.metadata
    return bool(
        metadata.get("speculative_algorithm")
        or metadata.get("sglang_speculative_algorithm")
        or metadata.get("launch_speculative_algorithm")
    )


def _decoder_seconds(metric: RequestMetric) -> float:
    if metric.ttft_seconds is None:
        return max(metric.latency_seconds, 0.0)
    return max(metric.latency_seconds - metric.ttft_seconds, 0.0)


def _error_type(metric: RequestMetric) -> ErrorType | None:
    if metric.success:
        return None
    status = metric.status_code
    if status is not None:
        if 400 <= status < 500:
            return "http_4xx"
        if status >= 500:
            return "http_5xx"
    error = (metric.error or "").lower()
    if "timeout" in error or "timed out" in error:
        return "timeout"
    if "connect" in error:
        return "connect_error"
    if metric.metadata.get("streaming") and not metric.done_seen:
        return "stream_truncated"
    if error:
        return "unknown"
    return "unknown"


def _iso_from_perf(wall_start: datetime, perf_start: float, perf_value: float) -> str:
    value = wall_start + timedelta(seconds=perf_value - perf_start)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _wall_runtime_seconds(rows: list[RequestProfileRow]) -> float:
    if not rows:
        return 0.0
    starts = [_parse_iso(row.send_ts) for row in rows]
    ends = [_parse_iso(row.done_ts) for row in rows]
    return max((max(ends) - min(starts)).total_seconds(), 0.0)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _summary_claim_status(rows: list[RequestProfileRow]) -> ClaimStatus:
    statuses = {row.claim_status for row in rows}
    if "not_proven" in statuses:
        return "not_proven"
    if "inferred" in statuses:
        return "inferred"
    return "measured"


def _percentile_block(values: list[float]) -> dict[str, float | None]:
    return {"p50": _percentile(values, 50), "p95": _percentile(values, 95), "p99": _percentile(values, 99)}


def _percentile(values: list[float | None], pct: int) -> float | None:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    idx = min(len(clean) - 1, max(0, round((pct / 100) * (len(clean) - 1))))
    return clean[idx]


def _number(value: float | None) -> str:
    return f"{(value or 0.0):.3f}"


__all__ = ["format_stdout_summary", "profile_endpoint", "run_request_profile"]
