# InferGuard Open Source Commit Hygiene Spec v0.1

Date: 2026-05-10
Repo: `/Users/chen/Projects/inferguard`
Branch: `ocwc/packet-b-l0-lifecycle-overlay`
Classification: AUTO for ignore/doc commits; REVIEW only for pushing/PR if credentials or branch policy blocks.

## Problem

The working tree contains more than 1,800 uncommitted paths because local Modal/H100 runtime artifacts under `modal-out/` are untracked. This is unsafe for an open-source repo because it can leak bulky/generated runtime evidence, environment snapshots, logs, and local machine context. A local agent-memory `AGENTS.md` is also untracked and should not be committed as public OSS project docs.

## Commit plan

1. Commit 1: ignore local/generated artifacts.
   - File: `.gitignore`
   - Add `modal-out/` under local benchmark/runtime artifacts.
   - Add `AGENTS.md` under local agent memory/context.
   - Do not delete local artifacts; only stop them from entering source control.

2. Commit 2: docs-only H100 release-smoke audit update.
   - Files:
     - `docs/CLI_REFERENCE.md`
     - `docs/reference/cli.md`
     - `docs/guides/observability-coverage-matrix.md`
     - `docs/sdlc/final-real-h100-release-smoke-report-v0.1.md`
     - `docs/sdlc/inferguard-cli-h100-doc-update-spec-v0.1.md`
   - Do not stage unrelated existing changes:
     - `docs/getting-started/quick-start.md`
     - `uv.lock`

## Verification gates

- `uv run mkdocs build` must pass before commit.
- `git status --short` after `.gitignore` must no longer show `modal-out/` or `AGENTS.md` as untracked.
- `git diff --cached --name-only` must match the intended commit scope before each commit.

## Commit messages

Commit 1:

```text
chore: ignore local runtime artifacts

- Ignore Modal/H100 runtime pulls under modal-out
- Ignore local agent memory context file
- Keep generated evidence out of the OSS source tree
```

Commit 2:

```text
docs: document final H100 LMCache smoke evidence

- Add auditable Packet B and H3 H100 smoke receipts
- Separate LMCache MP acceptance coverage from hardware telemetry
- Record DCGM/NVML telemetry as not proven until sampled
```
