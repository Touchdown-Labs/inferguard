# Final Real H100 Release Smoke Report v0.1

Date: 2026-05-10
Repo: `/Users/chen/Projects/inferguard`
Branch: `ocwc/packet-b-l0-lifecycle-overlay`
Run type: final release smoke after vLLM + LMCache + InferGuard CLI reached 100/100
Status: passed

## Scope discipline

This smoke stayed on the original release scope only:

- vLLM + LMCache + InferGuard CLI
- Packet B / LC1 MP lifecycle
- Packet H3 / embedded CacheBlend

Paused expansion lanes were not resumed: H2/SGLang, Mooncake, DLM, P2P, and PD.

## Local gates before H100

All required local gates passed before any H100 run:

```bash
uv run pytest tests/test_lmcache_live_fixtures.py -q
# 4 passed in 0.52s

uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
# 28 passed in 1.08s

uv run pytest tests/test_observability_coverage.py -q
# 21 passed in 0.44s

uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
# 32 passed, 1 skipped in 0.19s
```

Combined command used:

```bash
uv run pytest tests/test_lmcache_live_fixtures.py -q && \
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q && \
uv run pytest tests/test_observability_coverage.py -q && \
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
```

## Packet B / LC1 MP lifecycle smoke

Command:

```bash
INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache \
modal run scripts/lmcache_mp_modal_packet_lab.py --packet b
```

Receipt:

- Modal app/run: `https://modal.com/apps/ocwc22/main/ap-i3clSmO9WG4fwZQJlF5FLx`
- Modal output path: `/out/packet-b-lifecycle-reuse-eviction/20260510T230559Z`
- Local artifact path: `/Users/chen/Projects/inferguard/modal-out/pulls/20260510T230559Z`
- Pull command: `modal volume get --force lmcache-mp-lab /packet-b-lifecycle-reuse-eviction/20260510T230559Z modal-out/pulls`

Acceptance summary:

- `packet-b-lifecycle-evidence.json`: `claim_status=measured`
- `packet-b-lifecycle-evidence.json`: `acceptance_status=candidate_measured`
- `missing_required_families=[]`
- Required Packet B families populated:
  - `l0_l1_throughput`
  - `l0_lifecycle`
  - `l1_eviction`
  - `l1_lifecycle`
  - `lookup_hits`
  - `lookup_reuse`
  - `real_reuse`
- `lmcache_compat_report.json`: `detected_mode=mp`, `failure_reasons=[]`
- `observability_coverage.json`: `detected_lmcache_mode=mp`
- `diagnose-bottleneck/bottleneck_diagnosis.json`: present
- `agent_kv_offload_report.json`: present
- `l0_block_boundary_evidence.json`: present

Result: passed. The H100 smoke proves `lmcache_mp_l0_block_*` / L0 lifecycle still populates and the collect/compat/coverage/diagnose pipeline still runs on the MP runtime family.

## Packet H3 / embedded CacheBlend smoke

Existing focused runner was present, so one H100 H3 CacheBlend run was allowed by the smoke spec.

Command:

```bash
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py --packet h3-cacheblend
```

Receipt:

- Modal app/run: `https://modal.com/apps/ocwc22/main/ap-3OmReCOzyoAFB4qD88me8g`
- Modal output path: `/out/packet-h3-cacheblend/20260510T232009Z`
- Local artifact path: `/Users/chen/Projects/inferguard/modal-out/pulls/20260510T232009Z`
- Pull command: `modal volume get --force lmcache-embedded-advanced-lab /packet-h3-cacheblend/20260510T232009Z modal-out/pulls`

Acceptance summary:

- `lmcache_otel.jsonl`: present and non-empty (`32398` bytes)
- `cb.*` span evidence: present (`24` matching lines)
- `lmcache_blend_metrics.prom`: present and non-empty (`1664` bytes)
- `lmcache_blend_*` metrics: present
- `lmcache_compat_report.json`: `detected_mode=embedded_cacheblend`
- `lmcache_compat_report.json`: `detected_architecture.label=vllm_embedded_cacheblend`
- `lmcache_compat_report.json`: `failure_reasons=[]`
- `observability_coverage.json`: `detected_lmcache_mode=embedded_cacheblend`
- `diagnose-bottleneck/bottleneck_diagnosis.json`: present

Result: passed. The H100 smoke proves embedded CacheBlend starts, emits non-empty OTel evidence with `cb.*` spans, emits `lmcache_blend_*` metrics, and remains classified as `embedded_cacheblend` rather than MP/mixed.

## Fixture decision

No new fixture was imported. Both runtime families already had accepted live fixtures and these smoke artifacts do not change the 100/100 score. This report records the clean final release-smoke receipt instead of replacing accepted evidence.

## Auditable H100 runtime facts

These facts are artifact-backed by the Packet B and Packet H3 Modal receipts above.
They are the facts an external auditor should use when checking what was proven.

### Raw Modal allocation

- Modal GPU request: `gpu="H100"`.
- Code-level function shape: `@app.function(gpu="H100", timeout=4 * 60 * 60, startup_timeout=30 * 60, volumes={"/out": volume})`.
- Actual GPU identity from `nvidia-smi`: `NVIDIA H100 80GB HBM3`.
- Visible GPUs: `1`.
- Visible VRAM: `81,559 MiB`.
- Power cap: `700W`.
- MIG: disabled.
- Python: `3.11.5`.
- Persistent Modal volume mount: `/out`.

### Packet B / LC1 MP runtime config

- Modal run: `https://modal.com/apps/ocwc22/main/ap-i3clSmO9WG4fwZQJlF5FLx`.
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/pulls/20260510T230559Z`.
- Region: `sines-2`.
- Image: `im-RdAdU8rOwqS91oyt7Kvb8M`.
- CUDA container version: `13.0.2`.
- NCCL: `2.28.3-1`.
- Driver from `nvidia-smi`: `580.95.05`.
- CUDA reported by `nvidia-smi`: `13.0`.
- Workload: `long_context_agent_kv_offload`.
- Model: `Qwen/Qwen3-8B`.
- vLLM connector: `LMCacheMPConnector`.
- vLLM role: `kv_both`.
- vLLM max model length: `8192`.
- vLLM GPU memory utilization: `0.65`.
- vLLM port: `8000`.
- LMCache standalone server: yes.
- LMCache MP host/port: `tcp://127.0.0.1:6555`.
- LMCache HTTP port: `8080`.
- LMCache Prometheus port: `9090`.
- LMCache local CPU: `True`.
- LMCache max local CPU size: `8.0`.
- LMCache chunk size: `256`.
- LMCache L1 size: `1 GB`.
- Metrics sample rate: `1.0`.
- Requests: `48` total: `12` warm, `28` pressure, `8` retest.

### Packet B / LC1 measured observability

- `lmcache_compat_report.json`: `detected_mode=mp`, `failure_reasons=[]`.
- `packet-b-lifecycle-evidence.json`: `claim_status=measured`, `missing_required_families=[]`.
- Required Packet B families populated: `l0_l1_throughput`, `l0_lifecycle`, `l1_eviction`, `l1_lifecycle`, `lookup_hits`, `lookup_reuse`, `real_reuse`.
- Lookup requested tokens: `177,152`.
- Lookup hit tokens: `98,816`.
- Lookup hit rate: `0.5578`.
- L1 memory usage: `792,723,456` bytes.
- L1 evicted keys: `4`.
- L1 read keys: `386`.
- L1 write keys: `25`.
- L0 boundary events: `1,680`.
- Total reported L0 blocks: `58,460`.
- Report block allocation records: `336` through each stage.
- vLLM generation tokens: `4,608`.
- vLLM successful requests: `48`.
- Time per output token: `0.00662` seconds.
- Decode time: `0.629` seconds.

### Packet H3 / embedded CacheBlend runtime config

- Modal run: `https://modal.com/apps/ocwc22/main/ap-3OmReCOzyoAFB4qD88me8g`.
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/pulls/20260510T232009Z`.
- Region: `us-east4`.
- Cloud provider: GCP.
- Image: `im-V9Til821De3rwbJwx4nPUr`.
- CUDA container version: `12.8.1`.
- NCCL: `2.25.1-1`.
- Actual GPU identity from `nvidia-smi`: `NVIDIA H100 80GB HBM3`, `81,559 MiB` VRAM, MIG disabled.
- Model: `Qwen/Qwen3-0.6B`.
- vLLM package: `vllm==0.10.2`.
- transformers: `4.57.6`.
- vLLM connector: `LMCacheConnectorV1`.
- vLLM role: `kv_both`.
- vLLM max model length: `8192`.
- vLLM GPU memory utilization: `0.80`.
- OTel traces endpoint: `http://127.0.0.1:4317`.
- Detailed traces: `all`.
- LMCache local CPU: `True`.
- LMCache max local CPU size: `8.0`.
- LMCache chunk size: `256`.
- LMCache usage tracking: `false`.
- Workload: `cacheblend_reuse`.

### Packet H3 / embedded CacheBlend measured observability

- `lmcache_compat_report.json`: `detected_mode=embedded_cacheblend`, `detected_architecture.label=vllm_embedded_cacheblend`, `failure_reasons=[]`.
- `lmcache_otel.jsonl`: present and non-empty.
- `cb.*` spans: `24` span lines.
- `lmcache_blend_metrics.prom`: present and non-empty.
- `lmcache_blend_lookup_requests_total`: `1` per scrape sample.
- `lmcache_blend_lookup_requested_tokens_total`: `1,764`.
- `lmcache_blend_lookup_hit_tokens_total`: `1,764`.
- `lmcache_blend_retrieve_requests_total`: `1`.
- `lmcache_blend_retrieve_chunks_total`: `6`.
- CacheBlend lookup hit rate: `1.0`.
- Retrieve hit rate: p50 `0.5`, max `1.0`.
- Prompt tokens: `73,440`.
- Generation tokens: `3,840`.
- Request success total: `40`.
- Prefix cache hits: `31,648`.
- Prefix cache queries: `73,440`.
- Prefix cache hit rate: `0.4309`.
- Time per output token: `0.00352` seconds.
- Decode time: `0.334` seconds.
- Prefill time: `0.04098` seconds.

## Claim ledger

| Claim | Status | Evidence |
| --- | --- | --- |
| Original vLLM + LMCache + InferGuard CLI release scope is 100/100. | `release_ready` | Local gates above plus Packet B and H3 smoke receipts. |
| LMCache MP observability with vLLM is 100% covered for the InferGuard CLI acceptance scope. | `release_ready` | Packet A-F accepted fixtures plus Packet B H100 LC1 receipt. |
| Packet B measured real standalone LMCache MP L0/L1 lifecycle, lookup, reuse, and vLLM request metrics on H100. | `measured` | `/Users/chen/Projects/inferguard/modal-out/pulls/20260510T230559Z`. |
| Packet H3 measured embedded CacheBlend metrics and `cb.*` OTel spans on H100. | `measured` | `/Users/chen/Projects/inferguard/modal-out/pulls/20260510T232009Z`. |
| Continuous DCGM/NVML-level GPU utilization, HBM bandwidth, NVLink, PCIe, and sustained power telemetry are proven. | `not_proven` | InferGuard summaries show `dcgm_sample_count=0`; no accepted DCGM/NVML sampler artifact exists. |
| H2/SGLang, Mooncake, DLM/llm-d, P2P, and PD are complete release blockers for the original vLLM + LMCache CLI scope. | `not_applicable` | These are paused backend-expansion lanes, not the original release scope. |

## Overall result

Passed. No regression found. Score remains 100/100 for the original vLLM + LMCache + InferGuard CLI scope.

Precise yes/no answer: yes, LMCache MP observability with vLLM is 100% covered for the InferGuard CLI acceptance scope; no, this does not mean continuous low-level hardware telemetry is 100% covered.

## Next work

No additional H100 run is needed for the original release smoke. The only known missing proof is a separate hardware-telemetry lane:

1. Add or enable a DCGM or NVML sampler inside the Modal H100 runners.
2. Capture accepted samples for GPU utilization, HBM bandwidth, NVLink, PCIe, and power.
3. Re-run one focused H100 smoke and update this claim ledger from `not_proven` to `measured` only if those samples are populated.

For pre-demo confidence, rerun only local gates:

```bash
uv run pytest tests/test_lmcache_live_fixtures.py -q && \
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q && \
uv run pytest tests/test_observability_coverage.py -q && \
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
```
