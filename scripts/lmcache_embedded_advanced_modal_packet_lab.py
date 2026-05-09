#!/usr/bin/env python3
"""Modal scaffolding for embedded/advanced LMCache live packets H1/H2/H3.

These runners are intentionally separate from ``lmcache_mp_modal_packet_lab.py``
so Packet A-F work can continue independently. They do not move the LMCache
coverage score by themselves; H1/H2/H3 still require real Modal artifacts to be
collected, sanitized, imported as compact live fixtures, and pinned by tests.

Exact run commands are listed by:
    python scripts/lmcache_embedded_advanced_packet_commands.py
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import modal

APP_NAME = "lmcache-embedded-advanced-lab"
VOLUME_NAME = "lmcache-embedded-advanced-lab"
OUT_ROOT = Path("/out")

MODEL = "Qwen/Qwen3-0.6B"
MODEL_MAX_LEN = 8192
ENGINE_HOST = "127.0.0.1"
ENGINE_PORT = 8000
SECONDARY_ENGINE_PORT = 8001
OTLP_HTTP_PORT = 4318

ENGINE_BASE_URL = f"http://{ENGINE_HOST}:{ENGINE_PORT}"
ENGINE_HEALTH_URL = f"{ENGINE_BASE_URL}/health"
ENGINE_METRICS_URL = f"{ENGINE_BASE_URL}/metrics"
SECONDARY_ENGINE_BASE_URL = f"http://{ENGINE_HOST}:{SECONDARY_ENGINE_PORT}"

LMCACHE_CONFIG_FILE = "lmcache_embedded_config.json"
RUNNER_PROOF_FILE = "runner_launch_proof.json"
LMCACHE_OTEL_FILE = "lmcache_otel.jsonl"

REPO_ROOT = Path(__file__).resolve().parents[1]
MODAL_INFERGUARD_SOURCE = "/opt/inferguard"
MODAL_INFERGUARD_FILES = ("pyproject.toml", "README.md", "LICENSE")
MODAL_INFERGUARD_PACKAGE_DIR = "src/inferguard"
MODAL_SOURCE_IGNORE = ("**/__pycache__/**", "**/*.pyc")
INFERGUARD_LOCAL_INSTALL_COMMAND = f"python -m pip install -e {MODAL_INFERGUARD_SOURCE}"

MODAL_LMCACHE_SOURCE = "/opt/lmcache"
MODAL_SGLANG_SOURCE = "/opt/sglang"
LMCACHE_LOCAL_SOURCE_ENV = "INFERGUARD_H_LMCACHE_LOCAL_SOURCE"
SGLANG_LOCAL_SOURCE_ENV = "INFERGUARD_H_SGLANG_LOCAL_SOURCE"
DEFAULT_LMCACHE_LOCAL_SOURCE = REPO_ROOT.parent / "LMCache"
DEFAULT_SGLANG_LOCAL_SOURCE = REPO_ROOT.parent / "sglang"
PINNED_VLLM_PACKAGE = "vllm==0.10.2"
PINNED_TRANSFORMERS_PACKAGE = "transformers==4.57.6"
PINNED_TOKENIZERS_PACKAGE = "tokenizers==0.22.2"
CUDA_DEVEL_IMAGE = "nvidia/cuda:12.8.1-devel-ubuntu22.04"
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
BASE_MODAL_PIP_PACKAGES = (
    PINNED_VLLM_PACKAGE,
    PINNED_TRANSFORMERS_PACKAGE,
    PINNED_TOKENIZERS_PACKAGE,
    "hf-transfer",
    "huggingface-hub",
    "nvidia-cuda-runtime-cu12",
    "ninja",
    "packaging>=24.2",
    "setuptools>=77.0.3,<81.0.0",
    "setuptools_scm>=8",
    "wheel",
)
LMCACHE_LOCAL_INSTALL_COMMAND = f"python -m pip install -e {MODAL_LMCACHE_SOURCE} --no-build-isolation --no-deps"
SGLANG_LOCAL_INSTALL_COMMAND = (
    f"python -m pip install -e {MODAL_SGLANG_SOURCE}/python --no-build-isolation"
)


def _optional_local_source(env_key: str, default_path: Path) -> Path | None:
    raw = os.environ.get(env_key, "").strip()
    if raw:
        return Path(raw).expanduser()
    if default_path.exists():
        return default_path
    return None


LMCACHE_LOCAL_SOURCE = _optional_local_source(LMCACHE_LOCAL_SOURCE_ENV, DEFAULT_LMCACHE_LOCAL_SOURCE)
SGLANG_LOCAL_SOURCE = _optional_local_source(SGLANG_LOCAL_SOURCE_ENV, DEFAULT_SGLANG_LOCAL_SOURCE)


def _runtime_env() -> dict[str, str]:
    return {
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
        **CUDA_SOURCE_BUILD_ENV,
        "INFERGUARD_H_LMCACHE_SOURCE_REF": str(LMCACHE_LOCAL_SOURCE or "pypi"),
        "INFERGUARD_H_SGLANG_SOURCE_REF": str(SGLANG_LOCAL_SOURCE or "not-installed"),
        "INFERGUARD_H_VLLM_PACKAGE": PINNED_VLLM_PACKAGE,
        "INFERGUARD_H_TRANSFORMERS_PACKAGE": PINNED_TRANSFORMERS_PACKAGE,
        "INFERGUARD_H_TOKENIZERS_PACKAGE": PINNED_TOKENIZERS_PACKAGE,
    }


def _with_local_runtime_sources(built_image: modal.Image) -> modal.Image:
    if LMCACHE_LOCAL_SOURCE is not None:
        built_image = built_image.add_local_dir(
            local_path=str(LMCACHE_LOCAL_SOURCE),
            remote_path=MODAL_LMCACHE_SOURCE,
            copy=True,
        )
    if SGLANG_LOCAL_SOURCE is not None:
        built_image = built_image.add_local_dir(
            local_path=str(SGLANG_LOCAL_SOURCE),
            remote_path=MODAL_SGLANG_SOURCE,
            copy=True,
        )
    return built_image


def _runtime_install_commands() -> tuple[str, ...]:
    commands = []
    if LMCACHE_LOCAL_SOURCE is not None:
        commands.append(LMCACHE_LOCAL_INSTALL_COMMAND)
    commands.append(INFERGUARD_LOCAL_INSTALL_COMMAND)
    return tuple(commands)


def _build_modal_image() -> modal.Image:
    built_image = (
        modal.Image.from_registry(CUDA_DEVEL_IMAGE, add_python="3.11")
        .apt_install("build-essential", "curl", "git")
        .pip_install(*BASE_MODAL_PIP_PACKAGES)
    )
    built_image = _with_local_runtime_sources(built_image)
    return (
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
            ignore=MODAL_SOURCE_IGNORE,
        )
        .env(_runtime_env())
        .run_commands(*_runtime_install_commands())
    )


volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = _build_modal_image()

app = modal.App(APP_NAME, image=image)


@dataclass(frozen=True)
class EmbeddedAdvancedPacketSpec:
    """H1/H2/H3 runner contract.

    ``score_status`` is deliberately fixed as not scored. A real live packet must
    prove the lane before SDLC 195 can move.
    """

    packet_id: str
    sdlc_id: str
    name: str
    engine: str
    expected_engine: str
    expect_lmcache_mode: str
    workload: str
    output_slug: str
    primary_port: int = ENGINE_PORT
    secondary_port: int | None = None
    enable_otel: bool = False
    enable_cacheblend: bool = False
    enable_p2p: bool = False
    enable_pd: bool = False
    external_cache_configured: bool = False
    disaggregated_or_external_cache: bool = False
    connector_proof: tuple[str, ...] = ()
    cache_proof: tuple[str, ...] = ()
    extra_required_artifacts: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)
    score_status: str = "runner_scaffold_only_not_live_validated"


PACKETS: dict[str, EmbeddedAdvancedPacketSpec] = {
    "h1": EmbeddedAdvancedPacketSpec(
        packet_id="h1",
        sdlc_id="H1",
        name="H1 embedded vLLM LMCacheConnectorV1",
        engine="vllm",
        expected_engine="vllm",
        expect_lmcache_mode="embedded",
        workload="repeated_prefix_vllm_embedded",
        output_slug="packet-h1-embedded-vllm",
        external_cache_configured=True,
        connector_proof=("LMCacheConnectorV1", "--kv-transfer-config"),
        extra_required_artifacts=(),
        notes=(
            "Uses vLLM embedded/in-process --kv-transfer-config with "
            "LMCacheConnectorV1, not LMCacheMPConnector.",
        ),
    ),
    "h2": EmbeddedAdvancedPacketSpec(
        packet_id="h2",
        sdlc_id="H2",
        name="H2 SGLang --enable-lmcache embedded/layerwise",
        engine="sglang",
        expected_engine="sglang",
        expect_lmcache_mode="embedded",
        workload="repeated_prefix_sglang_lmcache",
        output_slug="packet-h2-sglang-embedded",
        connector_proof=("LMCacheLayerwiseConnector", "--enable-lmcache"),
        cache_proof=("LMCRadixCache",),
        extra_required_artifacts=(),
        notes=("SGLang standalone-MP is not claimed; this runner targets embedded/layerwise.",),
    ),
    "h3-cacheblend": EmbeddedAdvancedPacketSpec(
        packet_id="h3-cacheblend",
        sdlc_id="H3",
        name="H3 CacheBlend metrics and cb.* spans",
        engine="vllm",
        expected_engine="vllm",
        expect_lmcache_mode="auto",
        workload="cacheblend_reuse",
        output_slug="packet-h3-cacheblend",
        enable_otel=True,
        enable_cacheblend=True,
        external_cache_configured=True,
        connector_proof=("CacheBlend",),
        cache_proof=("lmcache_blend_*", "cb.*"),
        extra_required_artifacts=(LMCACHE_OTEL_FILE,),
        notes=("Requires live lmcache_blend_* metrics plus cb.* OTel spans before scoring.",),
    ),
    "h3-p2p": EmbeddedAdvancedPacketSpec(
        packet_id="h3-p2p",
        sdlc_id="H3",
        name="H3 two-engine P2P embedded transfer",
        engine="vllm",
        expected_engine="vllm",
        expect_lmcache_mode="embedded",
        workload="two_engine_p2p",
        output_slug="packet-h3-p2p",
        secondary_port=SECONDARY_ENGINE_PORT,
        enable_p2p=True,
        external_cache_configured=True,
        disaggregated_or_external_cache=True,
        connector_proof=("LMCacheConnectorV1", "enable_p2p"),
        cache_proof=("lmcache:p2p_*",),
        extra_required_artifacts=("secondary_engine.log", "combined_engine_metrics_loaded.prom"),
        notes=("Starts two engine roles and records peer/transfer log evidence.",),
    ),
    "h3-pd": EmbeddedAdvancedPacketSpec(
        packet_id="h3-pd",
        sdlc_id="H3",
        name="H3 1p1d PD role/proxy/NIXL packet",
        engine="vllm",
        expected_engine="vllm",
        expect_lmcache_mode="embedded",
        workload="pd_1p1d_nixl",
        output_slug="packet-h3-pd",
        secondary_port=SECONDARY_ENGINE_PORT,
        enable_pd=True,
        external_cache_configured=True,
        disaggregated_or_external_cache=True,
        connector_proof=("NIXL", "kv_producer", "kv_consumer"),
        cache_proof=("role+proxy+NIXL",),
        extra_required_artifacts=("secondary_engine.log", "combined_engine_metrics_loaded.prom"),
        notes=("Records prefiller/decoder role and NIXL/proxy evidence; no score without live proof.",),
    ),
}


def packet_specs() -> dict[str, EmbeddedAdvancedPacketSpec]:
    return dict(PACKETS)


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
        if text and not text.endswith("\n"):
            handle.write("\n")


def _run(
    cmd: list[str],
    log_path: Path,
    *,
    timeout: int,
    check: bool = False,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    _append(log_path, f"$ {_quote_cmd(cmd)}\n")
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=run_env,
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


def _quote_cmd(cmd: list[str]) -> str:
    return " ".join(json.dumps(part) if any(char.isspace() for char in part) else part for part in cmd)


def _curl_to_file(url: str, path: Path, log_path: Path, *, timeout: int = 30) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_best_effort(["curl", "-fsS", url, "-o", str(path)], log_path, timeout=timeout)
    return result == 0


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
        if _run_best_effort(["curl", "-fsS", url], log_path, timeout=30) == 0:
            _append(log_path, f"{label} health passed after {attempt} attempts\n")
            return
        time.sleep(10)
    raise RuntimeError(f"{label} did not become healthy at {url}")


def _ensure_sglang_runtime(run_dir: Path) -> None:
    if SGLANG_LOCAL_SOURCE is None:
        raise FileNotFoundError(
            f"{SGLANG_LOCAL_SOURCE_ENV} must point to an SGLang checkout for H2"
        )
    _run_required(["sh", "-lc", SGLANG_LOCAL_INSTALL_COMMAND], run_dir / "setup.log", timeout=20 * 60)


def _write_env_snapshot(run_dir: Path) -> None:
    env_path = run_dir / "env.txt"
    _run_best_effort(["nvidia-smi"], env_path, timeout=30)
    _run_best_effort(["python3", "-V"], env_path, timeout=30)
    _run_best_effort(["pip", "freeze"], env_path, timeout=60)
    blocked = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")
    safe_env = {
        key: "<redacted>" if any(marker in key.upper() for marker in blocked) else value
        for key, value in sorted(os.environ.items())
    }
    (run_dir / "env.redacted.json").write_text(
        json.dumps(safe_env, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _get_packet(packet: str) -> EmbeddedAdvancedPacketSpec:
    key = packet.lower().removeprefix("packet-")
    if key not in PACKETS:
        expected = ", ".join(sorted(PACKETS))
        raise ValueError(f"unknown packet {packet!r}; expected one of {expected}")
    return PACKETS[key]


def _write_lmcache_config(run_dir: Path, spec: EmbeddedAdvancedPacketSpec) -> Path:
    config = {
        "schema_version": "inferguard-lmcache-embedded-advanced-runner/v1",
        "packet_id": spec.packet_id,
        "sdlc_id": spec.sdlc_id,
        "claim_status": spec.score_status,
        "engine": spec.engine,
        "workload": spec.workload,
        "expected_connector_evidence": list(spec.connector_proof),
        "expected_cache_evidence": list(spec.cache_proof),
        "local_cpu": True,
        "max_local_cpu_size": 8.0,
        "chunk_size": 256,
        "cacheblend": {"enabled": spec.enable_cacheblend},
        "p2p": {
            "enabled": spec.enable_p2p,
            "instance_ids": ["inferguard-peer-a", "inferguard-peer-b"] if spec.enable_p2p else [],
            "transfer_mode": "tcp",
        },
        "pd": {
            "enabled": spec.enable_pd,
            "prefill_role": "kv_producer" if spec.enable_pd else None,
            "decode_role": "kv_consumer" if spec.enable_pd else None,
            "transport": "nixl",
            "proxy": "local-runner-scaffold",
        },
        "notes": [
            "Runner config is launch/config evidence only.",
            "SDLC score remains unchanged until a real packet is imported as a live fixture.",
        ],
    }
    config_path = run_dir / LMCACHE_CONFIG_FILE
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return config_path


def _build_runner_env(run_dir: Path, spec: EmbeddedAdvancedPacketSpec, *, role: str = "primary") -> dict[str, str]:
    env = {
        "LMCACHE_CONFIG_FILE": str(run_dir / LMCACHE_CONFIG_FILE),
        "LMCACHE_LOCAL_CPU": "True",
        "LMCACHE_MAX_LOCAL_CPU_SIZE": "8.0",
        "LMCACHE_CHUNK_SIZE": "256",
        "PYTHONHASHSEED": "0",
    }
    if spec.enable_cacheblend:
        env.update(
            {
                "LMCACHE_ENABLE_CACHEBLEND": "True",
                "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{OTLP_HTTP_PORT}",
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": f"http://127.0.0.1:{OTLP_HTTP_PORT}/v1/traces",
                "OTEL_TRACES_EXPORTER": "otlp",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
                "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/json",
                "OTEL_SERVICE_NAME": "inferguard-h3-cacheblend",
            }
        )
    if spec.enable_p2p:
        env.update(
            {
                "LMCACHE_ENABLE_P2P": "True",
                "LMCACHE_INSTANCE_ID": "inferguard-peer-a" if role == "primary" else "inferguard-peer-b",
                "LMCACHE_P2P_HOST": ENGINE_HOST,
                "LMCACHE_P2P_INIT_PORT": "6200" if role == "primary" else "6201",
                "LMCACHE_P2P_LOOKUP_PORT": "6300" if role == "primary" else "6301",
                "LMCACHE_P2P_CONTROLLER_URL": "http://127.0.0.1:6400",
                "LMCACHE_P2P_TRANSFER_MODE": "tcp",
            }
        )
    if spec.enable_pd:
        env.update(
            {
                "LMCACHE_ENABLE_PD": "True",
                "LMCACHE_PD_ROLE": "prefill" if role == "primary" else "decode",
                "LMCACHE_PD_PROXY_URL": "http://127.0.0.1:6500",
                "LMCACHE_NIXL_ROLE": "producer" if role == "primary" else "consumer",
                "LMCACHE_NIXL_BIND_HOST": ENGINE_HOST,
                "LMCACHE_NIXL_PORT": "6600" if role == "primary" else "6601",
            }
        )
    return env


def _build_vllm_embedded_command(
    run_dir: Path, spec: EmbeddedAdvancedPacketSpec | None = None, *, port: int = ENGINE_PORT
) -> list[str]:
    spec = spec or PACKETS["h1"]
    cmd = [
        "vllm",
        "serve",
        MODEL,
        "--max-model-len",
        str(MODEL_MAX_LEN),
        "--gpu-memory-utilization",
        "0.80",
        "--port",
        str(port),
    ]
    if spec.enable_pd:
        role = "kv_producer" if port == spec.primary_port else "kv_consumer"
        transfer_config = {
            "kv_connector": "NixlConnector",
            "kv_role": role,
            "kv_connector_extra_config": {
                "lmcache_pd_proxy": "http://127.0.0.1:6500",
                "transport": "nixl",
            },
        }
    else:
        transfer_config = {"kv_connector": "LMCacheConnectorV1", "kv_role": "kv_both"}
    cmd.extend(
        [
            "--kv-transfer-config",
            json.dumps(transfer_config, separators=(",", ":")),
        ]
    )
    return cmd


def _build_sglang_embedded_command(port: int = ENGINE_PORT) -> list[str]:
    return [
        "python3",
        "-m",
        "sglang.launch_server",
        "--model-path",
        MODEL,
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--enable-lmcache",
        "--max-total-tokens",
        str(MODEL_MAX_LEN),
    ]


def _build_engine_command(
    run_dir: Path,
    spec: EmbeddedAdvancedPacketSpec,
    *,
    role: str = "primary",
    port: int | None = None,
) -> list[str]:
    selected_port = port if port is not None else spec.primary_port
    if spec.engine == "sglang":
        return _build_sglang_embedded_command(selected_port)
    return _build_vllm_embedded_command(run_dir, spec, port=selected_port)


def _write_launch_proof(run_dir: Path, spec: EmbeddedAdvancedPacketSpec) -> Path:
    proof = {
        "schema_version": "inferguard-lmcache-live-runner-proof/v1",
        "packet_id": spec.packet_id,
        "sdlc_id": spec.sdlc_id,
        "claim_status": spec.score_status,
        "expected_engine": spec.expected_engine,
        "expect_lmcache_mode": spec.expect_lmcache_mode,
        "required_live_proof": _required_live_proof(spec),
        "primary_command": _build_engine_command(run_dir, spec),
        "secondary_command": _build_engine_command(
            run_dir, spec, role="secondary", port=spec.secondary_port
        )
        if spec.secondary_port is not None
        else None,
        "environment": _build_runner_env(run_dir, spec),
        "secondary_environment": _build_runner_env(run_dir, spec, role="secondary")
        if spec.secondary_port is not None
        else None,
        "notes": list(spec.notes),
    }
    proof_path = run_dir / RUNNER_PROOF_FILE
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return proof_path


def _required_live_proof(spec: EmbeddedAdvancedPacketSpec) -> list[str]:
    if spec.packet_id == "h1":
        return [
            "vLLM command/config proves LMCacheConnectorV1 via --kv-transfer-config",
            "engine /metrics includes embedded lmcache:* or lmcache_* production counters",
            "repeated-prefix traffic produces nonzero reuse/hit metrics",
            "logs prove store/retrieve/lookup activity",
        ]
    if spec.packet_id == "h2":
        return [
            "SGLang launch includes --enable-lmcache and LMCACHE_CONFIG_FILE",
            "launch/log evidence names LMCacheLayerwiseConnector and LMCRadixCache",
            "SGLang /metrics and LMCache embedded metrics are captured together",
        ]
    if spec.packet_id == "h3-cacheblend":
        return ["lmcache_blend_* metrics", "cb.* OTel spans", "CacheBlend logs/config"]
    if spec.packet_id == "h3-p2p":
        return ["two engine logs", "lmcache:p2p_* metrics or transfer logs", "peer/controller evidence"]
    if spec.packet_id == "h3-pd":
        return ["prefill/decode role configs", "NIXL/proxy logs", "KV transfer metrics or logs"]
    return []


def _launch_engine(
    run_dir: Path,
    spec: EmbeddedAdvancedPacketSpec,
    *,
    role: str = "primary",
    port: int | None = None,
) -> tuple[subprocess.Popen[str], object]:
    log_name = "engine.log" if role == "primary" else "secondary_engine.log"
    log_handle = (run_dir / log_name).open("w", encoding="utf-8")
    cmd = _build_engine_command(run_dir, spec, role=role, port=port)
    env = os.environ.copy()
    env.update(_build_runner_env(run_dir, spec, role=role))
    (run_dir / f"{role}_engine_command.json").write_text(
        json.dumps(cmd, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / f"{role}_engine_env.json").write_text(
        json.dumps(_build_runner_env(run_dir, spec, role=role), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=subprocess.STDOUT, text=True, env=env)
    return proc, log_handle


def _start_otel_collector(run_dir: Path) -> tuple[subprocess.Popen[str], object]:
    log_handle = (run_dir / "otel_collector.log").open("w", encoding="utf-8")
    otel_path = run_dir / LMCACHE_OTEL_FILE
    script = r'''
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

out = sys.argv[1]
port = int(sys.argv[2])

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length", "0") or "0")
        body = self.rfile.read(length)
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "path": self.path,
                "content_type": self.headers.get("content-type"),
                "body_preview": body.decode("utf-8", errors="replace")[:20000],
                "body_bytes": len(body),
            })
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                payload = record
            handle.write(json.dumps(payload) + "\n")
        self.send_response(200)
        self.end_headers()

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
'''
    proc = subprocess.Popen(
        ["python3", "-c", script, str(otel_path), str(OTLP_HTTP_PORT)],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, log_handle


def _drive_traffic(run_dir: Path, spec: EmbeddedAdvancedPacketSpec) -> None:
    requests = {
        "repeated_prefix_vllm_embedded": 16,
        "repeated_prefix_sglang_lmcache": 16,
        "cacheblend_reuse": 20,
        "two_engine_p2p": 12,
        "pd_1p1d_nixl": 12,
    }.get(spec.workload, 10)
    endpoint = ENGINE_BASE_URL
    api_path = "/v1/completions"
    script = r'''
import json
import sys
import time
import urllib.request

base_url = sys.argv[1]
model = sys.argv[2]
api_path = sys.argv[3]
requests = int(sys.argv[4])
shared_prefix = "InferGuard embedded LMCache repeated-prefix validation. " * 220
for idx in range(requests):
    prompt = shared_prefix + f"\nRequest variant {idx % 4}: summarize the cache evidence."
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "max_tokens": 96,
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url + api_path,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        print(resp.status, resp.read(512).decode("utf-8", errors="replace"))
    time.sleep(1)
'''
    _run(
        ["python3", "-c", script, endpoint, MODEL, api_path, str(requests)],
        run_dir / "traffic.log",
        timeout=30 * 60,
        check=True,
    )


def _capture_metrics(run_dir: Path, suffix: str) -> None:
    log_path = run_dir / "capture.log"
    primary = run_dir / f"engine_metrics_{suffix}.prom"
    secondary = run_dir / f"secondary_engine_metrics_{suffix}.prom"
    _curl_to_file(ENGINE_METRICS_URL, primary, log_path)
    if (run_dir / "secondary_engine.log").exists():
        _curl_to_file(f"{SECONDARY_ENGINE_BASE_URL}/metrics", secondary, log_path)
        _write_combined_metrics(run_dir, suffix)


def _write_combined_metrics(run_dir: Path, suffix: str) -> Path:
    combined = run_dir / f"combined_engine_metrics_{suffix}.prom"
    parts = []
    for source in (
        run_dir / f"engine_metrics_{suffix}.prom",
        run_dir / f"secondary_engine_metrics_{suffix}.prom",
    ):
        if source.exists():
            parts.append(f"# inferguard_source_file={source.name}\n{source.read_text(encoding='utf-8')}")
    combined.write_text("\n".join(parts), encoding="utf-8")
    return combined


def _metrics_input_path(run_dir: Path, spec: EmbeddedAdvancedPacketSpec) -> Path:
    if spec.secondary_port is not None:
        return run_dir / "combined_engine_metrics_loaded.prom"
    return run_dir / "engine_metrics_loaded.prom"


def _maybe_add_existing(cmd: list[str], flag: str, path: Path) -> None:
    if path.exists():
        cmd.extend([flag, str(path)])


def _build_collect_lmcache_cmd(run_dir: Path, spec: EmbeddedAdvancedPacketSpec) -> list[str]:
    packet_dir = run_dir / "lmcache-packet"
    metrics_path = _metrics_input_path(run_dir, spec)
    cmd = [
        "inferguard",
        "collect-lmcache",
        "--output-dir",
        str(packet_dir),
        "--engine-metrics-file",
        str(metrics_path),
        "--lmcache-metrics-file",
        str(metrics_path),
        "--engine-log-file",
        str(run_dir / "engine.log"),
        "--expect-mode",
        spec.expect_lmcache_mode,
        "--json",
    ]
    _maybe_add_existing(cmd, "--lmcache-log-file", run_dir / "secondary_engine.log")
    _maybe_add_existing(cmd, "--lmcache-otel-file", run_dir / LMCACHE_OTEL_FILE)
    return cmd


def _build_lmcache_compat_cmd(run_dir: Path, spec: EmbeddedAdvancedPacketSpec) -> list[str]:
    packet_dir = run_dir / "lmcache-packet"
    metrics_path = _metrics_input_path(run_dir, spec)
    cmd = [
        "inferguard",
        "lmcache-compat",
        "--engine-metrics-file",
        str(metrics_path),
        "--lmcache-metrics-file",
        str(metrics_path),
        "--lmcache-log-evidence-file",
        str(packet_dir / "lmcache_log_evidence.json"),
        "--expect-mode",
        spec.expect_lmcache_mode,
        "--output",
        str(run_dir / "lmcache_compat_report.json"),
        "--fail-on",
        "missing-required",
        "--json",
    ]
    _maybe_add_existing(cmd, "--lmcache-otel-evidence-file", packet_dir / "lmcache_otel_evidence.json")
    return cmd


def _build_observability_coverage_cmd(run_dir: Path, spec: EmbeddedAdvancedPacketSpec) -> list[str]:
    packet_dir = run_dir / "lmcache-packet"
    metrics_path = _metrics_input_path(run_dir, spec)
    cmd = [
        "inferguard",
        "observability-coverage",
        "--engine-metrics-file",
        str(metrics_path),
        "--lmcache-metrics-file",
        str(metrics_path),
        "--lmcache-log-evidence-file",
        str(packet_dir / "lmcache_log_evidence.json"),
        "--expected-engine",
        spec.expected_engine,
        "--expect-lmcache-mode",
        spec.expect_lmcache_mode,
        "--output",
        str(run_dir / "observability_coverage.json"),
        "--json",
    ]
    if spec.external_cache_configured:
        cmd.append("--external-cache-configured")
    if spec.disaggregated_or_external_cache:
        cmd.append("--disaggregated-or-external-cache")
    _maybe_add_existing(cmd, "--lmcache-otel-evidence-file", packet_dir / "lmcache_otel_evidence.json")
    return cmd


def _run_inferguard_packet(run_dir: Path, spec: EmbeddedAdvancedPacketSpec) -> None:
    commands_log = run_dir / "inferguard_commands.log"
    _run_required(_build_collect_lmcache_cmd(run_dir, spec), commands_log, timeout=180)
    _run_required(_build_lmcache_compat_cmd(run_dir, spec), commands_log, timeout=180)
    _run_required(_build_observability_coverage_cmd(run_dir, spec), commands_log, timeout=180)

    job_dir = run_dir / "inferguard-job"
    collect_metrics_cmd = [
        "inferguard",
        "collect-metrics",
        "--output-dir",
        str(job_dir / "metrics"),
        "--engine",
        spec.expected_engine,
        "--engine-metrics-url",
        ENGINE_METRICS_URL,
        "--lmcache-metrics-url",
        ENGINE_METRICS_URL,
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
    "engine.log",
    "primary_engine_command.json",
    "primary_engine_env.json",
    LMCACHE_CONFIG_FILE,
    RUNNER_PROOF_FILE,
    "engine_metrics_empty.prom",
    "engine_metrics_loaded.prom",
    "lmcache-packet/packet_manifest.json",
    "lmcache-packet/lmcache_log_evidence.json",
    "lmcache_compat_report.json",
    "observability_coverage.json",
    "artifact_index.json",
]

OPTIONAL_ARTIFACTS = [
    "secondary_engine.log",
    "secondary_engine_metrics_loaded.prom",
    LMCACHE_OTEL_FILE,
    "lmcache-packet/lmcache_otel_evidence.json",
    "diagnose-bottleneck/bottleneck_diagnosis.json",
]


def _required_artifacts(spec: EmbeddedAdvancedPacketSpec) -> list[str]:
    return list(dict.fromkeys([*REQUIRED_ARTIFACTS, *spec.extra_required_artifacts]))


def _optional_artifacts(_spec: EmbeddedAdvancedPacketSpec) -> list[str]:
    return list(OPTIONAL_ARTIFACTS)


def _missing_artifacts(run_dir: Path, rel_paths: list[str], *, require_nonempty: bool) -> list[str]:
    missing = []
    for rel in rel_paths:
        path = run_dir / rel
        if not path.exists():
            missing.append(rel)
        elif require_nonempty and path.is_file() and path.stat().st_size == 0:
            missing.append(f"{rel} (empty)")
    return missing


def _validate_required_artifacts(run_dir: Path, spec: EmbeddedAdvancedPacketSpec) -> None:
    _write_summary_and_index(run_dir, spec)
    missing = _missing_artifacts(run_dir, _required_artifacts(spec), require_nonempty=True)
    if missing:
        raise RuntimeError(f"Packet {spec.packet_id} missing required artifacts: " + ", ".join(missing))


def _write_summary_and_index(run_dir: Path, spec: EmbeddedAdvancedPacketSpec) -> None:
    artifact_index = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file():
            artifact_index.append({"path": str(path.relative_to(run_dir)), "bytes": path.stat().st_size})
    (run_dir / "artifact_index.json").write_text(
        json.dumps(artifact_index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    required = _required_artifacts(spec)
    optional = _optional_artifacts(spec)
    missing_required = _missing_artifacts(run_dir, required, require_nonempty=True)
    missing_optional = _missing_artifacts(run_dir, optional, require_nonempty=True)
    lines = [
        f"# {spec.sdlc_id} {spec.name} Modal Lab Summary",
        "",
        f"- Packet: `{spec.packet_id}`",
        f"- Score status: `{spec.score_status}`",
        f"- Engine: `{spec.engine}`",
        f"- Expected engine: `{spec.expected_engine}`",
        f"- Expected LMCache mode: `{spec.expect_lmcache_mode}`",
        f"- Workload: `{spec.workload}`",
        f"- Output directory: `{run_dir}`",
        "",
        "## Required Artifacts",
        "",
    ]
    lines.extend(_artifact_checkbox(run_dir, rel) for rel in required)
    lines.extend(["", "## Optional / Conditional Artifacts", ""])
    lines.extend(_artifact_checkbox(run_dir, rel) for rel in optional)
    if missing_required:
        lines.extend(["", "## Missing Required", ""])
        lines.extend(f"- `{rel}`" for rel in missing_required)
    if missing_optional:
        lines.extend(["", "## Missing Optional / Conditional", ""])
        lines.extend(f"- `{rel}`" for rel in missing_optional)
    lines.extend(["", "## Required Live Proof", ""])
    lines.extend(f"- {item}" for item in _required_live_proof(spec))
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in spec.notes)
    lines.append("")
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _artifact_checkbox(run_dir: Path, rel: str) -> str:
    marker = "x" if not _missing_artifacts(run_dir, [rel], require_nonempty=True) else " "
    return f"- [{marker}] `{rel}`"


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


def _run_packet(spec: EmbeddedAdvancedPacketSpec) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = OUT_ROOT / spec.output_slug / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    primary_proc: subprocess.Popen[str] | None = None
    secondary_proc: subprocess.Popen[str] | None = None
    otel_proc: subprocess.Popen[str] | None = None
    handles: list[object] = []
    try:
        if spec.engine == "sglang":
            _ensure_sglang_runtime(run_dir)
        _write_env_snapshot(run_dir)
        _write_lmcache_config(run_dir, spec)
        _write_launch_proof(run_dir, spec)
        if spec.enable_otel:
            otel_proc, otel_handle = _start_otel_collector(run_dir)
            handles.append(otel_handle)
        primary_proc, primary_handle = _launch_engine(run_dir, spec)
        handles.append(primary_handle)
        if spec.secondary_port is not None:
            secondary_proc, secondary_handle = _launch_engine(
                run_dir, spec, role="secondary", port=spec.secondary_port
            )
            handles.append(secondary_handle)
        _wait_for_http(
            ENGINE_HEALTH_URL,
            run_dir / "health.log",
            label="primary engine",
            max_wait_seconds=30 * 60,
            proc=primary_proc,
        )
        if spec.secondary_port is not None:
            _wait_for_http(
                f"{SECONDARY_ENGINE_BASE_URL}/health",
                run_dir / "health.log",
                label="secondary engine",
                max_wait_seconds=30 * 60,
                proc=secondary_proc,
            )
        _capture_metrics(run_dir, "empty")
        _drive_traffic(run_dir, spec)
        _capture_metrics(run_dir, "loaded")
        _run_inferguard_packet(run_dir, spec)
        _validate_required_artifacts(run_dir, spec)
    finally:
        _terminate(primary_proc)
        _terminate(secondary_proc)
        _terminate(otel_proc)
        _close_handles(handles)
        _write_summary_and_index(run_dir, spec)
        try:
            volume.commit()
        except Exception as exc:
            print(f"Modal volume commit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return str(run_dir)


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_h1_embedded_vllm() -> str:
    return _run_packet(PACKETS["h1"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_h2_sglang_embedded() -> str:
    return _run_packet(PACKETS["h2"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_h3_cacheblend() -> str:
    return _run_packet(PACKETS["h3-cacheblend"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_h3_p2p() -> str:
    return _run_packet(PACKETS["h3-p2p"])


@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})
def run_packet_h3_pd() -> str:
    return _run_packet(PACKETS["h3-pd"])


@app.local_entrypoint()
def main(packet: str = "h1") -> None:
    key = _get_packet(packet).packet_id
    runners = {
        "h1": run_packet_h1_embedded_vllm,
        "h2": run_packet_h2_sglang_embedded,
        "h3-cacheblend": run_packet_h3_cacheblend,
        "h3-p2p": run_packet_h3_p2p,
        "h3-pd": run_packet_h3_pd,
    }
    print(runners[key].remote())

