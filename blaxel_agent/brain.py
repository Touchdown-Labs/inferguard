"""InferGuard v6 L3 brain (Slice 2: direct GMI call, no RLM/Daytona yet)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx
import structlog

from blaxel_agent.daytona_client import DaytonaClient
from blaxel_agent.rlm_decomposer import RlmDecomposer

log = structlog.get_logger()


class InferGuardBrain:
    """Blaxel agent brain that returns proactive advisory dicts."""

    async def investigate(self, context_dict: dict[str, Any]) -> list[dict[str, Any]]:
        log.info(
            "brain_investigate_start",
            current_engine=context_dict.get("current_engine"),
            current_model=context_dict.get("current_model_name"),
            kv=(context_dict.get("current_snapshot", {}) or {}).get("kv_cache_usage"),
        )
        llm_backend = context_dict.get("llm_backend")
        if not isinstance(llm_backend, dict):
            log.warning("brain_llm_backend_missing")
            return []
        api_key = str(llm_backend.get("api_key") or "").strip()
        base_url = str(llm_backend.get("base_url") or "").strip()
        model = str(llm_backend.get("model") or "").strip()
        if not api_key or not base_url or not model:
            log.warning("brain_llm_backend_missing")
            return []

        prompt = self._build_investigation_prompt(context_dict)
        try:
            raw = await RlmDecomposer().run(
                prompt=prompt,
                model=model,
                api_base=base_url,
                api_key=api_key,
            )
        except Exception as exc:
            log.warning("brain_decomposer_failed", error=str(exc))
            raw = await self._call_gmi(prompt, base_url=base_url, api_key=api_key, model=model)
        records = self._extract_json_array(raw)
        out: list[dict[str, Any]] = []
        daytona = DaytonaClient()
        for record in records:
            normalized = self._normalize(record)
            if normalized.get("advisory_only") is not True:
                log.warning(
                    "brain_advisory_dropped_not_advisory_only",
                    record=str(record)[:240],
                )
                continue
            for action in normalized.get("recommended_safe_actions", []):
                if not isinstance(action, dict):
                    continue
                if action.get("action_type") != "recommend_compaction":
                    continue
                verdict = await daytona.run_canary(
                    action_type="recommend_compaction",
                    parameters=action.get("parameters", {}) if isinstance(action.get("parameters"), dict) else {},
                    context=context_dict,
                )
                action["canary_verdict"] = verdict.as_dict()
            out.append(normalized)
        log.info("brain_investigate_done", advisory_count=len(out))
        return out

    async def _call_gmi(self, prompt: str, *, base_url: str, api_key: str, model: str) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are InferGuard's proactive investigation brain. "
                                "Return only valid JSON arrays."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1500,
                },
            )
            response.raise_for_status()
            payload = response.json()
        message = payload.get("choices", [{}])[0].get("message", {})
        content = message.get("content") or message.get("reasoning_content") or ""
        return str(content)

    def _build_investigation_prompt(self, ctx: dict[str, Any]) -> str:
        model = ctx.get("current_model_name", "unknown")
        engine = ctx.get("current_engine", "unknown")
        window = ctx.get("window_snapshots", [])
        priors = ctx.get("prior_incidents", [])
        events = ctx.get("event_log_tail", [])
        current = ctx.get("current_snapshot", {})

        return f"""You are InferGuard's proactive investigation agent.
Your job is to anticipate KV cache inference failures AND recommend next-step remediation, whether alarms are currently firing or not.

Target engine: {engine}
Target model: {model}

You have access to:
- {len(window)} recent metric snapshots in a rolling window
- {len(priors)} semantically similar prior incidents with resolution outcomes
- {len(events)} recent events from the Redis event log
- The current snapshot

Current snapshot summary:
  kv_cache_usage: {current.get("kv_cache_usage", 0.0):.2f}
  prefix_cache_hit_rate: {current.get("prefix_cache_hit_rate", 0.0):.2f}
  requests_running: {current.get("requests_running", 0)}
  requests_waiting: {current.get("requests_waiting", 0)}
  requests_swapped: {current.get("requests_swapped", 0)}
  preemptions_total: {current.get("preemptions_total", 0)}
  ttft_avg_seconds: {current.get("ttft_avg_seconds")}

Decompose your investigation into these 4 sub-questions. The current snapshot may already show a firing alarm — if so, your job is to recommend the NEXT action, not to wait for the alarm to clear. Output advisories for both pre-alarm anticipation AND active-incident next-step recommendations.

W1 Trend analysis: Which metric slopes are rising toward their alert
   thresholds in the window? Estimate seconds until the threshold crosses.

W2 Pattern match: Does the current state match any prior resolved
   incident? If yes, which remediation worked and what MAD compaction
   threshold t would be optimal for this shape?

W3 Leading indicators: Are there pre-anomaly signals (prefix hit decay,
   VRAM slope, queue depth creep) that the reactive detector has not
   tripped yet?

W4 Compaction opportunity: Given current KV pressure and session shape,
   should we preemptively recommend AM compaction? What MAD threshold t?
   (Ramp Labs defaults: reasoning traffic t=2.0, balanced t=1.0,
   long dispersed t=-1.0. Paper: arXiv:2602.16284.)

Each advisory should describe CONCRETE next actions, not restate the current metrics.

Output ONLY a valid JSON array, no prose, matching this schema:
[
  {{
    "advisory_type": "capacity_cliff_predicted | degradation_trend | preemptive_compaction | preemptive_recycle | prior_pattern_match",
    "confidence": 0.0,
    "horizon_seconds": 0,
    "reason": "one sentence",
    "evidence": ["bullet 1", "bullet 2"],
    "recommended_safe_actions": [
      {{"action_type": "recommend_compaction", "parameters": {{"threshold_t": 1.0, "target_ratio": 0.68, "expected_overhead_s": 1.7}}}}
    ],
    "advisory_only": true
  }}
]

You MUST emit at least one advisory when any metric in the current snapshot is above its alert threshold (kv_cache_usage > 0.42, prefix_cache_hit_rate < 0.3, requests_waiting > 10, requests_swapped > 0, or preemptions_total changing). If every metric is green AND the window shows no concerning trend, you MAY return an empty array [].
"""

    def _extract_json_array(self, raw: str) -> list[dict[str, Any]]:
        text = (raw or "").strip()
        if not text:
            return []
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, dict)]

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(raw.get("id") or uuid.uuid4().hex[:12]),
            "timestamp": float(raw.get("timestamp") or time.time()),
            "advisory_type": str(raw.get("advisory_type", "degradation_trend")),
            "confidence": float(raw.get("confidence", 0.5)),
            "horizon_seconds": int(raw.get("horizon_seconds", 0) or 0),
            "reason": str(raw.get("reason", "")),
            "evidence": [str(e) for e in (raw.get("evidence") or []) if str(e).strip()][:8],
            "recommended_safe_actions": [
                dict(action)
                for action in (raw.get("recommended_safe_actions") or [])
                if isinstance(action, dict)
            ][:4],
            "advisory_only": True,
            "source": str(raw.get("source") or "blaxel_brain"),
        }
