# InferGuard SGLang + LMCache version provenance correction v0.1

## User request
Identify the exact LMCache/SGLang PRs and code versions that support SGLang + LMCache, show opened/edited dates and authors, determine what InferGuard must update, make the changes, and fully test the InferGuard support path.

## Evidence standard
- `source_backed`: official GitHub PR/issue/source/docs confirm the statement.
- `git_history_backed`: local git history/blame or GitHub commit metadata identifies code author/date/version.
- `fixture_tested`: InferGuard tests validate report behavior only.
- `not_proven`: no merged upstream or live accepted artifact proves the stronger claim.

## Required changes
1. Preserve embedded vs MP distinction.
2. Add SGLang + LMCache version/provenance metadata to InferGuard reports, not just prose docs.
3. Cite the source docs/code paths that prove embedded support:
   - LMCache SGLang adapter/config.
   - SGLang `--enable-lmcache` launch surface.
   - Runtime lookup/retrieve/store code paths.
4. Cite MP PRs separately as open/unmerged:
   - SGLang PR #24089.
   - LMCache PR #3166.
5. Update tests so the report must include provenance and non-claims.
6. Run focused Ruff and pytest gates.
