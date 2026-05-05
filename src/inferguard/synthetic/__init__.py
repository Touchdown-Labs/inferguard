"""Synthetic GPU mimic helpers shipped with the InferGuard package."""

from __future__ import annotations

from .mimic import (
    build_matrix_plan,
    load_json_config,
    simulate_from_options,
    simulate_job,
    simulate_main,
    simulate_results,
)
from .profiles import (
    ENGINE_ALIASES,
    GPU_PROFILE_ALIASES,
    GPU_PROFILE_CATALOG,
    MODEL_PROFILE_ALIASES,
    MODEL_PROFILES,
    WORKLOAD_ALIASES,
    WORKLOAD_PROFILES,
    load_gpu_profile_catalog,
    normalize_engine,
    normalize_hardware,
    normalize_model_profile,
    normalize_workload,
)
from .server import (
    CLAIM_BOUNDARY,
    SIMULATION_MODE,
    SyntheticOpenAIHandler,
    serve_main,
    serve_synthetic_endpoint,
)

__all__ = [
    "CLAIM_BOUNDARY",
    "ENGINE_ALIASES",
    "GPU_PROFILE_ALIASES",
    "GPU_PROFILE_CATALOG",
    "MODEL_PROFILE_ALIASES",
    "MODEL_PROFILES",
    "SIMULATION_MODE",
    "SyntheticOpenAIHandler",
    "WORKLOAD_ALIASES",
    "WORKLOAD_PROFILES",
    "build_matrix_plan",
    "load_gpu_profile_catalog",
    "load_json_config",
    "normalize_engine",
    "normalize_hardware",
    "normalize_model_profile",
    "normalize_workload",
    "serve_main",
    "serve_synthetic_endpoint",
    "simulate_from_options",
    "simulate_job",
    "simulate_main",
    "simulate_results",
]
