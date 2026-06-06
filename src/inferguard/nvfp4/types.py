"""Contracts for NVFP4 KV-cache qualification diagnostics.

NVFP4 KV cache (4-bit e2m1 data + fp8 block scale per 16 elements) gives a ~1.78x
capacity ceiling over fp8 but is model-dependent on quality. These types back the
three checks surfaced on the CLI:

  - sm120-compat   : is this GPU on the SM120 FA2 NVFP4-KV path?
  - kv-capacity    : how much KV pool does NVFP4 buy vs fp8?
  - nvfp4-quality  : is NVFP4 quality acceptable for this model? (PPL/divergence/retrieval/speed)

Background: docs/research/49-2026-06-06-nvfp4-kv-sm120-qualification (Touchdown Labs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

NVFP4_QUALIFICATION_SCHEMA_VERSION = "inferguard-nvfp4-qualification/v1"


class NVFp4Verdict(StrEnum):
    """Operator verdict surface for a qualification run."""

    QUALIFIED = "qualified"
    NOT_QUALIFIED = "not_qualified"
    NEEDS_REVIEW = "needs_review"


# Per-check claim provenance, mirroring inferguard.diagnose_bottleneck.Evidence.
CLAIM_MEASURED = "measured"
CLAIM_INFERRED = "inferred"
CLAIM_NOT_PROVEN = "not_proven"


@dataclass(frozen=True)
class QualThresholds:
    """Pass/fail criteria for the nvfp4-quality battery. See default/strict/relaxed."""

    max_ppl_delta_nats: float = 0.05
    min_ruler_ratio: float = 0.95
    min_first_div_tokens: int = 10
    min_capacity_ratio: float = 1.4
    min_speed_ratio: float = 0.85
    ppl_ctx_lengths: tuple[int, ...] = (2000, 8000, 32000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_ppl_delta_nats": self.max_ppl_delta_nats,
            "min_ruler_ratio": self.min_ruler_ratio,
            "min_first_div_tokens": self.min_first_div_tokens,
            "min_capacity_ratio": self.min_capacity_ratio,
            "min_speed_ratio": self.min_speed_ratio,
            "ppl_ctx_lengths": list(self.ppl_ctx_lengths),
        }


DEFAULT_THRESHOLDS = QualThresholds()
STRICT_THRESHOLDS = QualThresholds(
    max_ppl_delta_nats=0.02,
    min_ruler_ratio=0.98,
    min_first_div_tokens=20,
    min_capacity_ratio=1.5,
    min_speed_ratio=0.90,
)
RELAXED_THRESHOLDS = QualThresholds(
    max_ppl_delta_nats=0.10,
    min_ruler_ratio=0.90,
    min_first_div_tokens=5,
    min_capacity_ratio=1.2,
    min_speed_ratio=0.80,
)

THRESHOLD_PROFILES = {
    "default": DEFAULT_THRESHOLDS,
    "strict": STRICT_THRESHOLDS,
    "relaxed": RELAXED_THRESHOLDS,
}


@dataclass(frozen=True)
class CheckResult:
    """One measured criterion with its pass/fail outcome and provenance."""

    name: str
    passed: bool
    value: Any
    threshold: Any
    unit: str
    detail: str
    claim_status: str = CLAIM_MEASURED

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
            "unit": self.unit,
            "detail": self.detail,
            "claim_status": self.claim_status,
        }


@dataclass(frozen=True)
class NVFp4Qualification:
    """Emitted artifact for one check (nvfp4_qualification.json)."""

    check: str
    model: str
    endpoint: str
    verdict: NVFp4Verdict | str
    confidence: float
    claim_status: str
    results: list[CheckResult] = field(default_factory=list)
    reasoning: str = ""
    recommended_next: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    schema_version: str = NVFP4_QUALIFICATION_SCHEMA_VERSION

    def summary_line(self) -> str:
        return (
            f"inferguard nvfp4 {self.check}: "
            f"verdict={str(self.verdict)} "
            f"confidence={self.confidence:.3f} "
            f"checks={len(self.results)} "
            f"claim={self.claim_status}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "model": self.model,
            "endpoint": self.endpoint,
            "verdict": str(self.verdict),
            "confidence": self.confidence,
            "claim_status": self.claim_status,
            "results": [r.to_dict() for r in self.results],
            "reasoning": self.reasoning,
            "recommended_next": self.recommended_next,
            "raw": self.raw,
            "schema_version": self.schema_version,
        }
