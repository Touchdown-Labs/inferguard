"""Human-readable rendering helpers for ``inferguard profile``."""

from __future__ import annotations

from inferguard.profile.types import ProfileSample, ProfileSummary


def sample_line(sample: ProfileSample) -> str:
    """Return one compact streaming row for table mode."""
    snapshot = sample.snapshot
    endpoint = snapshot.get("endpoint", {}) if isinstance(snapshot, dict) else {}
    findings = ",".join(finding.code for finding in sample.findings) or "-"
    return (
        f"sample={sample.sequence} "
        f"engine={endpoint.get('engine', 'unknown')} "
        f"kv={_pct(snapshot.get('kv_cache_usage'))} "
        f"running={_value(snapshot.get('requests_running'))} "
        f"waiting={_value(snapshot.get('requests_waiting'))} "
        f"preemptions_delta={_value(sample.deltas.get('preemptions_total_delta'))} "
        f"findings={findings}"
    )


def summary_markdown(summary: ProfileSummary) -> str:
    """Render ``profile.md`` from the summary contract."""
    findings = summary.findings
    lines = [
        "# InferGuard profile live summary",
        "",
        f"- Profile ID: `{summary.profile_id}`",
        f"- Samples: {summary.sample_count}",
        f"- Duration seconds: {summary.duration_seconds:g}",
        f"- Engine: {summary.engine}",
        f"- Highest KV cache usage: {_pct(summary.highest_kv_cache_usage)}",
        f"- Max requests waiting: {_value(summary.max_requests_waiting)}",
        f"- Preemptions total delta: {_value(summary.preemptions_total_delta)}",
        f"- Prefix cache hit rate observed: {_pct(summary.prefix_cache_hit_rate_observed)}",
        "",
        "## Recommendation",
        "",
        summary.recommendation,
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("No profile findings tripped during the sample window.")
    else:
        for finding in findings:
            lines.append(f"- **{finding.severity}** `{finding.code}` — {finding.message}")
    lines.append("")
    return "\n".join(lines)


def _pct(value: object) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number * 100:.0f}%" if number <= 1.0 else f"{number:.0f}"


def _value(value: object) -> str:
    return "-" if value is None else str(value)
