# SGLang LMCache MP Observability Source-Backed Report v0.1

Date: 2026-05-12

## Status

`source_backed_fixture_tested`; live validation pending.

InferGuard now recognizes SGLang + LMCache MP observability when fixture or report evidence includes all of:

- SGLang metrics or launch-manifest evidence.
- LMCache MP metrics.
- PR-backed SGLang MP launch/source evidence for `--enable-lmcache`, `--lmcache-mp-host`, and `--lmcache-mp-port`.

## Upstream state

The SGLang and LMCache MP path is source-backed by open, unmerged upstream PRs:

- SGLang PR #24089: <https://github.com/sgl-project/sglang/pull/24089>
- LMCache PR #3166: <https://github.com/LMCache/LMCache/pull/3166>

## Non-claims

This report does not claim live validation, merged upstream support, performance validation, or production support for SGLang + LMCache MP.

## Verification scope

Fixture tests cover command assembly and observability report classification only. A real SGLang + LMCache MP GPU run remains required before any `live_validated` claim.
