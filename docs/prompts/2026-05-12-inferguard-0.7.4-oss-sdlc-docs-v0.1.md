# InferGuard 0.7.4 OSS / SDLC documentation closeout v0.1

Date: 2026-05-12
Status: executable documentation spec
Repository: `/Users/chen/Projects/inferguard`
Branch: `ocwc/packet-b-l0-lifecycle-overlay`

## Objective

Close out the GitHub-facing documentation for the published `inferguard==0.7.4` release so a reader can tell:

1. what changed in 0.7.4;
2. which claims are measured vs not claimed;
3. how the release followed the repo's SDLC / evidence-gated contract;
4. how OSS/source-available contributors should document future changes without broadening claims.

## Evidence standard

Claim status vocabulary:

- `published`: package or release exists on public registry/release page.
- `measured`: live artifacts and parser/report path exist.
- `fixture_tested`: tests prove parser/report behavior only.
- `source_backed`: source or docs prove the statement.
- `not_applicable`: the claim does not apply to this release.
- `not_proven`: not measured or not claimed.

Statements without evidence must be phrased as scope, policy, or non-claim, not product proof.

## Source ledger

- S1: PyPI `https://pypi.org/pypi/inferguard/json` reports version `0.7.4` and distribution files.
- S2: GitHub release `https://github.com/Touchdown-Labs/inferguard/releases/tag/v0.7.4`.
- S3: Successful GitHub Actions release workflow `https://github.com/Touchdown-Labs/inferguard/actions/runs/25703933137`.
- S4: `docs/sdlc/pr3255-packet-b-downstream-h100-measured-report-v0.1.md` records Modal H100 PR3255 downstream evidence.
- S5: `release_proofs/v0.7.4/README.md` records release proof bundle provenance.
- S6: `CHANGELOG.md` records 0.7.4 user-visible changes.

## Required updates

1. README:
   - Add a concise "Current release: 0.7.4" section.
   - State the PR3255 L0 allocation counter support, redacted boundary JSONL support, and Modal H100 downstream proof.
   - Preserve non-claims: no vLLM source changes, no performance improvement claim, DCGM/NVML hardware telemetry not claimed by this release.
   - Update citation version/license/repo URL drift if visible.

2. Docs index:
   - Use source-available/BUSL wording instead of generic "open-source" wording for current release line.
   - Add release 0.7.4 section linking PyPI, GitHub release, changelog, SDLC report, and release proof bundle.

3. LMCache compatibility / coverage docs:
   - Add PR3255-specific operator-facing text for `lmcache_mp_l0_block_allocation_records_total`, `lmcache_mp_l0_block_allocated_blocks_total`, and optional redacted L0 boundary evidence.
   - Keep evidence-gated scope.

4. CONTRIBUTING / PR template:
   - Add SDLC/evidence-gated documentation expectations and release proof checklist items.
   - Keep layer-lint and DCO requirements.

5. CITATION:
   - Update version/date/repo/license to match current release metadata.

## Verification gates

- Read back changed docs and check for forbidden overclaims:
  - no "made LMCache faster" claim;
  - no "vLLM changed" claim;
  - no `measured` DCGM/NVML hardware telemetry claim;
  - no current-release Apache-2.0 license claim.
- Run docs build if available via agent.
- Commit only intended documentation files and this prompt spec.

## Intended commit

`docs: close out InferGuard 0.7.4 OSS SDLC docs`
