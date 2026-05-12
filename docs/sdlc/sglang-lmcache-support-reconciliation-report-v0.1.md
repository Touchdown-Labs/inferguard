# SGLang + LMCache support reconciliation report v0.1

Date: 2026-05-12

## Decision

LMCache already has a documented embedded/in-process SGLang integration. InferGuard must describe that path as existing and source-backed instead of implying that InferGuard or fork-local SGLang changes make SGLang use LMCache.

SGLang + LMCache MP is separate. Current public GitHub evidence keeps MP in the open-PR / not-merged / not-clean-live-accepted bucket.

## Source ledger

- S1: LMCache SGLang quickstart, `docs/source/getting_started/quickstart.rst`, documents `LMCACHE_CONFIG_FILE=$PWD/lmc_config.yaml` and `python -m sglang.launch_server ... --enable-lmcache`.
- S2: LMCache SGLang adapter, `lmcache/integration/sglang/sglang_adapter.py`, initializes an LMCache engine and performs lookup/retrieve/store calls for SGLang.
- S3: LMCache SGLang config utility, `lmcache/integration/sglang/utils.py`, reads LMCache config from `LMCACHE_CONFIG_FILE` or environment variables.
- S4: LMCache KV events docs, `docs/source/production/kv_cache_events.rst`, documents `enable_kv_events: true` plus SGLang `--kv-events-config` for SGLang event publishing.
- S5: SGLang PR #24089, <https://github.com/sgl-project/sglang/pull/24089>, open, not merged, adds MP wiring via `--lmcache-mp-host` and `--lmcache-mp-port`, with LMCache PR #3166 as companion.
- S6: LMCache PR #3166, <https://github.com/LMCache/LMCache/pull/3166>, open, not merged, adds LMCache-side SGLang MP support and lists remaining abort/liveness work.
- S7: LMCache PR #3002, <https://github.com/LMCache/LMCache/pull/3002>, merged, fixes env-only config validation affecting vLLM/SGLang config paths.
- S8: LMCache issue #3192, <https://github.com/LMCache/LMCache/issues/3192>, open, records an SGLang integration gap for MLA models such as DeepSeek V3/R1.
- S9: LMCache issue #2440, <https://github.com/LMCache/LMCache/issues/2440>, open RFC to send LMCache KV events to SGLang.
- S10: SGLang PR #24549, <https://github.com/sgl-project/sglang/pull/24549>, open, fixes MLA-model support for LMCache Radix Cache.
- S11: SGLang PR #23534, <https://github.com/sgl-project/sglang/pull/23534>, open, adds XPU device support for LMCache radix cache integration.
- S12: LMCache PR #3121, <https://github.com/LMCache/LMCache/pull/3121>, open, adds SGLang XPU connectors for LMCache KV cache transfer.
- S13: LMCache PR #3212, <https://github.com/LMCache/LMCache/pull/3212>, closed/unmerged draft, documents a layerwise retriever cleanup/deadlock concern in the SGLang adapter path.
- S14: LMCache issue #1949, <https://github.com/LMCache/LMCache/issues/1949>, closed RFC describing LMCache's serving-engine-agnostic integration direction.

## Version / edit provenance ledger

- Embedded LMCache config path:
  - Repo: `LMCache/LMCache`
  - File: `lmcache/integration/sglang/utils.py`
  - Introduced: `f3bba133`
  - Author/date: Yuwei An, 2025-06-23
  - Code evidence: `lmcache_get_config()` reads `LMCACHE_CONFIG_FILE` or LMCache environment variables for SGLang.

- Embedded LMCache adapter path:
  - Repo: `LMCache/LMCache`
  - File: `lmcache/integration/sglang/sglang_adapter.py`
  - Introduced: `f3bba133`
  - Author/date: Yuwei An, 2025-06-23
  - Code evidence: `init_lmcache_engine()` and `LMCacheConnector` initialize the LMCache engine for SGLang.

- Embedded layerwise runtime calls:
  - Repo: `LMCache/LMCache`
  - File: `lmcache/integration/sglang/sglang_adapter.py`
  - Introduced/refined: `b72bdfd`, Yuwei An, 2025-08-30; lookup-pin/unpin refined by `9946f1b`, Yuwei An, 2025-10-13 and `ad92d02`, Ziqi Fan, 2025-10-30.
  - Code evidence: `start_load_kv()` calls `lookup()` and `retrieve_layer()`; `store_kv()` calls `lookup()`, `store_layer()`, and `lookup_unpin()`.

- SGLang launch surface:
  - Repo: `sgl-project/sglang`
  - Files: `python/sglang/srt/server_args.py`, `python/sglang/srt/managers/scheduler.py`, `python/sglang/srt/mem_cache/storage/lmcache/lmc_radix_cache.py`
  - Introduced: `9a7ced4`
  - Author/date: Yuwei An, 2025-09-06
  - Code evidence: `enable_lmcache` flag exists; scheduler selects `LMCRadixCache` when `server_args.enable_lmcache` is true; SGLang imports LMCache connector classes.

- Env-only config validation fix:
  - Repo: `LMCache/LMCache`
  - PR: #3002, <https://github.com/LMCache/LMCache/pull/3002>
  - Opened/merged: 2026-04-11T11:08:04Z / 2026-05-11T14:39:19Z
  - Author: `rebel-jinhwan`
  - Local lineage: `9985125f`, Jinhwan Suk, 2026-05-11
  - Code evidence: `config.validate()` now runs in the SGLang/vLLM env-only config path.

- SGLang + LMCache MP PRs:
  - SGLang PR #24089, <https://github.com/sgl-project/sglang/pull/24089>, opened 2026-04-29T21:01:46Z by `Shaoting-Feng`, open/unmerged, head `bcaa2854288b1332a5645450af61f73cbf805472`.
  - LMCache PR #3166, <https://github.com/LMCache/LMCache/pull/3166>, opened 2026-04-29T21:03:17Z by `Shaoting-Feng`, open/unmerged, head `d298d5807fc16aaf896347c1d927383e24c0195f`.

## Claim ledger

- Claim: SGLang can use LMCache without InferGuard in embedded/in-process mode.
  Status: `source_backed`.
  Evidence: S1, S2, S3.

- Claim: InferGuard enables SGLang to read from LMCache.
  Status: `not_applicable` / false framing.
  Evidence: S1-S3 show SGLang/LMCache runtime integration is separate from InferGuard. InferGuard only captures/classifies evidence.

- Claim: SGLang + LMCache embedded mode is production/performance validated by InferGuard.
  Status: `not_proven` until a live SGLang embedded packet is captured and accepted.
  Evidence: current changes are source-backed and fixture-tested only.

- Claim: SGLang + LMCache MP is merged stable support.
  Status: `not_proven`.
  Evidence: S5 and S6 are open PRs; S6 lists remaining work.

- Claim: SGLang + LMCache MP has unresolved compatibility gaps.
  Status: `source_backed`.
  Evidence: S5, S6, S8, S10, S13.

## InferGuard correction made

- `observability_coverage` now emits `sglang_lmcache_embedded_support` separately from `sglang_lmcache_mp_observability`.
- Embedded SGLang + LMCache reports include:
  - `upstream_state=versioned_existing_embedded_support` style source-backed existing support wording.
  - required launch flag `--enable-lmcache`.
  - required config source `LMCACHE_CONFIG_FILE or LMCache environment configuration`.
  - explicit non-claim that embedded support is not MP support.
  - explicit non-claim that InferGuard only captures/classifies evidence.
- Tests now cover:
  - embedded SGLang + LMCache with actual LMCache embedded metrics -> measured artifact-present classification for that fixture.
  - launch signal without LMCache metrics -> source-backed/pending, not upgraded.

## Non-claims

- This report does not claim clean SGLang + LMCache MP live validation.
- This report does not claim performance improvement.
- This report does not claim production support for all SGLang models, especially MLA models.
- This report does not claim InferGuard is in the runtime cache path.
