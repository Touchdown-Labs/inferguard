# InferGuard SGLang + LMCache embedded correction spec v0.1

## User request
Verify the current GitHub issue/PR state for LMCache and SGLang. If LMCache already supports SGLang, correct InferGuard so it represents the runtime relationship accurately.

## Classification
- AUTO: public GitHub PR/issue reconnaissance, source/doc inspection, docs/classifier/test changes, focused verification.
- REVIEW: upgrading any public support claim beyond source-backed/fixture-tested.
- MANUAL: live GPU/Modal rerun or upstream maintainer messaging.

## Evidence standard
- Source-backed claims require GitHub PR/issue/doc/source URL or local source path.
- Synthetic fixtures prove parser/classifier behavior only.
- Live validation requires accepted runtime artifacts.

## Recon targets
- `sgl-project/sglang` issues/PRs mentioning LMCache.
- `LMCache/LMCache` issues/PRs mentioning SGLang.
- Existing local LMCache docs/source for embedded SGLang support.
- Existing InferGuard wording/status around embedded vs MP support.

## Expected correction
- SGLang + LMCache embedded/in-process support is existing/source-backed when SGLang is launched with `--enable-lmcache` and LMCache config is provided via `LMCACHE_CONFIG_FILE`.
- SGLang + LMCache MP remains PR-backed/experimental/not cleanly live-accepted unless current upstream merge state and live InferGuard artifacts prove otherwise.
- InferGuard is the collector/classifier. It does not enable SGLang runtime cache behavior.

## Deliverables
1. Recon ledger with GitHub issue/PR evidence.
2. InferGuard code/docs/test correction, if required.
3. Focused verification output.
4. Conservative final status and non-claims.
