"""LMCache workload: retrieved documents are reused but reordered across turns."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from inferguard.bench.workloads.lmcache_multi_round_chat import (
    _base_record,
    _synthetic_text,
    _write_jsonl,
)


def generate_records(
    *,
    turns: int = 4,
    docs: int = 12,
    doc_tokens: int = 256,
    context_length_target: int = 32768,
    tenant_id: str = "tenant-a",
    seed: int = 1703,
    redact_prompts: bool = False,
) -> list[dict[str, Any]]:
    corpus = [
        f"RETRIEVED_DOC_{idx:02d}\n{_synthetic_text(f'mtrag-doc-{idx}', doc_tokens, seed)}"
        for idx in range(docs)
    ]
    records: list[dict[str, Any]] = []
    for turn in range(turns):
        order = list(range(docs))
        random.Random(seed + turn).shuffle(order)
        prompt = (
            "\n".join(corpus[idx] for idx in order)
            + f"\n\nSynthesize answer for reordered turn {turn}."
        )
        records.append(
            _base_record(
                family="mtrag_reorder",
                trace_id=f"lmcache-mtrag-reorder-{turn}",
                session_id="lmcache-mtrag-same-docs-reordered",
                tenant_id=tenant_id,
                turn_index=turn,
                context_length_target=context_length_target,
                prefix_ratio=0.08 if turn else 0.0,
                non_prefix_ratio=0.84 if turn else 0.0,
                cache_mode="non_prefix_reuse_reordered" if turn else "cold_retrieval_order",
                cache_salt=f"{tenant_id}:mtrag",
                prompt=prompt,
                seed=seed,
                redact_prompts=redact_prompts,
                metadata={"doc_count": docs, "doc_order": order},
            )
        )
    return records


def write_jsonl(path: Path, **kwargs: Any) -> Path:
    return _write_jsonl(path, generate_records(**kwargs))
