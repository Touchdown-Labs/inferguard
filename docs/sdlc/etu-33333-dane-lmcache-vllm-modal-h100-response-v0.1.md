# ETU #33333: Dane LMCache/vLLM Modal H100 CacheBlend and Merge-Readiness Response v0.1

Date: 2026-05-21
Repo: `/Users/chen/Projects/inferguard`
Branch: `ocwc/packet-b-l0-lifecycle-overlay`
Fork/branch link: <https://github.com/Touchdown-Labs/inferguard/tree/ocwc/packet-b-l0-lifecycle-overlay>
Artifact file link: <https://github.com/Touchdown-Labs/inferguard/blob/ocwc/packet-b-l0-lifecycle-overlay/docs/sdlc/etu-33333-dane-lmcache-vllm-modal-h100-response-v0.1.md>
Audience: Dane / ETU
Scope: InferGuard LMCache/vLLM Modal H100 CacheBlend and merge-readiness work
Status: not merge-ready on the latest reported readiness packet

## Executive summary

Dane, for ETU #33333 we have a docs-gated response for the InferGuard LMCache/vLLM H100 work. The evidence separates two things:

1. Historical accepted Modal H100 evidence for vLLM plus LMCache MP and embedded CacheBlend.
2. The latest reported merge-readiness command result from the 2026-05-18 local Packet B and Packet C artifacts.

The latest reported readiness result is `merge_ready: false`. The current blockers are:

- `cacheblend_not_measured`: CacheBlend was not measured in the latest reported Packet B / Packet C readiness packet.
- `lmcache_mp_l1_failures_observed`: diagnostic value `279.0`.
- `repo_dirty`: `/Users/chen/Projects/LMCache` was dirty at readiness-evaluation time.

Therefore, this is not a production-readiness or final-merge approval. It is a clear evidence ledger showing what has been measured, how to reproduce the readiness check, what is still blocked, and what we are not claiming.

## Modal run links

Accepted historical Modal H100 evidence already present in this repository:

| Evidence lane | Modal run | Local or remote artifact noted in repo | What it proves |
| --- | --- | --- | --- |
| LMCache MP complete acceptance | <https://modal.com/apps/ocwc22/main/ap-3vjXTB0zufbdBRDTPAbUqd> | `/artifacts/ocwc22_lmcache_mp/20260512T095222Z` | Historical accepted MP acceptance surface where documented. |
| Packet B / LC1 vLLM plus standalone LMCache MP | <https://modal.com/apps/ocwc22/main/ap-i3clSmO9WG4fwZQJlF5FLx> | `/Users/chen/Projects/inferguard/modal-out/pulls/20260510T230559Z` | H100 Packet B / LC1 MP lifecycle, lookup, reuse, and vLLM request evidence. |
| Packet H3 embedded CacheBlend / vLLM | <https://modal.com/apps/ocwc22/main/ap-3OmReCOzyoAFB4qD88me8g> | `/Users/chen/Projects/inferguard/modal-out/pulls/20260510T232009Z` | H100 embedded CacheBlend startup, `cb.*` spans, and `lmcache_blend_*` metrics. |

Latest reported 2026-05-18 local packet paths from the prior session:

- Packet B: `/tmp/packet-b-20260518T221627Z`
- Packet C: `/tmp/packet-c-20260518T220212Z`
- Readiness output: `/tmp/lmcache-merge-ready-current.json`

Those `/tmp` paths and `/tmp/lmcache-merge-ready-current.json` were not present in this checkout at doc-generation time, and no newer Modal URL was recoverable from the repository for those exact 2026-05-18 local packet paths. For that reason, this response uses the verified existing Modal links above and labels the 2026-05-18 packet paths as prior local artifacts only.

## Expected input

The reported readiness command consumes:

- A Packet B directory containing long-context agent KV offload and LMCache MP evidence.
- A Packet C directory containing L2 configuration and data evidence.
- Repository path arguments for vLLM, LMCache, and SGLang.
- An output path for the JSON readiness report.
- `--json` for machine-readable output.

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

Expected Packet B evidence fields from the prior session:

- `status`: `measured`
- `claim_status`: `measured`
- `acceptance_status`: `candidate_measured`
- `kv_offload_claim_status`: `measured`
- `workload_profile`: `long_context_agent_kv_offload`
- `workload_request_count`: `48`
- `cacheblend_measured`: `false`
- `l1_failures`: `279.0`

Expected Packet C evidence fields from the prior session:

- `status`: `measured`
- `l2_configured`: `true`
- `l2_data_file_count`: `14`
- `l2_data_bytes`: `528482304`
- `l2_metric_family_count`: `11`
- L2 CLI args present: `type fs`, `persist_enabled true`

## Expected output

The readiness output is expected to be JSON. The important customer-facing outcome from the latest reported run is:

```json
{
  "merge_ready": false,
  "blockers": [
    "cacheblend_not_measured",
    "lmcache_mp_l1_failures_observed",
    "repo_dirty"
  ]
}
```

The exact prior output path was reported as:

```text
/tmp/lmcache-merge-ready-current.json
```

That file is not present in this checkout now, so this document treats the JSON content as a prior-session result rather than a newly re-read artifact.

## Current readiness status and blockers

Current status: `merge_ready: false`.

| Blocker | Evidence status | Why it blocks merge readiness | Required closure condition |
| --- | --- | --- | --- |
| `cacheblend_not_measured` | Latest Packet B / C readiness packet says `cacheblend_measured=false`. | Historical H3 CacheBlend evidence exists, but the latest Packet B / C readiness packet did not measure CacheBlend. | Run or attach a readiness packet that includes measured CacheBlend evidence, or explicitly scope CacheBlend out of the merge gate. |
| `lmcache_mp_l1_failures_observed` | Prior readiness diagnostic value: `279.0`. | L1 failures are present and must be explained, expected, bounded, or fixed before calling the packet merge-ready. | Root-cause and classify the failures, then rerun and show either zero unexpected L1 failures or accepted expected-failure rationale. |
| `repo_dirty` | Prior readiness input reported `/Users/chen/Projects/LMCache` dirty. | Merge-readiness decisions must be tied to auditable source state. Dirty repo state makes reproduction ambiguous. | Commit, stash, or clean unrelated LMCache changes, then rerun and record exact SHAs. |

## How we test it exactly

### Prior implementation-level test report from the session

The prior session reported this command:

```bash
python -m pytest -q \
  tests/test_lmcache_merge_ready_cli.py \
  tests/test_observability_coverage.py \
  tests/test_lmcache_mp_modal_packet_lab.py \
  tests/test_compat_serde.py \
  tests/test_cacheblend_coverage_gaps.py
```

Reported result:

```text
109 passed
```

The prior session also reported ruff check and format passing on the new files.

Important checkout note: in this checkout, the claimed implementation files `src/inferguard/lmcache_merge_ready.py` and `tests/test_lmcache_merge_ready_cli.py` are not present, and `lmcache-merge-ready` is not documented in the files inspected for this docs-only artifact. This response therefore does not claim that those implementation files are pushed in this branch.

### Docs-only verification for this ETU artifact

For this docs-only artifact, the lightweight verification is:

```bash
git diff --check -- docs/sdlc/etu-33333-dane-lmcache-vllm-modal-h100-response-v0.1.md \
  docs/prompts/2026-05-21-etu-33333-dane-lmcache-vllm-modal-h100-response-v0.1.md
```

If a built MkDocs `site/` directory exists, the repository link checker can be run separately:

```bash
python scripts/check_docs_links.py site
```

No expensive runtime tests are required for this docs-only response artifact.

## How to reproduce exactly

### 1. Start from the pushed branch

```bash
git clone git@github.com:Touchdown-Labs/inferguard.git
cd inferguard
git checkout ocwc/packet-b-l0-lifecycle-overlay
```

### 2. Confirm the ETU response artifact

```bash
sed -n '1,240p' docs/sdlc/etu-33333-dane-lmcache-vllm-modal-h100-response-v0.1.md
```

### 3. Reproduce the readiness command when the packet artifacts and CLI implementation are available

The prior readiness command requires the Packet B and Packet C local artifacts and a checkout containing the `lmcache-merge-ready` CLI. With those present:

```bash
PYTHONPATH=src python -m inferguard.cli lmcache-merge-ready \
  --packet-b-dir /tmp/packet-b-20260518T221627Z \
  --packet-c-dir /tmp/packet-c-20260518T220212Z \
  --repo vllm=/Users/chen/Projects/vllm \
  --repo lmcache=/Users/chen/Projects/LMCache \
  --repo sglang=/Users/chen/Projects/sglang \
  --output /tmp/lmcache-merge-ready-current.json \
  --json

cat /tmp/lmcache-merge-ready-current.json
```

Expected readiness result until blockers are cleared:

```text
merge_ready: false
```

### 4. Reproduce historical Modal evidence already documented in repo

Packet B / LC1 MP historical run:

```bash
INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache \
modal run scripts/lmcache_mp_modal_packet_lab.py --packet b
```

Historical Modal receipt:

```text
https://modal.com/apps/ocwc22/main/ap-i3clSmO9WG4fwZQJlF5FLx
```

Packet H3 embedded CacheBlend historical run:

```bash
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py --packet h3-cacheblend
```

Historical Modal receipt:

```text
https://modal.com/apps/ocwc22/main/ap-3OmReCOzyoAFB4qD88me8g
```

These historical Modal receipts prove the documented historical lanes, not the latest 2026-05-18 Packet B / C merge-readiness result.

## Design decisions

- Evidence-gated response: every readiness statement is labeled as measured, historical, prior-session-reported, not recovered, or not proven.
- Separate historical CacheBlend evidence from current readiness evidence: H3 proves historical embedded CacheBlend behavior, while the latest Packet B / C readiness result still says `cacheblend_measured=false`.
- Dirty-repo refusal: a dirty LMCache source checkout blocks merge-readiness because exact source state cannot be reproduced.
- Conservative merge gate: Packet B and Packet C measurements are not enough to mark the work merge-ready when CacheBlend is unmeasured in the readiness packet and L1 failures are present.
- Docs-only delivery: this commit intentionally creates a durable ETU response artifact and prompt/spec only. It does not alter runtime code or tests.

## Limitations and trade-offs

- The 2026-05-18 local packet directories were reported from a prior session but are not present now under `/tmp`, so this artifact cannot re-open those JSON files.
- No newer Modal URL was recovered for `/tmp/packet-b-20260518T221627Z` or `/tmp/packet-c-20260518T220212Z`.
- Historical H3 CacheBlend evidence is valid for its Modal run, but it is not a substitute for CacheBlend being measured in the latest merge-readiness Packet B / C command.
- The readiness command result is intentionally strict. It prevents an ambiguous merge-ready claim while L1 failures and dirty repo state remain unresolved.
- This artifact does not claim performance improvement, production readiness, or customer deployment readiness.
- This artifact does not claim DCGM, NVML, HBM bandwidth, NVLink, PCIe, or sustained power coverage. Those require separate accepted hardware-telemetry artifacts.

## Evidence ledger

| Claim | Status | Evidence |
| --- | --- | --- |
| Latest reported readiness is merge-ready. | `false` | Prior readiness result reported `merge_ready: false`. |
| Packet B long-context agent KV offload was measured in the latest reported packet. | `measured` | Prior Packet B summary: `status=measured`, `claim_status=measured`, `kv_offload_claim_status=measured`, `workload_request_count=48`. |
| Packet C L2 filesystem persistence data was measured in the latest reported packet. | `measured` | Prior Packet C summary: `l2_configured=true`, `l2_data_file_count=14`, `l2_data_bytes=528482304`, `l2_metric_family_count=11`, `type fs`, `persist_enabled true`. |
| CacheBlend was measured in the latest Packet B / C readiness packet. | `not_measured` | Prior Packet B summary: `cacheblend_measured=false`. |
| CacheBlend has historical H100 evidence in repo docs. | `measured_historical` | Modal H3 run: <https://modal.com/apps/ocwc22/main/ap-3OmReCOzyoAFB4qD88me8g>. |
| LMCache MP complete acceptance has historical evidence in repo docs. | `measured_historical` | Modal run: <https://modal.com/apps/ocwc22/main/ap-3vjXTB0zufbdBRDTPAbUqd>. |
| L1 failure diagnostic is clean. | `false` | Prior readiness blocker: `lmcache_mp_l1_failures_observed`, diagnostic `279.0`. |
| LMCache source state was clean for readiness. | `false` | Prior readiness blocker: `repo_dirty` for `/Users/chen/Projects/LMCache`. |
| DCGM/NVML/HBM/NVLink/power telemetry is proven by this packet. | `not_proven` | No accepted artifact cited for those hardware telemetry surfaces. |

## Files changed and implementation touchpoints

This docs-only commit creates:

- `docs/sdlc/etu-33333-dane-lmcache-vllm-modal-h100-response-v0.1.md`
- `docs/prompts/2026-05-21-etu-33333-dane-lmcache-vllm-modal-h100-response-v0.1.md`

Claimed implementation touchpoints from the prior session:

- `src/inferguard/lmcache_merge_ready.py`
- `tests/test_lmcache_merge_ready_cli.py`
- `src/inferguard/cli.py`

Checkout status for those touchpoints during this docs-only artifact generation:

- `src/inferguard/lmcache_merge_ready.py`: not present in this checkout.
- `tests/test_lmcache_merge_ready_cli.py`: not present in this checkout.
- `src/inferguard/cli.py`: present, but this docs-only commit does not modify it.

Because the new CLI implementation files are not present in this checkout, this ETU response does not claim that the `lmcache-merge-ready` implementation is pushed in this branch. It only records the prior-session command and readiness result as context.

## Non-claims

We are not claiming:

- `merge_ready: true`.
- production readiness.
- performance improvement.
- CacheBlend measured in the latest Packet B / C readiness packet.
- that historical H3 CacheBlend evidence closes the latest Packet B / C CacheBlend blocker.
- clean LMCache repository state during the prior readiness run.
- zero LMCache MP L1 failures.
- DCGM, NVML, HBM bandwidth, NVLink, PCIe, or sustained power telemetry coverage.
- that the `lmcache-merge-ready` CLI implementation files are present in this branch.

## Final ETU answer for Dane

Dane, the durable ETU #33333 response is now documented on the pushed branch above. The short version is that we have historical Modal H100 evidence for vLLM plus standalone LMCache MP and embedded CacheBlend, but the latest reported merge-readiness packet is not ready to merge.

The readiness command reported `merge_ready: false`. The blockers are unmeasured CacheBlend in the latest Packet B / C readiness packet, observed LMCache MP L1 failures with diagnostic value `279.0`, and a dirty LMCache repo at readiness-evaluation time. The historical H3 CacheBlend Modal run remains valid evidence for that historical lane, but it does not replace CacheBlend measurement in the latest readiness packet.

To close this, rerun the readiness command from clean vLLM, LMCache, and SGLang source states, attach or regenerate Packet B and Packet C artifacts, include measured CacheBlend evidence or explicitly scope CacheBlend out of the merge gate, and resolve or classify the L1 failures. Until then, the evidence-backed answer is: measured progress exists, historical Modal H100 receipts exist, but final merge readiness is blocked.
