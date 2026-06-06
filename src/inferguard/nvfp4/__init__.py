"""NVFP4 KV-cache qualification diagnostics for InferGuard.

Answers "is NVFP4 KV cache safe and economical for THIS model on THIS GPU?"
via three checks: sm120-compat, kv-capacity, nvfp4-quality.

Background and methodology:
docs/research/49-2026-06-06-nvfp4-kv-sm120-qualification (Touchdown Labs).
"""

from __future__ import annotations

from .checks import (
    detect_local_capability,
    parse_kv_tokens_from_metrics,
    qualify_quality,
    run_kv_capacity,
    run_nvfp4_quality,
    run_sm120_compat,
)
from .render import render_qualification_console, render_qualification_markdown
from .types import (
    DEFAULT_THRESHOLDS,
    NVFP4_QUALIFICATION_SCHEMA_VERSION,
    RELAXED_THRESHOLDS,
    STRICT_THRESHOLDS,
    THRESHOLD_PROFILES,
    CheckResult,
    NVFp4Qualification,
    NVFp4Verdict,
    QualThresholds,
)

__all__ = [
    "DEFAULT_THRESHOLDS",
    "NVFP4_QUALIFICATION_SCHEMA_VERSION",
    "RELAXED_THRESHOLDS",
    "STRICT_THRESHOLDS",
    "THRESHOLD_PROFILES",
    "CheckResult",
    "NVFp4Qualification",
    "NVFp4Verdict",
    "QualThresholds",
    "detect_local_capability",
    "parse_kv_tokens_from_metrics",
    "qualify_quality",
    "render_qualification_console",
    "render_qualification_markdown",
    "run_kv_capacity",
    "run_nvfp4_quality",
    "run_sm120_compat",
]
