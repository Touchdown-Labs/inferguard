"""InferGuard agent orchestration loop."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncGenerator

import httpx
import structlog

from inferguard.config import InferGuardConfig
from inferguard.diagnosis import DiagnosisResult, diagnose
from inferguard.memory import Incident, MemoryStore, UpstashRedis, UpstashVector
from inferguard.metrics import (
    MetricSnapshot,
    detect_anomalies,
    detect_rlm_anomalies,
    get_effective_kv_threshold,
)
from inferguard.remediation import generate_fix
from inferguard.safe_actions import decide_safe_actions

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
            return self._with_proof_level({"status": "healthy", "metrics": snapshot.as_dict(), "safe_actions": []})

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

        safe_actions = decide_safe_actions(
            snapshot,
            anomaly,
            previous_snapshot,
            self.model_name,
            incident_id,
        )
        for action in safe_actions:
            await self.memory.log_event("safe_action", action.as_dict())

        task = asyncio.create_task(self._check_resolution(incident_id, delay_seconds=180))
        self._track_background_task(task)

        return self._with_proof_level(
            {
                "status": "anomaly_detected",
                "anomaly": anomaly.as_dict(),
                "metrics": snapshot.as_dict(),
                "diagnosis": diagnosis.as_dict(),
                "remediation": remediation.as_dict(),
                "safe_actions": [a.as_dict() for a in safe_actions],
            }
        )

    async def watch(self, max_cycles: int = 0) -> AsyncGenerator[dict[str, Any], None]:
        cycle = 0
        while max_cycles == 0 or cycle < max_cycles:
            cycle += 1
            report = await self.run_once()
            report["cycle"] = cycle
            yield report
            await asyncio.sleep(self.config.poll_interval_seconds)

    async def _check_resolution(self, incident_id: str, delay_seconds: int = 180) -> None:
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

    return DiagnosisResult(
        failure_mode=failure_mode,
        root_cause=(
            f"Rule-based fallback diagnosis for {snapshot.engine} because no LLM configuration is available."
        ),
        confidence=0.0,
        recommended_action="Apply the generated remediation suggestion and verify with a follow-up scrape.",
        raw_response="",
    )
