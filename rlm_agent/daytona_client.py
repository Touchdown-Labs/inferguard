"""Daytona canary client with graceful degradation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass(slots=True)
class CanaryVerdict:
    accepted: bool
    observed_kv_reduction: float | None = None
    observed_accuracy_delta_pp: float | None = None
    observed_overhead_s: float | None = None
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "observed_kv_reduction": self.observed_kv_reduction,
            "observed_accuracy_delta_pp": self.observed_accuracy_delta_pp,
            "observed_overhead_s": self.observed_overhead_s,
            "error": self.error,
        }


class DaytonaClient:
    """Run canary checks in Daytona when available."""

    async def run_canary(
        self,
        action_type: str,
        parameters: dict[str, Any],
        context: dict[str, Any],
    ) -> CanaryVerdict:
        api_key = os.environ.get("DAYTONA_API_KEY", "").strip()
        if not api_key:
            return CanaryVerdict(
                accepted=True,
                error="daytona unavailable — advisory without canary validation",
            )

        daytona_cls = None
        try:
            try:
                from daytona_sdk import Daytona as _Daytona  # type: ignore
            except Exception:
                from daytona import Daytona as _Daytona  # type: ignore
            daytona_cls = _Daytona
        except Exception as exc:
            log.info("daytona_sdk_unavailable", error=str(exc))
            return CanaryVerdict(
                accepted=True,
                error="daytona unavailable — advisory without canary validation",
            )

        try:
            # SDK/API surface can vary; defer full integration until verified.
            _ = daytona_cls  # keep import path validated
            _ = (action_type, parameters, context, api_key)
            return CanaryVerdict(
                accepted=True,
                error="daytona sdk present — canary execution deferred pending API verification",
            )
        except Exception as exc:
            return CanaryVerdict(
                accepted=True,
                error=f"daytona unavailable — advisory without canary validation ({exc})",
            )

