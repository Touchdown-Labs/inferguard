"""SGLang launch command assembly."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

SGLANG_CHUNKED_PREFILL_SCHEMA_VERSION = "inferguard-sglang-chunked-prefill/v1"
DEFAULT_SGLANG_CHUNKED_PREFILL_SIZE = 8192
BLACKWELL_SGLANG_SKU_TOKENS = ("B200", "GB200", "GB300", "BLACKWELL")


def build_sglang_command(
    model_path: str,
    *,
    host: str = "127.0.0.1",
    port: int = 30000,
    tensor_parallel_size: int = 1,
    data_parallel_size: int = 1,
    max_model_len: int | None = None,
    mem_fraction_static: float = 0.9,
    enable_metrics: bool = False,
    enable_cache_report: bool = True,
    chunked_prefill_size: int | None = None,
    hardware: str | None = None,
    quantization: str | None = None,
    extra_args: str | None = None,
) -> list[str]:
    resolved_chunked_prefill_size = resolve_sglang_chunked_prefill_size(
        chunked_prefill_size,
        hardware=hardware,
        quantization=quantization,
    )
    argv = [
        "python",
        "-m",
        "sglang.launch_server",
        "--model-path",
        model_path,
        "--host",
        host,
        "--port",
        str(port),
        "--tp",
        str(tensor_parallel_size),
        "--dp",
        str(data_parallel_size),
        "--mem-fraction-static",
        str(mem_fraction_static),
    ]
    if max_model_len is not None:
        argv.extend(["--context-length", str(max_model_len)])
    if enable_metrics:
        argv.append("--enable-metrics")
    if enable_cache_report:
        argv.append("--enable-cache-report")
    if resolved_chunked_prefill_size is not None:
        argv.extend(["--chunked-prefill-size", str(resolved_chunked_prefill_size)])
    if quantization:
        argv.extend(["--quantization", quantization])
    if extra_args:
        argv.extend(shlex.split(extra_args))
    return argv


def resolve_sglang_chunked_prefill_size(
    chunked_prefill_size: int | None,
    *,
    hardware: str | None = None,
    quantization: str | None = None,
) -> int | None:
    if not _is_blackwell_sku(hardware):
        return chunked_prefill_size
    if chunked_prefill_size == -1 and _is_fp8_quantization(quantization):
        raise ValueError(
            "SGLang B200/FP8 launch cannot disable chunked prefill; "
            "set --chunked-prefill-size to a positive value."
        )
    if chunked_prefill_size is None:
        return DEFAULT_SGLANG_CHUNKED_PREFILL_SIZE
    return chunked_prefill_size


def sglang_launch_warnings(
    *,
    hardware: str | None = None,
    quantization: str | None = None,
    chunked_prefill_size: int | None = None,
) -> list[str]:
    warnings: list[str] = []
    if _is_b200_sku(hardware) and _is_fp8_quantization(quantization):
        effective = resolve_sglang_chunked_prefill_size(
            chunked_prefill_size,
            hardware=hardware,
            quantization=quantization,
        )
        warnings.append(
            "SGLang B200/FP8 requires explicit --chunked-prefill-size; "
            f"effective_chunked_prefill_size={effective}; "
            f"schema_version={SGLANG_CHUNKED_PREFILL_SCHEMA_VERSION}."
        )
    return warnings


def _is_blackwell_sku(hardware: str | None) -> bool:
    raw = (hardware or "").upper()
    return any(token in raw for token in BLACKWELL_SGLANG_SKU_TOKENS)


def _is_b200_sku(hardware: str | None) -> bool:
    raw = (hardware or "").upper()
    return "B200" in raw


def _is_fp8_quantization(quantization: str | None) -> bool:
    return (quantization or "").strip().lower() in {"fp8", "fp8_e4m3", "fp8_e5m2"}


def launch_sglang(
    model_path: str,
    output_dir: str | Path,
    **flags: Any,
) -> Any:
    from inferguard.launch_engine import launch

    return launch(engine="sglang", model_path=model_path, output_dir=output_dir, **flags)
