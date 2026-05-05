"""vLLM launch command assembly."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any


def build_vllm_command(
    model_path: str,
    *,
    host: str = "0.0.0.0",
    port: int = 8000,
    tensor_parallel_size: int = 1,
    pipeline_parallel_size: int = 1,
    data_parallel_size: int = 1,
    max_model_len: int | None = None,
    gpu_memory_utilization: float = 0.9,
    enable_prefix_caching: bool = False,
    enable_chunked_prefill: bool = False,
    kv_cache_dtype: str | None = None,
    quantization: str | None = None,
    kv_transfer_config: str | None = None,
    extra_args: str | None = None,
) -> list[str]:
    argv = [
        "vllm",
        "serve",
        model_path,
        "--host",
        host,
        "--port",
        str(port),
        "--tensor-parallel-size",
        str(tensor_parallel_size),
        "--pipeline-parallel-size",
        str(pipeline_parallel_size),
        "--data-parallel-size",
        str(data_parallel_size),
        "--gpu-memory-utilization",
        str(gpu_memory_utilization),
    ]
    if max_model_len is not None:
        argv.extend(["--max-model-len", str(max_model_len)])
    if enable_prefix_caching:
        argv.append("--enable-prefix-caching")
    if enable_chunked_prefill:
        argv.append("--enable-chunked-prefill")
    if kv_cache_dtype:
        argv.extend(["--kv-cache-dtype", kv_cache_dtype])
    if quantization:
        argv.extend(["--quantization", quantization])
    if kv_transfer_config:
        argv.extend(["--kv-transfer-config", kv_transfer_config])
    if extra_args:
        argv.extend(shlex.split(extra_args))
    return argv


def launch_vllm(
    model_path: str,
    output_dir: str | Path,
    **flags: Any,
) -> Any:
    from inferguard.launch_engine import launch

    return launch(engine="vllm", model_path=model_path, output_dir=output_dir, **flags)
