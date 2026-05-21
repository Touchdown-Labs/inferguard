# ETU #33333 Dane LMCache/vLLM Modal H100 Response Generation Prompt v0.1

Date: 2026-05-21
Repo: `/Users/chen/Projects/inferguard`
Branch: `ocwc/packet-b-l0-lifecycle-overlay`
Output artifact: `docs/sdlc/etu-33333-dane-lmcache-vllm-modal-h100-response-v0.1.md`

## Goal

Create a durable docs-only ETU response artifact for Dane, issue/ticket `33333`, covering the InferGuard LMCache/vLLM Modal H100 CacheBlend and merge-readiness work.

The response must be suitable to paste/send to Dane as a customer-facing ETU final response. It must not be a vague internal update.

## Required content

The ETU response must include:

- Title with `ETU #33333`.
- Full fork or branch link where pushed.
- Modal run links.
- Summary.
- Expected input.
- Expected output.
- Exact testing approach.
- Exact reproduction commands.
- Design decisions.
- Limitations and trade-offs.
- Current readiness status and blockers.
- Evidence ledger or claim ledger.
- Non-claims.
- Files changed and implementation touchpoints only if actually present in the checkout.

## Required evidence discipline

- If `merge_ready` is false, say so.
- Do not call the work 100% complete or production-ready unless artifacts prove it.
- Separate measured Packet B / Packet C evidence from CacheBlend and non-prefix evidence.
- If CacheBlend is historical H3 evidence rather than current Packet B / C evidence, label it as historical.
- Do not make DCGM, NVML, HBM bandwidth, NVLink, PCIe, or power claims unless artifacts prove them.
- If the claimed CLI implementation files are not present in the checkout, state that and do not claim they are pushed.

## Prior-session context to preserve

Reported command:

```bash
PYTHONPATH=src python -m inferguard.cli lmcache-merge-ready \
  --packet-b-dir /tmp/packet-b-20260518T221627Z \
  --packet-c-dir /tmp/packet-c-20260518T220212Z \
  --repo vllm=/Users/chen/Projects/vllm \
  --repo lmcache=/Users/chen/Projects/LMCache \
  --repo sglang=/Users/chen/Projects/sglang \
  --output /tmp/lmcache-merge-ready-current.json \
  --json
```

Reported result:

- Output path: `/tmp/lmcache-merge-ready-current.json`
- `merge_ready: false`
- Blockers: `cacheblend_not_measured`, `lmcache_mp_l1_failures_observed` diagnostic `279.0`, `repo_dirty` for `/Users/chen/Projects/LMCache`

Reported Packet B evidence:

- `status`: `measured`
- `claim_status`: `measured`
- `acceptance_status`: `candidate_measured`
- `kv_offload_claim_status`: `measured`
- `workload_profile`: `long_context_agent_kv_offload`
- `workload_request_count`: `48`
- `cacheblend_measured`: `false`
- `l1_failures`: `279.0`

Reported Packet C evidence:

- `status`: `measured`
- `l2_configured`: `true`
- `l2_data_file_count`: `14`
- `l2_data_bytes`: `528482304`
- `l2_metric_family_count`: `11`
- L2 CLI arg present: `type fs`, `persist_enabled true`

Reported verification from prior implementation work:

```bash
python -m pytest -q \
  tests/test_lmcache_merge_ready_cli.py \
  tests/test_observability_coverage.py \
  tests/test_lmcache_mp_modal_packet_lab.py \
  tests/test_compat_serde.py \
  tests/test_cacheblend_coverage_gaps.py
```

Reported result: `109 passed`.

## Modal link handling

Prefer exact newer Modal links for the 2026-05-18 Packet B and Packet C artifacts if recoverable from repo or artifact metadata.

If no newer link is recoverable, use existing verified links and explicitly label 2026-05-18 packet paths as local artifacts without recovered Modal URLs:

- LMCache MP complete acceptance: <https://modal.com/apps/ocwc22/main/ap-3vjXTB0zufbdBRDTPAbUqd>, artifact `/artifacts/ocwc22_lmcache_mp/20260512T095222Z` if present in docs.
- Packet B / LC1: <https://modal.com/apps/ocwc22/main/ap-i3clSmO9WG4fwZQJlF5FLx>.
- H3 CacheBlend: <https://modal.com/apps/ocwc22/main/ap-3OmReCOzyoAFB4qD88me8g>.

## Docs-only verification

Run lightweight verification only:

```bash
git diff --check -- docs/sdlc/etu-33333-dane-lmcache-vllm-modal-h100-response-v0.1.md \
  docs/prompts/2026-05-21-etu-33333-dane-lmcache-vllm-modal-h100-response-v0.1.md
```

Do not run expensive tests unless required.

## Commit scope

Commit only these new docs files:

- `docs/sdlc/etu-33333-dane-lmcache-vllm-modal-h100-response-v0.1.md`
- `docs/prompts/2026-05-21-etu-33333-dane-lmcache-vllm-modal-h100-response-v0.1.md`

Preserve unrelated dirty work.
