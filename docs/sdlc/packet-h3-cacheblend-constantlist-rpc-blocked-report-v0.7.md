# Packet H3 CacheBlend ConstantList RPC blocked report v0.7

Date: 2026-05-10
Repo: `/Users/chen/Projects/inferguard`
Lane: H3-only vLLM + LMCache + InferGuard CLI
Status: blocked, score unchanged

## Summary

The already-committed H3 RoPE shim was validated live. The latest H3 CacheBlend rerun cleared both previous RoPE blockers:

- `TypeError: get_rope() got an unexpected keyword argument 'rope_parameters'`
- `TypeError: get_rope() missing 1 required positional argument: 'rotary_dim'`

The engine reached `/health`, registered `vllm-instance`, created the CacheBlend blender, and logged RoPE max-error lines. First completion traffic then crashed before loaded metrics and InferGuard reports with a new LMCache lookup RPC serialization blocker.

## Live run

- Modal app: `https://modal.com/apps/ocwc22/main/ap-kMi7Q3v3UtaO3eaPatANEw`
- Remote volume path: `lmcache-embedded-advanced-lab:/packet-h3-cacheblend/20260510T203922Z`
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/pulls/h3-cacheblend-20260510T203922Z/20260510T203922Z`

## Evidence that the RoPE shim worked

`engine.log` contains:

- `Registering vllm model for vllm-instance`
- `Creating blender for vllm-instance`
- `Max Q error: 0.01171875`
- `Max K error: 0.01171875`
- `Max K error (fused): 0.01171875`
- `GET /health HTTP/1.1" 200 OK`

`vllm_cacheblend_model_tracker_patch.json` records:

- `attention_backend: lazy non-sparse FlashAttention path for CacheBlend`
- `rope_compat: map LMCache rope_parameters onto installed vLLM get_rope signature when needed`

`sitecustomize.py` in the artifact contains the generated runtime wrapper that derives `rotary_dim` from `rope_dim` or `head_size * partial_rotary_factor` and filters kwargs to the installed vLLM `get_rope` signature.

## New blocker

First `/v1/completions` traffic failed with HTTP 500 because the vLLM engine core died inside LMCache lookup:

```text
TypeError: Encoding objects of type ConstantList is unsupported
```

Stack path:

```text
vllm/v1/core/sched/scheduler.py::schedule
vllm/distributed/kv_transfer/kv_connector/v1/lmcache_connector.py::get_num_new_matched_tokens
/opt/lmcache/lmcache/integration/vllm/vllm_v1_adapter.py::get_num_new_matched_tokens
/opt/lmcache/lmcache/v1/lookup_client/lmcache_lookup_client.py::lookup
/opt/lmcache/lmcache/v1/rpc/zmq_transport.py::send_and_recv_all
self.encoder.encode(m)
```

The failure occurs while encoding lookup messages that include vLLM `ConstantList` token containers.

## Missing artifacts

Because traffic failed before the loaded capture and InferGuard CLI chain:

- no `engine_metrics_loaded.prom`
- no `lmcache-packet/packet_manifest.json`
- no `lmcache-packet/lmcache_log_evidence.json`
- no `lmcache_compat_report.json`
- no `observability_coverage.json`
- no `lmcache_otel.jsonl`

## Local verification before rerun

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py tests/test_lmcache_live_fixtures.py tests/test_observability_coverage.py
# 51 passed
```

Additional generated-sitecustomize verification confirmed the committed runtime file includes:

- `if "rotary_dim" in parameters and "rotary_dim" not in kwargs`
- `kwargs["rotary_dim"] = rope_parameters["rope_dim"]`
- `kwargs["rotary_dim"] = int(kwargs["head_size"] * partial_factor)`
- `filtered_kwargs = {key: value for key, value in kwargs.items() if key in parameters}`

## Result

Do not import a packet_h3 fixture. Do not run I1. Score remains 96/100.

## Exact next action

Patch and test an H3-only compatibility layer for LMCache lookup RPC serialization of vLLM `ConstantList` prompt-token containers, then run exactly:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h3_cacheblend
```

Do not rerun A-F, G1, H1, H2/SGLang, Mooncake, or DLM.
