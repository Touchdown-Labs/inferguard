"""Markdown renderer for PRD §4.7 operator recommendations."""

from __future__ import annotations

from .types import OperatorRecommendation, Section


def render_markdown(rec: OperatorRecommendation) -> str:
    """Render an operator recommendation with claim labels on every claim line."""

    lines = [
        "# InferGuard operator recommendation",
        "",
        f"- [measured] Schema: `{rec.schema_version}`",
        f"- [{rec.claim_status}] Executive status: `{rec.executive_verdict_status}`",
        "",
    ]
    for section in rec.sections:
        lines.extend(_render_section(section))
    return "\n".join(lines).rstrip() + "\n"


def _render_section(section: Section) -> list[str]:
    lines = [f"## {section.title}", ""]
    lines.extend(section.lines)
    lines.append("")
    return lines


__all__ = ["render_markdown"]
