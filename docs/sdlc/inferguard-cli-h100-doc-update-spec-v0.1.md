# InferGuard CLI H100 Documentation Update Spec v0.1

Date: 2026-05-10
Repo: `/Users/chen/Projects/inferguard`
Branch: `ocwc/packet-b-l0-lifecycle-overlay`
Scope: docs-only update for the already-run real Modal H100 LMCache/vLLM + InferGuard smoke.

## Goal

Make the CLI and SDLC docs auditable by separating three claim states:

1. `release_ready`: original vLLM + LMCache + InferGuard CLI acceptance scope.
2. `measured`: application/runtime telemetry from real H100 Packet B and Packet H3 smoke artifacts.
3. `not_proven`: continuous DCGM/NVML hardware telemetry, including GPU util, HBM bandwidth, NVLink, PCIe, and sustained power telemetry.

## Source Ledger

| ID | Source | Path / URL | Verifies |
| --- | --- | --- | --- |
| H100-B | Packet B Modal smoke | `/Users/chen/Projects/inferguard/modal-out/pulls/20260510T230559Z` and `https://modal.com/apps/ocwc22/main/ap-i3clSmO9WG4fwZQJlF5FLx` | vLLM + standalone LMCache MP runtime telemetry on H100. |
| H100-H3 | Packet H3 Modal smoke | `/Users/chen/Projects/inferguard/modal-out/pulls/20260510T232009Z` and `https://modal.com/apps/ocwc22/main/ap-3OmReCOzyoAFB4qD88me8g` | embedded CacheBlend/vLLM runtime telemetry on H100. |
| RPT | Final smoke report | `docs/sdlc/final-real-h100-release-smoke-report-v0.1.md` | Human-readable release smoke receipt. |
| CLI | CLI reference | `docs/CLI_REFERENCE.md` and `docs/reference/cli.md` | Operator-facing command and evidence guidance. |
| MATRIX | Observability matrix | `docs/guides/observability-coverage-matrix.md` | Audit matrix for coverage state and next work. |

## Required doc updates

- Update `docs/sdlc/final-real-h100-release-smoke-report-v0.1.md` with raw H100 environment, runtime config, measured telemetry, coverage interpretation, and next work.
- Update both CLI reference copies with a concise final H100 receipt and the yes/no answer for LMCache MP observability coverage.
- Update `docs/guides/observability-coverage-matrix.md` so the matrix says Packet B MP and Packet H3 CacheBlend are real-H100 validated for the original CLI scope, while hardware telemetry remains not proven.

## Claim rules

- Do not claim DCGM-level hardware telemetry as measured unless `dcgm_sample_count > 0` or an accepted NVML/DCGM sampler artifact exists.
- Treat native vLLM CPU offload metrics as useful pressure evidence, not LMCache proof.
- Treat P2P, PD, SGLang/H2, Mooncake, and DLM/llm-d as backend-expansion lanes, not blockers for original vLLM + LMCache CLI release readiness.

## Verification

Docs-only verification target:

```bash
uv run mkdocs build
```

If command execution is unavailable in this session, verify by RepoPrompt diff and leave build status as `not_run_in_session`.
