"""Controlled safe-action execution for InferGuard."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

import httpx

from inferguard.config import InferGuardConfig
from inferguard.safe_actions import SafeAction


class ActionExecutor:
    def __init__(self, config: InferGuardConfig):
        self.config = config
        self._allowlist = set(config.actuation_allowlist)

    def is_eligible(self, action: SafeAction) -> bool:
        return (
            action.action_type in self._allowlist
            and self.config.actuation_mode in {"dry_run", "live"}
        )

    async def execute(self, action: SafeAction) -> SafeAction:
        if not self.is_eligible(action):
            return action

        action.advisory_only = False
        action.attempted = True
        payload = {
            "action_type": action.action_type,
            "parameters": dict(action.parameters),
            "incident_id": action.incident_id,
            "inferguard_action_id": action.id,
        }

        if self.config.actuation_mode == "dry_run":
            action.applied = False
            action.execution_error = "dry_run"
            return action

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.config.actuation_endpoint, json=payload)
                response.raise_for_status()
                body = response.json()
        except Exception as exc:
            action.applied = False
            action.execution_error = str(exc)
            return action

        accepted = bool(body.get("accepted", False)) if isinstance(body, dict) else False
        action.applied = accepted
        action.execution_error = "" if accepted else str((body or {}).get("error", "rejected"))
        return action

    async def verify(
        self,
        action: SafeAction,
        scrape_fn: Callable[[], Awaitable[Any]],
        *,
        baseline_snapshot: Any | None = None,
    ) -> SafeAction:
        await asyncio.sleep(self.config.actuation_verify_delay_seconds)
        try:
            current = await scrape_fn()
        except Exception:
            action.verified = True
            action.verification_result = "error"
            return action
        if getattr(current, "error", None):
            action.verified = True
            action.verification_result = "error"
            return action

        action.verified = True
        if action.action_type == "throttle_concurrency" and baseline_snapshot is not None:
            current_kv = float(getattr(current, "kv_cache_usage", 0.0) or 0.0)
            before_kv = float(getattr(baseline_snapshot, "kv_cache_usage", 0.0) or 0.0)
            current_running = int(getattr(current, "requests_running", 0) or 0)
            before_running = int(getattr(baseline_snapshot, "requests_running", 0) or 0)
            if current_kv < before_kv - 0.05 or current_running < before_running:
                action.verification_result = "improved"
            elif current_kv > before_kv + 0.05:
                action.verification_result = "regressed"
            else:
                action.verification_result = "unchanged"
            return action

        action.verification_result = "unchanged"
        return action
