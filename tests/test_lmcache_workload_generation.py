import importlib
import json
from pathlib import Path

from inferguard.bench.workloads.lmcache_multi_round_chat import REQUIRED_FIELDS

MODULES = [
    "lmcache_multi_round_chat",
    "lmcache_long_doc_qa",
    "lmcache_mtrag_reorder",
    "lmcache_agent_skills",
    "lmcache_multi_tenant_salt",
    "lmcache_mp_moe_redundant_prefill",
]


def test_lmcache_workload_generators_emit_required_jsonl_fields(tmp_path: Path) -> None:
    for name in MODULES:
        module = importlib.import_module(f"inferguard.bench.workloads.{name}")
        path = tmp_path / f"{name}.jsonl"
        module.write_jsonl(path, context_length_target=512)
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        assert rows, name
        for row in rows:
            assert set(REQUIRED_FIELDS) <= row.keys()
            assert row["workload_family"] == name.removeprefix("lmcache_")
            assert row["metadata"]["deterministic"] is True
            assert row["metadata"]["claim_boundary"] == "inferred_without_engine_metrics"
            assert isinstance(row["prompt_sha256"], str) and len(row["prompt_sha256"]) == 64
            assert 0.0 <= row["expected_prefix_overlap_ratio"] <= 1.0
            assert 0.0 <= row["expected_non_prefix_reuse_ratio"] <= 1.0


def test_mtrag_and_agent_skills_label_non_prefix_reuse() -> None:
    mtrag = importlib.import_module("inferguard.bench.workloads.lmcache_mtrag_reorder")
    agent_skills = importlib.import_module("inferguard.bench.workloads.lmcache_agent_skills")

    assert any(row["expected_non_prefix_reuse_ratio"] > 0.5 for row in mtrag.generate_records(context_length_target=512))
    assert any(row["expected_non_prefix_reuse_ratio"] > 0.5 for row in agent_skills.generate_records(context_length_target=512))


def test_multi_tenant_salt_never_claims_security_proof() -> None:
    module = importlib.import_module("inferguard.bench.workloads.lmcache_multi_tenant_salt")
    rows = module.generate_records(context_length_target=512)

    assert len({row["tenant_id"] for row in rows}) > 1
    assert all(row["cache_salt"].startswith("salt:") for row in rows)
    assert all(row["metadata"]["security_claim_status"] == "not_proven_without_engine_cache_salt_metrics" for row in rows)
