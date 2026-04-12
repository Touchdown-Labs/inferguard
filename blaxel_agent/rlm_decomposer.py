"""RLM decomposition wrapper with direct GMI fallback."""

from __future__ import annotations

import inspect
from typing import Any

import httpx
import structlog

log = structlog.get_logger()


class RlmDecomposer:
    """Run decomposition via rlm when available; fallback to direct GMI call."""

    async def run(self, prompt: str, model: str, api_base: str, api_key: str) -> str:
        try:
            return await self._run_via_rlm(prompt, model=model, api_base=api_base, api_key=api_key)
        except Exception as exc:
            log.info("rlm_unavailable_fallback_direct", error=str(exc))
            return await self._run_direct(prompt, model=model, api_base=api_base, api_key=api_key)

    async def _run_via_rlm(self, prompt: str, *, model: str, api_base: str, api_key: str) -> str:
        import rlm  # type: ignore

        result: Any
        if hasattr(rlm, "completion"):
            result = rlm.completion(
                prompt,
                model=model,
                api_base=api_base,
                api_key=api_key,
            )
        elif hasattr(rlm, "Agent"):
            agent = rlm.Agent(model=model, backend="openai", api_base=api_base, api_key=api_key)
            result = agent.run(prompt)
        else:
            raise RuntimeError("rlm package has no completion/Agent entry point")

        if inspect.isawaitable(result):
            result = await result
        return str(result)

    async def _run_direct(self, prompt: str, *, model: str, api_base: str, api_key: str) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{api_base.rstrip('/')}/chat/completions",
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
                                "You are InferGuard's proactive decomposition brain. "
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
        return str(message.get("content") or message.get("reasoning_content") or "")

