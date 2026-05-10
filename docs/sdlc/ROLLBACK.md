# LMCache + vLLM Release Rollback

Date: 2026-05-10
Scope: I1 release readiness for original vLLM + LMCache + InferGuard CLI
coverage. This file covers docs/operator rollback only; it does not ask for any
new H100 runs.

## When to rollback

Rollback the release claim from `release_ready` to `live_validated` if any of
these gates regress:

- `uv run mkdocs build` fails.
- The focused LMCache fixture suite fails for accepted Packet A-F, G1, H1, or
  H3 fixtures.
- H3 no longer reports `detected_mode=embedded_cacheblend` /
  `vllm_embedded_cacheblend` with `failure_reasons=[]`.
- MP Packet A-F strict compat starts requiring a paused backend-expansion lane
  such as H2/SGLang, Mooncake, P2P/PD, or DLM.

## Private overlay rollback

The accepted MP lifecycle evidence depends on private overlay refs recorded in
SDLC 195:

- vLLM private branch `ocwc/lmcache-mp-l0-lifecycle` at
  `2536687198bf69fbbe385decdbe3bb8b3aaaf816`.
- LMCache private branch `ocwc/l0-boundary-evidence` at
  `06a73b21580a53c13f37e9999fd001009d0881e3`.

If either overlay becomes suspect, do not delete fixtures. Instead:

1. Mark the relevant release note as `live_validated_pending_overlay_review`.
2. Re-run the local fixture tests against the compact fixtures.
3. Keep SDLC 195 at the last passing score only if the compact fixtures still
   pass and the release docs still name the private refs explicitly.
4. Open a follow-up to identify public vLLM/LMCache refs before recommending the
   lane to external operators.

## Accepted fixture rollback

Accepted fixtures are compact evidence, not raw Modal archives. If a fixture is
found to be malformed or over-permissive:

1. Move only the affected lane back from `release_ready` to `live_validated` or
   `fixture_backed` in SDLC 195.
2. Preserve the fixture directory for forensics unless it contains sensitive
   material.
3. Rebuild the reports from the original local artifact path when available.
4. Re-run the focused suite before restoring the release claim.

Key fixture directories:

- `tests/fixtures/lmcache_live/packet_a/` through `packet_f/`
- `tests/fixtures/lmcache_live/packet_h1/`
- `tests/fixtures/lmcache_live/packet_h3/`

## Paused expansion lanes

Do not rollback I1 because these lanes are paused:

- H2/SGLang: blocked on `sgl_kernel` runtime strategy.
- Mooncake: no runnable local source/runtime contract.
- DLM / `llm-d`: detection-only, no validated field map.
- P2P/PD: backend expansion outside the original vLLM + LMCache CLI closeout.

Rollback only if docs or tests accidentally promote any paused lane into a
release prerequisite.
