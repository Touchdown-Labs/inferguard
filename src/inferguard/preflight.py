"""Preflight checks for known engine/model compatibility traps."""

from __future__ import annotations

from typing import Any

from inferguard.disagg.types import DisaggFinding

HYBRID_ATTENTION_MODELS = {
    "deepseek-v4",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "kimi-k2.5",
    "kimik2.5",
}


def check_hma_offload_compat(
    disagg_status: dict[str, Any], model_family: str | None
) -> list[DisaggFinding]:
    """Warn if vLLM native KV offload is used with HMA still enabled."""
    normalized_model = _normalize(model_family)
    if normalized_model not in HYBRID_ATTENTION_MODELS:
        return []
    if not _has_vllm_engine(disagg_status):
        return []
    backend = _lookup(disagg_status, "kv_offloading_backend")
    if str(backend or "").lower() != "native":
        return []
    if _truthy(_lookup(disagg_status, "disable_hybrid_kv_cache_manager")):
        return []
    return [
        DisaggFinding(
            code="hma_offload_incompatible",
            severity="warning",
            message=(
                "vLLM native KV offload is incompatible with the hybrid KV cache "
                "manager for hybrid-attention models; add "
                "--disable-hybrid-kv-cache-manager when OFFLOADING=cpu."
            ),
            evidence={
                "engine": "vllm",
                "model_family": normalized_model,
                "kv_offloading_backend": "native",
                "disable_hybrid_kv_cache_manager": False,
            },
        )
    ]


def check_tokenizer_mismatch(
    *,
    client_tokenizer: str,
    server_tokenizer: str | None,
    client_prompt_tokens: int | float | None,
    server_prompt_tokens: int | float | None,
    sample_text_length: int,
) -> list[DisaggFinding]:
    """Detect silent client/server tokenizer-count drift before rollout."""
    client_count = _float_or_none(client_prompt_tokens)
    server_count = _float_or_none(server_prompt_tokens)
    if client_count is None or server_count is None or client_count <= 0:
        return []
    divergence_pct = abs(server_count - client_count) / client_count
    if divergence_pct <= 0.01:
        return []
    return [
        DisaggFinding(
            code="tokenizer_mismatch_silent_drift",
            severity="critical",
            message=(
                "Client-side tokenizer count diverges from server usage.prompt_tokens "
                f"by {divergence_pct:.1%}; block rollout until tokenizer versions match."
            ),
            evidence={
                "client_tokenizer": client_tokenizer,
                "server_tokenizer": server_tokenizer or "server_usage.prompt_tokens",
                "client_prompt_tokens": client_count,
                "server_prompt_tokens": server_count,
                "divergence_pct": divergence_pct,
                "sample_text_length": sample_text_length,
            },
        )
    ]


def _has_vllm_engine(status: dict[str, Any]) -> bool:
    for key in ("prefill", "decode", "transfer"):
        snap = status.get(key)
        if not isinstance(snap, dict):
            continue
        endpoint = snap.get("endpoint")
        if isinstance(endpoint, dict) and str(endpoint.get("engine", "")).lower() == "vllm":
            return True
    return str(status.get("engine", "")).lower() == "vllm"


def _lookup(status: dict[str, Any], key: str) -> Any:
    if key in status:
        return status[key]
    for container_key in ("launch", "preflight", "metadata", "env", "args", "topology"):
        container = status.get(container_key)
        if isinstance(container, dict) and key in container:
            return container[key]
    return None


def _normalize(model_family: str | None) -> str:
    raw = str(model_family or "").strip().lower()
    if not raw:
        return ""
    tail = raw.rsplit("/", 1)[-1].replace("_", "-")
    aliases = {
        "deepseek-v4-pro": "deepseek-v4-pro",
        "deepseekv4-pro": "deepseek-v4-pro",
        "deepseek-v4-flash": "deepseek-v4-flash",
        "deepseekv4-flash": "deepseek-v4-flash",
        "deepseek-v4": "deepseek-v4",
        "deepseekv4": "deepseek-v4",
        "kimi-k2.5": "kimi-k2.5",
        "kimik2.5": "kimik2.5",
    }
    return aliases.get(tail, tail)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["HYBRID_ATTENTION_MODELS", "check_hma_offload_compat", "check_tokenizer_mismatch"]
