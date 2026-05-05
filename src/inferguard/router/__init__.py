"""Rule-based execution-path router."""

from .classify import classify_run_dir, render_verdict_markdown

__all__ = ["classify_run_dir", "render_verdict_markdown"]
