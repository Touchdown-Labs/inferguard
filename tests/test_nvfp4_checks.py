"""Tests for the NVFP4 KV-cache qualification checks."""

from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from inferguard.nvfp4 import (
    NVFp4Verdict,
    QualThresholds,
    parse_kv_tokens_from_metrics,
    qualify_quality,
    run_kv_capacity,
    run_nvfp4_quality,
    run_sm120_compat,
)


# --- sm120-compat -----------------------------------------------------------

def test_sm120_compat_qualified_on_sm120():
    q = run_sm120_compat(model="m", capability=(12, 0))
    assert str(q.verdict) == NVFp4Verdict.QUALIFIED.value
    assert q.results[0].passed is True


def test_sm120_compat_needs_review_on_b200():
    q = run_sm120_compat(capability=(10, 0))
    assert str(q.verdict) == NVFp4Verdict.NEEDS_REVIEW.value


def test_sm120_compat_not_qualified_on_ampere():
    q = run_sm120_compat(capability=(8, 6))
    assert str(q.verdict) == NVFp4Verdict.NOT_QUALIFIED.value


def test_sm120_compat_needs_review_when_unknown():
    q = run_sm120_compat(capability=None)
    assert str(q.verdict) == NVFp4Verdict.NEEDS_REVIEW.value
    assert q.claim_status == "not_proven"


# --- kv-capacity ------------------------------------------------------------

def test_parse_kv_tokens_from_metrics():
    body = (
        'vllm:num_gpu_blocks{model_name="m"} 12000\n'
        'vllm:cache_config_info{block_size="16"} 1.0\n'
    )
    assert parse_kv_tokens_from_metrics(body) == 12000 * 16


def test_parse_kv_tokens_returns_none_without_gauge():
    assert parse_kv_tokens_from_metrics("# nothing here\n") is None


def test_kv_capacity_qualified_above_ratio():
    q = run_kv_capacity(model="m", nvfp4_tokens=2_960_263, fp8_tokens=1_663_988)
    assert str(q.verdict) == NVFp4Verdict.QUALIFIED.value
    ratio_check = [r for r in q.results if "Capacity gain" in r.name][0]
    assert ratio_check.passed is True
    assert ratio_check.value > 1.7


def test_kv_capacity_not_qualified_below_ratio():
    q = run_kv_capacity(model="m", nvfp4_tokens=1_100_000, fp8_tokens=1_000_000)
    assert str(q.verdict) == NVFp4Verdict.NOT_QUALIFIED.value


def test_kv_capacity_needs_review_without_baseline():
    q = run_kv_capacity(model="m", nvfp4_tokens=2_000_000)
    assert str(q.verdict) == NVFp4Verdict.NEEDS_REVIEW.value


# --- nvfp4-quality verdict logic (pure) -------------------------------------

def test_qualify_quality_all_pass():
    thr = QualThresholds(ppl_ctx_lengths=(2000,))
    results = qualify_quality(
        nvfp4_ppl={2000: {"mean_nll": 2.01}},
        fp8_ppl={2000: {"mean_nll": 2.00}},
        divergence={"median_first_div": 30},
        nvfp4_retrieval={"accuracy": 1.0},
        fp8_retrieval={"accuracy": 1.0},
        nvfp4_speed={"tok_per_sec": 110.0},
        fp8_speed={"tok_per_sec": 114.0},
        thresholds=thr,
    )
    assert results and all(r.passed for r in results)


def test_qualify_quality_fails_on_ppl_regression():
    thr = QualThresholds(ppl_ctx_lengths=(2000,))
    results = qualify_quality(
        nvfp4_ppl={2000: {"mean_nll": 2.20}},  # +0.20 nats, over threshold
        fp8_ppl={2000: {"mean_nll": 2.00}},
        divergence=None,
        nvfp4_retrieval=None,
        fp8_retrieval=None,
        nvfp4_speed=None,
        fp8_speed=None,
        thresholds=thr,
    )
    ppl = [r for r in results if "PPL" in r.name][0]
    assert ppl.passed is False


# --- nvfp4-quality integration (mocked endpoints) ---------------------------

def _quality_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/tokenize"):
        return httpx.Response(200, json={"count": 5000})
    body = json.loads(request.content or b"{}")
    if body.get("echo"):  # PPL probe (intentionally too few tokens -> skipped)
        return httpx.Response(200, json={"choices": [{"prompt_logprobs": [None, {"a": {"logprob": -1.0}}]}]})
    if body.get("logprobs") == 1:  # divergence
        return httpx.Response(200, json={"choices": [{"logprobs": {"tokens": [f"t{i}" for i in range(30)]}}]})
    if body.get("temperature") == 0.7:  # speed
        return httpx.Response(200, json={"choices": [{"text": "x"}], "usage": {"completion_tokens": 256}})
    return httpx.Response(200, json={"choices": [{"text": "00000"}]})  # retrieval


def test_run_nvfp4_quality_integration():
    client = httpx.Client(transport=httpx.MockTransport(_quality_handler))
    q = run_nvfp4_quality(
        model="m",
        nvfp4_endpoint="http://nvfp4",
        fp8_endpoint="http://fp8",
        thresholds=QualThresholds(ppl_ctx_lengths=(2000,)),
        client=client,
    )
    client.close()
    assert q.check == "nvfp4-quality"
    assert str(q.verdict) in {v.value for v in NVFp4Verdict}
    # divergence (30 identical tokens) should be present and pass
    div = [r for r in q.results if "divergence" in r.name.lower()]
    assert div and div[0].passed is True


# --- CLI wiring -------------------------------------------------------------

def _load_cli_app():
    """Import the Typer app, skipping if the repo tree is mid-merge (unrelated)."""
    try:
        from inferguard.cli import app
    except Exception as exc:  # noqa: BLE001 - pre-existing repo state, not our module
        pytest.skip(f"inferguard.cli unimportable on this tree: {exc}")
    return app


def test_cli_nvfp4_help_lists_subcommands():
    app = _load_cli_app()
    result = CliRunner().invoke(app, ["nvfp4", "--help"])
    assert result.exit_code == 0
    assert "sm120-compat" in result.stdout
    assert "kv-capacity" in result.stdout
    assert "quality" in result.stdout


def test_cli_sm120_compat_exit_code():
    app = _load_cli_app()
    result = CliRunner().invoke(app, ["nvfp4", "sm120-compat", "--cc", "12.0"])
    assert result.exit_code == 0  # qualified
    result_fail = CliRunner().invoke(app, ["nvfp4", "sm120-compat", "--cc", "8.6"])
    assert result_fail.exit_code == 1  # not_qualified
