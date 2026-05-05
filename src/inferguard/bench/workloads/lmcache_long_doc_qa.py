"""LMCache workload: long-document QA over a stable 40-document corpus."""

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
    questions: int = 3,
    docs: int = 40,
    doc_tokens: int = 128,
    context_length_target: int = 32768,
    tenant_id: str = "tenant-a",
    seed: int = 1702,
    redact_prompts: bool = False,
) -> list[dict[str, Any]]:
    corpus = [
        f"DOC_{idx:02d}\n{_synthetic_text(f'long-doc-{idx}', doc_tokens, seed)}"
        for idx in range(docs)
    ]
    records: list[dict[str, Any]] = []
    for question in range(questions):
        prompt = "\n".join(corpus) + f"\n\nQUESTION {question}: cite the relevant document ids."
        records.append(
            _base_record(
                family="long_doc_qa",
                trace_id=f"lmcache-long-doc-qa-{question}",
                session_id="lmcache-long-doc-shared-corpus",
                tenant_id=tenant_id,
                turn_index=question,
                context_length_target=context_length_target,
                prefix_ratio=0.92 if question else 0.0,
                non_prefix_ratio=0.02,
                cache_mode="doc_corpus_warm" if question else "doc_corpus_cold",
                cache_salt=f"{tenant_id}:long-doc",
                prompt=prompt,
                seed=seed,
                redact_prompts=redact_prompts,
                metadata={"doc_count": docs, "doc_tokens": doc_tokens, "question_index": question},
            )
        )
    return records


def write_jsonl(path: Path, **kwargs: Any) -> Path:
    return _write_jsonl(path, generate_records(**kwargs))
