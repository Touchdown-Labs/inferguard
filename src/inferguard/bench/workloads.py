"""Trace loading and synthetic KV/KVCast workload generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Keep the historical ``inferguard.bench.workloads`` module importable while
# allowing focused workload-generator submodules under ``bench/workloads/``.
__path__ = [str(Path(__file__).with_suffix(""))]
from typing import Literal

from inferguard.bench.types import RequestSpec
from inferguard.schemas.trace import TraceRecord, TraceValidationError

KVCastMode = Literal[
    "prefix-reuse",
    "cold-pressure",
    "mixed-agent",
    "eviction-probe",
    "fragmentation-probe",
    "multi-tenant-storm",
    "retry-storm",
]


class WorkloadLoadError(ValueError):
    """Raised for invalid workload input files or options."""


def load_trace_dir(trace_dir: Path) -> list[RequestSpec]:
    if not trace_dir.exists() or not trace_dir.is_dir():
        raise WorkloadLoadError(f"trace-dir does not exist or is not a directory: {trace_dir}")
    specs: list[RequestSpec] = []
    for path in sorted(trace_dir.rglob("*.jsonl")):
        specs.extend(_load_trace_file(path))
    if not specs:
        raise WorkloadLoadError(f"no JSONL trace records found under {trace_dir}")
    return specs


def generate_kv_stress_specs(
    *,
    context_lengths: list[int],
    output_tokens: int,
    requests_per_level: int = 4,
    mode: KVCastMode = "cold-pressure",
    customers: int = 1,
    sla_tiers: dict[str, str] | None = None,
) -> list[RequestSpec]:
    if requests_per_level <= 0:
        raise WorkloadLoadError("requests_per_level must be a positive integer")
    if mode not in {
        "prefix-reuse",
        "cold-pressure",
        "mixed-agent",
        "eviction-probe",
        "fragmentation-probe",
        "multi-tenant-storm",
        "retry-storm",
    }:
        raise WorkloadLoadError(
            "mode must be one of prefix-reuse|cold-pressure|mixed-agent|eviction-probe|fragmentation-probe|multi-tenant-storm|retry-storm"
        )
    if customers <= 0:
        raise WorkloadLoadError("customers must be a positive integer")
    specs: list[RequestSpec] = []
    for context_length in context_lengths:
        if context_length <= 0:
            raise WorkloadLoadError("context lengths must be positive integers")
        specs.extend(
            _generate_context_specs(
                context_length=context_length,
                output_tokens=output_tokens,
                requests_per_level=requests_per_level,
                mode=mode,
                customers=customers,
                sla_tiers=sla_tiers or {},
            )
        )
    return specs


def _generate_context_specs(
    *,
    context_length: int,
    output_tokens: int,
    requests_per_level: int,
    mode: KVCastMode,
    customers: int = 1,
    sla_tiers: dict[str, str] | None = None,
) -> list[RequestSpec]:
    shared_prefix = _synthetic_context(context_length, seed=f"shared-{context_length}")
    specs: list[RequestSpec] = []
    for turn in range(requests_per_level):
        workload_class, cache_mode, prefix_group, context = _mode_shape(
            mode=mode,
            context_length=context_length,
            turn=turn,
            shared_prefix=shared_prefix,
        )
        customer_id = f"customer-{turn % customers + 1:02d}" if customers > 1 else "customer-01"
        tier_names = list((sla_tiers or {"standard": "p99<5s"}).keys())
        sla_tier = tier_names[turn % len(tier_names)] if tier_names else "standard"
        trace = TraceRecord(
            trace_id=f"kvcast-{mode}-{context_length}-{turn}",
            session_id=f"kvcast-{mode}-{context_length}-{prefix_group or turn}",
            turn_index=turn,
            workload_class=workload_class,
            messages=[
                {
                    "role": "system",
                    "content": "You are a deterministic coding assistant. Answer briefly.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Synthetic KVCast {mode} context targeting approximately {context_length} "
                        f"tokens. Summarize the final marker.\n\n{context}\n\n"
                        f"FINAL_MARKER_{mode}_{context_length}_{turn}"
                    ),
                },
            ],
            expected_input_tokens=context_length,
            expected_output_tokens=output_tokens,
            prefix_group=prefix_group,
            tool_heavy=mode == "mixed-agent" and turn % 4 == 3,
            metadata={
                "benchmark_role": "kvcast",
                "kvcast_mode": mode,
                "cache_mode": cache_mode,
                "probe_phase": cache_mode,
                "target_context_tokens": context_length,
                "kv_pressure": "inferred_without_engine_metrics",
                "customer_id": customer_id,
                "sla_tier": sla_tier,
                "sla_policy": (sla_tiers or {}).get(sla_tier),
            },
        )
        specs.append(_spec_from_trace(trace))
    return specs


def _mode_shape(
    *,
    mode: KVCastMode,
    context_length: int,
    turn: int,
    shared_prefix: str,
) -> tuple[str, str, str | None, str]:
    if mode == "prefix-reuse":
        return "prefix-reuse", "prefix_reuse", f"kvcast-shared-{context_length}", shared_prefix
    if mode == "cold-pressure":
        return (
            "kv-pressure",
            "cold",
            None,
            _synthetic_context(context_length, seed=f"cold-{context_length}-{turn}"),
        )
    if mode == "eviction-probe":
        bucket = turn % 6
        if bucket in {0, 1}:
            return (
                "prefix-reuse",
                "eviction_warm",
                f"kvcast-evict-anchor-{context_length}",
                shared_prefix,
            )
        if bucket in {2, 3, 4}:
            pressure_length = max(context_length * 2, context_length + 1024)
            return (
                "kv-pressure",
                "eviction_pressure",
                None,
                _synthetic_context(pressure_length, seed=f"evict-pressure-{context_length}-{turn}"),
            )
        return (
            "session-resume",
            "eviction_retest",
            f"kvcast-evict-anchor-{context_length}",
            shared_prefix,
        )
    if mode == "multi-tenant-storm":
        # Implements S-05 multi-tenant concurrency storm (see docs/inferguard/24).
        bucket = turn % 12
        if bucket < 4:
            return (
                "agent-chat",
                "storm_interactive",
                f"storm-chat-{context_length}-{turn % 2}",
                shared_prefix,
            )
        if bucket < 8:
            return (
                "kv-pressure",
                "storm_batch_pressure",
                None,
                _synthetic_context(context_length * 2, seed=f"storm-batch-{context_length}-{turn}"),
            )
        return (
            "session-resume",
            "storm_resume",
            f"storm-resume-{context_length}-{turn % 3}",
            shared_prefix,
        )
    if mode == "retry-storm":
        # Implements S-26 function-call retry storm (see docs/inferguard/24).
        bucket = turn % 5
        if bucket == 0:
            return "tool-heavy", "retry_root_turn", f"retry-root-{context_length}", shared_prefix
        if bucket in {1, 2, 3}:
            retry_context = shared_prefix + "\n\nTOOL_FAILURE_SIGNATURE=HTTP_503_RETRYABLE\n"
            return (
                "tool-heavy",
                "retry_failed_tool_call",
                f"retry-root-{context_length}",
                retry_context,
            )
        return (
            "agent-chat",
            "retry_queue_replay",
            f"retry-replay-{context_length}-{turn % 2}",
            _synthetic_context(
                max(512, context_length // 4), seed=f"retry-replay-{context_length}-{turn}"
            ),
        )
    if mode == "fragmentation-probe":
        bucket = turn % 4
        if bucket == 0:
            short_length = max(128, context_length // 16)
            return (
                "agent-chat",
                "fragment_short",
                None,
                _synthetic_context(short_length, seed=f"fragment-short-{context_length}-{turn}"),
            )
        if bucket == 1:
            return (
                "kv-pressure",
                "fragment_long",
                None,
                _synthetic_context(context_length, seed=f"fragment-long-{context_length}-{turn}"),
            )
        if bucket == 2:
            mid_length = max(512, context_length // 4)
            return (
                "session-resume",
                "fragment_mid_resume",
                f"kvcast-fragment-mid-{context_length}",
                _synthetic_context(mid_length, seed=f"fragment-mid-{context_length}"),
            )
        return (
            "kv-pressure",
            "fragment_long_after",
            None,
            _synthetic_context(context_length, seed=f"fragment-long-after-{context_length}-{turn}"),
        )

    # Mixed-agent intentionally blends warm prefixes, cold sessions, resumes, and tool-heavy tails.
    bucket = turn % 10
    if bucket < 4:
        return "prefix-reuse", "prefix_reuse", f"kvcast-mixed-repo-{context_length}", shared_prefix
    if bucket < 7:
        return (
            "kv-pressure",
            "cold",
            None,
            _synthetic_context(context_length, seed=f"mixed-cold-{context_length}-{turn}"),
        )
    if bucket < 9:
        return "session-resume", "mixed", f"kvcast-resume-{context_length}", shared_prefix
    tool_context = shared_prefix + "\n\n" + _synthetic_tool_output(context_length, turn)
    return (
        "tool-heavy",
        "mixed",
        f"kvcast-tools-{context_length}",
        tool_context[: max(64, context_length * 4)],
    )


def _load_trace_file(path: Path) -> list[RequestSpec]:
    specs: list[RequestSpec] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        source = f"{path}:{line_no}"
        try:
            data = json.loads(line)
            trace = TraceRecord.from_dict(data, source=source)
        except (json.JSONDecodeError, TraceValidationError) as exc:
            raise WorkloadLoadError(str(exc)) from exc
        specs.append(_spec_from_trace(trace))
    return specs


def _spec_from_trace(trace: TraceRecord) -> RequestSpec:
    return RequestSpec(
        request_id=f"{trace.trace_id}:turn-{trace.turn_index}",
        trace_id=trace.trace_id,
        session_id=trace.session_id,
        turn_index=trace.turn_index,
        workload_class=trace.workload_class,
        messages=trace.messages,
        expected_input_tokens=trace.expected_input_tokens,
        expected_output_tokens=trace.expected_output_tokens,
        prefix_group=trace.prefix_group,
        tool_heavy=trace.tool_heavy,
        metadata=trace.metadata,
        customer_id=str(trace.metadata.get("customer_id"))
        if trace.metadata.get("customer_id")
        else None,
        sla_tier=str(trace.metadata.get("sla_tier")) if trace.metadata.get("sla_tier") else None,
    )


def _synthetic_context(target_tokens: int, *, seed: str) -> str:
    # Avoid tokenizer dependencies while approximately matching target length.
    target_chars = max(64, target_tokens * 4)
    digest = hashlib.sha256(seed.encode()).hexdigest()
    line = (
        f"# synthetic_context seed={seed} digest={digest}\n"
        "def inferguard_synthetic_workload(session_state, kv_cache, request): "
        "return {'status': 'measure', 'cache': kv_cache.lookup(request)}\n"
    )
    repeats = max(1, target_chars // len(line) + 1)
    content = "".join(f"{idx:06d}:{line}" for idx in range(repeats))
    return content[:target_chars]


def _synthetic_tool_output(target_tokens: int, turn: int) -> str:
    lines = []
    for idx in range(max(4, target_tokens // 512)):
        lines.append(
            json.dumps(
                {
                    "tool": "grep" if idx % 2 == 0 else "pytest",
                    "turn": turn,
                    "line": idx,
                    "path": f"src/module_{idx % 13}.py",
                    "output": "stack trace / JSON tool output / code context",
                },
                sort_keys=True,
            )
        )
    return "\n".join(lines)
