"""Markdown rendering for completed-run validation reports."""

from __future__ import annotations

from inferguard.validate.report import ValidationReport


def render_validation_markdown(report: ValidationReport) -> str:
    """Render a human-readable validation report."""
    lines = [
        "# InferGuard completed-run validation",
        "",
        f"- Status: `{report.status}`",
        f"- Results root: `{report.results_root}`",
        f"- Jobs: {len(report.jobs)}",
        f"- Schema: `{report.schema_version}`",
        "",
        "## Summary",
        "",
    ]
    for status, count in sorted(report.summary.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Jobs", ""])
    for job in report.jobs:
        lines.extend(
            [
                f"### `{job.job_id}`",
                "",
                f"- Status: `{job.status}`",
                f"- Claim status: `{job.claim_status}`",
                f"- Required paths present: {len(job.required_paths_present)}",
                f"- Required paths missing: {len(job.required_paths_missing)}",
                f"- Synthetic markers: {len(job.synthetic_markers)}",
                "",
            ]
        )
        if job.required_paths_missing:
            lines.append("Missing required paths:")
            lines.extend(f"- `{path}`" for path in sorted(job.required_paths_missing))
            lines.append("")
        if job.synthetic_markers:
            lines.append("Synthetic markers:")
            lines.extend(f"- `{marker}`" for marker in sorted(job.synthetic_markers))
            lines.append("")
        if job.downgrades:
            lines.append("Claim downgrades:")
            for downgrade in job.downgrades:
                lines.append(
                    f"- `{downgrade.claim_id}`: `{downgrade.from_label}` -> "
                    f"`{downgrade.to}` ({downgrade.reason})"
                )
            lines.append("")
    return "\n".join(lines)
