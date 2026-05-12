# Contributing to InferGuard

Thanks for contributing to InferGuard.

InferGuard is a source-available diagnostics package for inference operators. The current release line is distributed under BUSL-1.1, with the Additional Use Grant and Change License described in `LICENSE`. The best contributions preserve the project's core contract: read-only by default, evidence before recommendation, and no private/pro-tier imports in the source-available tree.

## Development setup

```bash
git clone git@github.com:Touchdown-Labs/inferguard.git
cd inferguard
python3 -m venv venv
source venv/bin/activate
pip install -e '.[dev,mcp]'
```

If you only need the CLI and test suite, `pip install -e '.[dev]'` is enough.

## Running tests

```bash
pytest --strict-markers
```

Useful narrower loops:

```bash
pytest tests/test_validate_completed.py --strict-markers
pytest tests/test_request_profile.py --strict-markers
pytest tests/test_collect_metrics.py --strict-markers
pytest tests/test_launch_engine.py --strict-markers
```

## Code style

- Ruff is used for linting and formatting.
- The project line limit is 100 characters.
- Keep generated artifacts out of commits unless they are small, intentional fixtures.

```bash
ruff check .
ruff format .
```

If pre-commit hooks are available in your environment:

```bash
pre-commit install
pre-commit run --all-files
```

## Architecture boundaries (layer-lint)

Changes in source-available package files must not import from private/pro-tier modules. In this public tree, do not introduce imports from outside the layer-lint allowlist, including forbidden modules such as:

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

## SDLC and evidence-gated claims

Every technical claim in code, docs, release notes, or PR text must be backed by
one of:

- a source path, commit, release, or public project URL;
- a fixture-backed test result;
- a live artifact path and command provenance;
- an explicit status such as `not_proven`, `not_applicable`, or `blocked`.

Use conservative language. Synthetic fixtures prove parser behavior only. A
claim is `measured` only when live artifacts exist and the relevant InferGuard
parser/report path accepts them. Performance, hardware telemetry, and cross-repo
runtime behavior must never be implied from parser-only changes.

For release PRs, include or update:

- `CHANGELOG.md`;
- user-facing README/docs pages affected by the behavior change;
- any SDLC report under `docs/sdlc/` that records live evidence;
- a `release_proofs/<version>/` bundle when release gates require it.

## Documentation expectations

Update documentation whenever behavior visible to operators changes:

- command flags or output files: update `docs/CLI_REFERENCE.md` and examples as needed;
- artifact schemas or evidence gates: update `docs/ARCHITECTURE.md`, `docs/SCHEMAS.md`, or `docs/SPEC.md` as appropriate;
- hardware support or template status: update `docs/HARDWARE_COVERAGE.md`;
- user-facing behavior: update `CHANGELOG.md`.

Do not claim a configuration is `measured` unless the artifact set can pass `inferguard validate-completed --strict` as `live_complete`.

## Submitting changes

1. Fork the repo.
2. Create a feature branch: `git checkout -b feat/your-change`.
3. Make changes and add or update tests.
4. Sign your commits: `git commit -s -m "type(scope): specific outcome"`.
5. Push to your fork and open a PR against `main`.
6. Wait for CI to pass and maintainer review.

## PR checklist

- [ ] DCO sign-off present on all commits.
- [ ] `ruff check .` passes.
- [ ] `ruff format .` has been run or intentionally skipped with explanation.
- [ ] `pytest --strict-markers` passes, or the PR explains the skipped environment requirement.
- [ ] `CHANGELOG.md` updated when user-facing behavior changes.
- [ ] Documentation updated for command, artifact, or schema changes.

## Reporting bugs

Use the GitHub issue templates and include:

- InferGuard version (`inferguard --version`);
- Python version and OS;
- serving engine and version when relevant;
- the exact command run;
- redacted `validation_report.json`, `requests_summary.json`, or log snippets when available.

For security issues, do not open a public issue. See [SECURITY.md](SECURITY.md).

## Discussion

Use GitHub Issues for bugs and concrete feature requests. If GitHub Discussions are enabled later, maintainers may redirect design discussions there.

## DCO sign-off

Every commit MUST be signed off with `git commit -s`. This adds a line like:

```text
Signed-off-by: Your Name <your.email@example.com>
```

The sign-off certifies the [Developer Certificate of Origin](https://developercertificate.org/).
