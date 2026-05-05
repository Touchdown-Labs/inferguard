"""Synthetic GPU rig profiles for InferGuard local harness validation."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

GPU_PROFILE_CATALOG: dict[str, Any] = {
    "schema_version": "inferguard-neocloud-nvidia-gpu-mimic-profiles/v1",
    "claim_boundary": "These profiles mimic operator-visible GPU evidence shape only; they are not performance evidence.",
    "sources": {
        "h100": "https://www.nvidia.com/en-us/data-center/h100/",
        "h200": "https://www.nvidia.com/en-in/data-center/h200/",
        "b200": "https://www.nvidia.com/en-us/data-center/dgx-b200/",
        "b300": "https://docs.nvidia.com/enterprise-reference-architectures/hgx-ai-factory/latest/components.html",
        "gb200": "https://www.nvidia.com/en-us/data-center/gb200-nvl72/",
        "gb300": "https://docs.nvidia.com/enterprise-reference-architectures/hgx-ai-factory/latest/components.html",
        "dcgm_exporter": "https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html",
        "nccl_tests": "https://github.com/NVIDIA/nccl-tests",
    },
    "profiles": {
        "h100_8gpu": {
            "display_name": "NVIDIA H100 SXM 8 GPU node",
            "gpu_name": "NVIDIA H100 80GB HBM3",
            "gpu_arch": "hopper",
            "nodes": 1,
            "gpus_per_node": 8,
            "memory_gb_per_gpu": 80,
            "hbm_bandwidth_tbps_per_gpu": 3.35,
            "nvlink_bandwidth_gbps_per_gpu": 900,
            "topology": "single_node_nvlink",
            "spec_confidence": "public_nvidia",
        },
        "h200_8gpu": {
            "display_name": "NVIDIA H200 SXM 8 GPU node",
            "gpu_name": "NVIDIA H200 141GB HBM3e",
            "gpu_arch": "hopper",
            "nodes": 1,
            "gpus_per_node": 8,
            "memory_gb_per_gpu": 141,
            "hbm_bandwidth_tbps_per_gpu": 4.8,
            "nvlink_bandwidth_gbps_per_gpu": 900,
            "topology": "single_node_nvlink",
            "spec_confidence": "public_nvidia",
        },
        "b200_8gpu": {
            "display_name": "NVIDIA B200 8 GPU node",
            "gpu_name": "NVIDIA B200",
            "gpu_arch": "blackwell",
            "nodes": 1,
            "gpus_per_node": 8,
            "memory_gb_per_gpu": 180,
            "hbm_bandwidth_tbps_per_gpu": 8.0,
            "nvlink_bandwidth_gbps_per_gpu": 1800,
            "topology": "single_node_nvlink",
            "spec_confidence": "public_nvidia",
        },
        "b300_8gpu": {
            "display_name": "NVIDIA B300 8 GPU node",
            "gpu_name": "NVIDIA B300",
            "gpu_arch": "blackwell",
            "nodes": 1,
            "gpus_per_node": 8,
            "memory_gb_per_gpu": 288,
            "hbm_bandwidth_tbps_per_gpu": 8.0,
            "nvlink_bandwidth_gbps_per_gpu": 1800,
            "topology": "single_node_nvlink",
            "spec_confidence": "public_nvidia_hgx_table",
        },
        "gb200_nvl72": {
            "display_name": "NVIDIA GB200 NVL72",
            "gpu_name": "NVIDIA GB200",
            "gpu_arch": "blackwell_gb_nvl",
            "nodes": 9,
            "gpus_per_node": 8,
            "memory_gb_per_gpu": 186,
            "hbm_bandwidth_tbps_per_gpu": 8.0,
            "nvlink_bandwidth_gbps_per_gpu": 1800,
            "topology": "nvl72_multinode",
            "spec_confidence": "public_nvidia",
        },
        "gb300_nvl72": {
            "display_name": "NVIDIA GB300 NVL72",
            "gpu_name": "NVIDIA GB300",
            "gpu_arch": "blackwell_gb_nvl",
            "nodes": 9,
            "gpus_per_node": 8,
            "memory_gb_per_gpu": 288,
            "hbm_bandwidth_tbps_per_gpu": 8.0,
            "nvlink_bandwidth_gbps_per_gpu": 1800,
            "topology": "nvl72_multinode",
            "spec_confidence": "public_spec_partial",
        },
    },
}

GPU_PROFILE_ALIASES = {
    "h100": "h100_8gpu",
    "h100-8gpu": "h100_8gpu",
    "h100_8gpu": "h100_8gpu",
    "h200": "h200_8gpu",
    "h200-8gpu": "h200_8gpu",
    "h200_8gpu": "h200_8gpu",
    "b200": "b200_8gpu",
    "b200-8gpu": "b200_8gpu",
    "b200_8gpu": "b200_8gpu",
    "b300": "b300_8gpu",
    "b300-8gpu": "b300_8gpu",
    "b300_8gpu": "b300_8gpu",
    "gb200": "gb200_nvl72",
    "gb200-nvl72": "gb200_nvl72",
    "gb200_nvl72": "gb200_nvl72",
    "gb300": "gb300_nvl72",
    "gb300-nvl72": "gb300_nvl72",
    "gb300_nvl72": "gb300_nvl72",
}

MODEL_PROFILES: dict[str, dict[str, Any]] = {
    "deepseek_v4_flash": {
        "hf_repo": "deepseek-ai/DeepSeek-V4-Flash",
        "architecture_class": "deepseek_v4",
        "hf_parameters_m": 158069.4,
        "claim_level": "hf_repo_metadata_verified",
    },
    "deepseek_v4_pro": {
        "hf_repo": "deepseek-ai/DeepSeek-V4-Pro",
        "architecture_class": "deepseek_v4",
        "hf_parameters_m": 861608.3,
        "claim_level": "hf_repo_metadata_verified",
    },
    "kimi_k2_5": {
        "hf_repo": "moonshotai/Kimi-K2.5",
        "architecture_class": "kimi_k25",
        "hf_parameters_m": 1058589.4,
        "claim_level": "hf_repo_metadata_verified",
    },
    "glm_5_1": {
        "hf_repo": "zai-org/GLM-5.1",
        "architecture_class": "glm_moe_dsa",
        "hf_parameters_m": 753864.1,
        "claim_level": "hf_repo_metadata_verified",
    },
    "minimax_m2_5": {
        "hf_repo": "MiniMaxAI/MiniMax-M2.5",
        "architecture_class": "minimax_m2",
        "hf_parameters_m": 228703.6,
        "claim_level": "hf_repo_metadata_verified",
    },
    "qwen3_5": {
        "hf_repo": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        "architecture_class": "qwen3_moe",
        "hf_parameters_m": 480000,
        "claim_level": "hf_repo_metadata_verified",
    },
}

MODEL_PROFILE_ALIASES = {
    "dsv4-flash": "deepseek_v4_flash",
    "deepseek-v4-flash": "deepseek_v4_flash",
    "deepseek_v4_flash": "deepseek_v4_flash",
    "dsv4-pro": "deepseek_v4_pro",
    "deepseek-v4-pro": "deepseek_v4_pro",
    "deepseek_v4_pro": "deepseek_v4_pro",
    "kimi-k2.5": "kimi_k2_5",
    "kimi_k2_5": "kimi_k2_5",
    "glm-5.1": "glm_5_1",
    "glm_5_1": "glm_5_1",
    "minimax-m2.5": "minimax_m2_5",
    "minimax_m2_5": "minimax_m2_5",
    "qwen3.5": "qwen3_5",
    "qwen3_5": "qwen3_5",
}

WORKLOAD_PROFILES: dict[str, dict[str, str]] = {
    "long_context_chat": {
        "model_profile": "deepseek_v4_pro",
        "bottleneck_focus": "prefill_kv_decode",
    },
    "long_context_coding": {
        "model_profile": "deepseek_v4_pro",
        "bottleneck_focus": "prefill_kv_tool_output_decode",
    },
    "multi_turn_agentic_coding": {
        "model_profile": "kimi_k2_5",
        "bottleneck_focus": "prefix_reuse_scheduler_decode",
    },
    "tiny_canary_api": {
        "model_profile": "qwen3_5",
        "bottleneck_focus": "api_healthcheck",
    },
}

WORKLOAD_ALIASES = {
    "long_context_chat": "long_context_chat",
    "chat": "long_context_chat",
    "long-context-chat": "long_context_chat",
    "long_context_coding": "long_context_coding",
    "long-context-coding": "long_context_coding",
    "coding": "long_context_coding",
    "agentic": "multi_turn_agentic_coding",
    "multi_turn_agentic_coding": "multi_turn_agentic_coding",
    "canary": "tiny_canary_api",
    "tiny_canary_api": "tiny_canary_api",
}

ENGINE_ALIASES = {
    "vllm": "vllm_baseline",
    "vllm_baseline": "vllm_baseline",
    "sglang": "sglang_baseline",
    "sglang_baseline": "sglang_baseline",
}


def load_gpu_profile_catalog(path: str | Path | None = None) -> dict[str, Any]:
    """Load a GPU profile catalog, defaulting to the packaged public mimic catalog."""
    if path is None:
        return copy.deepcopy(GPU_PROFILE_CATALOG)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
        raise ValueError(f"expected GPU profile catalog with a profiles object: {path}")
    return data


def normalize_hardware(raw: str, catalog: dict[str, Any] | None = None) -> str:
    """Normalize h100/h200/b200/b300/gb200/gb300 aliases to catalog keys."""
    profiles = (catalog or GPU_PROFILE_CATALOG).get("profiles", {})
    value = _key(raw)
    candidate = GPU_PROFILE_ALIASES.get(value, value)
    if candidate in profiles:
        return candidate
    allowed = ", ".join(sorted(GPU_PROFILE_ALIASES))
    raise ValueError(f"unsupported hardware profile {raw!r}; expected one of: {allowed}")


def normalize_model_profile(raw: str) -> str:
    value = _key(raw)
    candidate = MODEL_PROFILE_ALIASES.get(value, value)
    if candidate in MODEL_PROFILES:
        return candidate
    allowed = ", ".join(sorted(MODEL_PROFILE_ALIASES))
    raise ValueError(f"unsupported model profile {raw!r}; expected one of: {allowed}")


def normalize_workload(raw: str) -> str:
    value = _key(raw)
    candidate = WORKLOAD_ALIASES.get(value, value)
    if candidate in WORKLOAD_PROFILES:
        return candidate
    allowed = ", ".join(sorted(WORKLOAD_ALIASES))
    raise ValueError(f"unsupported workload {raw!r}; expected one of: {allowed}")


def normalize_engine(raw: str) -> str:
    value = _key(raw)
    candidate = ENGINE_ALIASES.get(value, value)
    if candidate in ENGINE_ALIASES.values():
        return candidate
    allowed = ", ".join(sorted(ENGINE_ALIASES))
    raise ValueError(f"unsupported engine {raw!r}; expected one of: {allowed}")


def _key(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


__all__ = [
    "ENGINE_ALIASES",
    "GPU_PROFILE_ALIASES",
    "GPU_PROFILE_CATALOG",
    "MODEL_PROFILE_ALIASES",
    "MODEL_PROFILES",
    "WORKLOAD_ALIASES",
    "WORKLOAD_PROFILES",
    "load_gpu_profile_catalog",
    "normalize_engine",
    "normalize_hardware",
    "normalize_model_profile",
    "normalize_workload",
]
