---
title: Supported engines
description: vLLM, SGLang, Dynamo, LMCache, llm-d coverage.
---

`path_trace` reports per-endpoint support using:

- `per_session`
- `aggregate_only`
- `unsupported`

## Engine matrix

| Engine | Metric prefix (expected) | Connector detection scheme | TTFT source | TPOT source | `path_trace` per-session label support |
|---|---|---|---|---|---|
| vLLM | `vllm:` | Best-effort from connector labels on KV-transfer-related metrics (e.g., `kv_transfer_backend`/`connector`) | Histogram/summary TTFT family exposed by endpoint metrics | Histogram/summary TPOT/token-latency family exposed by endpoint metrics | Usually `per_session` when request/session labels exist; otherwise `aggregate_only` |
| SGLang | `sglang:` | Best-effort label extraction from KV transfer / routing metric families | SGLang TTFT metric family normalized by adapter | SGLang TPOT metric family normalized by adapter | Varies by deployment labels; `per_session` or `aggregate_only` |
| LMCache embedded | `lmcache:` or `lmcache_` | vLLM: `LMCacheConnectorV1` / `LMCacheConnectorV1Dynamic`; SGLang: `--enable-lmcache` / `LMCacheLayerwiseConnector`; legacy `LMCacheConnector` is stale unless pinned | Engine TTFT source, not LMCache itself | Engine TPOT source, not LMCache itself | Usually `aggregate_only`; LMCache metrics prove cache behavior, not per-session request identity |
| LMCache MP | `lmcache_mp_` | Standalone `lmcache server` plus engine connector evidence; vLLM uses `LMCacheMPConnector`; SGLang MP is not proven on current mainline | Engine TTFT source plus LMCache MP lookup/retrieve evidence | Engine TPOT source plus LMCache MP store/retrieve evidence | Usually `aggregate_only`; MP HTTP/Prometheus/OTel/trace evidence is mode proof, not per-session identity by default |
| NVIDIA Dynamo | `nv_llm:` or `dynamo_` | Best-effort from transfer/connector labels when exposed; empty if not exported | Adapter-normalized Dynamo TTFT metric family | Adapter-normalized Dynamo TPOT metric family | Often `aggregate_only`; can be `per_session` if labels are emitted |
| llm-d | `llmd_` or `llm_d_` | Best-effort from llm-d transfer/connector labels when present | Adapter-normalized llm-d TTFT metric family | Adapter-normalized llm-d TPOT metric family | Engine-dependent; `per_session`, `aggregate_only`, or `unsupported` |

## Notes

- Prefix detection is best-effort when `--engine auto` is used.
- Explicit `--engine` is recommended in production automation.
- If metrics are insufficient for identity, output includes `engine_unidentified`.
- For LMCache MP, current vLLM source does not expose LMCache MP
  connector-specific Prometheus metrics from vLLM; collect the standalone
  LMCache MP `/metrics` endpoint.
- SGLang LMCache should be treated as embedded/layerwise until a current
  mainline SGLang MP connector contract and live fixture prove otherwise.
