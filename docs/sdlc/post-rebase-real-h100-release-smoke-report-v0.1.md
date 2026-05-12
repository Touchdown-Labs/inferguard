# Post-rebase real H100 release smoke report v0.1

Date: 2026-05-11
Scope: InferGuard LMCache/vLLM post-rebase release smoke
Classification: release smoke, not a new scoring exercise

## Baseline

This run followed `/Users/chen/Projects/inferguard/docs/prompts/2026-05-11-post-rebase-modal-h100-release-smoke-v0.1.md` after the LMCache and vLLM rebases.

Recorded refs before local gates:

| Repo | Branch / status | HEAD |
| --- | --- | --- |
| InferGuard | `ocwc/packet-b-l0-lifecycle-overlay`, ahead 2; unrelated dirty `docs/getting-started/quick-start.md`, `uv.lock`, untracked `docs/prompts/` preserved | `a83804008fac3a95668600acd1bf3c2b5fa8bccb` |
| LMCache | `ocwc/l0-boundary-evidence`; untracked `.DS_Store` preserved | `f2a6a037c2af2f91dae958ec9f94aacd1f34984b` |
| vLLM | `ocwc/simple-cpu-offload-metrics`, ahead 5 / behind 1 | `171fd54c4c3005c2f50f1feaefe4a5dd5a29ebf0` |
| Touchdown-Labs | `main`, ahead 7; unrelated dirty/untracked files preserved | `680fa98868550a5dd8371da2e4a0532709fccf20` |

The LMCache and vLLM heads match the post-rebase review prompt expectations. vLLM still reports branch divergence from origin; this was recorded, not modified.

## Delta since rebase review

- Local focused InferGuard gates passed before any H100 launch.
- Packet B / standalone LMCache MP was rerun after the InferGuard runner health/status route patch and is now green for the post-rebase release smoke.
- Packet H3 / embedded CacheBlend launched on Modal H100, completed, was pulled locally, and passed the existing InferGuard compatibility/report path.
- No fixture was imported. The new H3 artifact is a release-smoke receipt only; it does not supersede the prior accepted fixture.

## Local gates

All required local gates passed:

```text
uv run pytest tests/test_lmcache_live_fixtures.py -q
# 4 passed in 0.24s

uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
# 28 passed in 0.15s

uv run pytest tests/test_observability_coverage.py -q
# 21 passed in 0.27s

uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
# 32 passed, 1 skipped in 0.11s

uv run mkdocs build
# Documentation built in 0.97 seconds
```

## Evidence ledger

### Packet B / standalone LMCache MP

- Exact command:

```bash
cd /Users/chen/Projects/inferguard
INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache modal run scripts/lmcache_mp_modal_packet_lab.py --packet b
```

- Initial blocked Modal run URL: `https://modal.com/apps/ocwc22/main/ap-YPfI7S59z2PU0TW1mNOJxJ` (`/api/healthcheck` stale-route blocker).
- Fixed rerun Modal run URL: `https://modal.com/apps/ocwc22/main/ap-N4iIP7A8tie46P75qKYd16`
- Result: `live_validated`
- Modal output path: `/out/packet-b-lifecycle-reuse-eviction/20260511T053256Z`
- Pull command:

```bash
modal volume get --force lmcache-mp-lab /packet-b-lifecycle-reuse-eviction/20260511T053256Z modal-out/pulls
```

- Local artifact path: `/Users/chen/Projects/inferguard/modal-out/pulls/20260511T053256Z`
- Fixture decision: not imported because this was a release-smoke receipt, not a scoring exercise.
- Required Packet B assertions verified from the pulled artifact: `packet-b-lifecycle-evidence.json` has `claim_status=measured`, `acceptance_status=candidate_measured`, and `missing_required_families=[]`; `lmcache_compat_report.json` has `failure_reasons=[]`; `http/capture_manifest.json` records `healthcheck.json` at `/healthcheck` and `status.json` at `/status`.

Observed launch/build context before failure:

- Local LMCache source mounted from `/Users/chen/Projects/LMCache`.
- Local vLLM connector overlay mounted from `/Users/chen/Projects/vllm/vllm`.
- Runner env included `INFERGUARD_LMCACHE_SOURCE_KIND=local`, `INFERGUARD_LMCACHE_SOURCE_REF=/Users/chen/Projects/LMCache`, `INFERGUARD_VLLM_SOURCE_KIND=local_connector_overlay`, `INFERGUARD_VLLM_SOURCE_REF=/Users/chen/Projects/vllm`, `INFERGUARD_PACKET_B_VLLM_GPU_MEMORY_UTILIZATION=0.65`, and `INFERGUARD_PACKET_B_VLLM_MAX_MODEL_LEN=8192`.
- Container banner reported CUDA `13.0.2`.

### Packet H3 / embedded CacheBlend

- Exact command:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py --packet h3-cacheblend
```

- Modal run URL: `https://modal.com/apps/ocwc22/main/ap-Tlw2V883uj6vbcVT3tAsnm`
- Modal output path: `/out/packet-h3-cacheblend/20260511T051119Z`
- Pull command:

```bash
modal volume get --force lmcache-embedded-advanced-lab /packet-h3-cacheblend/20260511T051119Z modal-out/pulls
```

- Local artifact path: `/Users/chen/Projects/inferguard/modal-out/pulls/20260511T051119Z`
- Result: `live_validated` release-smoke receipt for H3.
- Fixture decision: not imported because the existing accepted H3 fixture remains sufficient and this was a release smoke, not a scoring exercise.

Runtime evidence from pulled artifact:

- GPU identity: `NVIDIA H100 80GB HBM3` from `env.txt`.
- Driver/CUDA: NVIDIA driver `580.95.05`, `nvidia-smi` CUDA `13.0`; container banner CUDA `12.8.1`.
- Python: `3.11.5`.
- NCCL: `nvidia-nccl-cu12==2.27.3`.
- vLLM: `0.10.2`.
- LMCache: editable source from `OCWC22/LMCache.git@f2a6a037...`; engine log reports `0.4.5.dev95-gf2a6a037`.
- Model: `Qwen/Qwen3-0.6B`.
- Max model length: `8192`.
- GPU memory utilization: `0.80`.
- Connector: `LMCacheConnectorV1`, `kv_role=kv_both`.
- Port: vLLM API on `8000`; OTLP endpoint `127.0.0.1:4317`.
- Cache config: `local_cpu=true`, `max_local_cpu_size=8.0`, `chunk_size=256`, `use_layerwise=true`, `enable_blending=true`, `blend_check_layers=[1]`, `blend_recompute_ratios=[0.15]`.

Generated telemetry files include:

- `engine_metrics_loaded.prom`
- `lmcache_blend_metrics.prom`
- `lmcache_otel.jsonl`
- `lmcache_compat_report.json`
- `observability_coverage.json`
- `diagnose-bottleneck/bottleneck_diagnosis.json`
- `inferguard-job/metrics/raw_samples.jsonl`
- `inferguard-job/metrics/engine_metrics_timeline.jsonl`

Compatibility/report verification from the artifact:

```text
lmcache_compat_report.json: detected_mode=embedded_cacheblend
lmcache_compat_report.json: detected_architecture.label=vllm_embedded_cacheblend
lmcache_compat_report.json: failure_reasons=[]
observability_coverage.json: detected_lmcache_mode=embedded_cacheblend
lmcache_otel.jsonl: 32396 bytes, 24 lines containing cb.*
lmcache_blend_metrics.prom: lmcache_blend_lookup_hit_tokens_total, lmcache_blend_lookup_requested_tokens_total, lmcache_blend_lookup_requests_total, lmcache_blend_retrieve_chunks_total, lmcache_blend_retrieve_requests_total
diagnose-bottleneck/bottleneck_diagnosis.json: claim_status=measured
```

## Status matrix

| Lane | Post-rebase smoke state | Evidence |
| --- | --- | --- |
| Local gates | `release_ready` | All required pytest gates and mkdocs build passed before Modal. |
| Packet B / standalone LMCache MP | `live_validated` | Modal run `ap-N4iIP7A8tie46P75qKYd16`, local pull `/Users/chen/Projects/inferguard/modal-out/pulls/20260511T053256Z`, lifecycle evidence `claim_status=measured`, `missing_required_families=[]`, `failure_reasons=[]`. |
| Packet H3 / embedded CacheBlend | `live_validated` | Modal run `ap-Tlw2V883uj6vbcVT3tAsnm`, local pull `/Users/chen/Projects/inferguard/modal-out/pulls/20260511T051119Z`, `failure_reasons=[]`. |
| Fixture import | `not_applicable` | Release-smoke receipt only; no new fixture imported. |
| Hardware telemetry | `not_proven` | `nvidia-smi` identity exists, but continuous DCGM/NVML GPU utilization, HBM bandwidth, NVLink, PCIe, and sustained power telemetry were not sampled. |

## Hardware telemetry caveat

This smoke does not prove continuous DCGM/NVML hardware telemetry, HBM bandwidth, NVLink, PCIe, or sustained power telemetry. The accepted wording remains: LMCache MP observability with vLLM is 100% covered for the InferGuard CLI acceptance scope. That does not mean continuous DCGM/NVML hardware telemetry is covered.

## Remaining work / blockers

1. Packet B stale-route blocker is resolved by updating the InferGuard runner to current LMCache MP routes: `/healthcheck` and `/status`.
2. Keep Packet B and H3 as release-smoke receipts; no fixture replacement is needed unless a future run improves or supersedes accepted evidence.
3. Hardware telemetry remains outside this smoke's proof scope.

## Next PR implications

- InferGuard: runner route contract patched and verified locally with `uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q` (`28 passed in 0.46s`); Packet B post-rebase release-smoke parity is restored.
- LMCache: no source change required for this blocker; current routes are `/healthcheck` and `/status`.
- vLLM: no H3 regression observed with vLLM package `0.10.2`; Packet B used the local connector overlay from the rebased vLLM checkout and produced green compatibility evidence.
