# Supported Engines

`path_trace` reports per-endpoint support using:

- `per_session`
- `aggregate_only`
- `unsupported`

## Engine matrix

| Engine | Metric prefix (expected) | Connector detection scheme | TTFT source | TPOT source | `path_trace` per-session label support |
|---|---|---|---|---|---|
| vLLM | `vllm:` | Best-effort from connector labels on KV-transfer-related metrics (e.g., `kv_transfer_backend`/`connector`) | Histogram/summary TTFT family exposed by endpoint metrics | Histogram/summary TPOT/token-latency family exposed by endpoint metrics | Usually `per_session` when request/session labels exist; otherwise `aggregate_only` |
| SGLang | `sglang:` | Best-effort label extraction from KV transfer / routing metric families | SGLang TTFT metric family normalized by adapter | SGLang TPOT metric family normalized by adapter | Varies by deployment labels; `per_session` or `aggregate_only` |
| NVIDIA Dynamo | `nv_llm:` or `dynamo_` | Best-effort from transfer/connector labels when exposed; empty if not exported | Adapter-normalized Dynamo TTFT metric family | Adapter-normalized Dynamo TPOT metric family | Often `aggregate_only`; can be `per_session` if labels are emitted |
| llm-d | `llmd_` or `llm_d_` | Best-effort from llm-d transfer/connector labels when present | Adapter-normalized llm-d TTFT metric family | Adapter-normalized llm-d TPOT metric family | Engine-dependent; `per_session`, `aggregate_only`, or `unsupported` |

## Notes

- Prefix detection is best-effort when `--engine auto` is used.
- Explicit `--engine` is recommended in production automation.
- If metrics are insufficient for identity, output includes `engine_unidentified`.
