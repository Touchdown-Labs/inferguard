"""Opt-in telemetry state machine for the v0.5 harness layer.

v0.5 never uploads to the network. When consent exists, payloads are validated
and written to ``~/.config/inferguard/uploads-pending/`` for auditability.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from inferguard.io import atomic_write_json, atomic_write_text
from inferguard.schemas.telemetry import (
    TELEMETRY_SCHEMA_VERSION,
    TelemetryPayload,
    validate_telemetry_payload,
)

LOGGER = logging.getLogger(__name__)
PRIVATE_FILE_MODE = 0o600
PRIVATE_DIR_MODE = 0o700
REDACTED_VALUE = "[REDACTED]"

NEVER_COLLECTED_KEYS = {
    "prompt",
    "prompts",
    "messages",
    "output_text",
    "completion",
    "tool_args",
    "tool_arguments",
    "file_path",
    "file_paths",
    "env",
    "environment",
    "api_key",
    "authorization",
    "ip",
    "ip_address",
    "username",
    "user",
    "kv_block_id",
    "kv_block_ids",
    "block_hash",
    "raw_block_hash",
}
DEFAULT_DP_PARAMS = {
    "epsilon": 1.0,
    "delta": 1e-5,
    "mechanism": "stub",
    "library": "stub",
}
SAFE_LONG_VALUE_MARKERS = {"schema_version", "rig_label"}
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
FILE_PATH_RE = re.compile(r"(?<![:\w])/(?:[A-Za-z0-9._-]+/){1,}[A-Za-z0-9._-]+")
IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)
IPV6_CANDIDATE_RE = re.compile(r"[0-9A-Fa-f:.]{3,}")
BASE64_BLOB_RE = re.compile(r"^[A-Za-z0-9+/=_-]{41,}$")
HEX_TOKEN_RE = re.compile(r"\b[0-9a-fA-F]{33,}\b")


class TelemetryState(StrEnum):
    DISABLED = "disabled"
    ENABLED_PENDING_CONSENT = "enabled-pending-consent"
    ENABLED_WITH_CONSENT = "enabled-with-consent"


@dataclass(frozen=True)
class TelemetryStatus:
    state: TelemetryState
    hard_disabled: bool
    consent_token_present: bool
    config_dir: Path
    uploads_pending_dir: Path

    @property
    def can_write_payloads(self) -> bool:
        return self.state is TelemetryState.ENABLED_WITH_CONSENT and not self.hard_disabled


class TelemetryClient:
    """Local-only consent and payload-spooling client."""

    def __init__(
        self,
        *,
        config_dir: Path | None = None,
        env: dict[str, str] | None = None,
        cluster_fingerprint: str | None = None,
        strict: bool = False,
    ) -> None:
        self.env = dict(os.environ if env is None else env)
        self.config_dir = config_dir or default_config_dir(self.env)
        self.secrets_dir = self.config_dir / "secrets"
        self.consent_path = self.secrets_dir / "consent.token"
        self.state_path = self.config_dir / "telemetry-state.json"
        self.uploads_pending_dir = self.config_dir / "uploads-pending"
        self.cluster_fingerprint = cluster_fingerprint or _default_cluster_fingerprint(self.env)
        self.strict = strict or self.env.get("INFERGUARD_TELEMETRY_STRICT", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.ring_buffer: deque[dict[str, Any]] = deque(maxlen=50)
        self._state = self._load_initial_state()

    @property
    def state(self) -> TelemetryState:
        if self._hard_disabled():
            return TelemetryState.DISABLED
        return self._state

    def status(self) -> TelemetryStatus:
        return TelemetryStatus(
            state=self.state,
            hard_disabled=self._hard_disabled(),
            consent_token_present=self.load_consent_token() is not None,
            config_dir=self.config_dir,
            uploads_pending_dir=self.uploads_pending_dir,
        )

    def enable_pending_consent(self) -> TelemetryStatus:
        if self._hard_disabled():
            self._state = TelemetryState.DISABLED
        else:
            self._state = TelemetryState.ENABLED_PENDING_CONSENT
            self._persist_state()
        return self.status()

    def grant_consent(self, consent_token: str) -> TelemetryStatus:
        if self._hard_disabled():
            self._state = TelemetryState.DISABLED
            return self.status()
        if not consent_token.strip():
            raise ValueError("consent_token must be non-empty")
        _ensure_private_dir(self.secrets_dir)
        _write_private_text(self.consent_path, consent_token.strip() + "\n")
        self._state = TelemetryState.ENABLED_WITH_CONSENT
        self._persist_state()
        return self.status()

    def disable(self, *, delete_pending: bool = False) -> TelemetryStatus:
        self._state = TelemetryState.DISABLED
        self._persist_state()
        if delete_pending and self.uploads_pending_dir.exists():
            for path in self.uploads_pending_dir.glob("*.json"):
                path.unlink()
        return self.status()

    def load_consent_token(self) -> str | None:
        if not self.consent_path.exists():
            return None
        if not _private_file_perms_ok(self.consent_path):
            LOGGER.warning(
                "Refusing to load telemetry consent token with insecure permissions: %s",
                self.consent_path,
            )
            return None
        token = self.consent_path.read_text(encoding="utf-8").strip()
        return token or None

    def can_upload(self) -> bool:
        return self.status().can_write_payloads and self.load_consent_token() is not None

    def anonymized_deployment_id(self, consent_token: str | None = None) -> str:
        token = consent_token or self.load_consent_token() or ""
        digest = hashlib.sha256((token + self.cluster_fingerprint).encode("utf-8")).hexdigest()
        return digest[:16]

    def verify_payload(
        self,
        *,
        payload_kind: str,
        rig_fingerprint: dict[str, Any],
        aggregates: dict[str, Any],
        consent_token: str | None = None,
    ) -> dict[str, Any]:
        token = consent_token or self.load_consent_token()
        if not token:
            raise PermissionError("telemetry consent token is required before preparing payloads")
        payload = {
            "schema_version": TELEMETRY_SCHEMA_VERSION,
            "consent_token": token,
            "anonymized_deployment_id": self.anonymized_deployment_id(token),
            "uploaded_at": _now_iso(),
            "payload_kind": payload_kind,
            "rig_fingerprint": sanitize_for_telemetry(rig_fingerprint, strict=self.strict),
            "aggregates": apply_dp_stub(sanitize_for_telemetry(aggregates, strict=self.strict)),
            "dp_params": dict(DEFAULT_DP_PARAMS),
        }
        return validate_telemetry_payload(payload).as_dict()

    def write_pending_payload(self, payload: TelemetryPayload | dict[str, Any]) -> Path:
        if not self.can_upload():
            raise PermissionError("telemetry is not enabled with consent")
        normalized = (
            payload.as_dict()
            if isinstance(payload, TelemetryPayload)
            else validate_telemetry_payload(payload).as_dict()
        )
        normalized = sanitize_for_telemetry(normalized, strict=self.strict)
        _ensure_private_dir(self.uploads_pending_dir)
        output_path = self.uploads_pending_dir / f"{int(time.time())}-{uuid.uuid4().hex}.json"
        _write_private_text(
            output_path,
            json.dumps(normalized, indent=2, sort_keys=True) + "\n",
        )
        self.ring_buffer.append(
            {"queued_at": _now_iso(), "path": str(output_path), "payload": normalized}
        )
        return output_path

    def queue_payload(
        self,
        *,
        payload_kind: str,
        rig_fingerprint: dict[str, Any],
        aggregates: dict[str, Any],
    ) -> Path:
        payload = self.verify_payload(
            payload_kind=payload_kind,
            rig_fingerprint=rig_fingerprint,
            aggregates=aggregates,
        )
        return self.write_pending_payload(payload)

    def log_tail(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return list(self.ring_buffer)[-limit:]

    def _load_initial_state(self) -> TelemetryState:
        if self._hard_disabled():
            return TelemetryState.DISABLED
        env_state = self.env.get("INFERGUARD_TELEMETRY", "").strip().lower()
        if env_state in {"enabled", "1", "true", "yes"}:
            return (
                TelemetryState.ENABLED_WITH_CONSENT
                if self.load_consent_token()
                else TelemetryState.ENABLED_PENDING_CONSENT
            )
        if self.state_path.exists():
            try:
                raw = json.loads(self.state_path.read_text(encoding="utf-8"))
                return TelemetryState(raw.get("state", TelemetryState.DISABLED.value))
            except (ValueError, OSError, json.JSONDecodeError):
                return TelemetryState.DISABLED
        return TelemetryState.DISABLED

    def _persist_state(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.state_path, {"state": self._state.value, "updated_at": _now_iso()})

    def _hard_disabled(self) -> bool:
        telemetry = self.env.get("INFERGUARD_TELEMETRY", "").strip().lower()
        return self.env.get("DO_NOT_TRACK") == "1" or telemetry in {"disabled", "0", "false", "off"}


def default_config_dir(env: dict[str, str] | None = None) -> Path:
    environ = os.environ if env is None else env
    xdg = environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "inferguard"
    return Path.home() / ".config" / "inferguard"


def sanitize_for_telemetry(value: Any, *, strict: bool = False) -> Any:
    """Drop fields that must never be uploaded under any consent tier."""

    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if _is_blocked_key(str(key)):
                continue
            clean[str(key)] = sanitize_for_telemetry(item, strict=strict)
        return clean
    if isinstance(value, list):
        return [sanitize_for_telemetry(item, strict=strict) for item in value]
    return _sanitize_value(value, strict=strict)


def apply_dp_stub(aggregates: dict[str, Any]) -> dict[str, Any]:
    """v0.5 DP stub: preserve already-bucketed values and annotate via dp_params."""

    return dict(aggregates)


def _is_blocked_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return normalized in NEVER_COLLECTED_KEYS or normalized.endswith("_api_key")


def _sanitize_value(value: Any, *, strict: bool = False) -> Any:
    """Redact sensitive string values that survive key-level telemetry filtering."""

    if not isinstance(value, str):
        return value
    if strict and len(value) > 50:
        return REDACTED_VALUE
    if EMAIL_RE.search(value):
        return REDACTED_VALUE
    if FILE_PATH_RE.search(value):
        return REDACTED_VALUE
    if IPV4_RE.search(value) or _contains_ipv6_address(value):
        return REDACTED_VALUE
    stripped = value.strip()
    if len(stripped) > 40 and BASE64_BLOB_RE.fullmatch(stripped):
        return REDACTED_VALUE
    if HEX_TOKEN_RE.search(value):
        return REDACTED_VALUE
    if len(value) > 200 and not any(marker in value for marker in SAFE_LONG_VALUE_MARKERS):
        return REDACTED_VALUE
    return value


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, PRIVATE_DIR_MODE)


def _write_private_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, text)
    os.chmod(path, PRIVATE_FILE_MODE)


def _private_file_perms_ok(path: Path) -> bool:
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        return False
    return mode & ~PRIVATE_FILE_MODE == 0


def _contains_ipv6_address(value: str) -> bool:
    for candidate in IPV6_CANDIDATE_RE.findall(value):
        if ":" not in candidate:
            continue
        try:
            if ipaddress.ip_address(candidate.strip("[]")).version == 6:
                return True
        except ValueError:
            continue
    return False


def _default_cluster_fingerprint(env: dict[str, str]) -> str:
    parts = [env.get("HOSTTYPE", ""), env.get("OSTYPE", ""), env.get("INFERGUARD_RIG_LABEL", "")]
    return "|".join(parts) or "local"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "DEFAULT_DP_PARAMS",
    "NEVER_COLLECTED_KEYS",
    "REDACTED_VALUE",
    "TelemetryClient",
    "TelemetryState",
    "TelemetryStatus",
    "_sanitize_value",
    "apply_dp_stub",
    "default_config_dir",
    "sanitize_for_telemetry",
]
