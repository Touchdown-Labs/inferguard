"""Markdown rendering for AgentX ingest summaries."""

from __future__ import annotations

from inferguard.agentx_adapter.types import AgentXIngestSummary


def render_ingest_summary(summary: AgentXIngestSummary) -> str:
    """Render a compact operator-readable AgentX ingest summary."""

    lines = [
        "# InferGuard AgentX ingest summary",
        "",
        f"- Status: `{summary.status}`",
        f"- Job ID: `{summary.job_id}`",
        f"- Requests: {summary.success_count}/{summary.request_count} succeeded",
        f"- Mapped metrics: {summary.mapped_metrics_count}",
        f"- Claim status: `{summary.claim_status}`",
        f"- Inputs under target warning: `{summary.inputs_under_target_warning}`",
    ]
    if summary.error_type:
        lines.extend(["", "## Error", "", f"- Type: `{summary.error_type}`"])
        if summary.error_message:
            lines.append(f"- Message: {summary.error_message}")
    if summary.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in summary.warnings)
    lines.extend(["", "## Raw artifacts", ""])
    for name, path in sorted(summary.raw_artifact_paths.items()):
        lines.append(f"- `{name}`: `{path}`")
    return "\n".join(lines) + "\n"


__all__ = ["render_ingest_summary"]
