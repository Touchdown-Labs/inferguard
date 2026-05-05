"""LMCache workload: shared system prompt with growing multi-round chat history."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

REQUIRED_FIELDS: tuple[str, ...] = (
    "trace_id",
    "session_id",
    "tenant_id",
    "turn_index",
    "context_length_target",
    "expected_prefix_overlap_ratio",
    "expected_non_prefix_reuse_ratio",
    "cache_mode",
    "cache_salt",
    "workload_family",
    "prompt",
    "prompt_redacted",
    "prompt_sha256",
    "metadata",
)


def generate_records(
    *,
    sessions: int = 2,
    turns: int = 4,
    context_length_target: int = 8192,
    tenant_id: str = "tenant-a",
    seed: int = 1701,
    redact_prompts: bool = False,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    system_prompt = _synthetic_text("shared-system", max(128, context_length_target // 4), seed)
    for session in range(sessions):
        history: list[str] = []
        for turn in range(turns):
            history.append(
                _synthetic_text(
                    f"chat-{session}-{turn}", max(64, context_length_target // 16), seed
                )
            )
            prompt = f"SYSTEM:\n{system_prompt}\n\nHISTORY:\n" + "\n".join(history)
            jitter = rng.randint(0, 9999)
            records.append(
                _base_record(
                    family="multi_round_chat",
                    trace_id=f"lmcache-multi-round-chat-{session}-{turn}",
                    session_id=f"lmcache-chat-session-{session}",
                    tenant_id=tenant_id,
                    turn_index=turn,
                    context_length_target=context_length_target,
                    prefix_ratio=0.0 if turn == 0 else min(0.95, 0.55 + turn * 0.1),
                    non_prefix_ratio=0.05,
                    cache_mode="warm_chat_prefix" if turn else "cold_chat_start",
                    cache_salt=f"{tenant_id}:chat",
                    prompt=prompt,
                    seed=seed,
                    redact_prompts=redact_prompts,
                    metadata={
                        "session_index": session,
                        "history_turns": turn + 1,
                        "jitter": jitter,
                    },
                )
            )
    return records


def write_jsonl(path: Path, **kwargs: Any) -> Path:
    return _write_jsonl(path, generate_records(**kwargs))


def _base_record(
    *,
    family: str,
    trace_id: str,
    session_id: str,
    tenant_id: str,
    turn_index: int,
    context_length_target: int,
    prefix_ratio: float,
    non_prefix_ratio: float,
    cache_mode: str,
    cache_salt: str,
    prompt: str,
    seed: int,
    redact_prompts: bool,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    digest = hashlib.sha256(prompt.encode()).hexdigest()
    return {
        "trace_id": trace_id,
        "session_id": session_id,
        "tenant_id": tenant_id,
        "turn_index": turn_index,
        "context_length_target": context_length_target,
        "expected_prefix_overlap_ratio": round(prefix_ratio, 4),
        "expected_non_prefix_reuse_ratio": round(non_prefix_ratio, 4),
        "cache_mode": cache_mode,
        "cache_salt": cache_salt,
        "workload_family": family,
        "prompt": "<redacted>" if redact_prompts else prompt,
        "prompt_redacted": redact_prompts,
        "prompt_sha256": digest,
        "metadata": {
            "schema_version": "inferguard-lmcache-workload/v1",
            "generator": family,
            "seed": seed,
            "deterministic": True,
            "claim_boundary": "inferred_without_engine_metrics",
            **(metadata or {}),
        },
    }


def _synthetic_text(label: str, target_tokens: int, seed: int) -> str:
    target_chars = max(64, target_tokens * 4)
    digest = hashlib.sha256(f"{label}:{seed}".encode()).hexdigest()
    line = f"[{label}] seed={seed} digest={digest} cache-observation-material.\n"
    repeats = target_chars // len(line) + 1
    return (line * repeats)[:target_chars]


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
    )
    return path


__all__ = ["REQUIRED_FIELDS", "generate_records", "write_jsonl"]
