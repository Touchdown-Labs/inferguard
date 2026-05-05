"""LMCache launch helpers for vLLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from inferguard.launch_engine.vllm import build_vllm_command

LMCACHE_LAUNCH_SCHEMA_VERSION = "inferguard-lmcache-launch/v1"
LMCACHE_KV_TRANSFER_CONFIG = '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'
DEFAULT_PROMETHEUS_MULTIPROC_DIR = "/tmp/lmcache_prometheus"


class LMCacheLaunchError(ValueError):
    """Raised when an LMCache launch violates the locked V1 connector contract."""


def lmcache_env(
    base_env: dict[str, str] | None = None,
    *,
    prometheus_multiproc_dir: str | None = None,
) -> dict[str, str]:
    env = dict(base_env or {})
    if prometheus_multiproc_dir is not None:
        env["PROMETHEUS_MULTIPROC_DIR"] = prometheus_multiproc_dir
    return ensure_prometheus_multiproc_env(env)


def ensure_prometheus_multiproc_env(env: dict[str, str]) -> dict[str, str]:
    final = dict(env)
    multiproc_dir = final.get("PROMETHEUS_MULTIPROC_DIR") or DEFAULT_PROMETHEUS_MULTIPROC_DIR
    Path(multiproc_dir).mkdir(parents=True, exist_ok=True)
    final["PROMETHEUS_MULTIPROC_DIR"] = multiproc_dir
    return final


def validate_lmcache_kv_transfer_config(kv_transfer_config: str | None) -> str:
    raw = (kv_transfer_config or LMCACHE_KV_TRANSFER_CONFIG).strip()
    connector = _kv_connector_value(raw)
    if connector == "LMCacheConnectorV1":
        return raw
    if connector == "LMCacheConnector" or _mentions_old_connector(raw):
        raise LMCacheLaunchError(
            "--kv-transfer-config must use LMCacheConnectorV1; "
            "LMCacheConnector is the rejected v0 connector class."
        )
    if connector is None and "LMCacheConnectorV1" in raw:
        return raw
    if kv_transfer_config is None:
        return LMCACHE_KV_TRANSFER_CONFIG
    return raw


def is_lmcache_v1_config(kv_transfer_config: str | None) -> bool:
    raw = (kv_transfer_config or "").strip()
    if not raw:
        return False
    if _kv_connector_value(raw) == "LMCacheConnectorV1":
        return True
    return "LMCacheConnectorV1" in raw


def lmcache_metrics_present(prometheus_text: str) -> bool:
    for line in prometheus_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("lmcache:"):
            return True
    return False


def build_lmcache_vllm_command(
    model_path: str,
    **flags: Any,
) -> list[str]:
    flags = dict(flags)
    flags["kv_transfer_config"] = validate_lmcache_kv_transfer_config(
        flags.get("kv_transfer_config")
    )
    return build_vllm_command(model_path, **flags)


def launch_vllm_lmcache(
    model_path: str,
    output_dir: str | Path,
    **flags: Any,
) -> Any:
    from inferguard.launch_engine import launch

    flags = dict(flags)
    env = lmcache_env(flags.pop("env", None))
    flags["kv_transfer_config"] = validate_lmcache_kv_transfer_config(
        flags.get("kv_transfer_config")
    )
    return launch(
        engine="lmcache",
        model_path=model_path,
        output_dir=output_dir,
        env=env,
        **flags,
    )


def _kv_connector_value(raw: str) -> str | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("kv_connector") or payload.get("connector")
    return str(value) if value is not None else None


def _mentions_old_connector(raw: str) -> bool:
    return '"LMCacheConnector"' in raw or "'LMCacheConnector'" in raw


__all__ = [
    "DEFAULT_PROMETHEUS_MULTIPROC_DIR",
    "LMCACHE_KV_TRANSFER_CONFIG",
    "LMCACHE_LAUNCH_SCHEMA_VERSION",
    "LMCacheLaunchError",
    "build_lmcache_vllm_command",
    "ensure_prometheus_multiproc_env",
    "is_lmcache_v1_config",
    "launch_vllm_lmcache",
    "lmcache_env",
    "lmcache_metrics_present",
    "validate_lmcache_kv_transfer_config",
]
