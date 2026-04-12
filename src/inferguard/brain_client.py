"""Brain client and proactive wire shapes for InferGuard v6.

Slice 1 intentionally ships a stubbed client that always returns no
advisories. This unblocks L2 wiring while L3 is scaffolded in later slices.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from inferguard.config import InferGuardConfig
from inferguard.memory import MemoryStore

log = structlog.get_logger()


@dataclass(slots=True)
class ProactiveAdvisory:
    id: str
    timestamp: float
    advisory_type: str
    confidence: float
    horizon_seconds: int
    reason: str
    evidence: list[str]
    recommended_safe_actions: list[dict[str, Any]]
    advisory_only: bool = True
    source: str = "brain_client"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "advisory_type": self.advisory_type,
            "confidence": self.confidence,
            "horizon_seconds": self.horizon_seconds,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "recommended_safe_actions": [dict(a) for a in self.recommended_safe_actions],
            "advisory_only": self.advisory_only,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProactiveAdvisory":
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:12]),
            timestamp=float(data.get("timestamp") or time.time()),
            advisory_type=str(data.get("advisory_type", "degradation_trend")),
            confidence=float(data.get("confidence", 0.5)),
            horizon_seconds=int(data.get("horizon_seconds", 0) or 0),
            reason=str(data.get("reason", "")),
            evidence=[str(e) for e in (data.get("evidence") or [])],
            recommended_safe_actions=[
                dict(a)
                for a in (data.get("recommended_safe_actions") or [])
                if isinstance(a, dict)
            ],
            advisory_only=(data.get("advisory_only") is True),
            source=str(data.get("source") or "brain_client"),
        )


@dataclass(slots=True)
class InvestigationContext:
    window_snapshots: list[dict[str, Any]]
    prior_incidents: list[dict[str, Any]]
    event_log_tail: list[dict[str, Any]]
    current_model_name: str
    current_engine: str
    current_snapshot: dict[str, Any]
    llm_backend: dict[str, str]

    def to_json(self) -> str:
        return json.dumps(
            {
                "window_snapshots": self.window_snapshots,
                "prior_incidents": self.prior_incidents,
                "event_log_tail": self.event_log_tail,
                "current_model_name": self.current_model_name,
                "current_engine": self.current_engine,
                "current_snapshot": self.current_snapshot,
                "llm_backend": self.llm_backend,
            },
            default=str,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_snapshots": self.window_snapshots,
            "prior_incidents": self.prior_incidents,
            "event_log_tail": self.event_log_tail,
            "current_model_name": self.current_model_name,
            "current_engine": self.current_engine,
            "current_snapshot": self.current_snapshot,
            "llm_backend": self.llm_backend,
        }

    def as_dict(self) -> dict[str, Any]:
        return self.to_dict()


class BrainClient:
    """L2 bridge to L3 brain."""

    def __init__(self, config: InferGuardConfig, memory: MemoryStore):
        self.config = config
        self.memory = memory

    async def request_investigation(
        self, ctx: InvestigationContext
    ) -> list[ProactiveAdvisory]:
        try:
            payload = ctx.to_dict()
            payload["llm_backend"] = {
                "base_url": self.config.llm_base_url,
                "api_key": self.config.llm_api_key,
                "model": self.config.llm_model,
            }
            if self.config.brain_mode == "local":
                records = await self._request_local(payload)
            else:
                log.info(
                    "brain_client_remote_not_implemented",
                    mode=self.config.brain_mode,
                    agent=self.config.brain_agent_name,
                )
                return []
        except Exception as exc:
            log.warning("brain_client_request_failed", error=str(exc))
            return []
        return self._validate_records(records)

    async def _request_local(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        repo_root = Path(__file__).resolve().parents[2]
        repo_root_str = str(repo_root)
        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)

        from blaxel_agent.brain import InferGuardBrain

        brain = InferGuardBrain()
        result = await brain.investigate(payload)
        if not isinstance(result, list):
            return []
        return [r for r in result if isinstance(r, dict)]

    def _validate_records(
        self, records: list[dict[str, Any]]
    ) -> list[ProactiveAdvisory]:
        out: list[ProactiveAdvisory] = []
        for record in records:
            if record.get("advisory_only") is not True:
                log.warning(
                    "brain_client_record_dropped_not_advisory_only",
                    record=str(record)[:240],
                )
                continue
            advisory = ProactiveAdvisory.from_dict(record)
            if advisory.advisory_only is not True:
                log.warning(
                    "brain_client_record_dropped_post_parse",
                    record=str(record)[:240],
                )
                continue
            out.append(advisory)
        return out
