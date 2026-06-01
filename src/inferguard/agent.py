"""InferGuard agent orchestration loop."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncGenerator

import httpx
import structlog

from inferguard.brain_client import (
    BrainClient,
    InvestigationContext,
    ProactiveAdvisory,
)
from inferguard.config import InferGuardConfig
from inferguard.diagnosis import DiagnosisResult, diagnose
from inferguard.memory import Incident, MemoryStore, UpstashRedis, UpstashVector
from inferguard.metrics import (
    MetricSnapshot,
    detect_anomalies,
    detect_rlm_anomalies,
    get_effective_kv_threshold,
)
from inferguard.executor import ActionExecutor
from inferguard.remediation import generate_fix
from inferguard.safe_actions import SafeAction, decide_safe_actions

log = structlog.get_logger()


class InferGuardAgent:
    """Standalone-first agent loop for scrape → detect → diagnose → remember."""

    def __init__(self, config: InferGuardConfig, model_name: str = ""):
        self.config = config
        self.model_name = model_name
        self.baseline_ttft: float | None = None
        self._last_preemptions: int | None = None
        self._last_snapshot: MetricSnapshot | None = None
        self._proof_level = "unknown"
        self._proof_level_checked = False
        self._pending_resolution_tasks: set[asyncio.Task[Any]] = set()

        redis = UpstashRedis(config.redis_url, config.redis_token) if config.has_redis else None
        vector = UpstashVector(config.vector_url, config.vector_token) if config.has_vector else None
        self.memory = MemoryStore(redis, vector)

        self._brain_client = BrainClient(config=config, memory=self.memory)
        self._proactive_cycle_every = self.config.proactive_cycle_every
        self._reactive_cycle_counter = 0
        self._last_proactive_advisories: list[dict[str, Any]] = []
        self._proactive_task: asyncio.Task[Any] | None = None
        self._replay_baseline: Any = None
        self._replay_baseline_captured = False
        self._executor = ActionExecutor(config) if config.has_actuation else None

    async def _scrape(self) -> MetricSnapshot:
        snapshot = await MetricSnapshot.scrape_endpoint(self.config.target_endpoint)
        if not snapshot.error:
            if not self.model_name:
                self.model_name = await self._detect_model_name()
            if not self._proof_level_checked:
                self._proof_level = await self._detect_proof_level()
                self._proof_level_checked = True
        return snapshot

    async def _detect_model_name(self) -> str:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.config.target_endpoint.rstrip('/')}/v1/models")
                response.raise_for_status()
                data = response.json()
            models = data.get("data", [])
            if isinstance(models, list) and models:
                first = models[0]
                if isinstance(first, dict):
                    return str(first.get("id", ""))
        except Exception:
            return ""
        return ""

    async def _detect_proof_level(self) -> str:
        health_url = f"{self.config.target_endpoint.rstrip('/')}/health"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(health_url)
                if response.status_code != 200:
                    log.debug("proof_level_detection_non_200", url=health_url, status_code=response.status_code)
                    return "unknown"
                payload = response.json()
        except Exception as exc:
            log.debug("proof_level_detection_failed", url=health_url, error=str(exc))
            return "unknown"

        if isinstance(payload, dict) and payload.get("mock") is True:
            return "mock"
        return "live"

    async def _diagnose(self, snapshot: MetricSnapshot, reasons: list[str]) -> DiagnosisResult:
        if not self.config.has_llm:
            return _fallback_diagnosis(snapshot, reasons)

        similar = await self.memory.find_similar_incidents(" ".join(reasons), top_k=3)
        return await diagnose(
            metrics=snapshot.as_dict(),
            anomaly_reasons=reasons,
            past_incidents=similar,
            llm_base_url=self.config.llm_base_url,
            llm_api_key=self.config.llm_api_key,
            llm_model=self.config.llm_model,
            model_name=self.model_name,
        )

    def _track_background_task(self, task: asyncio.Task[Any]) -> None:
        self._pending_resolution_tasks.add(task)

        def _done(completed: asyncio.Task[Any]) -> None:
            self._pending_resolution_tasks.discard(completed)
            try:
                completed.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # pragma: no cover - safety/logging path
                log.warning("resolution_task_failed", error=str(exc))

        task.add_done_callback(_done)

    async def run_once(self) -> dict[str, Any]:
        snapshot = await self._scrape()
        if snapshot.error:
            return self._with_proof_level({"status": "error", "error": snapshot.error})

        await self.memory.store_snapshot(snapshot.as_dict())

        if self.baseline_ttft is None and snapshot.ttft_avg_seconds is not None:
            self.baseline_ttft = snapshot.ttft_avg_seconds

        effective_threshold = get_effective_kv_threshold(
            self.model_name,
            self.config.kv_alert_threshold,
        )
        anomaly = detect_anomalies(
            snapshot,
            baseline_ttft=self.baseline_ttft,
            previous_preemptions=self._last_preemptions,
            kv_threshold=effective_threshold,
            ttft_multiplier=self.config.ttft_alert_multiplier,
        )

        rlm_reasons = detect_rlm_anomalies(snapshot, self._last_snapshot, self.model_name)
        if rlm_reasons:
            anomaly.reasons.extend(rlm_reasons)
            anomaly.is_anomaly = True
            if anomaly.severity == "none":
                anomaly.severity = "warning"

        previous_snapshot = self._last_snapshot
        self._last_preemptions = snapshot.preemptions_total
        self._last_snapshot = snapshot

        if not anomaly.is_anomaly:
            await self.memory.save_state(
                {
                    "baseline_ttft": self.baseline_ttft,
                    "last_preemptions": self._last_preemptions,
                    "model_name": self.model_name,
                }
            )
            baseline_validation = None
            if self.config.has_replay and not self._replay_baseline_captured:
                baseline_validation = await self._capture_replay_baseline()
            report = {
                "status": "healthy",
                "metrics": snapshot.as_dict(),
                "safe_actions": [],
                "proactive_advisories": self._drain_proactive_advisories(),
            }
            if baseline_validation is not None:
                report["replay_validation"] = baseline_validation
            return self._with_proof_level(report)

        diagnosis = await self._diagnose(snapshot, anomaly.reasons)
        remediation = generate_fix(
            diagnosis.failure_mode,
            snapshot.engine,
            snapshot.as_dict(),
            diagnosis.recommended_action,
            self.model_name,
        )

        incident_id = f"inc-{int(time.time() * 1000)}"
        incident = Incident(
            id=incident_id,
            timestamp=time.time(),
            engine=snapshot.engine,
            anomaly_reasons=list(anomaly.reasons),
            severity=anomaly.severity,
            metrics_snapshot=snapshot.as_dict(),
            diagnosis=diagnosis.root_cause,
            recommended_fix=remediation.launch_command,
        )

        await self.memory.store_incident(incident)
        await self.memory.save_incident_metrics(incident_id, snapshot.as_dict())
        await self.memory.save_state(
            {
                "baseline_ttft": self.baseline_ttft,
                "last_preemptions": self._last_preemptions,
                "model_name": self.model_name,
                "last_incident_id": incident_id,
            }
        )

        prior_compaction_outcomes: list[dict[str, Any]] = []
        try:
            prior_compaction_outcomes = await self.memory.find_similar_incidents(
                f"KV compaction session trajectory {self.model_name} {' '.join(anomaly.reasons)}",
                top_k=3,
            )
        except Exception as exc:  # pragma: no cover - network/degraded path
            log.debug("prior_compaction_lookup_failed", error=str(exc))

        safe_actions = decide_safe_actions(
            snapshot,
            anomaly,
            previous_snapshot,
            self.model_name,
            incident_id,
            prior_compaction_outcomes=prior_compaction_outcomes,
        )
        for action in safe_actions:
            if self._executor is not None and self._executor.is_eligible(action):
                baseline_for_action = snapshot
                action = await self._executor.execute(action)
                await self.memory.log_event(
                    "action_execution",
                    {
                        "action_id": action.id,
                        "action_type": action.action_type,
                        "incident_id": incident_id,
                        "applied": action.applied,
                        "error": action.execution_error,
                        "mode": self.config.actuation_mode,
                    },
                )
                if action.applied:
                    task = asyncio.create_task(
                        self._verify_action(action, incident_id, baseline_for_action)
                    )
                    self._track_background_task(task)
            await self.memory.log_event("safe_action", action.as_dict())

        # v6: when an anomaly fires in a one-shot scan context, proactively
        # invoke the brain inline so /api/scan reports include advisories.
        # In the watch loop this path still fires every N cycles from watch(),
        # so we guard with a "buffer is empty" check to avoid duplicating work.
        if self.config.brain_mode == "local" and not self._last_proactive_advisories:
            try:
                await asyncio.wait_for(self.proactive_cycle(), timeout=45.0)
            except asyncio.TimeoutError:
                log.info("proactive_inline_timeout")
            except Exception as exc:
                log.debug("proactive_inline_failed", error=str(exc))

        replay_validation = None
        if self.config.has_replay:
            try:
                replay_validation = await asyncio.wait_for(
                    self._replay_validate(incident_id), timeout=300.0
                )
            except asyncio.TimeoutError:
                log.info("replay_validation_timeout", incident_id=incident_id)
            except Exception as exc:
                log.debug("replay_validation_failed", incident_id=incident_id, error=str(exc))

        canary_observed = self._extract_canary_outcome_from_advisories(self._last_proactive_advisories)
        if isinstance(replay_validation, dict) and replay_validation.get("verdict"):
            await self.memory.update_incident_resolution(
                incident_id,
                replay_validation.get("verdict") == "improved",
                improvements=replay_validation.get("improvements", []),
                regressions=replay_validation.get("regressions", []),
                observed_kv_reduction=abs(float(replay_validation.get("cache_usage_delta", 0.0))),
                action_type="replay_validation",
            )
        else:
            task = asyncio.create_task(
                self._check_resolution(
                    incident_id,
                    delay_seconds=180,
                    observed_kv_reduction=canary_observed.get("observed_kv_reduction"),
                    observed_accuracy_delta_pp=canary_observed.get("observed_accuracy_delta_pp"),
                    observed_overhead_s=canary_observed.get("observed_overhead_s"),
                    action_type=canary_observed.get("action_type"),
                )
            )
            self._track_background_task(task)

        report = {
            "status": "anomaly_detected",
            "anomaly": anomaly.as_dict(),
            "metrics": snapshot.as_dict(),
            "diagnosis": diagnosis.as_dict(),
            "remediation": remediation.as_dict(),
            "safe_actions": [a.as_dict() for a in safe_actions],
            "proactive_advisories": self._drain_proactive_advisories(),
        }
        if replay_validation is not None:
            report["replay_validation"] = replay_validation
        return self._with_proof_level(report)

    def _drain_proactive_advisories(self) -> list[dict[str, Any]]:
        advisories = list(self._last_proactive_advisories)
        self._last_proactive_advisories = []
        return advisories

    def _extract_canary_outcome_from_advisories(
        self, advisories: list[dict[str, Any]]
    ) -> dict[str, Any]:
        for advisory in advisories:
            if not isinstance(advisory, dict):
                continue
            for action in advisory.get("recommended_safe_actions", []):
                if not isinstance(action, dict):
                    continue
                verdict = action.get("canary_verdict")
                if not isinstance(verdict, dict):
                    continue
                return {
                    "observed_kv_reduction": verdict.get("observed_kv_reduction"),
                    "observed_accuracy_delta_pp": verdict.get("observed_accuracy_delta_pp"),
                    "observed_overhead_s": verdict.get("observed_overhead_s"),
                    "action_type": action.get("action_type"),
                }
        return {}

    def _build_replay_validator(self) -> Any:
        from inferguard.replay_validation import ReplayValidator

        max_sessions = self.config.replay_max_sessions or None
        return ReplayValidator(
            export_file=self.config.replay_export_file,
            target_endpoint=self.config.target_endpoint,
            model_id=self.model_name,
            max_concurrency=self.config.replay_max_concurrency,
            max_sessions=max_sessions,
            runtime_stack_id=self.config.replay_runtime_stack_id or None,
            skip_tokenizer=self.config.replay_skip_tokenizer,
        )

    async def _capture_replay_baseline(self) -> dict[str, Any] | None:
        if not self.model_name:
            return None
        try:
            validator = self._build_replay_validator()
            baseline = await asyncio.wait_for(
                validator.run_replay("baseline", phase="baseline"), timeout=300.0
            )
        except Exception as exc:
            log.debug("replay_baseline_capture_failed", error=str(exc))
            return None
        self._replay_baseline = baseline
        self._replay_baseline_captured = True
        await self.memory.log_event("replay_validation", baseline.as_dict())
        return baseline.as_dict()

    async def _replay_validate(self, incident_id: str) -> dict[str, Any] | None:
        if not self.model_name:
            return None
        validator = self._build_replay_validator()
        post = await validator.run_replay(incident_id, phase="post_remediation")
        await self.memory.log_event("replay_validation", post.as_dict())
        if self._replay_baseline is None:
            return post.as_dict()
        comparison = validator.compare(self._replay_baseline, post)
        await self.memory.log_event("replay_comparison", comparison.as_dict())
        return comparison.as_dict()

    async def _verify_action(
        self,
        action: SafeAction,
        incident_id: str,
        baseline_snapshot: MetricSnapshot,
    ) -> None:
        if self._executor is None:
            return
        try:
            await self._executor.verify(action, self._scrape, baseline_snapshot=baseline_snapshot)
            await self.memory.log_event(
                "action_verification",
                {
                    "action_id": action.id,
                    "action_type": action.action_type,
                    "incident_id": incident_id,
                    "verification_result": action.verification_result,
                },
            )
            if action.verification_result in {"improved", "regressed"}:
                await self.memory.update_incident_resolution(
                    incident_id,
                    action.verification_result == "improved",
                    improvements=[f"{action.action_type}_applied"] if action.verification_result == "improved" else [],
                    regressions=[f"{action.action_type}_regressed"] if action.verification_result == "regressed" else [],
                    action_type=action.action_type,
                )
        except Exception as exc:
            log.warning("action_verification_failed", action_id=action.id, error=str(exc))

    async def proactive_cycle(self) -> list[ProactiveAdvisory]:
        """Run one proactive investigation cycle via BrainClient."""
        if self._last_snapshot is None or self._last_snapshot.error:
            return []

        window_snapshots: list[dict[str, Any]] = []
        prior_incidents: list[dict[str, Any]] = []
        event_log_tail: list[dict[str, Any]] = []
        try:
            window_snapshots = await self.memory.load_window_snapshots(window_seconds=600)
        except Exception as exc:
            log.debug("proactive_window_load_failed", error=str(exc))
        try:
            prior_incidents = await self.memory.find_similar_incidents(
                f"KV cache inference health {self.model_name}", top_k=10,
            )
        except Exception as exc:
            log.debug("proactive_prior_incidents_failed", error=str(exc))
        try:
            event_log_tail = await self.memory.load_event_log_tail(count=50)
        except Exception as exc:
            log.debug("proactive_event_tail_failed", error=str(exc))

        ctx = InvestigationContext(
            window_snapshots=window_snapshots,
            prior_incidents=prior_incidents,
            event_log_tail=event_log_tail,
            current_model_name=self.model_name or "unknown",
            current_engine=self._last_snapshot.engine,
            current_snapshot=self._last_snapshot.as_dict(),
            llm_backend={
                "base_url": self.config.llm_base_url,
                "api_key": self.config.llm_api_key,
                "model": self.config.llm_model,
            },
        )
        advisories = await self._brain_client.request_investigation(ctx)
        for advisory in advisories:
            try:
                await self.memory.log_event("proactive_advisory", advisory.as_dict())
            except Exception as exc:
                log.debug("proactive_advisory_log_failed", error=str(exc))
        self._last_proactive_advisories = [a.as_dict() for a in advisories]
        return advisories

    async def watch(self, max_cycles: int = 0) -> AsyncGenerator[dict[str, Any], None]:
        cycle = 0
        while max_cycles == 0 or cycle < max_cycles:
            cycle += 1
            report = await self.run_once()
            report["cycle"] = cycle
            yield report

            self._reactive_cycle_counter += 1
            if (
                self._proactive_cycle_every > 0
                and self._reactive_cycle_counter % self._proactive_cycle_every == 0
                and (self._proactive_task is None or self._proactive_task.done())
            ):
                self._proactive_task = asyncio.create_task(self.proactive_cycle())
                self._track_background_task(self._proactive_task)

            await asyncio.sleep(self.config.poll_interval_seconds)

    async def _check_resolution(
        self,
        incident_id: str,
        delay_seconds: int = 180,
        *,
        observed_kv_reduction: float | None = None,
        observed_accuracy_delta_pp: float | None = None,
        observed_overhead_s: float | None = None,
        action_type: str | None = None,
    ) -> None:
        await asyncio.sleep(delay_seconds)
        try:
            snapshot = await self._scrape()
            original_metrics = await self.memory.load_incident_metrics(incident_id)
            if snapshot.error or not original_metrics:
                return

            improvements: list[str] = []
            regressions: list[str] = []

            original_kv = original_metrics.get("kv_cache_usage")
            if isinstance(original_kv, (int, float)):
                kv_delta = snapshot.kv_cache_usage - float(original_kv)
                if kv_delta < -0.1:
                    improvements.append("kv_improved")
                elif kv_delta > 0.05:
                    regressions.append("kv_worsened")

            original_ttft = original_metrics.get("ttft_avg_seconds")
            if isinstance(original_ttft, (int, float)) and snapshot.ttft_avg_seconds is not None:
                if snapshot.ttft_avg_seconds < float(original_ttft) * 0.7:
                    improvements.append("ttft_improved")
                elif snapshot.ttft_avg_seconds > float(original_ttft) * 1.1:
                    regressions.append("ttft_worsened")

            original_queue = original_metrics.get("requests_waiting", 0)
            if isinstance(original_queue, (int, float)) and float(original_queue) > 5 and snapshot.requests_waiting < 3:
                improvements.append("queue_drained")

            resolved = bool(improvements) and not regressions
            await self.memory.update_incident_resolution(
                incident_id,
                resolved,
                improvements=improvements,
                regressions=regressions,
                observed_kv_reduction=observed_kv_reduction,
                observed_accuracy_delta_pp=observed_accuracy_delta_pp,
                observed_overhead_s=observed_overhead_s,
                action_type=action_type,
            )
        except Exception as exc:  # pragma: no cover - safety/logging path
            log.warning("resolution_check_failed", incident_id=incident_id, error=str(exc))

    async def shutdown(self) -> None:
        pending = list(self._pending_resolution_tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def _with_proof_level(self, report: dict[str, Any]) -> dict[str, Any]:
        report["proof_level"] = self._proof_level
        return report


def _fallback_diagnosis(snapshot: MetricSnapshot, reasons: list[str]) -> DiagnosisResult:
    joined = " ".join(reasons).lower()

    if "kv cache" in joined:
        failure_mode = "kv_saturation"
    elif "prefix cache" in joined:
        failure_mode = "prefix_cache_miss"
    elif "queue depth" in joined:
        failure_mode = "queue_backup"
    elif "preemption" in joined:
        failure_mode = "preemption_storm"
    elif "swap" in joined:
        failure_mode = "swap_thrash"
    elif "ttft" in joined:
        failure_mode = "ttft_regression"
    else:
        failure_mode = "unknown"

    kv_usage = float(getattr(snapshot, "kv_cache_usage", 0.0) or 0.0)
    if failure_mode in {"preemption_storm"} or kv_usage > 0.95:
        risk_level = "high"
        actuation_recommendation = "manual_review"
    elif failure_mode in {"queue_backup", "ttft_regression", "kv_saturation"}:
        risk_level = "medium"
        actuation_recommendation = "safe_to_actuate"
    else:
        risk_level = "low"
        actuation_recommendation = "safe_to_actuate"

    return DiagnosisResult(
        failure_mode=failure_mode,
        root_cause=(
            f"Rule-based fallback diagnosis for {snapshot.engine} because no LLM configuration is available."
        ),
        confidence=0.0,
        recommended_action="Apply the generated remediation suggestion and verify with a follow-up scrape.",
        raw_response="",
        risk_level=risk_level,
        actuation_recommendation=actuation_recommendation,
    )
