# InferGuard SGLang LMCache MP Observability Support Spec v0.1

Generated: 2026-05-12
Repo: `/Users/chen/Projects/inferguard`
Branch: `ocwc/packet-b-l0-lifecycle-overlay`

## Purpose

Add InferGuard support for **SGLang + LMCache MP observability** without falsely claiming SGLang MP is stable or live-validated.

The user asked to make InferGuard support SGLang LMCache MP observability after challenging the prior fixture-only SGLang work.

This spec is a runnable implementation prompt for a coding agent.

## Evidence Standard

Claim statuses:

- `source_backed`: upstream docs/source/PR metadata show the intended interface.
- `fixture_tested`: synthetic/compact fixtures prove InferGuard parser/report behavior only.
- `live_validated`: real SGLang + LMCache MP run produced artifacts and InferGuard report accepted them.
- `blocked`: upstream state or local artifacts are insufficient.
- `not_proven`: design target only.

Rules:

1. Do not claim live SGLang + LMCache MP support from fixture tests.
2. Do not claim SGLang MP support is merged. The current key upstream PRs are open.
3. Do not invent flags or metric families. Use upstream PR/source-backed names and conservative detection.
4. Keep unrelated dirty files untouched.
5. Follow TDD: RED test first, GREEN implementation, focused regression, docs update.

## Upstream Source Ledger

### S1 — SGLang PR #24089

URL: `https://github.com/sgl-project/sglang/pull/24089`
Title: `[Feat][LMCache] Support LMCache mp mode`
State: open, non-draft, not merged as of 2026-05-12 recon.
Head: `Shaoting-Feng:shaoting/sglang-lmcache-mp-nonlayerwise` at `bcaa2854288b1332a5645450af61f73cbf805472`.

PR body facts:

- Adds SGLang-side wiring for LMCache MP mode.
- Companion dependency: `LMCache/LMCache#3166`.
- Adds `--lmcache-mp-host` and `--lmcache-mp-port` in `server_args.py`.
- `lmc_radix_cache.py` selects connector at construction:
  - existing in-process `LMCacheLayerwiseConnector` when `lmcache_mp_host` unset;
  - `LMCacheMPLayerwiseConnector` when `lmcache_mp_host` set.
- Test launch shape in PR body:

```bash
lmcache server \
  --host 127.0.0.1 --port 5556 \
  --chunk-size 256 --l1-size-gb 4 \
  --eviction-policy LRU --disable-observability

python -m sglang.launch_server \
  --model-path Qwen/Qwen2.5-1.5B-Instruct \
  --host 127.0.0.1 --port 30000 \
  --enable-lmcache \
  --lmcache-mp-host 127.0.0.1 \
  --lmcache-mp-port 5556
```

Changed files include:

- `python/sglang/srt/server_args.py`
- `python/sglang/srt/mem_cache/storage/lmcache/lmc_radix_cache.py`
- `python/sglang/srt/mem_cache/storage/lmcache/README.md`
- docs for server arguments / HiCache design.

### S2 — LMCache PR #3166

URL: `https://github.com/LMCache/LMCache/pull/3166`
Title: `[Feat] Add mp support for sglang`
State: open, non-draft, not merged as of 2026-05-12 recon.
Head: `LMCache:shaoting/sglang-lmcache-mp-nonlayerwise` at `d298d5807fc16aaf896347c1d927383e24c0195f`.

PR body facts:

- Adds LMCache MP support for SGLang.
- Companion SGLang PR: `sgl-project/sglang#24089`.
- Notes remaining next steps around abort paths / liveness recovery:
  - SGLang abort hooks can leave LMCache read locks/sessions hanging if `LOOKUP` already triggered.
  - Proposed `release_aborted_request(rid)` to call `release_pending` + `end_session`.
  - Daemon-side liveness recovery is also called out.

Changed files include:

- `lmcache/integration/sglang/multi_process_adapter.py` added.
- `lmcache/integration/sglang/sglang_adapter.py` modified.
- `lmcache/v1/gpu_connector/utils.py` modified.
- `csrc/mp_mem_kernels.cu` modified.
- layout invariant docs updated.

### S3 — Previous closed attempts

SGLang PR #16185 and LMCache PR #2857 were earlier SGLang MP attempts and are closed/unmerged. Treat as history and warning, not current support.

### S4 — Existing InferGuard facts

Current branch already includes fixture/parser SGLang work:

- Implementation commit `9123143974ef1915aaa36e718e2985cfacd6c1fc`.
- Spec commit `626c671b6a93704ca5501571e017d286845eaf63`.
- Current docs plan: `docs/plans/2026-05-12-sglang-lmcache-recon-and-live-validation-v0.1.md`.
- Prior spec: `docs/prompts/2026-05-12-inferguard-sglang-lmcache-support-v0.1.md`.

Existing dirty/untracked files to preserve:

- `docs/getting-started/quick-start.md`
- `uv.lock`
- `docs/prompts/inferguard-rebase-smoke-verification-v0.1.md`
- `docs/plans/` currently contains a new recon plan from this session.
- `prompt-exports/` may contain Oracle export from RepoPrompt planning.

## Work Classification

AUTO:

- Add parser/report support for SGLang + LMCache MP observability as source-backed/fixture-tested.
- Add launch command support for PR-backed SGLang MP flags:
  - `--lmcache-mp-host`
  - `--lmcache-mp-port`
- Add compatibility/coverage detection for SGLang LMCache MP observability evidence.
- Add fixtures and tests.
- Update docs matrix and changelog with blocked/pending live-validation status.

REVIEW:

- Any wording that says “supported” without `fixture_tested` or `pending_live_validation` qualifier.
- Any upgrade to `live_validated`.

MANUAL/EXPENSIVE:

- Actual SGLang + LMCache MP GPU run.
- Fork/remote upstream PR creation. Local runtime currently lacks GitHub auth/gh.

## Target Behavior

### 1. Launch support

Add explicit launch plumbing for SGLang MP observability flags.

Expected command when user supplies MP host/port:

```bash
python -m sglang.launch_server \
  --model-path Qwen/Qwen2.5-1.5B-Instruct \
  --host 127.0.0.1 \
  --port 30000 \
  --enable-lmcache \
  --lmcache-mp-host 127.0.0.1 \
  --lmcache-mp-port 5556
```

If `kv_events_config` is also provided, include existing `--kv-events-config` support.

Do not invent `--lmcache-mp-enable`: current PR #24089 uses host/port to select MP connector.

### 2. Metrics / compatibility support

InferGuard should classify SGLang + LMCache MP observability evidence when all are present:

- SGLang engine metrics or SGLang launch/manifest evidence.
- LMCache MP metrics or MP evidence from LMCache server.
- SGLang MP launch flags / live manifest fields, or source fixture showing `lmcache_mp_host` / `lmcache_mp_port`.

Output should distinguish:

- `sglang_embedded_lmcache`: `--enable-lmcache` only, no MP host/port.
- `sglang_mp_lmcache_candidate`: partial evidence only.
- `sglang_mp_lmcache_observability`: source-backed/fixture-tested SGLang + LMCache MP observability path.
- `sglang_mp_lmcache_live_validated`: only when a live manifest and real artifacts prove it. Do not produce this status in fixture-only tests.

### 3. Coverage report

Add or strengthen a top-level support/status block, for example:

```json
"sglang_lmcache_mp_observability": {
  "support_status": "source_backed_fixture_tested",
  "claim_status": "fixture_tested",
  "upstream_state": "open_prs_not_merged",
  "sglang_pr": "https://github.com/sgl-project/sglang/pull/24089",
  "lmcache_pr": "https://github.com/LMCache/LMCache/pull/3166",
  "live_validation": "pending",
  "required_launch_flags": ["--enable-lmcache", "--lmcache-mp-host", "--lmcache-mp-port"],
  "non_claims": [
    "not live validated",
    "not merged upstream",
    "not performance validated",
    "not production support"
  ]
}
```

Field names can match existing style; preserve backwards compatibility.

### 4. Fixtures

Add compact fixtures representing SGLang + LMCache MP observability.

Possible fixtures:

- `tests/fixtures/lmcache_metrics/sglang_lmcache_mp.prom`
- `tests/fixtures/sglang_lmcache_mp_launch_manifest.json`
- If needed, `tests/fixtures/sglang_lmcache_mp_command.json`

Fixture contents should be synthetic but reflect PR-backed launch flags and existing LMCache MP metric families already supported by InferGuard.

Include enough evidence for parser classification:

- SGLang metric family present.
- LMCache MP metric family present.
- MP host/port launch flag evidence present.
- Upstream PR references present in manifest.

### 5. Docs

Update docs with conservative language:

- SGLang + LMCache MP observability: source-backed from open upstream PRs #24089/#3166, fixture-tested in InferGuard, live validation pending.
- No claim that SGLang MP is merged/upstream supported yet.
- No claim of performance benefit.
- No claim of production readiness.

## Suggested File Targets

Inspect before editing:

- `src/inferguard/launch_engine/sglang.py`
- `src/inferguard/launch_engine/__init__.py`
- `src/inferguard/cli.py`
- `src/inferguard/compat.py`
- `src/inferguard/observability_coverage.py`
- `src/inferguard/collect_metrics/normalize.py`
- `tests/test_launch_engine_sglang.py`
- `tests/test_observability_coverage.py`
- `tests/test_collect_metrics.py`
- `docs/guides/observability-coverage-matrix.md`
- `CHANGELOG.md`

## TDD Requirements

1. RED:
   - Add failing test for SGLang launch including `--lmcache-mp-host` and `--lmcache-mp-port`.
   - Add failing test for observability coverage report classifying SGLang + LMCache MP observability as source-backed/fixture-tested but pending live validation.
   - Add failing test that MP candidate without launch/source evidence stays blocked/candidate.

2. GREEN:
   - Implement minimal launch plumbing and report support.

3. REFACTOR:
   - Keep new logic additive and small.
   - Avoid broad schema breakage.

4. DOCS:
   - Update matrix/changelog.

5. VERIFY:

```bash
uv run --with pytest --with pytest-asyncio --with aiohttp --with msgpack pytest -q \
  tests/test_collect_metrics.py \
  tests/test_observability_coverage.py \
  tests/test_launch_engine_sglang.py

uv run mkdocs build
```

If CLI touched substantially, run any relevant CLI tests found in the repo.

## Commit Scope

Commit only intended files. Preserve unrelated dirty files.

Commit message suggestion:

```text
feat(inferguard): add SGLang LMCache MP observability support
```

Return:

- commit SHA
- tests run and results
- files changed
- status summary
- exact claim status after implementation
