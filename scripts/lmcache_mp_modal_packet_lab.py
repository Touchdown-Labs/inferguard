#!/usr/bin/env python3
"""Modal H100 lab for Packet A LMCache MP observability capture.

Exact run command:
    modal run scripts/lmcache_mp_modal_packet_lab.py

Outputs are written to the persistent Modal volume mounted at /out, under
/out/packet-a/<timestamp>/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import modal

APP_NAME = "lmcache-mp-lab"
VOLUME_NAME = "lmcache-mp-lab"
OUT_ROOT = Path("/out")

MODEL = "Qwen/Qwen3-8B"
MODEL_MAX_LEN = 16384
VLLM_PORT = 8000
LMCACHE_HOST = "127.0.0.1"
LMCACHE_ZMQ_PORT = 6555
LMCACHE_HTTP_PORT = 8080
LMCACHE_PROMETHEUS_PORT = 9090
OTLP_GRPC_PORT = 4317
OTLP_HTTP_PORT = 4318
MP_EVENT_BUS_QUEUE_SIZE = 10000
MP_METRICS_SAMPLE_RATE = 1.0
LMCACHE_L1_SIZE_GB = "8"

VLLM_BASE_URL = f"http://127.0.0.1:{VLLM_PORT}"
VLLM_HEALTH_URL = f"{VLLM_BASE_URL}/health"
VLLM_METRICS_URL = f"{VLLM_BASE_URL}/metrics"
LMCACHE_HTTP_BASE_URL = f"http://127.0.0.1:{LMCACHE_HTTP_PORT}"
LMCACHE_HEALTH_URL = f"{LMCACHE_HTTP_BASE_URL}/healthcheck"
LMCACHE_HTTP_METRICS_URL = f"{LMCACHE_HTTP_BASE_URL}/metrics"
LMCACHE_STANDALONE_METRICS_URL = f"http://127.0.0.1:{LMCACHE_PROMETHEUS_PORT}/metrics"
LMCACHE_METRICS_URLS = (LMCACHE_HTTP_METRICS_URL, LMCACHE_STANDALONE_METRICS_URL)
LMCACHE_METRICS_URL = LMCACHE_HTTP_METRICS_URL
LMCACHE_METRICS_URL_FILE = "lmcache_metrics_url.txt"
LMCACHE_TRACE_FILE = "lmcache_trace.lct"
LMCACHE_OTEL_FILE = "lmcache_otel.jsonl"
TRACE_REPLAY_DIR = "trace-replay"
LOOKUP_HASH_DIR = "lookup_hashes"
L2_CONFIG_FILE = "lmcache_l2_config.json"
PACKET_B_VLLM_GPU_MEMORY_UTILIZATION_ENV = "INFERGUARD_PACKET_B_VLLM_GPU_MEMORY_UTILIZATION"
PACKET_B_VLLM_MAX_MODEL_LEN_ENV = "INFERGUARD_PACKET_B_VLLM_MAX_MODEL_LEN"
PACKET_B_LMCACHE_LOG_LEVEL_ENV = "INFERGUARD_PACKET_B_LMCACHE_LOG_LEVEL"
PACKET_B_DEFAULT_VLLM_GPU_MEMORY_UTILIZATION = "0.65"
PACKET_B_DEFAULT_VLLM_MAX_MODEL_LEN = 8192

REPO_ROOT = Path(__file__).resolve().parents[1]
MODAL_INFERGUARD_SOURCE = "/opt/inferguard"
MODAL_INFERGUARD_FILES = ("pyproject.toml", "README.md", "LICENSE")
MODAL_INFERGUARD_PACKAGE_DIR = "src/inferguard"
INFERGUARD_LOCAL_INSTALL_COMMAND = f"python -m pip install -e {MODAL_INFERGUARD_SOURCE}"

MODAL_LMCACHE_SOURCE = "/opt/lmcache"
MODAL_VLLM_SOURCE = "/opt/vllm"
LMCACHE_LOCAL_SOURCE_ENV = "INFERGUARD_LMCACHE_LOCAL_SOURCE"
LMCACHE_GIT_REF_ENV = "INFERGUARD_LMCACHE_GIT_REF"
LMCACHE_GIT_REPO_ENV = "INFERGUARD_LMCACHE_GIT_REPO"
LMCACHE_PIP_SPEC_ENV = "INFERGUARD_LMCACHE_PIP_SPEC"
VLLM_LOCAL_SOURCE_ENV = "INFERGUARD_VLLM_LOCAL_SOURCE"
DEFAULT_VLLM_LOCAL_SOURCE = REPO_ROOT.parent / "vllm"
VLLM_CONNECTOR_RELATIVE_PATH = Path("distributed/kv_transfer/kv_connector/v1/lmcache_mp_connector.py")
LEGACY_LMCACHE_LOCAL_SOURCE_ENV = "INFERGUARD_PACKET_A_LMCACHE_LOCAL_SOURCE"
LEGACY_LMCACHE_GIT_REF_ENV = "INFERGUARD_PACKET_A_LMCACHE_GIT_REF"
LEGACY_LMCACHE_GIT_REPO_ENV = "INFERGUARD_PACKET_A_LMCACHE_GIT_REPO"
LEGACY_LMCACHE_PIP_SPEC_ENV = "INFERGUARD_PACKET_A_LMCACHE_PIP_SPEC"
LMCACHE_SOURCE_KIND_RUNTIME_ENV = "INFERGUARD_LMCACHE_SOURCE_KIND"
LMCACHE_SOURCE_REF_RUNTIME_ENV = "INFERGUARD_LMCACHE_SOURCE_REF"
LEGACY_LMCACHE_SOURCE_KIND_RUNTIME_ENV = "INFERGUARD_PACKET_A_LMCACHE_SOURCE_KIND"
LEGACY_LMCACHE_SOURCE_REF_RUNTIME_ENV = "INFERGUARD_PACKET_A_LMCACHE_SOURCE_REF"
DEFAULT_LMCACHE_PIP_SPEC = "lmcache"
DEFAULT_LMCACHE_GIT_REPO = "https://github.com/LMCache/LMCache.git"
CUDA_DEVEL_IMAGE = "nvidia/cuda:13.0.2-devel-ubuntu22.04"
UPSTREAM_LMCACHE_MP_PROMETHEUS_FAMILIES = (
    "lmcache_mp_lookup_requested_tokens_total",
    "lmcache_mp_lookup_hit_tokens_total",
    "lmcache_mp_l1_memory_usage_bytes",
)
PACKET_B_LIFECYCLE_EVIDENCE_FILE = "packet-b-lifecycle-evidence.json"
AGENT_KV_OFFLOAD_REPORT_FILE = "agent_kv_offload_report.json"
L0_BLOCK_BOUNDARY_EVENTS_FILE = "l0_block_boundary_events.jsonl"
L0_BLOCK_BOUNDARY_EVIDENCE_FILE = "l0_block_boundary_evidence.json"
L0_BLOCK_BOUNDARY_EVIDENCE_ENV = "INFERGUARD_L0_BLOCK_BOUNDARY_EVIDENCE_PATH"
WORKLOAD_MANIFEST_FILE = "workload_manifest.json"
PACKET_B_TRACE_SOURCE = "traces/isb1-dsv4-agent"
PACKET_B_TRACE_CLASSES = (
    "coding-long",
    "kv-pressure",
    "multi-agent-coding",
    "prefix-reuse",
    "session-resume",
    "tool-heavy",
)
PACKET_B_REQUIRED_TELEMETRY = {
    "lookup_reuse": ("lmcache_mp_lookup_requested_tokens", "lmcache_mp.lookup_requested_tokens"),
    "lookup_hits": ("lmcache_mp_lookup_hit_tokens", "lmcache_mp.lookup_hit_tokens"),
    "l1_lifecycle": ("lmcache_mp_l1_chunk_", "lmcache_mp.l1_chunk_"),
    "l0_lifecycle": ("lmcache_mp_l0_block_", "lmcache_mp.l0_block_"),
    "real_reuse": ("lmcache_mp_real_reuse_gap_", "lmcache_mp.real_reuse_gap_"),
    "l1_eviction": ("lmcache_mp_l1_evicted_keys", "lmcache_mp.l1_evicted_keys"),
    "l0_l1_throughput": ("lmcache_mp_l0_l1_", "lmcache_mp.l0_l1_"),
}


def _first_env(env: Mapping[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    return default


def _env_float_string(
    env: Mapping[str, str],
    key: str,
    *,
    default: str,
    minimum: float,
    maximum: float,
) -> str:
    value = env.get(key, "").strip() or default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be a float in [{minimum}, {maximum}], got {value!r}") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{key} must be in [{minimum}, {maximum}], got {value!r}")
    return value


def _env_int(
    env: Mapping[str, str],
    key: str,
    *,
    default: int,
    minimum: int,
) -> int:
    value = env.get(key, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer >= {minimum}, got {value!r}") from exc
    if parsed < minimum:
        raise ValueError(f"{key} must be >= {minimum}, got {value!r}")
    return parsed


def _packet_b_lmcache_log_level(env: Mapping[str, str] | None = None) -> str | None:
    env = env or os.environ
    value = env.get(PACKET_B_LMCACHE_LOG_LEVEL_ENV, "").strip().upper()
    return value or None


def _packet_b_vllm_gpu_memory_utilization(env: Mapping[str, str] | None = None) -> str:
    env = env or os.environ
    return _env_float_string(
        env,
        PACKET_B_VLLM_GPU_MEMORY_UTILIZATION_ENV,
        default=PACKET_B_DEFAULT_VLLM_GPU_MEMORY_UTILIZATION,
        minimum=0.1,
        maximum=1.0,
    )


def _packet_b_vllm_max_model_len(env: Mapping[str, str] | None = None) -> int:
    env = env or os.environ
    return _env_int(
        env,
        PACKET_B_VLLM_MAX_MODEL_LEN_ENV,
        default=PACKET_B_DEFAULT_VLLM_MAX_MODEL_LEN,
        minimum=1024,
    )


@dataclass(frozen=True)
class LmcacheInstallPlan:
    source_kind: str
    pip_packages: tuple[str, ...]
    run_commands: tuple[str, ...] = ()
    local_source: Path | None = None
    remote_source: str | None = None
    source_ref: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "source_kind": self.source_kind,
            "pip_packages": list(self.pip_packages),
            "run_commands": list(self.run_commands),
            "local_source": str(self.local_source) if self.local_source else None,
            "remote_source": self.remote_source,
            "source_ref": self.source_ref,
            "required_mp_prometheus_families": list(UPSTREAM_LMCACHE_MP_PROMETHEUS_FAMILIES),
        }


@dataclass(frozen=True)
class VllmOverlayPlan:
    source_kind: str
    run_commands: tuple[str, ...] = ()
    local_source: Path | None = None
    source_ref: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "source_kind": self.source_kind,
            "run_commands": list(self.run_commands),
            "local_source": str(self.local_source) if self.local_source else None,
            "source_ref": self.source_ref,
            "overlaid_file": str(VLLM_CONNECTOR_RELATIVE_PATH) if self.local_source else None,
        }


def _sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _installed_vllm_connector_path() -> Path | None:
    try:
        import vllm
    except ImportError:
        return None
    return Path(vllm.__file__).parent / VLLM_CONNECTOR_RELATIVE_PATH


def _augment_vllm_overlay_plan(plan: dict[str, object]) -> dict[str, object]:
    local_source = plan.get("local_source")
    local_root = Path(str(local_source)).expanduser() if local_source else None
    source_connector = local_root / "vllm" / VLLM_CONNECTOR_RELATIVE_PATH if local_root else None
    installed_connector = _installed_vllm_connector_path()
    plan.update(
        {
            "source_git_head": _git_head(local_root) if local_root else None,
            "source_connector_sha256": _sha256_file(source_connector) if source_connector else None,
            "installed_connector_path": str(installed_connector) if installed_connector else None,
            "installed_connector_sha256": (
                _sha256_file(installed_connector) if installed_connector else None
            ),
        }
    )
    return plan


def _runtime_vllm_overlay_plan_dict() -> dict[str, object]:
    """Return the vLLM overlay plan, preserving image-build runtime evidence."""
    source_kind = os.environ.get("INFERGUARD_VLLM_SOURCE_KIND", "").strip()
    source_ref = os.environ.get("INFERGUARD_VLLM_SOURCE_REF", "").strip()
    if source_kind and source_kind != VLLM_OVERLAY_PLAN.source_kind:
        return _augment_vllm_overlay_plan(
            {
                "source_kind": source_kind,
                "run_commands": list(VLLM_OVERLAY_PLAN.run_commands),
                "local_source": source_ref or None,
                "source_ref": source_ref or None,
                "overlaid_file": str(VLLM_CONNECTOR_RELATIVE_PATH) if source_ref else None,
            }
        )
    return _augment_vllm_overlay_plan(VLLM_OVERLAY_PLAN.as_dict())


BASE_MODAL_PIP_PACKAGES = (
    "vllm",
    "hf-transfer",
    "huggingface-hub",
    "nvidia-cuda-runtime-cu12",
)
LMCACHE_SOURCE_BUILD_DEPS = (
    "ninja",
    "packaging>=24.2",
    "setuptools>=77.0.3,<81.0.0",
    "setuptools_scm>=8",
    "wheel",
)
CUDA_SOURCE_BUILD_ENV = {
    "CC": "gcc",
    "CXX": "g++",
    "CUDA_HOME": "/usr/local/cuda",
    "TORCH_CUDA_ARCH_LIST": "9.0",
    "ENABLE_CXX11_ABI": "1",
    "LD_LIBRARY_PATH": (
        "/usr/local/cuda/lib64:"
        "/usr/local/lib/python3.11/site-packages/nvidia/cuda_runtime/lib"
    ),
}


def _select_lmcache_install_plan(env: Mapping[str, str] | None = None) -> LmcacheInstallPlan:
    env = env or os.environ
    local_source = _first_env(env, LMCACHE_LOCAL_SOURCE_ENV, LEGACY_LMCACHE_LOCAL_SOURCE_ENV)
    git_ref = _first_env(env, LMCACHE_GIT_REF_ENV, LEGACY_LMCACHE_GIT_REF_ENV)
    git_repo = _first_env(
        env,
        LMCACHE_GIT_REPO_ENV,
        LEGACY_LMCACHE_GIT_REPO_ENV,
        default=DEFAULT_LMCACHE_GIT_REPO,
    )
    pip_spec = _first_env(
        env,
        LMCACHE_PIP_SPEC_ENV,
        LEGACY_LMCACHE_PIP_SPEC_ENV,
        default=DEFAULT_LMCACHE_PIP_SPEC,
    )

    if local_source:
        return LmcacheInstallPlan(
            source_kind="local",
            pip_packages=(*BASE_MODAL_PIP_PACKAGES, *LMCACHE_SOURCE_BUILD_DEPS),
            run_commands=(
                f"python -m pip install -e {MODAL_LMCACHE_SOURCE} --no-build-isolation",
            ),
            local_source=Path(local_source).expanduser(),
            source_ref=local_source,
        )

    if git_ref:
        git_spec = f"git+{git_repo}@{git_ref}"
        return LmcacheInstallPlan(
            source_kind="git",
            pip_packages=(*BASE_MODAL_PIP_PACKAGES, *LMCACHE_SOURCE_BUILD_DEPS),
            run_commands=(
                f"python -m pip install {shlex.quote(git_spec)} --no-build-isolation",
            ),
            remote_source=git_repo,
            source_ref=git_ref,
        )

    return LmcacheInstallPlan(
        source_kind="pypi",
        pip_packages=(*BASE_MODAL_PIP_PACKAGES, pip_spec),
        remote_source=pip_spec,
        source_ref=pip_spec,
    )


LMCACHE_INSTALL_PLAN = _select_lmcache_install_plan()


def _select_vllm_overlay_plan(env: Mapping[str, str] | None = None) -> VllmOverlayPlan:
    env = env or os.environ
    local_source_raw = env.get(VLLM_LOCAL_SOURCE_ENV, "").strip()
    if local_source_raw:
        local_source = Path(local_source_raw).expanduser()
    elif DEFAULT_VLLM_LOCAL_SOURCE.exists():
        local_source = DEFAULT_VLLM_LOCAL_SOURCE
        local_source_raw = str(DEFAULT_VLLM_LOCAL_SOURCE)
    else:
        return VllmOverlayPlan(source_kind="pypi")
    connector_source = local_source / "vllm" / VLLM_CONNECTOR_RELATIVE_PATH
    if not connector_source.exists():
        raise FileNotFoundError(
            f"{VLLM_LOCAL_SOURCE_ENV} must point to a vLLM checkout containing {connector_source}"
        )

    overlay_command = "python -c " + shlex.quote(
        "from pathlib import Path; "
        "import shutil, vllm; "
        f"rel = Path({str(VLLM_CONNECTOR_RELATIVE_PATH)!r}); "
        f"src = Path({(MODAL_VLLM_SOURCE + '/vllm')!r}) / rel; "
        "dst = Path(vllm.__file__).parent / rel; "
        "dst.parent.mkdir(parents=True, exist_ok=True); "
        "shutil.copy2(src, dst); "
        "print(f'Overlayed vLLM connector {src} -> {dst}')"
    )
    return VllmOverlayPlan(
        source_kind="local_connector_overlay",
        run_commands=(overlay_command,),
        local_source=local_source,
        source_ref=local_source_raw,
    )


VLLM_OVERLAY_PLAN = _select_vllm_overlay_plan()


def _build_modal_image() -> modal.Image:
    if LMCACHE_INSTALL_PLAN.source_kind in {"local", "git"}:
        built_image = modal.Image.from_registry(CUDA_DEVEL_IMAGE, add_python="3.11").apt_install(
            "build-essential", "curl", "git"
        )
    else:
        built_image = modal.Image.debian_slim(python_version="3.11").apt_install("curl", "git")

    built_image = built_image.pip_install(*LMCACHE_INSTALL_PLAN.pip_packages)
    if LMCACHE_INSTALL_PLAN.source_kind in {"local", "git"}:
        built_image = built_image.env(CUDA_SOURCE_BUILD_ENV)

    if LMCACHE_INSTALL_PLAN.local_source is not None:
        built_image = built_image.add_local_dir(
            local_path=str(LMCACHE_INSTALL_PLAN.local_source),
            remote_path=MODAL_LMCACHE_SOURCE,
            copy=True,
        )
    if VLLM_OVERLAY_PLAN.local_source is not None:
        built_image = built_image.add_local_dir(
            local_path=str(VLLM_OVERLAY_PLAN.local_source / "vllm"),
            remote_path=f"{MODAL_VLLM_SOURCE}/vllm",
            copy=True,
        )
    built_image = (
        built_image.add_local_file(
            local_path=str(REPO_ROOT / "pyproject.toml"),
            remote_path=f"{MODAL_INFERGUARD_SOURCE}/pyproject.toml",
            copy=True,
        )
        .add_local_file(
            local_path=str(REPO_ROOT / "README.md"),
            remote_path=f"{MODAL_INFERGUARD_SOURCE}/README.md",
            copy=True,
        )
        .add_local_file(
            local_path=str(REPO_ROOT / "LICENSE"),
            remote_path=f"{MODAL_INFERGUARD_SOURCE}/LICENSE",
            copy=True,
        )
        .add_local_dir(
            local_path=str(REPO_ROOT / MODAL_INFERGUARD_PACKAGE_DIR),
            remote_path=f"{MODAL_INFERGUARD_SOURCE}/{MODAL_INFERGUARD_PACKAGE_DIR}",
            copy=True,
        )
        .run_commands(
            *LMCACHE_INSTALL_PLAN.run_commands,
            *VLLM_OVERLAY_PLAN.run_commands,
            INFERGUARD_LOCAL_INSTALL_COMMAND,
        )
        .env(
            {
                "HF_HUB_ENABLE_HF_TRANSFER": "1",
                "HF_HOME": "/out/hf-cache",
                "VLLM_CACHE_ROOT": "/out/vllm-cache",
                "PYTHONHASHSEED": "0",
                "LMCACHE_USE_EXPERIMENTAL": "True",
                "LMCACHE_LOCAL_CPU": "True",
                "LMCACHE_MAX_LOCAL_CPU_SIZE": "8.0",
                "LMCACHE_CHUNK_SIZE": "256",
                "VLLM_USE_FLASHINFER_SAMPLER": "0",
                "VLLM_USE_DEEP_GEMM": "0",
                "VLLM_DEEP_GEMM_WARMUP": "skip",
                "VLLM_SKIP_DEEP_GEMM_WARMUP": "1",
                LMCACHE_SOURCE_KIND_RUNTIME_ENV: LMCACHE_INSTALL_PLAN.source_kind,
                LMCACHE_SOURCE_REF_RUNTIME_ENV: LMCACHE_INSTALL_PLAN.source_ref or "",
                LEGACY_LMCACHE_SOURCE_KIND_RUNTIME_ENV: LMCACHE_INSTALL_PLAN.source_kind,
                LEGACY_LMCACHE_SOURCE_REF_RUNTIME_ENV: LMCACHE_INSTALL_PLAN.source_ref or "",
                "INFERGUARD_VLLM_SOURCE_KIND": VLLM_OVERLAY_PLAN.source_kind,
                "INFERGUARD_VLLM_SOURCE_REF": VLLM_OVERLAY_PLAN.source_ref or "",
                PACKET_B_VLLM_GPU_MEMORY_UTILIZATION_ENV: _packet_b_vllm_gpu_memory_utilization(),
                PACKET_B_VLLM_MAX_MODEL_LEN_ENV: str(_packet_b_vllm_max_model_len()),
                PACKET_B_LMCACHE_LOG_LEVEL_ENV: _packet_b_lmcache_log_level() or "",
                "LD_LIBRARY_PATH": (
                    CUDA_SOURCE_BUILD_ENV["LD_LIBRARY_PATH"]
                    if LMCACHE_INSTALL_PLAN.source_kind in {"local", "git"}
                    else "/usr/local/lib/python3.11/site-packages/nvidia/cuda_runtime/lib"
                ),
            }
        )
    )
    return built_image


volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = _build_modal_image()
app = modal.App(APP_NAME, image=image)


@dataclass(frozen=True)
class PacketSpec:
    packet_id: str
    name: str
    workload: str
    output_slug: str | None = None
    l1_size_gb: str = LMCACHE_L1_SIZE_GB
    metrics_sample_rate: float = MP_METRICS_SAMPLE_RATE
    request_count: int | None = None
    l2_configured: bool = False
    l2_adapter: str | None = None
    l2_store_policy: str | None = None
    l2_prefetch_policy: str | None = None
    enable_otel: bool = False
    enable_cache_salt: bool = False
    eviction_policy: str = "LRU"
    vllm_gpu_memory_utilization: str = "0.80"
    vllm_max_model_len: int = MODEL_MAX_LEN
    lmcache_log_level: str | None = None
    strict_inferguard_gate: bool = True
    extra_required_artifacts: tuple[str, ...] = ()
    extra_optional_artifacts: tuple[str, ...] = ()
    sdlc_row_id: str | None = None
    benchmark_id: str | None = None
    workload_profile: str | None = None
    trace_source: str | None = None
    trace_workload_classes: tuple[str, ...] = ()
    requires_l0_block_metrics: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


PACKETS: dict[str, PacketSpec] = {
    "a": PacketSpec(
        packet_id="a",
        name="Packet A MP L1 smoke",
        workload="smoke",
        notes=("L2 is intentionally not configured for Packet A L1-only evidence.",),
    ),
    "b": PacketSpec(
        packet_id="b",
        name="Packet B LC1/C1 long-context agent KV/offload",
        workload="reuse_eviction",
        output_slug="packet-b-lifecycle-reuse-eviction",
        l1_size_gb="1",
        metrics_sample_rate=1.0,
        request_count=48,
        vllm_gpu_memory_utilization=_packet_b_vllm_gpu_memory_utilization(),
        vllm_max_model_len=_packet_b_vllm_max_model_len(),
        lmcache_log_level=_packet_b_lmcache_log_level(),
        strict_inferguard_gate=False,
        sdlc_row_id="C1",
        benchmark_id="LC1",
        workload_profile="long_context_agent_kv_offload",
        trace_source=PACKET_B_TRACE_SOURCE,
        trace_workload_classes=PACKET_B_TRACE_CLASSES,
        requires_l0_block_metrics=True,
        extra_required_artifacts=(
            WORKLOAD_MANIFEST_FILE,
            PACKET_B_LIFECYCLE_EVIDENCE_FILE,
            AGENT_KV_OFFLOAD_REPORT_FILE,
            L0_BLOCK_BOUNDARY_EVIDENCE_FILE,
            "traffic.log",
        ),
        notes=(
            "Metrics sample rate is pinned to 1.0; LC1/C1 workload warms long-context agent prefixes, "
            "pressures unique agent contexts, then retests warm contexts for lifecycle/reuse/eviction proof.",
            "Packet B constrains vLLM GPU KV capacity by default; override with "
            f"`{PACKET_B_VLLM_GPU_MEMORY_UTILIZATION_ENV}` and `{PACKET_B_VLLM_MAX_MODEL_LEN_ENV}`.",
        ),
    ),
    "c": PacketSpec(
        packet_id="c",
        name="Packet C MP L2 fs adapter",
        workload="l2_reuse",
        l2_configured=True,
        l2_adapter="mock",
        l2_store_policy="skip_l1",
        l2_prefetch_policy="default",
        extra_required_artifacts=(L2_CONFIG_FILE,),
        notes=("Mock L2 adapter config is written into the run directory and launched with LMCache MP L2 CLI flags.",),
    ),
    "d": PacketSpec(
        packet_id="d",
        name="Packet D MP OTel tracing",
        workload="otel_reuse",
        enable_otel=True,
        extra_required_artifacts=(LMCACHE_OTEL_FILE, "lmcache-packet/lmcache_otel_evidence.json"),
        notes=("A local OTLP/HTTP collector captures spans to lmcache_otel.jsonl and reports --mp-tracing-enabled.",),
    ),
    "e": PacketSpec(
        packet_id="e",
        name="Packet E trace replay",
        workload="trace_replay",
        notes=("Trace replay artifacts are required for this gate and are wired into compat and coverage reports.",),
    ),
    "f": PacketSpec(
        packet_id="f",
        name="Packet F cache_salt and IsolatedLRU",
        workload="cache_salt_isolated_lru",
        enable_cache_salt=True,
        eviction_policy="IsolatedLRU",
        notes=(
            "Uses tenant cache_salt request fields when vLLM/LMCache accept them; "
            "IsolatedLRU launch support is upstream-version dependent.",
        ),
    ),
}


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
        if text and not text.endswith("\n"):
            handle.write("\n")


def _runtime_lmcache_install_source() -> tuple[str, str]:
    source_kind = _first_env(
        os.environ,
        LMCACHE_SOURCE_KIND_RUNTIME_ENV,
        LEGACY_LMCACHE_SOURCE_KIND_RUNTIME_ENV,
        default=LMCACHE_INSTALL_PLAN.source_kind,
    )
    source_ref = _first_env(
        os.environ,
        LMCACHE_SOURCE_REF_RUNTIME_ENV,
        LEGACY_LMCACHE_SOURCE_REF_RUNTIME_ENV,
        default=LMCACHE_INSTALL_PLAN.source_ref or "",
    )
    return source_kind, source_ref or source_kind


def _run(
    cmd: list[str],
    log_path: Path,
    *,
    timeout: int,
    check: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    _append(log_path, f"$ {_quote_cmd(cmd)}\n")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=check,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        _append(log_path, output)
        _append(log_path, f"TIMEOUT after {timeout}s\n")
        raise
    _append(log_path, result.stdout or "")
    _append(log_path, f"exit_code={result.returncode}\n")
    return result


def _run_best_effort(cmd: list[str], log_path: Path, *, timeout: int) -> int:
    try:
        return _run(cmd, log_path, timeout=timeout).returncode
    except Exception as exc:
        _append(log_path, f"ERROR: {type(exc).__name__}: {exc}\n")
        return 1


def _run_required(cmd: list[str], log_path: Path, *, timeout: int) -> None:
    result = _run(cmd, log_path, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"required command failed with exit code {result.returncode}: {_quote_cmd(cmd)}")


def _curl_to_file(url: str, path: Path, log_path: Path, *, timeout: int = 30) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_best_effort(["curl", "-fsS", url, "-o", str(path)], log_path, timeout=timeout)
    return result == 0


def _write_lmcache_metrics_url(run_dir: Path, url: str) -> None:
    (run_dir / LMCACHE_METRICS_URL_FILE).write_text(f"{url}\n", encoding="utf-8")


def _selected_lmcache_metrics_url(run_dir: Path) -> str:
    path = run_dir / LMCACHE_METRICS_URL_FILE
    if path.exists():
        selected = path.read_text(encoding="utf-8").strip()
        if selected:
            return selected
    return LMCACHE_METRICS_URL


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _wait_for_http(
    url: str,
    log_path: Path,
    *,
    label: str,
    max_wait_seconds: int,
    proc: subprocess.Popen[str] | None,
) -> None:
    deadline = time.monotonic() + max_wait_seconds
    attempt = 0
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"{label} exited before health passed with code {proc.returncode}")
        attempt += 1
        result = _run_best_effort(["curl", "-fsS", url], log_path, timeout=30)
        if result == 0:
            _append(log_path, f"{label} health passed after {attempt} attempts\n")
            return
        time.sleep(10)
    raise RuntimeError(f"{label} did not become healthy at {url}")


def _wait_for_any_http(
    urls: tuple[str, ...],
    log_path: Path,
    *,
    label: str,
    max_wait_seconds: int,
    proc: subprocess.Popen[str] | None,
) -> str:
    deadline = time.monotonic() + max_wait_seconds
    attempt = 0
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"{label} exited before health passed with code {proc.returncode}")
        attempt += 1
        for url in urls:
            result = _run_best_effort(["curl", "-fsS", url], log_path, timeout=30)
            if result == 0:
                _append(log_path, f"{label} health passed at {url} after {attempt} attempts\n")
                return url
        time.sleep(10)
    raise RuntimeError(f"{label} did not become healthy at any of {', '.join(urls)}")


def _quote_cmd(cmd: list[str]) -> str:
    return " ".join(json.dumps(part) if any(char.isspace() for char in part) else part for part in cmd)


def _write_env_snapshot(run_dir: Path) -> None:
    env_path = run_dir / "env.txt"
    _run_best_effort(["nvidia-smi"], env_path, timeout=30)
    _run_best_effort(["python3", "-V"], env_path, timeout=30)
    _run_best_effort(["pip", "freeze"], env_path, timeout=60)
    safe_env = {}
    blocked = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")
    for key, value in sorted(os.environ.items()):
        safe_env[key] = "<redacted>" if any(marker in key.upper() for marker in blocked) else value
    (run_dir / "env.redacted.json").write_text(
        json.dumps(safe_env, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "lmcache_install_plan.json").write_text(
        json.dumps(LMCACHE_INSTALL_PLAN.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "vllm_overlay_plan.json").write_text(
        json.dumps(_runtime_vllm_overlay_plan_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _get_packet(packet: str) -> PacketSpec:
    key = packet.lower().removeprefix("packet-")
    if key not in PACKETS:
        raise ValueError(f"unknown packet {packet!r}; expected one of {', '.join(sorted(PACKETS))}")
    return PACKETS[key]


def _build_lmcache_command(run_dir: Path, spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    cmd = [
        "lmcache",
        "server",
        "--host",
        LMCACHE_HOST,
        "--port",
        str(LMCACHE_ZMQ_PORT),
        "--http-port",
        str(LMCACHE_HTTP_PORT),
        "--l1-size-gb",
        spec.l1_size_gb,
        "--eviction-policy",
        spec.eviction_policy,
        "--prometheus-port",
        str(LMCACHE_PROMETHEUS_PORT),
        "--event-bus-queue-size",
        str(MP_EVENT_BUS_QUEUE_SIZE),
        "--metrics-sample-rate",
        str(spec.metrics_sample_rate),
        "--trace-level",
        "storage",
        "--trace-output",
        str(run_dir / LMCACHE_TRACE_FILE),
        "--lookup-hash-log-dir",
        str(run_dir / LOOKUP_HASH_DIR),
        "--lookup-hash-log-rotation-interval",
        "21600",
        "--lookup-hash-log-rotation-max-size",
        "104857600",
        "--lookup-hash-log-max-files",
        "10",
    ]
    if spec.l2_configured:
        l2_adapter = {
            "type": spec.l2_adapter or "mock",
            "max_size_gb": 80,
            "mock_bandwidth_gb": 4,
        }
        cmd.extend(
            [
                "--l2-store-policy",
                spec.l2_store_policy or "skip_l1",
                "--l2-prefetch-policy",
                spec.l2_prefetch_policy or "default",
                "--l2-adapter",
                json.dumps(l2_adapter, separators=(",", ":")),
            ]
        )
    if spec.enable_otel:
        cmd.extend(["--enable-tracing", "--otlp-endpoint", f"http://127.0.0.1:{OTLP_GRPC_PORT}"])
    return cmd


def _write_l2_config(run_dir: Path, spec: PacketSpec) -> Path | None:
    if not spec.l2_configured:
        return None
    l2_dir = run_dir / "l2-fs"
    l2_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "adapter": {
            "type": spec.l2_adapter or "mock",
            "max_size_gb": 80,
            "mock_bandwidth_gb": 4,
        },
        "l2_store_policy": spec.l2_store_policy or "skip_l1",
        "l2_prefetch_policy": spec.l2_prefetch_policy or "default",
        "path": str(l2_dir),
        "claim_status": "runner_configured_unvalidated_until_modal_packet_runs",
        "notes": [
            "This file is the runner-owned L2 evidence contract.",
            "If the installed LMCache version expects different L2 config keys, "
            "update this file before running Packet C.",
        ],
    }
    config_path = run_dir / L2_CONFIG_FILE
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return config_path


def _build_lmcache_env(run_dir: Path, spec: PacketSpec | None = None) -> dict[str, str]:
    spec = spec or PACKETS["a"]
    env: dict[str, str] = {}
    if spec.enable_otel:
        endpoint = f"http://127.0.0.1:{OTLP_HTTP_PORT}"
        env.update(
            {
                "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": f"{endpoint}/v1/traces",
                "OTEL_TRACES_EXPORTER": "otlp",
                "OTEL_SERVICE_NAME": f"lmcache-mp-packet-{spec.packet_id}",
            }
        )
    if spec.lmcache_log_level:
        env["LMCACHE_LOG_LEVEL"] = spec.lmcache_log_level
    return env


def _launch_lmcache(run_dir: Path, spec: PacketSpec | None = None) -> tuple[subprocess.Popen[str], object]:
    spec = spec or PACKETS["a"]
    log_handle = (run_dir / "lmcache.log").open("w", encoding="utf-8")
    _write_l2_config(run_dir, spec)
    cmd = _build_lmcache_command(run_dir, spec)
    env_update = _build_lmcache_env(run_dir, spec)
    (run_dir / "lmcache_command.json").write_text(
        json.dumps(cmd, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "lmcache_env.json").write_text(
        json.dumps(env_update, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(env_update)
    if spec.packet_id == "b":
        env[L0_BLOCK_BOUNDARY_EVIDENCE_ENV] = str(run_dir / L0_BLOCK_BOUNDARY_EVENTS_FILE)
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=subprocess.STDOUT, text=True, env=env)
    return proc, log_handle


def _build_vllm_command(spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    kv_transfer_config = {
        "kv_connector": "LMCacheMPConnector",
        "kv_role": "kv_both",
        "kv_load_failure_policy": "recompute",
        "kv_connector_extra_config": {
            "lmcache.mp.host": f"tcp://{LMCACHE_HOST}",
            "lmcache.mp.port": LMCACHE_ZMQ_PORT,
            "lmcache.mp.mq_timeout": 10,
        },
    }
    return [
        "vllm",
        "serve",
        MODEL,
        "--kv-transfer-config",
        json.dumps(kv_transfer_config, separators=(",", ":")),
        "--disable-hybrid-kv-cache-manager",
        "--max-model-len",
        str(spec.vllm_max_model_len),
        "--gpu-memory-utilization",
        spec.vllm_gpu_memory_utilization,
        "--port",
        str(VLLM_PORT),
    ]


def _launch_vllm(run_dir: Path, spec: PacketSpec | None = None) -> tuple[subprocess.Popen[str], object]:
    spec = spec or PACKETS["a"]
    log_handle = (run_dir / "vllm.log").open("w", encoding="utf-8")
    cmd = _build_vllm_command(spec)
    (run_dir / "vllm_command.json").write_text(json.dumps(cmd, indent=2) + "\n", encoding="utf-8")
    env = os.environ.copy()
    if spec.packet_id == "b":
        env[L0_BLOCK_BOUNDARY_EVIDENCE_ENV] = str(run_dir / L0_BLOCK_BOUNDARY_EVENTS_FILE)
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=subprocess.STDOUT, text=True, env=env)
    return proc, log_handle


def _capture_safe_http(run_dir: Path) -> dict[str, dict[str, object]]:
    log_path = run_dir / "capture.log"
    endpoints = {
        "root.txt": "/",
        "healthcheck.json": "/healthcheck",
        "status.json": "/status",
        "conf.json": "/conf",
        "version.txt": "/version",
        "lmc_version.txt": "/lmc_version",
        "commit_id.txt": "/commit_id",
        "quota.json": "/api/quota",
        "threads.json": "/threads",
        "periodic_threads.json": "/periodic-threads",
        "periodic_threads_health.json": "/periodic-threads-health",
    }
    results: dict[str, dict[str, object]] = {}
    for filename, path in endpoints.items():
        target = run_dir / "http" / filename
        ok = _curl_to_file(f"{LMCACHE_HTTP_BASE_URL}{path}", target, log_path)
        results[filename] = {"path": path, "ok": ok, "bytes": target.stat().st_size if target.exists() else 0}

    thread_name = _discover_periodic_thread_name(run_dir / "http" / "periodic_threads.json")
    if thread_name:
        filename = "periodic_thread.json"
        path = f"/periodic-threads/{thread_name}"
        target = run_dir / "http" / filename
        ok = _curl_to_file(f"{LMCACHE_HTTP_BASE_URL}{path}", target, log_path)
        results[filename] = {"path": path, "ok": ok, "bytes": target.stat().st_size if target.exists() else 0}

    (run_dir / "http" / "capture_manifest.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return results


def _discover_periodic_thread_name(path: Path) -> str | None:
    payload = _read_json(path)
    if isinstance(payload, list) and payload:
        return str(payload[0])
    if not isinstance(payload, dict):
        return None
    for key in ("periodic_threads", "threads"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict) and first.get("name"):
                return str(first["name"])
    return None


def _capture_metrics(run_dir: Path, suffix: str) -> None:
    log_path = run_dir / "capture.log"
    _curl_to_file(VLLM_METRICS_URL, run_dir / f"vllm_metrics_{suffix}.prom", log_path)
    target = run_dir / f"lmcache_metrics_{suffix}.prom"
    selected = _selected_lmcache_metrics_url(run_dir)
    urls = (selected,) + tuple(url for url in LMCACHE_METRICS_URLS if url != selected)
    for url in urls:
        if _curl_to_file(url, target, log_path):
            _write_lmcache_metrics_url(run_dir, url)
            _append(log_path, f"LMCache metrics {suffix} captured from {url}\n")
            return
    _append(log_path, f"ERROR: LMCache metrics {suffix} failed for {', '.join(urls)}\n")


def _build_trace_replay_command(run_dir: Path, spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    replay_dir = run_dir / TRACE_REPLAY_DIR
    return [
        "lmcache",
        "trace",
        "replay",
        str(run_dir / LMCACHE_TRACE_FILE),
        "--output-dir",
        str(replay_dir),
        "--json",
        "--jsonl-out",
        str(replay_dir / "trace_replay.jsonl"),
        "--l1-size-gb",
        spec.l1_size_gb,
        "--eviction-policy",
        spec.eviction_policy,
        "--disable-metrics",
    ]


def _run_trace_replay(run_dir: Path, spec: PacketSpec | None = None) -> None:
    trace_path = run_dir / LMCACHE_TRACE_FILE
    replay_dir = run_dir / TRACE_REPLAY_DIR
    log_path = run_dir / "trace_replay.log"
    if not trace_path.exists() or trace_path.stat().st_size == 0:
        _append(log_path, f"SKIP: missing or empty {trace_path}\n")
        return

    replay_dir.mkdir(parents=True, exist_ok=True)
    _run_required(
        ["lmcache", "trace", "info", str(trace_path)],
        replay_dir / "trace_info.txt",
        timeout=120,
    )
    _run_required(_build_trace_replay_command(run_dir, spec), log_path, timeout=10 * 60)


def _packet_b_phase_plan(requests: int, spec: PacketSpec) -> list[dict[str, object]]:
    return [
        {
            "phase": "warm",
            "request_count": min(requests, 12),
            "prefix_pattern": "shared-agent-session-prefix",
            "trace_classes": ["coding-long", "prefix-reuse", "session-resume"],
            "intent": "populate reusable long-context agent KV state",
        },
        {
            "phase": "pressure",
            "request_count": max(min(requests, 40) - 12, 0),
            "prefix_pattern": "unique-agent-pressure-window",
            "trace_classes": ["kv-pressure", "tool-heavy", "multi-agent-coding"],
            "intent": "force unique-prefix KV writes and L1 eviction pressure",
        },
        {
            "phase": "retest",
            "request_count": max(requests - 40, 0),
            "prefix_pattern": "shared-agent-session-prefix",
            "trace_classes": ["coding-long", "prefix-reuse", "session-resume"],
            "intent": "revisit warm agent context to expose reuse and L0/L1 lifecycle",
        },
    ]


def _write_workload_manifest(run_dir: Path, spec: PacketSpec, requests: int) -> None:
    if spec.packet_id == "b":
        phases = _packet_b_phase_plan(requests, spec)
    elif spec.workload == "reuse_eviction":
        phases = [
            {
                "phase": "warm",
                "request_count": min(requests, 12),
                "prefix_pattern": "shared-anchor",
                "intent": "populate L0/L1 and create baseline prefix reuse candidates",
            },
            {
                "phase": "pressure",
                "request_count": max(min(requests, 40) - 12, 0),
                "prefix_pattern": "unique-pressure-window",
                "intent": "force unique-prefix writes and L1 eviction pressure",
            },
            {
                "phase": "retest",
                "request_count": max(requests - 40, 0),
                "prefix_pattern": "shared-anchor",
                "intent": "revisit the warm prefix to expose real reuse and evict-reuse gaps",
            },
        ]
    else:
        phases = [
            {
                "phase": "steady",
                "request_count": requests,
                "prefix_pattern": spec.workload,
                "intent": "drive packet workload traffic",
            }
        ]
    payload = {
        "schema_version": "inferguard-lmcache-mp-workload-manifest/v1",
        "packet_id": spec.packet_id,
        "sdlc_row_id": spec.sdlc_row_id,
        "benchmark_id": spec.benchmark_id,
        "workload": spec.workload,
        "workload_profile": spec.workload_profile or spec.workload,
        "trace_source": spec.trace_source,
        "trace_workload_classes": list(spec.trace_workload_classes),
        "request_count": requests,
        "metrics_sample_rate": spec.metrics_sample_rate,
        "l1_size_gb": spec.l1_size_gb,
        "eviction_policy": spec.eviction_policy,
        "vllm_gpu_memory_utilization": spec.vllm_gpu_memory_utilization,
        "vllm_max_model_len": spec.vllm_max_model_len,
        "lmcache_log_level": spec.lmcache_log_level,
        "raw_prompts_recorded": False,
        "request_log": "traffic_requests.jsonl",
        "phases": phases,
        "required_packet_b_telemetry": sorted(PACKET_B_REQUIRED_TELEMETRY)
        if spec.packet_id == "b"
        else [],
    }
    (run_dir / WORKLOAD_MANIFEST_FILE).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _start_otel_collector(run_dir: Path) -> tuple[subprocess.Popen[str], object]:
    log_handle = (run_dir / "otel_collector.log").open("w", encoding="utf-8")
    otel_path = run_dir / LMCACHE_OTEL_FILE
    script = r"""
import json
import sys
from concurrent import futures

import grpc
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2, metrics_service_pb2_grpc
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc

out = sys.argv[1]
port = int(sys.argv[2])


def _append(payload):
    with open(out, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


class TraceService(trace_service_pb2_grpc.TraceServiceServicer):
    def Export(self, request, context):
        payload = MessageToDict(request, preserving_proto_field_name=True)
        _append(payload)
        return trace_service_pb2.ExportTraceServiceResponse()


class MetricsService(metrics_service_pb2_grpc.MetricsServiceServicer):
    def Export(self, request, context):
        return metrics_service_pb2.ExportMetricsServiceResponse()


server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
trace_service_pb2_grpc.add_TraceServiceServicer_to_server(TraceService(), server)
metrics_service_pb2_grpc.add_MetricsServiceServicer_to_server(MetricsService(), server)
server.add_insecure_port(f"127.0.0.1:{port}")
server.start()
print(f"OTLP gRPC collector listening on 127.0.0.1:{port}", flush=True)
server.wait_for_termination()
"""
    proc = subprocess.Popen(
        ["python3", "-c", script, str(otel_path), str(OTLP_GRPC_PORT)],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, log_handle


def _drive_traffic(run_dir: Path, spec: PacketSpec | None = None) -> None:
    spec = spec or PACKETS["a"]
    requests = spec.request_count or {
        "smoke": 10,
        "reuse_eviction": 36,
        "l2_reuse": 24,
        "otel_reuse": 16,
        "trace_replay": 20,
        "cache_salt_isolated_lru": 24,
    }.get(spec.workload, 10)
    _write_workload_manifest(run_dir, spec, requests)
    script = r"""
import json
import sys
import time
import urllib.request

base_url = sys.argv[1]
model = sys.argv[2]
workload = sys.argv[3]
requests = int(sys.argv[4])
cache_salt_enabled = sys.argv[5] == "1"
request_manifest = sys.argv[6]
sdlc_row_id = sys.argv[7]
benchmark_id = sys.argv[8]
workload_profile = sys.argv[9]
trace_source = sys.argv[10]
trace_classes = [item for item in sys.argv[11].split(",") if item]
shared_prefix = "InferGuard LMCache MP shared repeated-prefix validation. " * 220
eviction_prefix = "InferGuard LMCache MP eviction pressure unique block. " * 260
for idx in range(requests):
    if workload == "reuse_eviction":
        phase = ("warm" if idx < 12 else "pressure" if idx < 40 else "retest")
    elif workload == "cache_salt_isolated_lru":
        phase = ("warm" if idx % 6 in {0, 1} else "pressure" if idx % 6 in {2, 3, 4} else "retest")
    else:
        phase = "steady"
    if phase == "pressure":
        prefix = eviction_prefix + (f" unique-window-{idx} " * 384)
        prefix_group = f"pressure-{idx}"
    else:
        prefix = shared_prefix
        prefix_group = "shared-anchor"
    prompt = prefix + f"\nRequest variant {idx % 4}: summarize the observability evidence."
    if phase == "warm":
        trace_class = "coding-long"
    elif phase == "pressure":
        trace_class = trace_classes[idx % len(trace_classes)] if trace_classes else "kv-pressure"
    else:
        trace_class = "session-resume"
    cache_salt = f"tenant-{idx % 2}" if cache_salt_enabled else None
    row = {
        "schema_version": "inferguard-lc1-traffic-request/v1",
        "request_index": idx,
        "trace_id": f"isb1-dsv4-agent/{trace_class}/sanitized-template-{idx:04d}",
        "trace_source": trace_source or None,
        "trace_workload_class": trace_class,
        "phase": phase,
        "prefix_group": prefix_group,
        "prompt_chars": len(prompt),
        "workload": workload,
        "workload_profile": workload_profile or workload,
        "sdlc_row_id": sdlc_row_id or None,
        "benchmark_id": benchmark_id or None,
        "cache_salt": cache_salt,
        "synthetic_redaction_status": "raw_prompt_not_recorded",
        "raw_prompt_recorded": False,
    }
    with open(request_manifest, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "max_tokens": 96,
        "temperature": 0,
        **({"cache_salt": f"tenant-{idx % 2}"} if cache_salt_enabled else {}),
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url + "/v1/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        print(resp.status, resp.read(512).decode("utf-8", errors="replace"))
    time.sleep(1)
"""
    script_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            prefix="inferguard_packet_traffic_",
            suffix=".py",
            delete=False,
        ) as handle:
            handle.write(script)
            script_path = Path(handle.name)
        _run(
            [
                "python3",
                str(script_path),
                VLLM_BASE_URL,
                MODEL,
                spec.workload,
                str(requests),
                "1" if spec.enable_cache_salt else "0",
                str(run_dir / "traffic_requests.jsonl"),
                spec.sdlc_row_id or "",
                spec.benchmark_id or "",
                spec.workload_profile or spec.workload,
                spec.trace_source or "",
                ",".join(spec.trace_workload_classes),
            ],
            run_dir / "traffic.log",
            timeout=30 * 60,
            check=True,
        )
    finally:
        if script_path is not None:
            try:
                script_path.unlink()
            except OSError:
                pass


def _maybe_add_existing(cmd: list[str], flag: str, path: Path) -> None:
    if path.exists():
        cmd.extend([flag, str(path)])


def _metric_values_by_name(prom_text: str) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {}
    for raw_line in prom_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            value = float(parts[1])
        except ValueError:
            continue
        name = parts[0].split("{", 1)[0]
        values.setdefault(name, []).append(value)
    return values


def _metric_family_row(metric_values: dict[str, list[float]], prefixes: tuple[str, ...]) -> dict[str, object]:
    matched = sorted(name for name in metric_values if name.startswith(prefixes))
    populated = sorted(
        name for name in matched if any(value > 0 for value in metric_values.get(name, []))
    )
    if populated:
        status = "populated"
        claim_status = "measured"
    elif matched:
        status = "zero"
        claim_status = "not_measured"
    else:
        status = "missing"
        claim_status = "not_measured"
    return {
        "status": status,
        "claim_status": claim_status,
        "matched_metrics": matched,
        "populated_metrics": populated,
    }


def _write_packet_b_lifecycle_evidence(run_dir: Path, spec: PacketSpec) -> None:
    if spec.packet_id != "b":
        return
    prom_path = run_dir / "lmcache_metrics_loaded.prom"
    prom_text = prom_path.read_text(encoding="utf-8") if prom_path.exists() else ""
    metric_values = _metric_values_by_name(prom_text)
    families = {
        family: _metric_family_row(metric_values, prefixes)
        for family, prefixes in PACKET_B_REQUIRED_TELEMETRY.items()
    }
    missing = [family for family, row in families.items() if row["status"] != "populated"]
    l0_blocked = families.get("l0_lifecycle", {}).get("status") in {"missing", "zero"}
    claim_status = "measured" if not missing else "not_proven"
    payload = {
        "schema_version": "inferguard-lmcache-mp-packet-b-lifecycle/v1",
        "packet_id": spec.packet_id,
        "sdlc_row_id": spec.sdlc_row_id,
        "benchmark_id": spec.benchmark_id,
        "workload_profile": spec.workload_profile,
        "trace_source": spec.trace_source,
        "requires_l0_block_metrics": spec.requires_l0_block_metrics,
        "claim_status": claim_status,
        "acceptance_status": "candidate_measured" if claim_status == "measured" else "blocked",
        "metrics_file": str(prom_path),
        "metrics_sample_rate": spec.metrics_sample_rate,
        "l1_size_gb": spec.l1_size_gb,
        "eviction_policy": spec.eviction_policy,
        "vllm_gpu_memory_utilization": spec.vllm_gpu_memory_utilization,
        "vllm_max_model_len": spec.vllm_max_model_len,
        "lmcache_log_level": spec.lmcache_log_level,
        "workload_manifest": str(run_dir / WORKLOAD_MANIFEST_FILE),
        "required_families": families,
        "missing_required_families": missing,
        "debug_log_markers": _packet_b_debug_log_markers(run_dir),
    }
    if l0_blocked:
        payload.update(
            {
                "blocked_reason": "lmcache_mp_l0_block_metrics_absent",
                "operator_facing_code": "lmcache_mp_l0_lifecycle_missing",
                "recommendation": (
                    "C1 cannot be accepted until lmcache_mp_l0_block_* metrics are emitted "
                    "by the tested LMCache/vLLM ref."
                ),
            }
        )
    (run_dir / PACKET_B_LIFECYCLE_EVIDENCE_FILE).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_l0_block_boundary_events(run_dir: Path) -> list[dict[str, object]]:
    path = run_dir / L0_BLOCK_BOUNDARY_EVENTS_FILE
    events: list[dict[str, object]] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _summarize_l0_block_boundary_events(events: list[dict[str, object]]) -> dict[str, object]:
    stage_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    request_samples: list[dict[str, object]] = []
    total_blocks = 0
    for event in events:
        stage = str(event.get("stage", "unknown"))
        source = str(event.get("source", "unknown"))
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1
        records = event.get("records")
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            block_count = int(record.get("block_count", 0) or 0)
            total_blocks += block_count
            if len(request_samples) < 20:
                request_samples.append(
                    {
                        "stage": stage,
                        "source": source,
                        "request_id": str(record.get("request_id", "")),
                        "block_count": block_count,
                    }
                )
    return {
        "event_count": len(events),
        "stage_counts": stage_counts,
        "source_counts": source_counts,
        "total_reported_blocks": total_blocks,
        "request_samples": request_samples,
    }


def _write_l0_block_boundary_evidence(run_dir: Path, spec: PacketSpec) -> None:
    if spec.packet_id != "b":
        return
    events = _read_l0_block_boundary_events(run_dir)
    summary = _summarize_l0_block_boundary_events(events)
    overlay = _read_json(run_dir / "vllm_overlay_plan.json")
    evidence = _read_json(run_dir / PACKET_B_LIFECYCLE_EVIDENCE_FILE)
    overlay = overlay if isinstance(overlay, dict) else {}
    evidence = evidence if isinstance(evidence, dict) else {}
    payload = {
        "schema_version": "inferguard-l0-block-boundary-evidence/v1",
        "packet_id": spec.packet_id,
        "sdlc_row_id": spec.sdlc_row_id,
        "benchmark_id": spec.benchmark_id,
        "raw_prompts_recorded": False,
        "boundary_event_file": L0_BLOCK_BOUNDARY_EVENTS_FILE,
        "summary": summary,
        "vllm_overlay": {
            "source_kind": overlay.get("source_kind"),
            "source_ref": overlay.get("source_ref"),
            "overlaid_file": overlay.get("overlaid_file"),
            "source_git_head": overlay.get("source_git_head"),
            "source_connector_sha256": overlay.get("source_connector_sha256"),
            "installed_connector_path": overlay.get("installed_connector_path"),
            "installed_connector_sha256": overlay.get("installed_connector_sha256"),
        },
        "packet_b_lifecycle_status": {
            "claim_status": evidence.get("claim_status"),
            "acceptance_status": evidence.get("acceptance_status"),
            "blocked_reason": evidence.get("blocked_reason"),
            "missing_required_families": evidence.get("missing_required_families", []),
        },
        "diagnostic_interpretation": {
            "vllm_attempted": summary["stage_counts"].get("report_block_allocation_attempt", 0) > 0,
            "lmcache_received": summary["stage_counts"].get("report_block_allocation_received", 0) > 0,
            "lmcache_subscriber_processed": (
                summary["stage_counts"].get("l0_lifecycle_subscriber_processed", 0) > 0
            ),
        },
    }
    (run_dir / L0_BLOCK_BOUNDARY_EVIDENCE_FILE).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_agent_kv_offload_report(run_dir: Path, spec: PacketSpec) -> None:
    if spec.packet_id != "b":
        return
    workload = _read_json(run_dir / WORKLOAD_MANIFEST_FILE)
    evidence = _read_json(run_dir / PACKET_B_LIFECYCLE_EVIDENCE_FILE)
    coverage = _read_json(run_dir / "observability_coverage.json")
    compat = _read_json(run_dir / "lmcache_compat_report.json")
    diagnosis = _read_json(run_dir / "diagnose-bottleneck" / "bottleneck_diagnosis.json")
    evidence = evidence if isinstance(evidence, dict) else {}
    workload = workload if isinstance(workload, dict) else {}
    coverage = coverage if isinstance(coverage, dict) else {}
    compat = compat if isinstance(compat, dict) else {}
    diagnosis = diagnosis if isinstance(diagnosis, dict) else {}
    families = evidence.get("required_families") if isinstance(evidence.get("required_families"), dict) else {}
    l0_row = families.get("l0_lifecycle") if isinstance(families.get("l0_lifecycle"), dict) else {}
    offload = coverage.get("kv_cache_offload") if isinstance(coverage.get("kv_cache_offload"), dict) else {}
    payload = {
        "schema_version": "inferguard-agent-kv-offload-report/v1",
        "packet_id": spec.packet_id,
        "sdlc_row_id": spec.sdlc_row_id,
        "benchmark_id": spec.benchmark_id,
        "workload": {
            "profile": spec.workload_profile or spec.workload,
            "legacy_workload": spec.workload,
            "trace_source": spec.trace_source,
            "trace_workload_classes": list(spec.trace_workload_classes),
            "raw_prompts_recorded": workload.get("raw_prompts_recorded", False),
            "request_count": workload.get("request_count", spec.request_count),
            "phases": workload.get("phases") or _packet_b_phase_plan(spec.request_count or 48, spec),
        },
        "vllm": {
            "native_cpu_offload": offload.get("vllm_native_cpu_offload"),
            "external_prefix_cache": offload.get("vllm_external_prefix_cache"),
        },
        "lmcache_mp": {
            "lookup_requested_tokens": families.get("lookup_reuse"),
            "lookup_hit_tokens": families.get("lookup_hits"),
            "l0_l1_store_load_throughput": families.get("l0_l1_throughput"),
            "l1_lifecycle_and_real_reuse": {
                "l1_lifecycle": families.get("l1_lifecycle"),
                "real_reuse": families.get("real_reuse"),
            },
            "l0_lifecycle": {
                "status": l0_row.get("status", "missing"),
                "required_for_c1_acceptance": True,
                "matched_metrics": l0_row.get("matched_metrics", []),
            },
        },
        "diagnosis": {
            "claim_status": evidence.get("claim_status", "not_proven"),
            "acceptance_status": evidence.get("acceptance_status", "blocked"),
            "missing_telemetry": evidence.get("missing_required_families", []),
            "blocked_reason": evidence.get("blocked_reason"),
            "operator_facing_code": evidence.get("operator_facing_code"),
            "diagnose_bottleneck_rule": diagnosis.get("rule_fired"),
            "compat_failure_reasons": compat.get("failure_reasons", []),
            "compat_diagnostic_findings": compat.get("diagnostic_findings", []),
            "concrete_remediation": evidence.get("recommendation"),
        },
        "artifacts": {
            "workload_manifest": WORKLOAD_MANIFEST_FILE,
            "packet_b_lifecycle_evidence": PACKET_B_LIFECYCLE_EVIDENCE_FILE,
            "l0_block_boundary_evidence": L0_BLOCK_BOUNDARY_EVIDENCE_FILE,
            "lmcache_compat_report": "lmcache_compat_report.json",
            "observability_coverage": "observability_coverage.json",
            "bottleneck_diagnosis": "diagnose-bottleneck/bottleneck_diagnosis.json",
        },
    }
    (run_dir / AGENT_KV_OFFLOAD_REPORT_FILE).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _packet_b_debug_log_markers(run_dir: Path) -> dict[str, dict[str, object]]:
    markers = {
        "vllm_gpu_block_allocation": ("gpu block", "gpu blocks", "block allocation", "allocate blocks"),
        "lmcache_l0_block": ("l0 block", "lmcache_mp_l0_block"),
    }
    logs = {
        "vllm.log": run_dir / "vllm.log",
        "lmcache.log": run_dir / "lmcache.log",
    }
    results: dict[str, dict[str, object]] = {}
    for name, needles in markers.items():
        hits: list[str] = []
        for log_name, path in logs.items():
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                lower = line.lower()
                if any(needle in lower for needle in needles):
                    hits.append(f"{log_name}: {line[:500]}")
                    if len(hits) >= 20:
                        break
            if len(hits) >= 20:
                break
        results[name] = {
            "status": "found" if hits else "missing",
            "matched_lines": hits,
        }
    return results


def _build_collect_lmcache_cmd(run_dir: Path, spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    packet_dir = run_dir / "lmcache-packet"
    cmd = [
        "inferguard",
        "collect-lmcache",
        "--output-dir",
        str(packet_dir),
        "--engine-metrics-file",
        str(run_dir / "vllm_metrics_loaded.prom"),
        "--lmcache-metrics-file",
        str(run_dir / "lmcache_metrics_loaded.prom"),
        "--lmcache-http-base-url",
        LMCACHE_HTTP_BASE_URL,
        "--lmcache-health-file",
        str(run_dir / "http" / "healthcheck.json"),
        "--lmcache-status-file",
        str(run_dir / "http" / "status.json"),
        "--lmcache-conf-file",
        str(run_dir / "http" / "conf.json"),
        "--lmcache-threads-file",
        str(run_dir / "http" / "threads.json"),
        "--lmcache-periodic-threads-file",
        str(run_dir / "http" / "periodic_threads.json"),
        "--lmcache-periodic-threads-health-file",
        str(run_dir / "http" / "periodic_threads_health.json"),
        "--lmcache-version-file",
        str(run_dir / "http" / "version.txt"),
        "--lmcache-lmc-version-file",
        str(run_dir / "http" / "lmc_version.txt"),
        "--lmcache-commit-id-file",
        str(run_dir / "http" / "commit_id.txt"),
        "--lmcache-quota-file",
        str(run_dir / "http" / "quota.json"),
        "--engine-log-file",
        str(run_dir / "vllm.log"),
        "--lmcache-log-file",
        str(run_dir / "lmcache.log"),
        "--lmcache-trace-file",
        str(run_dir / LMCACHE_TRACE_FILE),
        "--expect-mode",
        "mp",
        "--mp-prometheus-port",
        str(LMCACHE_PROMETHEUS_PORT),
        "--mp-event-bus-queue-size",
        str(MP_EVENT_BUS_QUEUE_SIZE),
        "--mp-metrics-sample-rate",
        str(spec.metrics_sample_rate),
        "--mp-trace-recording-enabled",
        "--json",
    ]
    if spec.l2_configured:
        cmd.append("--l2-configured")
    if spec.enable_otel:
        cmd.append("--mp-tracing-enabled")
    _maybe_add_existing(cmd, "--lmcache-periodic-thread-file", run_dir / "http" / "periodic_thread.json")
    _maybe_add_existing(cmd, "--lmcache-otel-file", run_dir / LMCACHE_OTEL_FILE)
    _maybe_add_existing(cmd, "--lmcache-trace-replay-output", run_dir / TRACE_REPLAY_DIR)
    _maybe_add_existing(cmd, "--lmcache-lookup-hash-path", run_dir / LOOKUP_HASH_DIR)
    return cmd


def _build_lmcache_compat_cmd(run_dir: Path, spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    packet_dir = run_dir / "lmcache-packet"
    cmd = [
        "inferguard",
        "lmcache-compat",
        "--engine-metrics-file",
        str(run_dir / "vllm_metrics_loaded.prom"),
        "--lmcache-metrics-file",
        str(run_dir / "lmcache_metrics_loaded.prom"),
        "--lmcache-http-evidence-file",
        str(packet_dir / "lmcache_http_evidence.json"),
        "--lmcache-log-evidence-file",
        str(packet_dir / "lmcache_log_evidence.json"),
        "--lmcache-trace-evidence-file",
        str(packet_dir / "lmcache_trace_evidence.json"),
        "--expect-mode",
        "mp",
        "--mp-prometheus-port",
        str(LMCACHE_PROMETHEUS_PORT),
        "--mp-event-bus-queue-size",
        str(MP_EVENT_BUS_QUEUE_SIZE),
        "--mp-metrics-sample-rate",
        str(spec.metrics_sample_rate),
        "--mp-trace-recording-enabled",
        "--output",
        str(run_dir / "lmcache_compat_report.json"),
        "--fail-on",
        "missing-required",
        "--json",
    ]
    if spec.l2_configured:
        cmd.append("--l2-configured")
    if spec.enable_otel:
        cmd.append("--mp-tracing-enabled")
    _maybe_add_existing(cmd, "--lmcache-trace-replay-evidence-file", packet_dir / "lmcache_trace_replay_evidence.json")
    _maybe_add_existing(cmd, "--lmcache-lookup-hash-evidence-file", packet_dir / "lmcache_lookup_hash_evidence.json")
    _maybe_add_existing(cmd, "--lmcache-otel-evidence-file", packet_dir / "lmcache_otel_evidence.json")
    if spec.packet_id == "b":
        _maybe_add_existing(cmd, "--lmcache-l0-boundary-evidence-file", run_dir / L0_BLOCK_BOUNDARY_EVENTS_FILE)
    return cmd


def _build_observability_coverage_cmd(run_dir: Path, spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    packet_dir = run_dir / "lmcache-packet"
    cmd = [
        "inferguard",
        "observability-coverage",
        "--engine-metrics-file",
        str(run_dir / "vllm_metrics_loaded.prom"),
        "--lmcache-metrics-file",
        str(run_dir / "lmcache_metrics_loaded.prom"),
        "--lmcache-http-evidence-file",
        str(packet_dir / "lmcache_http_evidence.json"),
        "--lmcache-log-evidence-file",
        str(packet_dir / "lmcache_log_evidence.json"),
        "--lmcache-trace-evidence-file",
        str(packet_dir / "lmcache_trace_evidence.json"),
        "--expected-engine",
        "vllm",
        "--expect-lmcache-mode",
        "mp",
        "--external-cache-configured",
        "--output",
        str(run_dir / "observability_coverage.json"),
        "--json",
    ]
    if spec.l2_configured:
        cmd.append("--l2-configured")
    _maybe_add_existing(cmd, "--lmcache-trace-replay-evidence-file", packet_dir / "lmcache_trace_replay_evidence.json")
    _maybe_add_existing(cmd, "--lmcache-lookup-hash-evidence-file", packet_dir / "lmcache_lookup_hash_evidence.json")
    _maybe_add_existing(cmd, "--lmcache-otel-evidence-file", packet_dir / "lmcache_otel_evidence.json")
    if spec.packet_id == "b":
        _maybe_add_existing(cmd, "--lmcache-l0-boundary-evidence-file", run_dir / L0_BLOCK_BOUNDARY_EVENTS_FILE)
    return cmd


def _run_inferguard_packet(run_dir: Path, spec: PacketSpec | None = None) -> None:
    spec = spec or PACKETS["a"]
    commands_log = run_dir / "inferguard_commands.log"
    _run_required(_build_collect_lmcache_cmd(run_dir, spec), commands_log, timeout=180)
    if spec.strict_inferguard_gate:
        _run_required(_build_lmcache_compat_cmd(run_dir, spec), commands_log, timeout=180)
        _run_required(_build_observability_coverage_cmd(run_dir, spec), commands_log, timeout=180)
    else:
        _run_best_effort(_build_lmcache_compat_cmd(run_dir, spec), commands_log, timeout=180)
        _run_best_effort(_build_observability_coverage_cmd(run_dir, spec), commands_log, timeout=180)

    job_dir = run_dir / "inferguard-job"
    collect_metrics_cmd = [
        "inferguard",
        "collect-metrics",
        "--output-dir",
        str(job_dir / "metrics"),
        "--engine",
        "vllm",
        "--engine-metrics-url",
        VLLM_METRICS_URL,
        "--lmcache-metrics-url",
        _selected_lmcache_metrics_url(run_dir),
        "--duration-seconds",
        "30",
        "--interval-seconds",
        "5",
        "--keep-raw-samples",
    ]
    _run_best_effort(collect_metrics_cmd, commands_log, timeout=120)
    if (run_dir / "lmcache_compat_report.json").exists():
        (job_dir / "metrics").mkdir(parents=True, exist_ok=True)
        shutil.copy2(run_dir / "lmcache_compat_report.json", job_dir / "metrics" / "lmcache_compat_report.json")
    diagnose_cmd = [
        "inferguard",
        "diagnose-bottleneck",
        "--job-dir",
        str(job_dir),
        "--output-dir",
        str(run_dir / "diagnose-bottleneck"),
    ]
    _run_best_effort(diagnose_cmd, commands_log, timeout=120)


REQUIRED_ARTIFACTS = [
    "env.txt",
    "env.redacted.json",
    "vllm.log",
    "lmcache.log",
    "lmcache_command.json",
    "vllm_command.json",
    LMCACHE_METRICS_URL_FILE,
    "http/capture_manifest.json",
    "vllm_metrics_empty.prom",
    "lmcache_metrics_empty.prom",
    "vllm_metrics_loaded.prom",
    "lmcache_metrics_loaded.prom",
    LMCACHE_TRACE_FILE,
    "trace-replay/trace_info.txt",
    "lmcache-packet/packet_manifest.json",
    "lmcache-packet/lmcache_http_evidence.json",
    "lmcache-packet/lmcache_log_evidence.json",
    "lmcache-packet/lmcache_trace_evidence.json",
    "lmcache-packet/lmcache_trace_replay_evidence.json",
    "lmcache_compat_report.json",
    "observability_coverage.json",
    "artifact_index.json",
]

OPTIONAL_ARTIFACTS = [
    "lmcache_env.json",
    "http/periodic_thread.json",
    "traffic_requests.jsonl",
    L2_CONFIG_FILE,
    LMCACHE_OTEL_FILE,
    "lmcache-packet/lmcache_otel_evidence.json",
    "lmcache-packet/lmcache_lookup_hash_evidence.json",
    "trace-replay/trace_replay.jsonl",
    "diagnose-bottleneck/bottleneck_diagnosis.json",
]


def _missing_artifacts(run_dir: Path, rel_paths: list[str], *, require_nonempty: bool) -> list[str]:
    missing = []
    for rel in rel_paths:
        path = run_dir / rel
        if not path.exists():
            missing.append(rel)
        elif require_nonempty and path.is_file() and path.stat().st_size == 0:
            missing.append(f"{rel} (empty)")
    return missing


def _required_artifacts(spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    return [*REQUIRED_ARTIFACTS, *spec.extra_required_artifacts]


def _optional_artifacts(spec: PacketSpec | None = None) -> list[str]:
    spec = spec or PACKETS["a"]
    return [*OPTIONAL_ARTIFACTS, *spec.extra_optional_artifacts]


def _validate_required_artifacts(run_dir: Path, spec: PacketSpec | None = None) -> None:
    spec = spec or PACKETS["a"]
    _write_summary_and_index(run_dir, spec)
    missing = _missing_artifacts(run_dir, _required_artifacts(spec), require_nonempty=True)
    if missing:
        raise RuntimeError(f"Packet {spec.packet_id.upper()} missing required artifacts: " + ", ".join(missing))
    if spec.packet_id == "b":
        evidence = _read_json(run_dir / PACKET_B_LIFECYCLE_EVIDENCE_FILE)
        missing_families = evidence.get("missing_required_families") if isinstance(evidence, dict) else None
        if not isinstance(evidence, dict) or evidence.get("claim_status") != "measured":
            warning = (
                "Packet B lifecycle evidence is not measured; missing required families: "
                + ", ".join(str(item) for item in (missing_families or []))
            )
            (run_dir / "validation_warnings.log").write_text(warning + "\n", encoding="utf-8")
            print(warning, file=sys.stderr)


def _write_summary_and_index(run_dir: Path, spec: PacketSpec | None = None) -> None:
    spec = spec or PACKETS["a"]
    artifact_index = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file():
            artifact_index.append(
                {
                    "path": str(path.relative_to(run_dir)),
                    "bytes": path.stat().st_size,
                }
            )
    (run_dir / "artifact_index.json").write_text(
        json.dumps(artifact_index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    required_artifacts = _required_artifacts(spec)
    optional_artifacts = _optional_artifacts(spec)
    missing_required = _missing_artifacts(run_dir, required_artifacts, require_nonempty=True)
    missing_optional = _missing_artifacts(run_dir, optional_artifacts, require_nonempty=True)
    source_kind, source_ref = _runtime_lmcache_install_source()
    lines = [
        f"# Packet {spec.packet_id.upper()} LMCache MP Modal Lab Summary",
        "",
        f"- Gate: {spec.name}",
        f"- Model: `{MODEL}`",
        "- Architecture: standalone `lmcache server` plus vLLM `LMCacheMPConnector`.",
        f"- Workload: `{spec.workload}`",
        f"- Metrics sample rate: `{spec.metrics_sample_rate}`",
        f"- L1 size GB: `{spec.l1_size_gb}`",
        f"- vLLM GPU memory utilization: `{spec.vllm_gpu_memory_utilization}`",
        f"- vLLM max model len: `{spec.vllm_max_model_len}`",
        f"- LMCache log level: `{spec.lmcache_log_level or 'default'}`",
        f"- L2 configured: `{spec.l2_configured}`",
        f"- OTel enabled: `{spec.enable_otel}`",
        f"- Eviction policy: `{spec.eviction_policy}`",
        f"- Strict InferGuard gate: `{spec.strict_inferguard_gate}`",
        f"- LMCache install source: `{source_kind}` (`{source_ref}`)",
        "- Required upstream MP metrics: "
        + ", ".join(f"`{name}`" for name in UPSTREAM_LMCACHE_MP_PROMETHEUS_FAMILIES),
        f"- Output directory: `{run_dir}`",
        "",
        "## Required Artifacts",
        "",
    ]
    lines.extend(_artifact_checkbox(run_dir, rel) for rel in required_artifacts)
    lines.extend(
        [
            "",
            "## Optional / Conditional Artifacts",
            "",
        ]
    )
    lines.extend(_artifact_checkbox(run_dir, rel) for rel in optional_artifacts)
    if missing_required:
        lines.extend(["", "## Missing Required", ""])
        lines.extend(f"- `{rel}`" for rel in missing_required)
    if missing_optional:
        lines.extend(["", "## Missing Optional / Conditional", ""])
        lines.extend(f"- `{rel}`" for rel in missing_optional)
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- LMCache and vLLM health failures raise immediately before traffic is sent.",
            "- Packet A treats InferGuard compatibility and coverage failures as fatal; "
            "exploratory packets keep blocked reports for diagnosis.",
            "- Safe LMCache HTTP endpoint captures are recorded in `http/capture_manifest.json`; "
            "destructive endpoints are not called.",
        ]
    )
    lines.extend(f"- {note}" for note in spec.notes)
    lines.append("")
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _artifact_checkbox(run_dir: Path, rel: str) -> str:
    marker = "x" if not _missing_artifacts(run_dir, [rel], require_nonempty=True) else " "
    return f"- [{marker}] `{rel}`"


def _run_dir_for_packet(spec: PacketSpec, timestamp: str) -> Path:
    return OUT_ROOT / (spec.output_slug or f"packet-{spec.packet_id}") / timestamp


def _terminate(proc: subprocess.Popen[str] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=30)


def _close_handles(handles: list[object]) -> None:
    while handles:
        handle = handles.pop()
        try:
            handle.close()
        except Exception:
            pass


def _run_packet(spec: PacketSpec) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = _run_dir_for_packet(spec, timestamp)
    run_dir.mkdir(parents=True, exist_ok=True)
    lmcache_proc: subprocess.Popen[str] | None = None
    vllm_proc: subprocess.Popen[str] | None = None
    otel_proc: subprocess.Popen[str] | None = None
    handles: list[object] = []
    try:
        _write_env_snapshot(run_dir)
        if spec.enable_otel:
            otel_proc, otel_handle = _start_otel_collector(run_dir)
            handles.append(otel_handle)
        lmcache_proc, lmcache_handle = _launch_lmcache(run_dir, spec)
        handles.append(lmcache_handle)
        _wait_for_http(
            LMCACHE_HEALTH_URL,
            run_dir / "health.log",
            label="LMCache HTTP",
            max_wait_seconds=180,
            proc=lmcache_proc,
        )
        lmcache_metrics_url = _wait_for_any_http(
            LMCACHE_METRICS_URLS,
            run_dir / "health.log",
            label="LMCache Prometheus",
            max_wait_seconds=180,
            proc=lmcache_proc,
        )
        _write_lmcache_metrics_url(run_dir, lmcache_metrics_url)
        _capture_safe_http(run_dir)

        vllm_proc, vllm_handle = _launch_vllm(run_dir, spec)
        handles.append(vllm_handle)
        _wait_for_http(
            VLLM_HEALTH_URL,
            run_dir / "health.log",
            label="vLLM",
            max_wait_seconds=30 * 60,
            proc=vllm_proc,
        )
        _capture_metrics(run_dir, "empty")
        _drive_traffic(run_dir, spec)
        _capture_metrics(run_dir, "loaded")
        _write_packet_b_lifecycle_evidence(run_dir, spec)
        _capture_safe_http(run_dir)
        _run_trace_replay(run_dir, spec)
        _run_inferguard_packet(run_dir, spec)
        _write_agent_kv_offload_report(run_dir, spec)
        _write_l0_block_boundary_evidence(run_dir, spec)
        _validate_required_artifacts(run_dir, spec)
    finally:
        _terminate(vllm_proc)
        _terminate(lmcache_proc)
        _terminate(otel_proc)
        _close_handles(handles)
        _write_summary_and_index(run_dir, spec)
        try:
            volume.commit()
        except Exception as exc:
            print(f"Modal volume commit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return str(run_dir)


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_a() -> str:
    return _run_packet(PACKETS["a"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_b() -> str:
    return _run_packet(PACKETS["b"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_c() -> str:
    return _run_packet(PACKETS["c"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_d() -> str:
    return _run_packet(PACKETS["d"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_e() -> str:
    return _run_packet(PACKETS["e"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_f() -> str:
    return _run_packet(PACKETS["f"])


@app.local_entrypoint()
def main(packet: str = "a") -> None:
    key = _get_packet(packet).packet_id
    print(_remote_packet_runner(key).remote())


def _remote_packet_runner(packet: str) -> modal.Function:
    key = _get_packet(packet).packet_id
    runners = {
        "a": run_packet_a,
        "b": run_packet_b,
        "c": run_packet_c,
        "d": run_packet_d,
        "e": run_packet_e,
        "f": run_packet_f,
    }
    return runners[key]


def _run_from_python_api(packet: str) -> None:
    runner = _remote_packet_runner(packet)
    with modal.enable_output():
        with app.run():
            print(runner.remote())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run LMCache MP packet lab through the Modal Python API.")
    parser.add_argument("--packet", default="a", choices=sorted(PACKETS), help="Packet id to run.")
    args = parser.parse_args()
    _run_from_python_api(args.packet)
