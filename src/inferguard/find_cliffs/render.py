"""Markdown rendering for PRD §4.8 capacity cliffs."""

from __future__ import annotations

from typing import Any

from .types import CapacityCliffs, Cliff


def render_capacity_cliffs_markdown(capacity: CapacityCliffs) -> str:
    """Render capacity cliffs with claim labels on every cliff section."""

    summary = capacity.summary
    lines = [
        "# InferGuard capacity cliffs",
        "",
        f"- [measured] Schema: `{capacity.schema_version}`",
        f"- [{capacity.claim_status}] Results root: `{capacity.results_root}`",
        f"- [{capacity.claim_status}] Cliffs found: {summary.get('cliffs_found', 0)}",
        "",
        "## Summary",
        "",
        "| Field | Value |",
        "|---|---:|",
    ]
    for key in (
        "max_concurrency",
        "max_context",
        "throughput_plateau_tokens_per_sec",
        "kv_saturation_concurrency",
        "decode_collapse_concurrency",
        "queue_explosion_concurrency",
    ):
        lines.append(f"| `{key}` | {_fmt(summary.get(key))} |")
    lines.append("")

    for cliff in capacity.cliffs:
        lines.extend(_render_cliff(cliff))
    return "\n".join(lines).rstrip() + "\n"


def _render_cliff(cliff: Cliff) -> list[str]:
    lines = [
        f"## {cliff.name}",
        "",
        f"- [{cliff.claim_status}] Value: `{_fmt(cliff.value)}`",
        f"- [{cliff.claim_status}] Confidence: `{cliff.confidence:.3f}`",
        f"- [{cliff.claim_status}] Reasoning: {cliff.reasoning}",
        f"- [{cliff.claim_status}] Recommended next run: {cliff.recommended_next_run}",
        "",
    ]
    if cliff.evidence_paths:
        lines.extend(["### Evidence paths", ""])
        for path in cliff.evidence_paths:
            lines.append(f"- [{cliff.claim_status}] `{path}`")
        lines.append("")
    if cliff.supporting_curve:
        lines.extend(
            [
                "### Supporting curve",
                "",
                "| x | y | metric | job |",
                "|---:|---:|---|---|",
            ]
        )
        for point in cliff.supporting_curve:
            lines.append(
                "| {x} | {y} | `{metric}` | `{job}` |".format(
                    x=_fmt(point.get("x")),
                    y=_fmt(point.get("y")),
                    metric=point.get("metric") or "",
                    job=point.get("job_id") or "",
                )
            )
        lines.append("")
    return lines


def _fmt(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


__all__ = ["render_capacity_cliffs_markdown"]
