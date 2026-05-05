"""Dataclasses and schema constants for InferGuard engine launch artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

COMMAND_SCHEMA_VERSION = "inferguard-launch-command/v1"
HEALTHCHECK_SCHEMA_VERSION = "inferguard-healthcheck/v1"
ENGINE_VERSION_SCHEMA_VERSION = "inferguard-engine-version/v1"
OUTCOME_SCHEMA_VERSION = "inferguard-launch-outcome/v1"


@dataclass(frozen=True)
class LaunchCommand:
    engine: str
    argv: list[str]
    env: dict[str, str]
    cwd: str
    started_at: str
    model_path: str | None
    external: bool
    host: str
    port: int
    endpoint: str | None = None
    warnings: list[str] = field(default_factory=list)
    schema_version: str = field(default=COMMAND_SCHEMA_VERSION, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "engine": self.engine,
            "argv": list(self.argv),
            "env": dict(sorted(self.env.items())),
            "cwd": self.cwd,
            "started_at": self.started_at,
            "model_path": self.model_path,
            "external": self.external,
            "host": self.host,
            "port": self.port,
            "endpoint": self.endpoint,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class HealthcheckResult:
    endpoint: str
    model_id: str
    first_probe_at: str
    ready_at: str | None
    ready_after_seconds: float
    metrics_endpoint_reachable: bool
    openai_models_endpoint_reachable: bool
    canary_completion: dict[str, Any] | None
    status: str
    failure_reason: str | None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    lmcache_metrics_present: bool | None = None
    claim_status: str = "measured"
    schema_version: str = field(default=HEALTHCHECK_SCHEMA_VERSION, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "endpoint": self.endpoint,
            "model_id": self.model_id,
            "first_probe_at": self.first_probe_at,
            "ready_at": self.ready_at,
            "ready_after_seconds": self.ready_after_seconds,
            "metrics_endpoint_reachable": self.metrics_endpoint_reachable,
            "openai_models_endpoint_reachable": self.openai_models_endpoint_reachable,
            "canary_completion": self.canary_completion,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "warnings": list(self.warnings),
            "lmcache_metrics_present": self.lmcache_metrics_present,
            "claim_status": self.claim_status,
            "attempts": list(self.attempts),
        }


@dataclass(frozen=True)
class LaunchOutcome:
    command: LaunchCommand
    healthcheck: HealthcheckResult
    engine_version: dict[str, Any]
    output_dir: str
    pid: int | None
    return_code: int
    healthcheck_ms: float
    schema_version: str = field(default=OUTCOME_SCHEMA_VERSION, init=False)

    @property
    def status(self) -> str:
        return self.healthcheck.status

    def summary_line(self) -> str:
        first_token_ts = "None"
        canary = self.healthcheck.canary_completion
        if isinstance(canary, dict) and canary.get("first_token_ts"):
            first_token_ts = str(canary["first_token_ts"])
        return (
            "inferguard launch-engine: "
            f"engine={self.command.engine} "
            f"status={self.status} "
            f"pid={self.pid if self.pid is not None else 'None'} "
            f"port={self.command.port} "
            f"healthcheck_ms={self.healthcheck_ms:.3f} "
            f"first_token_ts={first_token_ts}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "command": self.command.to_dict(),
            "healthcheck": self.healthcheck.to_dict(),
            "engine_version": dict(self.engine_version),
            "output_dir": self.output_dir,
            "pid": self.pid,
            "return_code": self.return_code,
            "healthcheck_ms": self.healthcheck_ms,
            "status": self.status,
        }
