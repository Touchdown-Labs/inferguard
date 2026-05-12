## Summary

## SDLC / evidence
- [ ] User-visible claims are tied to source paths, test output, live artifacts, or public release URLs
- [ ] Claims without live evidence are labeled `not_proven`, `not_applicable`, `blocked`, or equivalent
- [ ] No synthetic fixture is used to claim live performance or hardware telemetry
- [ ] Release PRs include/update `CHANGELOG.md`, affected docs, SDLC reports, and `release_proofs/<version>/` when required

## Test plan
- [ ] `ruff check .`
- [ ] `pytest --strict-markers`
- [ ] `uv run mkdocs build` or docs build intentionally skipped with reason
- [ ] `CHANGELOG.md` updated for user-facing changes
- [ ] Layer-lint boundary respected (no imports from forbidden private modules — see CONTRIBUTING.md)
- [ ] DCO sign-off on every commit (`git commit -s`)
