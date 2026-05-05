"""Regex and string anchors for InferGuard failure triage."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inferguard.classify_failures.types import CLAIM_STATUSES, FAILURE_CLASS_NAMES

# Source notes are intentionally embedded with the regex table so operators can
# audit why each default anchor exists. Local lock: PRD §4.6.5 in
# docs/inferguard/31-2026-05-04-inferguard-neocloud-gmi-verifiable-prd-and-rubric.md.
VLLM_OOM_SOURCE = "https://github.com/vllm-project/vllm/issues/1949"
VLLM_NCCL_SOURCE = "https://github.com/vllm-project/vllm/issues/15255"
VLLM_SERVER_CRASH_SOURCE = "https://github.com/vllm-project/vllm/issues/6252"
VLLM_ENDPOINT_SOURCE = "https://github.com/vllm-project/vllm/issues/17941"
SGLANG_REASONING_SOURCE = "https://github.com/sgl-project/sglang/issues/6675"
SGLANG_CONFIG_SOURCE = "https://github.com/sgl-project/sglang/issues/9178"
NVIDIA_DCGM_XID_SOURCE = "https://docs.nvidia.com/datacenter/dcgm/3.1/dcgm-api/dcgm-api-field-ids.html"
SLURM_SBATCH_SOURCE = "https://slurm.schedmd.com/sbatch.html"
RDMA_FACT_PACK_SOURCE = (
    "prompt-exports/2026-05-04-inferguard-neocloud-prd-probe-2-engine-metric-hardware-fact-pack.md#F.1"
)


@dataclass(frozen=True)
class PatternRule:
    """One regex rule that contributes evidence to a failure class."""

    regex_id: str
    failure_class: str
    pattern: str
    confidence: float
    root_cause_priority: int
    claim_status: str = "measured"
    flags: int = re.IGNORECASE
    source_urls: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.failure_class not in FAILURE_CLASS_NAMES:
            raise ValueError(f"unsupported failure_class for {self.regex_id}: {self.failure_class}")
        if self.claim_status not in CLAIM_STATUSES:
            raise ValueError(f"unsupported claim_status for {self.regex_id}: {self.claim_status}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be between 0 and 1 for {self.regex_id}")

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.pattern, self.flags)


DEFAULT_PATTERNS: tuple[PatternRule, ...] = (
    PatternRule(
        "oom_cuda_out_of_memory",
        "oom_hbm_exhaustion",
        r"CUDA out of memory",
        0.9,
        75,
        source_urls=(VLLM_OOM_SOURCE,),
    ),
    PatternRule(
        "oom_hbm_exhausted",
        "oom_hbm_exhaustion",
        r"HBM exhausted",
        0.88,
        75,
        source_urls=(RDMA_FACT_PACK_SOURCE,),
    ),
    PatternRule(
        "oom_torch_exception",
        "oom_hbm_exhaustion",
        r"torch\.cuda\.OutOfMemoryError",
        0.92,
        75,
        source_urls=(VLLM_OOM_SOURCE,),
    ),
    PatternRule(
        "cuda_error_generic",
        "cuda_error",
        r"CUDA error:\s*[\w -]+",
        0.76,
        70,
        source_urls=(NVIDIA_DCGM_XID_SOURCE,),
    ),
    PatternRule(
        "cuda_illegal_address",
        "cuda_error",
        r"cudaErrorIllegalAddress|illegal memory access|illegal instruction",
        0.82,
        70,
        source_urls=(NVIDIA_DCGM_XID_SOURCE,),
    ),
    PatternRule(
        "nccl_error",
        "nccl_error",
        r"NCCL .* error",
        0.82,
        78,
        source_urls=(VLLM_NCCL_SOURCE,),
    ),
    PatternRule(
        "nccl_abort",
        "nccl_error",
        r"NCCL ABORT",
        0.84,
        78,
        source_urls=(VLLM_NCCL_SOURCE,),
    ),
    PatternRule(
        "nccl_system_error",
        "nccl_error",
        r"ncclSystemError",
        0.86,
        78,
        source_urls=(VLLM_NCCL_SOURCE,),
    ),
    PatternRule(
        "rdma_state_down",
        "rdma_inactive",
        r"State:\s*Down",
        0.88,
        80,
        source_urls=(RDMA_FACT_PACK_SOURCE,),
    ),
    PatternRule(
        "rdma_physical_state_bad",
        "rdma_inactive",
        r"Physical state:\s*(Polling|Disabled)",
        0.87,
        80,
        source_urls=(RDMA_FACT_PACK_SOURCE,),
    ),
    PatternRule(
        "rdma_ibv_async",
        "rdma_inactive",
        r"ibv_get_async_event",
        0.78,
        80,
        source_urls=(RDMA_FACT_PACK_SOURCE,),
    ),
    PatternRule(
        "model_hidden_size_mismatch",
        "model_config_mismatch",
        r"hidden_size .* does not match",
        0.82,
        85,
        source_urls=(SGLANG_CONFIG_SOURCE,),
    ),
    PatternRule(
        "model_vocab_size_mismatch",
        "model_config_mismatch",
        r"vocab_size .* mismatch",
        0.82,
        85,
        source_urls=(SGLANG_CONFIG_SOURCE,),
    ),
    PatternRule(
        "model_type_key_error",
        "model_config_mismatch",
        r"KeyError:\s*['\"][\w.-]+['\"]",
        0.72,
        85,
        source_urls=(SGLANG_CONFIG_SOURCE,),
    ),
    PatternRule(
        "tokenizer_not_found",
        "tokenizer_or_parser_failure",
        r"Tokenizer .* not found",
        0.8,
        68,
        source_urls=(SGLANG_REASONING_SOURCE,),
    ),
    PatternRule(
        "chat_template_not_found",
        "tokenizer_or_parser_failure",
        r"chat template not found|No chat template",
        0.8,
        68,
        source_urls=(SGLANG_REASONING_SOURCE,),
    ),
    PatternRule(
        "reasoning_parser_invalid",
        "tokenizer_or_parser_failure",
        r"reasoning parser .* invalid|invalid reasoning parser",
        0.8,
        68,
        source_urls=(SGLANG_REASONING_SOURCE,),
    ),
    PatternRule(
        "tool_parser_invalid",
        "tokenizer_or_parser_failure",
        r"tool[-_ ]?call parser .* invalid|invalid tool[-_ ]?call parser",
        0.76,
        68,
        source_urls=(SGLANG_REASONING_SOURCE,),
    ),
    PatternRule(
        "image_glibc",
        "container_image_incompatibility",
        r"GLIBC_\d",
        0.82,
        90,
        source_urls=(VLLM_SERVER_CRASH_SOURCE,),
    ),
    PatternRule(
        "image_libnccl_missing",
        "container_image_incompatibility",
        r"libnccl\.so .* not found",
        0.84,
        90,
        source_urls=(VLLM_NCCL_SOURCE,),
    ),
    PatternRule(
        "image_glibcxx",
        "container_image_incompatibility",
        r"version [`']GLIBCXX_",
        0.84,
        90,
        source_urls=(VLLM_SERVER_CRASH_SOURCE,),
    ),
    PatternRule(
        "endpoint_connection_refused",
        "endpoint_healthcheck_failure",
        r"Connection refused|Failed to connect|ECONNREFUSED",
        0.78,
        65,
        source_urls=(VLLM_ENDPOINT_SOURCE,),
    ),
    PatternRule(
        "endpoint_connect_timeout",
        "endpoint_healthcheck_failure",
        r"connect timeout|healthcheck timeout|Healthcheck failed",
        0.76,
        65,
        source_urls=(VLLM_ENDPOINT_SOURCE,),
    ),
    PatternRule(
        "client_timeout_text",
        "client_timeout",
        r"ReadTimeout|timed out waiting|request timeout",
        0.72,
        50,
        source_urls=(VLLM_ENDPOINT_SOURCE,),
    ),
    PatternRule(
        "server_segfault",
        "server_crash",
        r"Segmentation fault",
        0.82,
        60,
        source_urls=(VLLM_SERVER_CRASH_SOURCE,),
    ),
    PatternRule(
        "server_core_dumped",
        "server_crash",
        r"core dumped",
        0.8,
        60,
        source_urls=(VLLM_SERVER_CRASH_SOURCE,),
    ),
    PatternRule(
        "server_sigabrt",
        "server_crash",
        r"SIGABRT|Aborted \(core dumped\)|Fatal Python error: Aborted",
        0.82,
        60,
        source_urls=(VLLM_SERVER_CRASH_SOURCE,),
    ),
    PatternRule(
        "server_engine_dead",
        "server_crash",
        r"EngineDeadError",
        0.78,
        60,
        source_urls=(VLLM_SERVER_CRASH_SOURCE,),
    ),
    PatternRule(
        "slurm_sbatch_error",
        "slurm_allocation_failure",
        r"sbatch: error",
        0.84,
        100,
        source_urls=(SLURM_SBATCH_SOURCE,),
    ),
    PatternRule(
        "slurm_load_jobs_error",
        "slurm_allocation_failure",
        r"slurm_load_jobs error",
        0.84,
        100,
        source_urls=(SLURM_SBATCH_SOURCE,),
    ),
    PatternRule(
        "slurm_unable_allocate",
        "slurm_allocation_failure",
        r"Unable to allocate resources|Batch job submission failed",
        0.82,
        100,
        source_urls=(SLURM_SBATCH_SOURCE,),
    ),
)


def load_patterns(config_path: Path | None = None) -> tuple[PatternRule, ...]:
    """Load default regex rules plus an optional operator JSON override."""

    if config_path is None:
        return DEFAULT_PATTERNS
    data = json.loads(config_path.read_text(encoding="utf-8"))
    rows = data.get("patterns") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("--regex-config must be a JSON list or an object with a patterns list")
    patterns = list(DEFAULT_PATTERNS)
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"regex-config entry {index} must be an object")
        patterns.append(_pattern_from_config(row, index))
    return tuple(patterns)


def _pattern_from_config(row: dict[str, Any], index: int) -> PatternRule:
    regex_id = str(row.get("regex_id") or row.get("id") or f"operator_pattern_{index}")
    source_urls = row.get("source_urls") or ()
    if isinstance(source_urls, str):
        source_tuple = (source_urls,)
    else:
        source_tuple = tuple(str(item) for item in source_urls)
    return PatternRule(
        regex_id=regex_id,
        failure_class=str(row["class"]),
        pattern=str(row["pattern"]),
        confidence=float(row.get("confidence", 0.7)),
        root_cause_priority=int(row.get("root_cause_priority", 50)),
        claim_status=str(row.get("claim_status", "inferred")),
        source_urls=source_tuple,
    )


__all__ = [
    "DEFAULT_PATTERNS",
    "NVIDIA_DCGM_XID_SOURCE",
    "PatternRule",
    "load_patterns",
]
