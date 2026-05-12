# Packet H1 Modal/H100 live validation blocked report v0.1

Date: 2026-05-09
Lane: H1 embedded vLLM LMCacheConnectorV1
Score impact: none; remains blocked, no fixture imported

## Trigger

This rerun consumed the single allowed H1 rerun for the changed vLLM connector command state.

Previous blocker:

```text
vllm: error: unrecognized arguments: --kv-offloading-backend lmcache
```

## Local command-contract fix

Local vLLM/LMCache sources show the current embedded/in-process LMCache contract is:

```bash
LMCACHE_CONFIG_FILE=<config> \
vllm serve <model> \
  --kv-transfer-config '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'
```

This is not the standalone MP connector contract and does not use `LMCacheMPConnector`.

## RED/GREEN proof

RED:

```bash
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
# failed: H1 still emitted --kv-offloading-backend lmcache
```

GREEN/local gates:

```bash
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
# 12 passed
uv run pytest tests/test_lmcache_live_fixtures.py -q
# 4 passed
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
# 28 passed
uv run pytest tests/test_observability_coverage.py -q
# 21 passed
```

## H1 rerun receipt

Modal app URL:

```text
https://modal.com/apps/ocwc22/main/ap-3u23SKZIvL4DpbXOkQTjOR
```

Remote artifact:

```text
lmcache-embedded-advanced-lab:/packet-h1-embedded-vllm/20260509T193704Z
```

Local artifact:

```text
/Users/chen/Projects/inferguard/modal-out/packet-h1-embedded-vllm/20260509T193704Z
```

Actual launched command:

```json
[
  "vllm",
  "serve",
  "Qwen/Qwen3-8B",
  "--max-model-len",
  "16384",
  "--gpu-memory-utilization",
  "0.80",
  "--port",
  "8000",
  "--kv-transfer-config",
  "{\"kv_connector\":\"LMCacheConnectorV1\",\"kv_role\":\"kv_both\"}"
]
```

## Result

H1 still blocked before health. The command-contract blocker is fixed, but the runtime now exits during tokenizer initialization.

New precise blocker from `engine.log`:

```text
AttributeError: Qwen2Tokenizer has no attribute all_special_tokens_extended. Did you mean: 'num_special_tokens_to_add'?
```

The log also confirms vLLM parsed the current connector contract:

```text
kv_transfer_config: KVTransferConfig(kv_connector='LMCacheConnectorV1', ... kv_role='kv_both' ...)
```

## Score / protocol outcome

- No H1 fixture imported.
- H2/H3 were not run.
- I1 release readiness remains blocked.
- Score remains 96/100.

## Exact next command

Do not rerun H1 until the tokenizer/runtime compatibility issue is fixed locally with TDD.

After that fix, the next runtime command remains:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h1_embedded_vllm
```
