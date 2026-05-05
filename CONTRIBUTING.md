# Contributing

Thanks for contributing to InferGuard OSS.

## Required before opening a PR

1. Sign commits with DCO (`git commit -s ...`).
2. Run quality checks locally:
   - `ruff check .`
   - `pytest --strict-markers`
3. Ensure CI is green before requesting review.
4. Do not merge or request merge with failing CI.

## Layering rule (OSS boundary)

Changes in OSS files must not import from private/pro-tier modules. In this OSS tree, do not introduce imports from outside the OSS layer-lint allowlist, including forbidden modules such as:

- `agent`
- `brain_client`
- `diagnosis`
- `memory`
- `executor`
- `replay_validation`
- `safe_actions`
- `remediation`
- `blaxel_agent`

CI enforces this boundary via `.github/workflows/layer-lint.yml`.

## PR checklist

- [ ] DCO sign-off present on all commits.
- [ ] `ruff check .` passes.
- [ ] `pytest --strict-markers` passes.
- [ ] `CHANGELOG.md` updated when user-facing behavior changes.
