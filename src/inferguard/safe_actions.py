from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import time
import uuid


@dataclass(slots=True)
class SafeAction:
    id: str
    timestamp: float
    action_type: str
    reason: str
    parameters: dict
    advisory_only: bool = True
    applied: bool = False
    incident_id: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "action_type": self.action_type,
            "reason": self.reason,
            "parameters": dict(self.parameters),
            "advisory_only": self.advisory_only,
            "applied": self.applied,
            "incident_id": self.incident_id,
        }


class SafeActionApplier:
    """v1: advisory-only. Returns SafeAction records; does not mutate the target engine."""

    def _mk(self, action_type: str, reason: str, parameters: dict, incident_id: str) -> SafeAction:
        return SafeAction(
            id=uuid.uuid4().hex[:12], timestamp=time.time(), action_type=action_type,
            reason=reason, parameters=parameters, advisory_only=True, applied=False,
            incident_id=incident_id,
        )

    def throttle_concurrency(self, current_max_num_seqs_hint: int, incident_id: str) -> SafeAction:
        after = max(8, current_max_num_seqs_hint // 2)
        return self._mk(
            "throttle_concurrency",
            "High KV pressure with churn detected; suggest lowering max_num_seqs.",
            {"max_num_seqs_before": current_max_num_seqs_hint, "max_num_seqs_after": after},
            incident_id,
        )

    def flush_session_radix(self, session_id: str, incident_id: str) -> SafeAction:
        return self._mk(
            "flush_session_radix",
            "Prefix cache thrashing detected; suggest flushing the active session radix tree.",
            {"session_id": session_id},
            incident_id,
        )

    def drain_and_recycle(self, incident_id: str) -> SafeAction:
        return self._mk(
            "drain_and_recycle",
            "Swap activity detected; suggest draining traffic and recycling the current replica.",
            {"replica": "current"},
            incident_id,
        )

    def quarantine_shape(self, shape_hash: str, reason: str, incident_id: str) -> SafeAction:
        return self._mk("quarantine_shape", reason, {"shape_hash": shape_hash}, incident_id)

    def shrink_speculation_window(self, current_window: int, incident_id: str) -> SafeAction:
        return self._mk(
            "shrink_speculation_window",
            "Speculation instability detected; suggest shrinking speculation window.",
            {"window_before": current_window, "window_after": max(1, current_window // 2)},
            incident_id,
        )


def decide_safe_actions(
    snapshot: Any, anomaly: Any, previous_snapshot: Any, model_name: str, incident_id: str
) -> list[SafeAction]:
    """Rule-based mapping from anomaly signals to SAFE actions. Empty list if no action warranted."""
    _ = model_name
    applier = SafeActionApplier()
    actions: list[SafeAction] = []
    seen_types: set[str] = set()
    reasons = list(getattr(anomaly, "reasons", []) or [])
    reasons_l = [str(r).lower() for r in reasons]

    def add(action: SafeAction) -> None:
        if action.action_type not in seen_types:
            seen_types.add(action.action_type)
            actions.append(action)

    kv_usage = float(getattr(snapshot, "kv_cache_usage", 0.0) or 0.0)
    preemption_delta = 0 if previous_snapshot is None else (
        int(getattr(snapshot, "preemptions_total", 0) or 0)
        - int(getattr(previous_snapshot, "preemptions_total", 0) or 0)
    )
    if kv_usage > 0.85 and previous_snapshot is not None and preemption_delta > 0:
        add(applier.throttle_concurrency(current_max_num_seqs_hint=16, incident_id=incident_id))
    if any("prefix cache thrashing" in r for r in reasons_l):
        add(applier.flush_session_radix(session_id="current", incident_id=incident_id))
    if any("preemption storm" in r for r in reasons_l):
        add(applier.throttle_concurrency(current_max_num_seqs_hint=16, incident_id=incident_id))
    if int(getattr(snapshot, "requests_swapped", 0) or 0) > 0 or any(
        str(r).startswith("Swap active") for r in reasons
    ):
        add(applier.drain_and_recycle(incident_id=incident_id))
    return actions
