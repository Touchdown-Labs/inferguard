"""LMCache workload: same prefix bytes across tenants with explicit cache_salt labels."""

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
    tenants: tuple[str, ...] = ("tenant-a", "tenant-b", "tenant-c"),
    repeats_per_tenant: int = 2,
    context_length_target: int = 16384,
    seed: int = 1705,
    redact_prompts: bool = False,
) -> list[dict[str, Any]]:
    shared_prefix = _synthetic_text("identical-cross-tenant-prefix", context_length_target, seed)
    records: list[dict[str, Any]] = []
    for tenant_index, tenant_id in enumerate(tenants):
        for repeat in range(repeats_per_tenant):
            turn = tenant_index * repeats_per_tenant + repeat
            prompt = f"TENANT_NEUTRAL_SHARED_PREFIX:\n{shared_prefix}\n\nTenant-local query repeat={repeat}."
            records.append(
                _base_record(
                    family="multi_tenant_salt",
                    trace_id=f"lmcache-multi-tenant-salt-{tenant_id}-{repeat}",
                    session_id=f"lmcache-salt-{tenant_id}",
                    tenant_id=tenant_id,
                    turn_index=turn,
                    context_length_target=context_length_target,
                    prefix_ratio=0.9 if repeat else 0.0,
                    non_prefix_ratio=0.0,
                    cache_mode="same_prefix_cross_tenant",
                    cache_salt=f"salt:{tenant_id}",
                    prompt=prompt,
                    seed=seed,
                    redact_prompts=redact_prompts,
                    metadata={
                        "tenant_index": tenant_index,
                        "security_claim_status": "not_proven_without_engine_cache_salt_metrics",
                    },
                )
            )
    return records


def write_jsonl(path: Path, **kwargs: Any) -> Path:
    return _write_jsonl(path, generate_records(**kwargs))
