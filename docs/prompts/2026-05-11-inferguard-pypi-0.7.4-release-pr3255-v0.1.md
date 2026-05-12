# InferGuard PyPI Release Spec — PR3255 Downstream Consumer

Date: 2026-05-11
Status: executable release spec
Target package version: `0.7.4`
Repository: `/Users/chen/Projects/inferguard`
Starting branch: `ocwc/packet-b-l0-lifecycle-overlay`

## Objective

Ship the InferGuard update that consumes LMCache PR #3255 L0 allocation counters and redacted boundary evidence to PyPI as `inferguard==0.7.4`.

This release should make the downstream CLI/reporting support installable by users instead of living only on the feature branch.

## Evidence already available

- InferGuard feature branch: `ocwc/packet-b-l0-lifecycle-overlay`
- PR3255 consumer commit: `02c79b2f7b7ac873478975ee9c39f16516219e89`
- Commit message: `feat(inferguard): consume LMCache PR3255 L0 allocation evidence`
- Modal H100 app/run: `https://modal.com/apps/ocwc22/main/ap-Vz0QD1FjLH33nKUYSOcEBR`
- Modal artifact path: `/Users/chen/Projects/inferguard/modal-out/pulls/20260511T224306Z/20260511T224306Z`
- Measured counters:
  - `lmcache_mp_l0_block_allocation_records_total=336.0`
  - `lmcache_mp_l0_block_allocated_blocks_total=11692.0`
- Boundary evidence:
  - schema `inferguard-l0-block-boundary-event/v1`
  - accepted rows `1008`
  - rejected rows `0`
  - raw tokens recorded `false`
  - raw block IDs recorded `false`
- No vLLM code changes are part of this release.

## Release claim boundaries

Allowed claims:

- InferGuard can parse/report LMCache PR #3255 L0 allocation counters.
- InferGuard can ingest/report redacted PR3255 boundary JSONL evidence.
- The PR3255 downstream path was measured on Modal H100 with vLLM + LMCache local source containing PR #3255 + updated InferGuard CLI.
- vLLM source was unchanged for this proof.

Disallowed claims:

- Do not claim full LMCache 100/100 coverage.
- Do not claim vLLM-native PR3255 support.
- Do not claim DCGM/NVML hardware telemetry was measured for this release.
- Do not claim PR3255 improves performance.
- Do not claim CacheBlend/non-prefix lifecycle boundary is final until Kuntai answers.

## Dirty tree hygiene

Current known dirty/untracked files before release work may include:

- `docs/getting-started/quick-start.md`
- `uv.lock`
- `docs/prompts/inferguard-rebase-smoke-verification-v0.1.md`

Do not stage these unless they are deliberately part of the release and verified. Prefer leaving them untouched.

If local runtime artifacts appear under `modal-out/`, do not commit them. Use `.gitignore` only if needed and scoped.

## Required release edits

1. Update package version:
   - `pyproject.toml`: `version = "0.7.4"`
   - `src/inferguard/__init__.py`: `__version__ = "0.7.4"`

2. Update `CHANGELOG.md`:
   - Convert the current Unreleased PR3255/release-readiness content into `## [0.7.4] - 2026-05-11`.
   - Mention:
     - LMCache PR #3255 L0 allocation counter consumption.
     - Redacted L0 boundary JSONL ingestion/reporting.
     - Modal H100 measured downstream proof.
     - No vLLM source changes.
     - Full coverage remains evidence-gated, not claimed complete.
   - Keep a fresh empty `## [Unreleased]` section above it.

3. If release docs need a short note, update only docs that are already release-facing and necessary. Do not broaden scope.

## Local verification gates

Run the smallest sufficient gates first:

```bash
python - <<'PY'
import tomllib
from pathlib import Path
pyproject = tomllib.loads(Path('pyproject.toml').read_text())
ns = {}
exec(Path('src/inferguard/__init__.py').read_text(), ns)
assert pyproject['project']['version'] == ns['__version__'] == '0.7.4'
print('version gate OK', ns['__version__'])
PY
```

Run focused PR3255 gates:

```bash
uv run pytest -q tests/test_lmcache_metrics_adapter.py tests/test_observability_coverage.py tests/test_lmcache_mp_modal_packet_lab.py
```

Run package build gates:

```bash
rm -rf dist build *.egg-info
python -m pip install build twine
python -m build
python -m twine check dist/*
```

If feasible, run release gate subset:

```bash
uv run pytest -q tests/test_lmcache_metrics_adapter.py tests/test_observability_coverage.py tests/test_lmcache_packet.py tests/test_lmcache_otel.py tests/test_lmcache_trace.py tests/test_lmcache_lookup_hash.py tests/test_cli_analyze.py tests/test_cli_bench.py
```

Do not block forever on expensive full-suite or H100 reruns. This release is packaging the already-measured downstream consumer.

## Git / GitHub sequence

Preferred path:

1. Commit version/changelog/release docs on `ocwc/packet-b-l0-lifecycle-overlay`.
2. Push the branch.
3. If a PR to `main` already exists, update it. If none exists, open one with title:
   - `feat: consume LMCache PR3255 L0 allocation evidence`
4. Merge to `main` only if CI/status checks and repo permissions allow.
5. Create and push tag `v0.7.4` from the release commit on `main`.
6. Monitor `.github/workflows/release.yml`.
7. Verify PyPI shows `inferguard==0.7.4`.

Fallback path if merge is blocked but user wants release immediately:

- Tag the verified release commit on `ocwc/packet-b-l0-lifecycle-overlay` only if the repository release workflow permits tag releases from non-main commits.
- Record that the PyPI release came from the feature branch and create a follow-up PR/merge task.

## Release workflow facts

- PyPI currently shows latest `inferguard==0.7.3`.
- `.github/workflows/release.yml` triggers on `v*.*.*` tags.
- The workflow verifies tag version equals `src/inferguard/__init__.py`.
- The workflow verifies `pyproject.toml` version equals runtime version.
- The workflow builds, runs `twine check`, publishes to TestPyPI, smoke-installs, then publishes to PyPI.
- Secrets required in GitHub Actions environment `pypi`:
  - `TEST_PYPI_API_TOKEN`
  - `PYPI_API_TOKEN`

## PR / release body skeleton

```markdown
## Summary
- Adds InferGuard downstream support for LMCache PR #3255 L0 allocation counters.
- Adds/ships redacted L0 boundary evidence ingestion/reporting.
- Records Modal H100 downstream proof for vLLM + LMCache PR3255 source + updated InferGuard CLI.

## Evidence
- InferGuard commit: 02c79b2f7b7ac873478975ee9c39f16516219e89
- Modal H100 run: https://modal.com/apps/ocwc22/main/ap-Vz0QD1FjLH33nKUYSOcEBR
- Allocation records: 336
- Allocated blocks: 11692
- Boundary rows: 1008 accepted, 0 rejected
- Raw tokens/block IDs: not recorded

## Scope boundaries
- No vLLM source changes.
- No performance improvement claim.
- Full LMCache coverage remains evidence-gated and is not claimed complete.

## Test plan
- [ ] Version gate passes for pyproject and runtime version.
- [ ] Focused LMCache/PR3255 tests pass.
- [ ] Package builds and `twine check` passes.
- [ ] Release workflow publishes `inferguard==0.7.4`.
```

## Final report required

Return:

- Commit SHA for version/changelog release commit.
- PR URL if opened/updated.
- Tag SHA for `v0.7.4` if pushed.
- GitHub Actions release workflow URL/status.
- PyPI version verification result.
- Any blockers, especially missing PyPI/TestPyPI secrets or CI failures.
