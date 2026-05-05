"""Live profile loop for existing serving endpoints.

Unlike ``bench``, this module never sends generation traffic. It only scrapes
engine ``/metrics`` surfaces, computes sample-to-sample deltas, streams profile
findings, and writes profile artifacts.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from inferguard.config import HTTP_TIMEOUT_SECONDS
from inferguard.disagg.adapters import scrape
from inferguard.disagg.types import DisaggSnapshot, EngineName
from inferguard.io import atomic_write_json
from inferguard.profile.render import sample_line, summary_markdown
from inferguard.profile.types import ProfileFinding, ProfileSample, ProfileSummary

KV_CACHE_HIGH_THRESHOLD = 0.90
KV_CACHE_CRITICAL_THRESHOLD = 0.95
PREFIX_QUERY_MIN_DELTA = 50
PREFIX_HIT_RATE_LOW_THRESHOLD = 0.50

_COUNTER_FIELDS: tuple[str, ...] = (
    "preemptions_total",
    "prefix_cache_hits",
    "prefix_cache_queries",
    "cpu_prefix_cache_hits",
    "cpu_prefix_cache_queries",
    "kv_offload_bytes_gpu_to_cpu",
    "kv_offload_bytes_cpu_to_gpu",
    "kv_offload_time_gpu_to_cpu",
    "kv_offload_time_cpu_to_gpu",
    "kv_transfer_sent_bytes_total",
    "kv_transfer_recv_bytes_total",
    "kv_transfer_errors_total",
    "vllm_offload_eviction_count",
)


class ProfileError(RuntimeError):
    """Raised when profile options are invalid or artifacts cannot be written."""


@dataclass(frozen=True)
class ProfileLiveOptions:
    """Options for ``inferguard profile live``."""

    endpoint: str
    output_dir: Path
    duration_seconds: float = 60.0
    interval_seconds: float = 2.0
    engine: EngineName | None = None
    timeout_seconds: float = HTTP_TIMEOUT_SECONDS
    output_format: str = "table"


async def run_profile_live(
    options: ProfileLiveOptions,
    *,
    emit: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run the live profile loop and write ``profile.*`` artifacts.

    Returns a dict containing the in-memory ``samples`` and ``summary`` for
    tests and programmatic callers. The on-disk public contracts are
    ``profile.jsonl``, ``profile_summary.json``, and ``profile.md``.
    """
    _validate_options(options)
    emit = emit or (lambda _line: None)
    output_dir = options.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_path = output_dir / "profile.jsonl"
    summary_path = output_dir / "profile_summary.json"
    markdown_path = output_dir / "profile.md"
    endpoint = _normalize_endpoint(options.endpoint)
    profile_id = _profile_id()
    samples: list[ProfileSample] = []
    previous: DisaggSnapshot | None = None
    backlog_streak = 0
    deadline = time.monotonic() + options.duration_seconds

    async with httpx.AsyncClient(timeout=options.timeout_seconds) as client:
        with sample_path.open("w", encoding="utf-8") as fp:
            sequence = 0
            while True:
                snapshot = await scrape(endpoint, "prefill", options.engine, client)
                deltas = _compute_deltas(previous, snapshot)
                backlog_streak = _next_backlog_streak(backlog_streak, snapshot)
                findings = _sample_findings(
                    previous=previous,
                    snapshot=snapshot,
                    deltas=deltas,
                    backlog_streak=backlog_streak,
                )
                sample = ProfileSample(
                    profile_id=profile_id,
                    sequence=sequence,
                    observed_at=_utc_now_iso(),
                    mode="single-endpoint",
                    snapshot=snapshot.as_dict(),
                    deltas=deltas,
                    findings=findings,
                )
                fp.write(json.dumps(sample.as_dict(), sort_keys=True) + "\n")
                fp.flush()
                samples.append(sample)
                _emit_sample(sample, options.output_format, emit)
                previous = snapshot
                sequence += 1

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(options.interval_seconds, remaining))

    summary = _build_summary(
        profile_id=profile_id,
        duration_seconds=options.duration_seconds,
        samples=samples,
    )
    atomic_write_json(summary_path, summary.as_dict())
    markdown_path.write_text(summary_markdown(summary), encoding="utf-8")
    return {"samples": samples, "summary": summary}


def _validate_options(options: ProfileLiveOptions) -> None:
    if not options.endpoint:
        raise ProfileError("--endpoint is required for profile live MVP")
    if options.duration_seconds <= 0:
        raise ProfileError("--duration must be positive")
    if options.interval_seconds <= 0:
        raise ProfileError("--interval must be positive")
    if options.timeout_seconds <= 0:
        raise ProfileError("--timeout must be positive")
    if options.output_format not in {"table", "json"}:
        raise ProfileError("--format must be one of table|json")


def _normalize_endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/metrics"):
        endpoint = endpoint[: -len("/metrics")]
    return endpoint


def _profile_id() -> str:
    return "profile_" + datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _compute_deltas(
    previous: DisaggSnapshot | None,
    current: DisaggSnapshot,
) -> dict[str, int | float]:
    if previous is None:
        return {}
    deltas: dict[str, int | float] = {}
    for field_name in _COUNTER_FIELDS:
        prev_value = getattr(previous, field_name)
        cur_value = getattr(current, field_name)
        if prev_value is None or cur_value is None:
            continue
        delta = cur_value - prev_value
        if delta < 0:
            # Prometheus counter reset; keep the row useful without fabricating
            # negative churn.
            delta = cur_value
        deltas[f"{field_name}_delta"] = delta
    return deltas


def _next_backlog_streak(current_streak: int, snapshot: DisaggSnapshot) -> int:
    waiting = snapshot.requests_waiting
    running = snapshot.requests_running
    if waiting is None or running is None:
        return 0
    return current_streak + 1 if waiting > running else 0


def _sample_findings(
    *,
    previous: DisaggSnapshot | None,
    snapshot: DisaggSnapshot,
    deltas: dict[str, int | float],
    backlog_streak: int,
) -> list[ProfileFinding]:
    findings: list[ProfileFinding] = []
    if snapshot.scrape_error:
        findings.append(
            ProfileFinding(
                code="profile_metrics_unavailable",
                severity="critical",
                message=f"metrics scrape failed: {snapshot.scrape_error}",
                evidence={"endpoint": snapshot.endpoint.url, "error": snapshot.scrape_error},
            )
        )
        return findings

    kv_usage = snapshot.kv_cache_usage
    if kv_usage is not None and kv_usage >= KV_CACHE_CRITICAL_THRESHOLD:
        findings.append(
            ProfileFinding(
                code="profile_kv_cache_critical",
                severity="critical",
                message=f"KV cache usage is critical at {kv_usage:.0%}",
                evidence={"kv_cache_usage": kv_usage, "threshold": KV_CACHE_CRITICAL_THRESHOLD},
            )
        )
    elif kv_usage is not None and kv_usage >= KV_CACHE_HIGH_THRESHOLD:
        findings.append(
            ProfileFinding(
                code="profile_kv_cache_high",
                severity="warning",
                message=f"KV cache usage is high at {kv_usage:.0%}",
                evidence={"kv_cache_usage": kv_usage, "threshold": KV_CACHE_HIGH_THRESHOLD},
            )
        )

    preempt_delta = deltas.get("preemptions_total_delta")
    if preempt_delta is not None and preempt_delta > 0:
        findings.append(
            ProfileFinding(
                code="profile_preemptions_rising",
                severity="warning",
                message=f"preemptions_total increased by {preempt_delta:g}",
                evidence={
                    "previous": previous.preemptions_total if previous is not None else None,
                    "current": snapshot.preemptions_total,
                    "delta": preempt_delta,
                },
            )
        )

    if backlog_streak >= 2:
        findings.append(
            ProfileFinding(
                code="profile_queue_backlog",
                severity="warning",
                message=(
                    "requests_waiting exceeded requests_running for "
                    f"{backlog_streak} consecutive samples"
                ),
                evidence={
                    "requests_running": snapshot.requests_running,
                    "requests_waiting": snapshot.requests_waiting,
                    "backlog_streak": backlog_streak,
                },
            )
        )

    prefix_finding = _prefix_hit_rate_finding(deltas)
    if prefix_finding is not None:
        findings.append(prefix_finding)

    if _has_offload_churn(deltas) and kv_usage is not None and kv_usage >= KV_CACHE_HIGH_THRESHOLD:
        findings.append(
            ProfileFinding(
                code="profile_offload_churn",
                severity="warning",
                message="offload counters increased while KV cache usage stayed high",
                evidence={
                    "kv_cache_usage": kv_usage,
                    "offload_deltas": {
                        key: value for key, value in deltas.items() if "offload" in key
                    },
                },
            )
        )
    return findings


def _prefix_hit_rate_finding(deltas: dict[str, int | float]) -> ProfileFinding | None:
    hits_delta = _number(deltas.get("prefix_cache_hits_delta"))
    queries_delta = _number(deltas.get("prefix_cache_queries_delta"))
    if hits_delta is None or queries_delta is None:
        return None
    if queries_delta < PREFIX_QUERY_MIN_DELTA:
        return None
    rate = hits_delta / queries_delta if queries_delta else 0.0
    if rate >= PREFIX_HIT_RATE_LOW_THRESHOLD:
        return None
    severity = "warning" if rate < 0.25 else "info"
    return ProfileFinding(
        code="profile_prefix_hit_rate_low",
        severity=severity,
        message=(f"prefix cache hit-rate delta was {rate:.0%} over {queries_delta:g} queries"),
        evidence={
            "prefix_cache_hits_delta": hits_delta,
            "prefix_cache_queries_delta": queries_delta,
            "hit_rate": rate,
            "threshold": PREFIX_HIT_RATE_LOW_THRESHOLD,
        },
    )


def _has_offload_churn(deltas: dict[str, int | float]) -> bool:
    churn_keys = (
        "kv_offload_bytes_gpu_to_cpu_delta",
        "kv_offload_bytes_cpu_to_gpu_delta",
        "kv_offload_time_gpu_to_cpu_delta",
        "kv_offload_time_cpu_to_gpu_delta",
        "vllm_offload_eviction_count_delta",
    )
    return any((_number(deltas.get(key)) or 0) > 0 for key in churn_keys)


def _build_summary(
    *,
    profile_id: str,
    duration_seconds: float,
    samples: list[ProfileSample],
) -> ProfileSummary:
    snapshots = [sample.snapshot for sample in samples]
    reachable_snapshots = [snapshot for snapshot in snapshots if not snapshot.get("scrape_error")]
    engine = _summary_engine(reachable_snapshots or snapshots)
    highest_kv = _max_present(snapshot.get("kv_cache_usage") for snapshot in reachable_snapshots)
    max_waiting = _max_present(snapshot.get("requests_waiting") for snapshot in reachable_snapshots)
    preemptions_delta = _first_last_delta(reachable_snapshots, "preemptions_total")
    prefix_hit_rate = _observed_prefix_hit_rate(reachable_snapshots)
    all_findings = [finding for sample in samples for finding in sample.findings]
    summary_findings = _dedupe_findings(all_findings)
    recommendation = _recommendation(summary_findings)
    return ProfileSummary(
        profile_id=profile_id,
        duration_seconds=duration_seconds,
        sample_count=len(samples),
        engine=engine,
        highest_kv_cache_usage=highest_kv,
        max_requests_waiting=int(max_waiting) if max_waiting is not None else None,
        preemptions_total_delta=int(preemptions_delta) if preemptions_delta is not None else None,
        prefix_cache_hit_rate_observed=prefix_hit_rate,
        recommendation=recommendation,
        findings=summary_findings,
    )


def _summary_engine(snapshots: list[dict[str, Any]]) -> str:
    for snapshot in reversed(snapshots):
        endpoint = snapshot.get("endpoint") or {}
        engine = endpoint.get("engine")
        if engine:
            return str(engine)
    return "unknown"


def _max_present(values: Any) -> float | None:
    present = [_number(value) for value in values]
    present = [value for value in present if value is not None]
    return max(present) if present else None


def _first_last_delta(snapshots: list[dict[str, Any]], field_name: str) -> float | None:
    present = [_number(snapshot.get(field_name)) for snapshot in snapshots]
    present = [value for value in present if value is not None]
    if len(present) < 2:
        return None
    delta = present[-1] - present[0]
    return max(0.0, delta)


def _observed_prefix_hit_rate(snapshots: list[dict[str, Any]]) -> float | None:
    hits = _first_last_delta(snapshots, "prefix_cache_hits")
    queries = _first_last_delta(snapshots, "prefix_cache_queries")
    if hits is None or queries is None or queries <= 0:
        return None
    return hits / queries


def _dedupe_findings(findings: list[ProfileFinding]) -> list[ProfileFinding]:
    seen: set[str] = set()
    out: list[ProfileFinding] = []
    for finding in findings:
        if finding.code in seen:
            continue
        seen.add(finding.code)
        out.append(finding)
    return out


def _recommendation(findings: list[ProfileFinding]) -> str:
    codes = {finding.code for finding in findings}
    if "profile_metrics_unavailable" in codes:
        return (
            "Metrics were unavailable; verify the endpoint base URL and that /metrics is exposed."
        )
    if "profile_kv_cache_critical" in codes or (
        "profile_kv_cache_high" in codes and "profile_preemptions_rising" in codes
    ):
        return (
            "KV usage high and preemptions rising; lower concurrency or "
            "enable/validate offload before the next sweep."
        )
    if "profile_kv_cache_high" in codes:
        return "KV usage is high; watch preemptions and consider lowering concurrency or validating offload."
    if "profile_queue_backlog" in codes:
        return "Queue backlog is building; reduce arrival rate or add decode capacity."
    if "profile_prefix_hit_rate_low" in codes:
        return "Prefix cache hit-rate is low; validate prompt reuse shape and prefix-cache configuration."
    if "profile_offload_churn" in codes:
        return "Offload churn observed; validate CPU/GPU offload sizing and cache residency."
    return "No profile findings tripped; keep this artifact as a healthy baseline."


def _emit_sample(sample: ProfileSample, output_format: str, emit: Callable[[str], None]) -> None:
    if output_format == "json":
        emit(json.dumps(sample.as_dict(), sort_keys=True))
    else:
        emit(sample_line(sample))


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
