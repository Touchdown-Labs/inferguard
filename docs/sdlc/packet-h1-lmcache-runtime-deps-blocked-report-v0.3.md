# Packet H1 LMCache runtime deps live validation blocked report v0.3

Date: 2026-05-09
Lane: H1 embedded vLLM LMCacheConnectorV1
Score impact: none; remains blocked, no fixture imported

## Trigger

This pass fixed the prior H1 runtime import blocker:

```text
ModuleNotFoundError: No module named 'sortedcontainers'
```

The fix was TDD-backed before the live rerun.

## Dependency contract found

LMCache declares dynamic runtime dependencies through `setup.py`, which reads:

```text
requirements/common.txt
requirements/cuda_core.txt
```

For H1, the full `requirements/common.txt` file cannot be installed directly after vLLM because it contains:

```text
transformers >= 5.4
```

That would let the resolver lift the vLLM-compatible tokenizer/runtime pins. H1 therefore keeps the local LMCache editable install as:

```text
python -m pip install -e /opt/lmcache --no-build-isolation --no-deps
```

and explicitly installs only the required missing LMCache runtime import that was the current blocker:

```text
sortedcontainers
```

## Implementation change

`BASE_MODAL_PIP_PACKAGES` now includes `sortedcontainers` via `LMCACHE_RUNTIME_DEP_PACKAGES`, while preserving:

```text
vllm==0.10.2
transformers==4.57.6
tokenizers==0.22.2
```

The runner still does not install `requirements/common.txt`, so LMCache's `transformers >= 5.4` requirement cannot upgrade the pinned tokenizer stack.

## RED/GREEN proof

RED:

```bash
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py::test_h1_image_installs_minimal_lmcache_runtime_deps_without_lifting_tokenizer_pins -q
# failed: AttributeError: module has no attribute LMCACHE_RUNTIME_DEP_PACKAGES
```

GREEN/local gates:

```bash
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py::test_h1_image_installs_minimal_lmcache_runtime_deps_without_lifting_tokenizer_pins -q
# 1 passed
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
# 14 passed
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
https://modal.com/apps/ocwc22/main/ap-kWfAFi8N8BAYUqyzfLB2FS
```

Remote artifact:

```text
lmcache-embedded-advanced-lab:/packet-h1-embedded-vllm/20260509T203006Z
```

Local artifact:

```text
/Users/chen/Projects/inferguard/modal-out/packet-h1-embedded-vllm/20260509T203006Z
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
-e git+https://github.com/OCWC22/LMCache.git@06a73b21580a53c13f37e9999fd001009d0881e3#egg=lmcache
sortedcontainers==2.4.0
transformers==4.57.6
tokenizers==0.22.2
vllm==0.10.2
```

The previous `sortedcontainers` blocker is cleared.

## Result

H1 still blocked before health. New precise blocker:

```text
ModuleNotFoundError: No module named 'aiofile'
```

Stack path:

```text
vllm.distributed.kv_transfer.kv_connector.v1.lmcache_connector
→ lmcache.integration.vllm.vllm_v1_adapter
→ lmcache.integration.vllm.vllm_service_factory
→ lmcache.v1.cache_engine
→ lmcache.v1.storage_backend.__init__
→ lmcache.v1.storage_backend.gds_backend
→ import aiofile
```

Cause: `--no-deps` continues to correctly protect `transformers==4.57.6`, but it now exposes the next uninstalled LMCache runtime dependency imported unconditionally by LMCache's storage backend package.

## Score / protocol outcome

- No H1 fixture imported.
- H2/H3 were not run.
- I1 release readiness remains blocked.
- Score remains 96/100.
- No second H1 rerun was performed per the cost guard.

## Exact next command

Do not rerun H1 until the explicit LMCache runtime dependency allowlist includes the next proven missing import without installing LMCache's full `requirements/common.txt` or lifting the transformers/tokenizers pins.

Next TDD change should add `aiofile` to `LMCACHE_RUNTIME_DEP_PACKAGES`, keep `transformers==4.57.6` / `tokenizers==0.22.2`, and rerun local gates before the next single H1 runtime attempt.

```bash
cd /Users/chen/Projects/inferguard
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
uv run pytest tests/test_lmcache_live_fixtures.py -q
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
uv run pytest tests/test_observability_coverage.py -q
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h1_embedded_vllm
```
