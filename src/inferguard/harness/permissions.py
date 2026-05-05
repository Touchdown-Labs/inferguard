"""Permission decisions for InferGuard harness operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit


class PermissionDecision(StrEnum):
    """Warp-shaped high-level decision: ``Allowed`` or ``Denied``."""

    ALLOWED = "Allowed"
    DENIED = "Denied"


class AllowedReason(StrEnum):
    """Allowed reason codes mirrored from the Warp study."""

    DISPATCHED = "Dispatched"
    EXPLICITLY_ALLOWLISTED = "ExplicitlyAllowlisted"
    IS_READ_ONLY_AND_SETTING_ENABLED = "IsReadOnlyAndSettingEnabled"
    AGENT_DECIDED = "AgentDecided"
    ALWAYS_ALLOWED = "AlwaysAllowed"
    RUN_TO_COMPLETION = "RunToCompletion"


class DeniedReason(StrEnum):
    """Denied reason codes mirrored from the Warp study."""

    AUTONOMY_FORCE_DISABLED = "AutonomyForceDisabled"
    ALWAYS_ASK_ENABLED = "AlwaysAskEnabled"
    EXPLICITLY_DENYLISTED = "ExplicitlyDenylisted"
    CONTAINS_DESTRUCTIVE_OPERATION = "ContainsDestructiveOperation"
    INCONCLUSIVE = "Inconclusive"
    AGENT_DECIDED = "AgentDecided"
    PROTECTED_RESOURCE = "ProtectedResource"


PROTECTED_RESOURCE_MARKERS = (
    "production model serving process",
    "production routing rule",
    "customer-facing api endpoint",
    "prod-router",
    "prod-ingress",
    "model-server-prod",
)
DESTRUCTIVE_VERBS = (
    "rm -rf",
    "kubectl delete",
    "terraform destroy",
    "DROP TABLE",
    "truncate table",
)
UNSPECIFIED_IPV4_HOST = ".".join(("0", "0", "0", "0"))
WILDCARD_BIND_HOSTS = {"", UNSPECIFIED_IPV4_HOST, "::"}


@dataclass(frozen=True)
class PermissionResult:
    """A typed permission result with a human-readable explanation."""

    decision: PermissionDecision
    reason: AllowedReason | DeniedReason
    message: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision is PermissionDecision.ALLOWED

    def raise_if_denied(self) -> None:
        if not self.allowed:
            raise PermissionError(f"{self.reason.value}: {self.message}")


class PermissionPolicy:
    """Small gate used by harness code before filesystem or network operations."""

    def __init__(
        self,
        *,
        allow_network: bool = False,
        allow_filesystem: bool = True,
        allowlist_hosts: set[str] | None = None,
        denylist_hosts: set[str] | None = None,
        protected_resources: tuple[str, ...] = PROTECTED_RESOURCE_MARKERS,
    ) -> None:
        self.allow_network = allow_network
        self.allow_filesystem = allow_filesystem
        self.allowlist_hosts = allowlist_hosts or {"127.0.0.1", "localhost", "::1"}
        self.denylist_hosts = denylist_hosts or set()
        self.protected_resources = protected_resources

    def check_network(self, url: str, *, opted_in: bool = False) -> PermissionResult:
        host = urlsplit(url).hostname or ""
        if host in self.denylist_hosts:
            return deny(DeniedReason.EXPLICITLY_DENYLISTED, f"network host denied: {host}")
        if self._is_protected(url):
            return deny(DeniedReason.PROTECTED_RESOURCE, f"protected network resource: {url}")
        if host in self.allowlist_hosts:
            return allow(AllowedReason.IS_READ_ONLY_AND_SETTING_ENABLED, f"loopback host: {host}")
        if self.allow_network or opted_in:
            return allow(AllowedReason.EXPLICITLY_ALLOWLISTED, f"network host allowed: {host}")
        return deny(
            DeniedReason.ALWAYS_ASK_ENABLED, f"outbound network requires explicit opt-in: {url}"
        )

    def check_bind(self, host: str, port: int, *, opted_in: bool = False) -> PermissionResult:
        """Gate local listen sockets before exposing daemon HTTP endpoints."""

        normalized_host = host.strip() if host else ""
        display_host = normalized_host or "<all-interfaces>"
        endpoint = f"{display_host}:{port}"
        if normalized_host in self.denylist_hosts:
            return deny(DeniedReason.EXPLICITLY_DENYLISTED, f"listen host denied: {endpoint}")
        if self._is_protected(endpoint):
            return deny(DeniedReason.PROTECTED_RESOURCE, f"protected listen endpoint: {endpoint}")
        if normalized_host in self.allowlist_hosts:
            return allow(
                AllowedReason.IS_READ_ONLY_AND_SETTING_ENABLED, f"loopback listen: {endpoint}"
            )
        if normalized_host in WILDCARD_BIND_HOSTS:
            if self.allow_network or opted_in:
                return allow(
                    AllowedReason.EXPLICITLY_ALLOWLISTED, f"cluster listen allowed: {endpoint}"
                )
            return deny(
                DeniedReason.ALWAYS_ASK_ENABLED, f"non-loopback listen requires opt-in: {endpoint}"
            )
        if self.allow_network or opted_in:
            return allow(
                AllowedReason.EXPLICITLY_ALLOWLISTED, f"listen endpoint allowed: {endpoint}"
            )
        return deny(DeniedReason.ALWAYS_ASK_ENABLED, f"listen endpoint requires opt-in: {endpoint}")

    def check_filesystem(self, path: str | Path, *, write: bool = False) -> PermissionResult:
        path_text = str(path)
        if self._is_protected(path_text):
            return deny(
                DeniedReason.PROTECTED_RESOURCE, f"protected filesystem resource: {path_text}"
            )
        if write and not self.allow_filesystem:
            return deny(DeniedReason.ALWAYS_ASK_ENABLED, f"filesystem write denied: {path_text}")
        return allow(AllowedReason.IS_READ_ONLY_AND_SETTING_ENABLED, path_text)

    def check_command(self, command: list[str] | str) -> PermissionResult:
        command_text = command if isinstance(command, str) else " ".join(command)
        lower = command_text.lower()
        if any(marker.lower() in lower for marker in DESTRUCTIVE_VERBS):
            return deny(DeniedReason.CONTAINS_DESTRUCTIVE_OPERATION, command_text)
        if self._is_protected(command_text):
            return deny(DeniedReason.PROTECTED_RESOURCE, command_text)
        return allow(AllowedReason.DISPATCHED, command_text)

    def _is_protected(self, value: str) -> bool:
        lower = value.lower()
        return any(marker.lower() in lower for marker in self.protected_resources)


def allow(reason: AllowedReason, message: str = "") -> PermissionResult:
    return PermissionResult(PermissionDecision.ALLOWED, reason, message)


def deny(reason: DeniedReason, message: str = "") -> PermissionResult:
    return PermissionResult(PermissionDecision.DENIED, reason, message)


def is_protected_resource(value: str) -> bool:
    lower = value.lower()
    return any(marker.lower() in lower for marker in PROTECTED_RESOURCE_MARKERS)


__all__ = [
    "AllowedReason",
    "DeniedReason",
    "PermissionDecision",
    "PermissionPolicy",
    "PermissionResult",
    "WILDCARD_BIND_HOSTS",
    "allow",
    "deny",
    "is_protected_resource",
]
