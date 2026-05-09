# Packet H1 tokenizer/runtime live validation blocked report v0.2

Date: 2026-05-09
Lane: H1 embedded vLLM LMCacheConnectorV1
Score impact: none; remains blocked, no fixture imported

## Trigger

This pass fixed the prior H1 startup blocker:

```text
AttributeError: Qwen2Tokenizer has no attribute all_special_tokens_extended
```

The fix was TDD-backed before the live rerun.

## Chosen fix

Root cause: H1 used `vllm==0.10.2` with resolver-selected `transformers==5.8.0`. vLLM 0.10.2 calls `tokenizer.all_special_tokens_extended` during tokenizer caching, but the H1 artifact showed `Qwen2Tokenizer` under transformers 5.8.0 did not expose that attribute.

Local verification showed `transformers==4.57.6` with `tokenizers==0.22.2` exposes `all_special_tokens_extended` for Qwen3 tokenizers. H1 was also moved from `Qwen/Qwen3-8B` to `Qwen/Qwen3-0.6B` to keep the validation cheaper while preserving the Qwen3/Qwen2Tokenizer family and the embedded `LMCacheConnectorV1` KV-transfer path.

Implementation changes:

- `MODEL = "Qwen/Qwen3-0.6B"`
- `MODEL_MAX_LEN = 8192`
- pinned `transformers==4.57.6`
- pinned `tokenizers==0.22.2`
- LMCache editable install changed to `--no-deps` so `transformers>=5.4` from local LMCache cannot override the vLLM-compatible tokenizer pin
- Modal source snapshot ignores `**/__pycache__/**` and `**/*.pyc` to avoid unrelated local bytecode churn during image build

## RED/GREEN proof

RED 1:

```bash
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
# failed: no PINNED_TRANSFORMERS_PACKAGE / PINNED_TOKENIZERS_PACKAGE and model was Qwen/Qwen3-8B
```

RED 2:

```bash
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
# failed: LMCACHE_LOCAL_INSTALL_COMMAND did not end with --no-build-isolation --no-deps
```

RED 3:

```bash
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
# failed: no MODAL_SOURCE_IGNORE for __pycache__ / *.pyc Modal snapshot churn
```

GREEN/local gates:

```bash
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
# 13 passed
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
https://modal.com/apps/ocwc22/main/ap-3mHzStephkbZTz3qL6qxUs
```

Remote artifact:

```text
lmcache-embedded-advanced-lab:/packet-h1-embedded-vllm/20260509T201100Z
```

Local artifact:

```text
/Users/chen/Projects/inferguard/modal-out/packet-h1-embedded-vllm/20260509T201100Z
```

Actual launched command:

```json
[
  "vllm",
  "serve",
  "Qwen/Qwen3-0.6B",
  "--max-model-len",
  "8192",
  "--gpu-memory-utilization",
  "0.80",
  "--port",
  "8000",
  "--kv-transfer-config",
  "{\"kv_connector\":\"LMCacheConnectorV1\",\"kv_role\":\"kv_both\"}"
]
```

Runtime package proof from `env.txt`:

```text
vllm==0.10.2
transformers==4.57.6
tokenizers==0.22.2
-e git+https://github.com/OCWC22/LMCache.git@06a73b21580a53c13f37e9999fd001009d0881e3#egg=lmcache
```

The previous tokenizer blocker is cleared. `engine.log` shows vLLM reached engine-core startup with:

```text
model='Qwen/Qwen3-0.6B'
tokenizer='Qwen/Qwen3-0.6B'
kv_transfer_config: KVTransferConfig(kv_connector='LMCacheConnectorV1', ... kv_role='kv_both' ...)
```

## Result

H1 still blocked before health. New precise blocker:

```text
ModuleNotFoundError: No module named 'sortedcontainers'
```

Cause: pin protection used `pip install -e /opt/lmcache --no-build-isolation --no-deps` to prevent LMCache's `transformers>=5.4` dependency from re-upgrading transformers to 5.8.0. That preserved the tokenizer fix but exposed an uninstalled LMCache runtime dependency imported by `lmcache.v1.memory_management`.

## Score / protocol outcome

- No H1 fixture imported.
- H2/H3 were not run.
- I1 release readiness remains blocked.
- Score remains 96/100.

## Exact next command

Do not rerun H1 until the LMCache dependency floor is installed explicitly without allowing transformers to upgrade. The next fix should add a local image contract test that `sortedcontainers` and any required LMCache runtime deps are installed while `transformers==4.57.6` remains pinned.

After that TDD fix, the next runtime command remains:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h1_embedded_vllm
```
