"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_GMI_BASE_URL = "https://api.gmi-serving.com/v1"
DEFAULT_DIAGNOSIS_MODEL = "openai/gpt-oss-120b"


def _read_env(primary: str, legacy: str, default: str = "") -> str:
    """Read a primary env var, then a documented legacy compatibility alias."""
    return (os.environ.get(primary) or os.environ.get(legacy) or default).strip()


def load_diagnosis_env() -> tuple[str, str, str]:
    """Return `(base_url, api_key, model)` for GMI-first diagnosis settings.

    Empty or whitespace-only values are treated as unset. `LLM_*` is read only
    as a low-cost compatibility alias when the corresponding `GMI_*` value is
    absent.
    """
    return (
        _read_env("GMI_BASE_URL", "LLM_BASE_URL", DEFAULT_GMI_BASE_URL),
        _read_env("GMI_API_KEY", "LLM_API_KEY"),
        _read_env("GMI_MODEL", "LLM_MODEL", DEFAULT_DIAGNOSIS_MODEL),
    )


@dataclass(frozen=True)
class InferGuardConfig:
    """Runtime configuration for the standalone-first InferGuard core."""

    target_endpoint: str

    redis_url: str = ""
    redis_token: str = ""

    vector_url: str = ""
    vector_token: str = ""

    llm_base_url: str = DEFAULT_GMI_BASE_URL
    llm_api_key: str = ""
    llm_model: str = DEFAULT_DIAGNOSIS_MODEL

    kv_alert_threshold: float = 0.85
    ttft_alert_multiplier: float = 2.0
    poll_interval_seconds: int = 30
    brain_mode: str = "local"
    brain_agent_name: str = "inferguard-brain"
    proactive_cycle_every: int = 5

    @classmethod
    def from_env(cls) -> "InferGuardConfig":
        endpoint = os.environ.get("TARGET_ENDPOINT", "").strip()
        if not endpoint:
            raise ValueError("TARGET_ENDPOINT env var is required")
        llm_base_url, llm_api_key, llm_model = load_diagnosis_env()

        return cls(
            target_endpoint=endpoint,
            redis_url=os.environ.get("UPSTASH_REDIS_URL", "").strip(),
            redis_token=os.environ.get("UPSTASH_REDIS_TOKEN", "").strip(),
            vector_url=os.environ.get("UPSTASH_VECTOR_URL", "").strip(),
            vector_token=os.environ.get("UPSTASH_VECTOR_TOKEN", "").strip(),
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            kv_alert_threshold=float(os.environ.get("KV_ALERT_THRESHOLD", "0.85")),
            ttft_alert_multiplier=float(os.environ.get("TTFT_ALERT_MULTIPLIER", "2.0")),
            poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "30")),
            brain_mode=os.environ.get("INFERGUARD_BRAIN_MODE", "local").strip() or "local",
            brain_agent_name=os.environ.get(
                "INFERGUARD_BRAIN_AGENT_NAME", "inferguard-brain"
            ).strip()
            or "inferguard-brain",
            proactive_cycle_every=int(os.environ.get("INFERGUARD_PROACTIVE_CYCLE_EVERY", "5")),
        )

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url and self.redis_token)

    @property
    def has_vector(self) -> bool:
        return bool(self.vector_url and self.vector_token)

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_api_key)
