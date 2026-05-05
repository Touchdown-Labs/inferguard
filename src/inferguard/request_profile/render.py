"""Human-readable rendering helpers for request-profile summaries."""

from __future__ import annotations

from inferguard.request_profile.types import RequestProfileSummary


def summary_markdown(summary: RequestProfileSummary) -> str:
    """Render a compact markdown summary for operator reports."""

    lines = [
        "# InferGuard request profile summary",
        "",
        f"- Job ID: `{summary.job_id}`",
        f"- Workload label: `{summary.workload_label}`",
        f"- Engine: `{summary.engine}`",
        f"- Concurrency: {summary.concurrency}",
        f"- Requests: {summary.success_count} success / {summary.request_count} total",
        f"- Claim status: `{summary.claim_status}`",
        "",
        "## Latency",
        "",
        f"- TTFT p50/p95/p99 ms: {_metric(summary.ttft_ms)}",
        f"- TPOT p50/p95/p99 ms: {_metric(summary.tpot_ms)}",
        f"- E2E p50/p95/p99 ms: {_metric(summary.e2e_latency_ms)}",
        "",
        "## Tokens",
        "",
        f"- Prompt tokens total: {summary.prompt_tokens_total}",
        f"- Completion tokens total: {summary.completion_tokens_total}",
        f"- Aggregate completion tokens/sec: {_value(summary.tokens_per_sec_aggregate)}",
        "",
        "## Failures",
        "",
    ]
    if summary.failure_breakdown:
        lines.extend(f"- `{key}`: {count}" for key, count in sorted(summary.failure_breakdown.items()))
    else:
        lines.append("No failed requests recorded.")
    lines.append("")
    return "\n".join(lines)


def _metric(block: dict[str, float | None]) -> str:
    return f"{_value(block.get('p50'))} / {_value(block.get('p95'))} / {_value(block.get('p99'))}"


def _value(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


__all__ = ["summary_markdown"]
