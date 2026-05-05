"""LMCache workload: duplicate long contexts across MP/MoE-style ranks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inferguard.bench.workloads.lmcache_multi_round_chat import (
    _base_record,
    _synthetic_text,
    _write_jsonl,
)


def generate_records(
    *,
    ranks: int = 4,
    repeats_per_rank: int = 2,
    context_length_target: int = 65536,
    tenant_id: str = "tenant-a",
    seed: int = 1706,
    redact_prompts: bool = False,
) -> list[dict[str, Any]]:
    shared_long_context = _synthetic_text("mp-moe-redundant-prefill", context_length_target, seed)
    records: list[dict[str, Any]] = []
    for rank in range(ranks):
        for repeat in range(repeats_per_rank):
            turn = rank * repeats_per_rank + repeat
            prompt = f"RANK={rank}\n{shared_long_context}\n\nDecode request repeat={repeat}."
            records.append(
                _base_record(
                    family="mp_moe_redundant_prefill",
                    trace_id=f"lmcache-mp-moe-rank-{rank}-{repeat}",
                    session_id="lmcache-mp-moe-shared-prefill",
                    tenant_id=tenant_id,
                    turn_index=turn,
                    context_length_target=context_length_target,
                    prefix_ratio=0.88 if turn else 0.0,
                    non_prefix_ratio=0.0,
                    cache_mode="mp_mode_redundant_prefill",
                    cache_salt=f"{tenant_id}:mp-moe",
                    prompt=prompt,
                    seed=seed,
                    redact_prompts=redact_prompts,
                    metadata={"rank_id": rank, "rank_count": ranks, "mp_mode_expected": True},
                )
            )
    return records


def write_jsonl(path: Path, **kwargs: Any) -> Path:
    return _write_jsonl(path, generate_records(**kwargs))
