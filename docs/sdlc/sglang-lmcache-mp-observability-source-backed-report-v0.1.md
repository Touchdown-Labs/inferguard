# SGLang LMCache MP Observability Source-Backed Report v0.1

Date: 2026-05-12

## Status

`source_backed_fixture_tested`; live validation pending.

InferGuard now recognizes SGLang + LMCache MP observability when fixture or report evidence includes all of:

- SGLang metrics or launch-manifest evidence.
- LMCache MP metrics.
- SGLang runtime launch evidence using existing `--enable-lmcache`, `--lmcache-mp-host`, and `--lmcache-mp-port` flags.

## Upstream state

This closeout is source-backed by LMCache MP observability and InferGuard ingestion/replay changes. SGLang is only the serving engine source of runtime metrics/logs and is launched with existing LMCache flags; it is not a repo to modify for this closeout.

- LMCache observability surface: standalone MP metrics/logs/HTTP evidence.
- InferGuard ingestion/replay: classification and acceptance gating over SGLang runtime metrics plus LMCache MP evidence.

## Non-claims

This report does not claim merged upstream SGLang changes, performance validation, or production support for SGLang + LMCache MP.

## Verification scope

Fixture tests cover command assembly and observability report classification only. A real SGLang + LMCache MP GPU run remains required before any `live_validated` claim.
