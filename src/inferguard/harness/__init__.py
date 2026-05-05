"""InferGuard v0.5 harness layer."""

from __future__ import annotations

from inferguard.harness.agent_trace import (
    AgentTracer,
    LangGraphCallback,
    LangGraphTraceCallback,
    TraceRunResult,
    framework_callback,
)
from inferguard.harness.daemon import Daemon, DaemonSnapshot, SlidingWindow
from inferguard.harness.env import EnvironmentAdapter, RigContext
from inferguard.harness.permissions import (
    AllowedReason,
    DeniedReason,
    PermissionDecision,
    PermissionPolicy,
    PermissionResult,
)
from inferguard.harness.telemetry import TelemetryClient, TelemetryState, TelemetryStatus

HARNESS_VERSION = "0.5.0"

__all__ = [
    "HARNESS_VERSION",
    "AgentTracer",
    "AllowedReason",
    "Daemon",
    "DaemonSnapshot",
    "DeniedReason",
    "EnvironmentAdapter",
    "LangGraphCallback",
    "LangGraphTraceCallback",
    "PermissionDecision",
    "PermissionPolicy",
    "PermissionResult",
    "RigContext",
    "SlidingWindow",
    "TelemetryClient",
    "TelemetryState",
    "TelemetryStatus",
    "TraceRunResult",
    "framework_callback",
]
