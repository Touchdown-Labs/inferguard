# Packet H1 LMCache runtime deps rerun blocked report v0.4

Date: 2026-05-09
Lane: H1 embedded vLLM `LMCacheConnectorV1`
Status: blocked, no fixture imported, score unchanged

## Change under test

The H1 Modal image now installs a minimal explicit LMCache connector runtime dependency allowlist while preserving the vLLM-compatible pins:

- `aiofile`
- `aiofiles`
- `msgspec`
- `prometheus-client>=0.18.0,<=0.24.1`
- `psutil`
- `py-cpuinfo`
- `pyyaml`
- `pyzmq>=25.0.0`
- `sortedcontainers==2.4.0`
- preserved: `transformers==4.57.6`, `tokenizers==0.22.2`
- LMCache still installs editable with `--no-build-isolation --no-deps`; `requirements/common.txt` is not installed directly because it declares `transformers >= 5.4`.

Source evidence:

- `/Users/chen/Projects/LMCache/requirements/common.txt` contains the dependency source and the incompatible `transformers >= 5.4` line.
- `lmcache.v1.storage_backend.__init__` imports `gds_backend` eagerly.
- `lmcache.v1.storage_backend.gds_backend` imports `aiofile` at module import time.
- `lmcache.v1.memory_management` and `storage_backend/cache_policy/lfu.py` import `sortedcontainers`.
- `lmcache.v1.storage_backend.p2p_backend`, offload/rpc/transfer surfaces import `msgspec` and `zmq`.
- `lmcache.observability`, `lmcache.v1.config`, `lmcache.v1.system_detection`, and `lmcache.usage_context` import `prometheus_client`, `pyyaml`, `psutil`, and `cpuinfo`.

## RED / GREEN

RED:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
# 1 failed, 13 passed
# failing assertion: LMCACHE_RUNTIME_DEP_PACKAGES was only ('sortedcontainers',)
```

GREEN:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
# 14 passed
```

Requested local gates:

```bash
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q  # 14 passed
uv run pytest tests/test_lmcache_live_fixtures.py -q                       # 4 passed
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q                 # 28 passed
uv run pytest tests/test_observability_coverage.py -q                      # 21 passed
```

## Single allowed H1 rerun

Command:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h1_embedded_vllm
```

Modal run: `https://modal.com/apps/ocwc22/main/ap-vI8k8R9cM1MakNWvNYHT8i`
Remote artifact: `lmcache-embedded-advanced-lab:/packet-h1-embedded-vllm/20260509T205313Z`
Local artifact: `/Users/chen/Projects/inferguard/modal-out/packet-h1-embedded-vllm/20260509T205313Z`

Dependency result:

- `aiofile` installed successfully.
- `aiofiles`, `msgspec`, `prometheus-client`, `psutil`, `py-cpuinfo`, `pyyaml`, `pyzmq`, and `sortedcontainers==2.4.0` installed successfully.
- `transformers==4.57.6` and `tokenizers==0.22.2` remained pinned.
- LMCache installed from local source as `lmcache-0.4.5.dev83` with `--no-deps`.
- H1 reached vLLM health, drove repeated-prefix traffic, captured metrics, and ran `collect-lmcache`.

## New blocker

H1 failed at strict `lmcache-compat --fail-on missing-required`:

```text
RuntimeError: required command failed with exit code 1: inferguard lmcache-compat ... --expect-mode embedded ... --fail-on missing-required --json
```

The emitted compat report says:

```json
"detected_mode": "unknown",
"failure_reasons": [
  {"code": "lmcache_mode_mismatch", "message": "expected LMCache mode 'embedded', detected 'unknown'"}
]
```

Important partial proof in the blocked artifact:

- command proof is correct: `--kv-transfer-config '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'`;
- logs contain both `LMCacheConnectorV1` and LMCache store/retrieve activity;
- traffic ran: repeated requests show LMCache hit-token log lines after the first request;
- vLLM `/metrics` did not include embedded `lmcache:*` / `lmcache_*` production counters, so InferGuard could not classify the metrics surface as embedded;
- `observability_coverage.json` was not produced because strict compat failed first.

## Status

No H1 fixture was imported. H2/H3/I1 were not run. Score remains 96/100.

Next exact command after fixing embedded metric export/classification, not before:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h1_embedded_vllm
```
