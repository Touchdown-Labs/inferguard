"""Tests for HMA/native-offload preflight findings."""

from inferguard.preflight import check_hma_offload_compat


def _status(*, disable_hma: bool = False, model: str = "deepseek-v4-pro") -> dict:
    return {
        "schema_version": "disagg-status/v1",
        "prefill": {"endpoint": {"engine": "vllm", "role": "prefill"}},
        "decode": {"endpoint": {"engine": "vllm", "role": "decode"}},
        "kv_offloading_backend": "native",
        "disable_hybrid_kv_cache_manager": disable_hma,
        "model_family": model,
    }


def test_hybrid_model_native_offload_without_hma_flag_warns() -> None:
    findings = check_hma_offload_compat(_status(), "deepseek-v4-pro")
    assert len(findings) == 1
    assert findings[0].code == "hma_offload_incompatible"
    assert findings[0].severity == "warning"
    assert "--disable-hybrid-kv-cache-manager" in findings[0].message


def test_hybrid_model_with_hma_flag_set_does_not_warn() -> None:
    findings = check_hma_offload_compat(_status(disable_hma=True), "deepseek-v4-pro")
    assert findings == []


def test_non_hybrid_model_does_not_warn() -> None:
    findings = check_hma_offload_compat(_status(model="minimaxm2.5"), "minimaxm2.5")
    assert findings == []
