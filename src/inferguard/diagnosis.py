"""GMI Cloud-backed diagnosis of inference engine anomalies.

InferGuard uses GMI Cloud's OpenAI-compatible `/v1/chat/completions` contract
for structured diagnosis when diagnosis credentials are configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json

import httpx


@dataclass(slots=True)
class DiagnosisResult:
    failure_mode: str
    root_cause: str
    confidence: float
    recommended_action: str
    raw_response: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "failure_mode": self.failure_mode,
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "recommended_action": self.recommended_action,
            "raw_response": self.raw_response,
        }


SYSTEM_PROMPT = """You are an inference engine diagnostic expert.

You analyze Prometheus metrics from vLLM and SGLang deployments running GPT-OSS,
DeepSeek-R1, or Qwen3.5 model families on H100/H200/B200 GPUs.

Return JSON with exactly:
{
  "failure_mode": "kv_saturation" | "prefix_cache_miss" | "queue_backup" |
                  "preemption_storm" | "swap_thrash" | "ttft_regression" |
                  "unknown",
  "root_cause": "short explanation",
  "confidence": 0.0,
  "recommended_action": "specific operator action"
}

Model-specific interpretation matters:
- DeepSeek-R1 MLA compresses apparent KV pressure.
- Qwen3.5 hybrid models can under-report pressure in standard KV metrics.
- GPT-OSS follows more standard GQA-style interpretation.

Engine-specific recommendations should use vLLM or SGLang flags only.
"""


async def diagnose(
    metrics: dict[str, Any],
    anomaly_reasons: list[str],
    past_incidents: list[dict[str, Any]],
    llm_base_url: str,
    llm_api_key: str,
    llm_model: str,
    model_name: str = "",
) -> DiagnosisResult:
    """Call the GMI Cloud chat endpoint for structured diagnosis.

    `llm_base_url` should be the GMI Cloud API base URL, e.g.
    `https://api.gmi-serving.com/v1`.
    """

    user_parts = []
    if model_name:
        user_parts.append(f"Model being monitored: {model_name}")
        user_parts.append("")

    user_parts.extend(
        [
            "Current metrics:",
            json.dumps(metrics, indent=2, default=str),
            "",
            "Anomaly triggers:",
            *[f"- {reason}" for reason in anomaly_reasons],
        ]
    )

    if past_incidents:
        user_parts.append("")
        user_parts.append(f"Similar past incidents ({len(past_incidents)}):")
        for index, incident in enumerate(past_incidents, start=1):
            metadata = incident.get("metadata", {})
            user_parts.append(f"Incident {index} (similarity: {incident.get('score', 0):.2f})")
            user_parts.append(f"  Diagnosis: {metadata.get('diagnosis', 'N/A')}")
            user_parts.append(f"  Fix applied: {metadata.get('recommended_fix', 'N/A')}")
            user_parts.append(f"  Fix worked: {metadata.get('resolution_effective', 'unknown')}")

    headers = {
        "Authorization": f"Bearer {llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(user_parts)},
        ],
        "temperature": 0.2,
        "max_tokens": 2000,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{llm_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            raw = message.get("content") or message.get("reasoning_content") or ""
    except Exception as exc:
        return DiagnosisResult(
            failure_mode="unknown",
            root_cause=f"LLM call failed: {exc}",
            confidence=0.0,
            recommended_action="Manual investigation required.",
            raw_response=str(exc),
        )

    parsed = _parse_json_response(raw)
    if parsed is None:
        return DiagnosisResult(
            failure_mode="unknown",
            root_cause=raw[:200],
            confidence=0.3,
            recommended_action="Could not parse structured diagnosis. See raw response.",
            raw_response=raw,
        )

    return DiagnosisResult(
        failure_mode=str(parsed.get("failure_mode", "unknown")),
        root_cause=str(parsed.get("root_cause", "")),
        confidence=float(parsed.get("confidence", 0.0)),
        recommended_action=str(parsed.get("recommended_action", "")),
        raw_response=raw,
    )


def _parse_json_response(raw: str) -> dict[str, Any] | None:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None
