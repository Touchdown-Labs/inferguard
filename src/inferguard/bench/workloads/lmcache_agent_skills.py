"""LMCache workload: reusable skill/tool docs appear after dynamic user content."""

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
    turns: int = 5,
    skills: int = 6,
    skill_tokens: int = 384,
    context_length_target: int = 32768,
    tenant_id: str = "tenant-a",
    seed: int = 1704,
    redact_prompts: bool = False,
) -> list[dict[str, Any]]:
    skill_docs = [f"SKILL_DOC_{idx}\n{_synthetic_text(f'agent-skill-{idx}', skill_tokens, seed)}" for idx in range(skills)]
    shared_suffix = "\n".join(skill_docs)
    records: list[dict[str, Any]] = []
    for turn in range(turns):
        dynamic = _synthetic_text(f"dynamic-user-{turn}", max(128, context_length_target // 8), seed)
        prompt = f"USER_CONTEXT:\n{dynamic}\n\nREUSABLE_SKILL_DOCS:\n{shared_suffix}"
        records.append(
            _base_record(
                family="agent_skills",
                trace_id=f"lmcache-agent-skills-{turn}",
                session_id="lmcache-agent-skills-shared-docs",
                tenant_id=tenant_id,
                turn_index=turn,
                context_length_target=context_length_target,
                prefix_ratio=0.04 if turn else 0.0,
                non_prefix_ratio=0.72 if turn else 0.0,
                cache_mode="suffix_skill_reuse" if turn else "cold_skill_docs",
                cache_salt=f"{tenant_id}:agent-skills",
                prompt=prompt,
                seed=seed,
                redact_prompts=redact_prompts,
                metadata={"skill_count": skills, "dynamic_content_before_skills": True},
            )
        )
    return records


def write_jsonl(path: Path, **kwargs: Any) -> Path:
    return _write_jsonl(path, generate_records(**kwargs))
