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

    def recommend_compaction(
        self,
        session_id: str,
        threshold_t: float,
        target_ratio: float,
        expected_overhead_s: float,
        prior_outcome: str,
        incident_id: str,
    ) -> SafeAction:
        """Advisory: recommend AM (Attention Matching) KV compaction for the given session.

        Per-session surgical remediation that compacts stale trajectory KV in latent space
        via the Attention Matching algorithm (Zweiger et al., MIT, arXiv:2602.16284) with
        MAD adaptive thresholding from Ramp Labs' Latent Briefing modification.

        Reference implementation: github.com/adamzweiger/compaction (MIT licensed).
        """
        reason = (
            f"Session trajectory pressure detected — recommend AM compaction at t={threshold_t:.1f} "
            f"(expected ~{int(target_ratio * 100)}% KV reduction, ~{expected_overhead_s:.1f}s overhead). "
            f"{prior_outcome}"
        )
        return self._mk(
            "recommend_compaction",
            reason,
            {
                "session_id": session_id,
                "threshold_t": threshold_t,
                "target_ratio": target_ratio,
                "expected_overhead_s": expected_overhead_s,
                "algorithm": "attention_matching_MAD_thresholding",
                "reference_impl": "github.com/adamzweiger/compaction",
                "paper": "arXiv:2602.16284",
                "prior_outcome": prior_outcome,
            },
            incident_id,
        )


def _choose_compaction_threshold(snapshot: Any, model_name: str, reasons_l: list[str]) -> tuple[float, float, str]:
    """Choose MAD threshold `t` for AM compaction based on workload signature.

    Returns (threshold_t, expected_target_ratio, rationale).
    Mapping is Ramp Labs' Latent Briefing empirical defaults for RLM orchestrator-worker
    workloads on LongBench v2:
      - speculative reasoning / hard tasks → t=2.0 (aggressive, ~0.79 reduction)
      - short focused chat / coding        → t=1.0 (moderate, ~0.68 reduction)
      - long dispersed docs (>64K proxy)   → t=-1.0 (light,    ~0.18 reduction)
    v1 selects via observable heuristics; the MAD policy learner will later key this on
    Upstash Vector shape-matched prior outcomes.
    """
    kv_usage = float(getattr(snapshot, "kv_cache_usage", 0.0) or 0.0)
    running = int(getattr(snapshot, "requests_running", 0) or 0)
    lower_model = (model_name or "").lower()
    is_reasoning = any(kw in lower_model for kw in ("deepseek-r1", "qwen3.5", "gpt-oss", "gptoss"))
    has_thrashing = any("prefix cache thrashing" in r for r in reasons_l)
    has_kv_surge = any("kv surge" in r for r in reasons_l)

    if is_reasoning and has_thrashing and kv_usage > 0.85:
        return 2.0, 0.79, "Speculative-reasoning signature; aggressive compaction preferred."
    if running >= 10 and kv_usage > 0.85:
        return -1.0, 0.18, "High-concurrency long-context signature; light compaction preserves coverage."
    if has_kv_surge or has_thrashing or kv_usage > 0.85:
        return 1.0, 0.68, "Moderate-trajectory signature; balanced compaction."
    return 1.0, 0.54, "Default policy pending MAD learner warmup."


def decide_safe_actions(
    snapshot: Any,
    anomaly: Any,
    previous_snapshot: Any,
    model_name: str,
    incident_id: str,
    prior_compaction_outcomes: list[dict] | None = None,
) -> list[SafeAction]:
    """Rule-based mapping from anomaly signals to SAFE actions. Empty list if no action warranted.

    `prior_compaction_outcomes` is an optional list of prior incident metadata fetched from
    Upstash Vector (v5 §E.2 learning loop). When present and a matching shape is found, the
    MAD threshold is taken from the prior row instead of the heuristic default.
    """
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
    has_thrashing = any("prefix cache thrashing" in r for r in reasons_l)
    has_kv_surge = any("kv surge" in r for r in reasons_l)
    has_preemption_storm = any("preemption storm" in r for r in reasons_l)

    # A.4 / A.5 — compaction advisory (PREFERRED surgical action).
    # Fires first so the per-session surgical remediation is always visible before
    # the blunt cluster-wide levers below.
    if has_thrashing or has_kv_surge or (kv_usage > 0.85 and (has_preemption_storm or preemption_delta > 0)):
        threshold_t, target_ratio, rationale = _choose_compaction_threshold(snapshot, model_name, reasons_l)
        prior_outcome = "Cold start — no prior incidents in memory."
        # Learning loop hook: if the agent passed in prior outcomes, pick the best resolved
        # match and use its threshold. v5.1 supports the signal; the shape-matcher is v5.2.
        if prior_compaction_outcomes:
            for row in prior_compaction_outcomes:
                metadata = (row.get("metadata") if isinstance(row, dict) else None) or {}
                if metadata.get("action_type") == "recommend_compaction" and metadata.get("resolution_effective") is True:
                    threshold_t = float(metadata.get("threshold_t", threshold_t))
                    target_ratio = float(metadata.get("target_ratio", target_ratio))
                    prior_outcome = (
                        f"Prior similar incident resolved with t={threshold_t:.1f} "
                        f"(reduction {int(target_ratio * 100)}%)."
                    )
                    break
            else:
                prior_outcome = (
                    f"{len(prior_compaction_outcomes)} similar prior incidents in memory; "
                    f"no resolved compaction outcome yet — using heuristic default. ({rationale})"
                )
        else:
            prior_outcome = f"Cold start — {rationale}"
        add(
            applier.recommend_compaction(
                session_id="current",
                threshold_t=threshold_t,
                target_ratio=target_ratio,
                expected_overhead_s=1.7,
                prior_outcome=prior_outcome,
                incident_id=incident_id,
            )
        )

    # Legacy blunt levers — still emitted as safety-net fallbacks.
    if kv_usage > 0.85 and previous_snapshot is not None and preemption_delta > 0:
        add(applier.throttle_concurrency(current_max_num_seqs_hint=16, incident_id=incident_id))
    if has_thrashing:
        add(applier.flush_session_radix(session_id="current", incident_id=incident_id))
    if has_preemption_storm:
        add(applier.throttle_concurrency(current_max_num_seqs_hint=16, incident_id=incident_id))
    if int(getattr(snapshot, "requests_swapped", 0) or 0) > 0 or any(
        str(r).startswith("Swap active") for r in reasons
    ):
        add(applier.drain_and_recycle(incident_id=incident_id))
    return actions
