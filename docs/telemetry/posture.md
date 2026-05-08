---
title: "InferGuard Telemetry v0 Posture"
status: "production-v0.5-zero-telemetry-commitment"
date: "2026-04-30"
purpose: "Publish the zero-telemetry commitment for InferGuard CLI v0.4.x and v0.5.x, including operator verification steps."
supersedes-policy: "New posture document; does not supersede oss/inferguard/docs/SPEC.md."
---

# InferGuard Telemetry v0 Posture

## 1. Scope

This document states the current InferGuard zero-telemetry commitment.
It applies to CLI v0.4.x.
It applies to the current `0.7.1` CLI. References to v0.5.x below name the
feature tranche where the local-only telemetry posture was introduced.
It applies to a fresh install.
It applies before a user runs any explicit telemetry enable command.
It applies when `DO_NOT_TRACK=1` is present.
It applies when `INFERGUARD_TELEMETRY=disabled` is present.
It is grounded in `docs/designs/2026-04-30-inferguard-harness-architecture.md`.
It is paired with the opt-in v1 spec at `oss/inferguard/docs/telemetry/v1/SPEC.md`.

## 2. Plain-language commitment

InferGuard does not phone home by default.
InferGuard does not send analytics by default.
InferGuard does not check a license server by default.
InferGuard does not check for updates by default.
InferGuard does not upload benchmark artifacts by default.
InferGuard does not upload agent traces by default.
InferGuard does not upload machine fingerprints by default.
InferGuard does not require a Touchdown account for CLI use.
InferGuard network calls are limited to endpoints the operator passes by flag.
Examples include an inference endpoint, a metrics endpoint, or a localhost daemon endpoint.

## 3. Version-specific posture

v0.4.x shipped the then-current CLI surface.
v0.4.x has no hosted telemetry path.
v0.4.x should make no outbound calls except to user-supplied endpoints.
v0.5.x adds harness commands.
v0.5.x keeps telemetry disabled by default.
v0.5.x adds `inferguard telemetry status` for proof.
v0.5.x adds `inferguard telemetry verify-payload` for audit.
v0.5.x may write local pending payloads only after explicit enablement.
v0.5.x does not ship real network upload to Touchdown hosted ingest.
v0.5.x real upload is deferred to a later hosted release.

## 4. Hard overrides

`DO_NOT_TRACK=1` is a hard telemetry disable.
`INFERGUARD_TELEMETRY=disabled` is a hard telemetry disable.
When either override is present, `telemetry status` must report disabled.
When either override is present, `telemetry enable` must refuse or no-op safely.
When either override is present, `verify-payload` may render a local dry-run payload but must say it cannot be sent.
No user config file may override these environment variables.
No consent token may override these environment variables.
No command-line telemetry flag may override these environment variables.

## 5. Secure local storage

v0.5 separates secrets from payloads.
The consent token is stored at:

```text
~/.config/inferguard/secrets/consent.token
```

The consent token file must be mode `0o600`.
The `secrets/` directory should be mode `0o700`.
When the consent token is world-readable or otherwise broader than owner-only, InferGuard refuses to load it and logs a warning.
Candidate telemetry payloads are written separately under:

```text
~/.config/inferguard/uploads-pending/
```

Pending payload files are local audit artifacts only in v0.5.
They are not uploaded by the CLI package.
They should be treated as sensitive operational records even after redaction.

## 6. Runtime privacy fixture coverage

The v0.5 privacy test fixture now guards the major Python and shell outbound paths used by harness code.
It blocks unmocked non-loopback calls through:

- `httpx.AsyncClient.send` and `httpx.Client.send`;
- `requests.Session.request` when `requests` is installed;
- `aiohttp.ClientSession._request` when `aiohttp` is installed;
- `urllib.request.urlopen`;
- `urllib3.PoolManager.request` when `urllib3` is installed;
- `socket.create_connection`;
- `socket.socket.connect`;
- `subprocess.run` and `subprocess.Popen` when the first executable is `curl`, `wget`, `http`, or `grpc-cli`.

Loopback targets are allowed so tests can exercise local daemon and metrics endpoints.
Tests that intentionally contact an external endpoint must carry an explicit network opt-in marker.
This fixture is still a regression guard, not a formal security proof.
Release review should pair it with source review and payload inspection.

## 7. Verification recipe

Run this from `oss/inferguard/` in the worktree or source checkout.
The command searches for common Python HTTP client call sites.
It excludes expected localhost, explicit endpoint, and explicit metrics URL patterns.
It should return empty output for the zero-telemetry posture.

```bash
grep -rE 'requests\.(get|post)|httpx\.(get|post|AsyncClient)|aiohttp' src/inferguard/ --include='*.py' | grep -v 'localhost\|127\.0\.0\.1\|--endpoint\|--metrics-url'
```

Empty output means this grep did not find unexpected direct HTTP clients.
Non-empty output requires manual review.
This grep is not a complete security proof.
It is a fast operator-verifiable regression check.
CI and release review should pair it with the broader outbound fixture coverage in §6.

## 8. Runtime proof command

v0.5 introduces:

```bash
inferguard telemetry status
```

On a fresh install, it should report:

```text
No telemetry. No network calls outside endpoints you pass via flags. Verified: see oss/inferguard/docs/telemetry/v0/POSTURE.md.
```

The status command should print the effective state.
The status command should print whether `DO_NOT_TRACK` is active.
The status command should print whether `INFERGUARD_TELEMETRY=disabled` is active.
The status command should print whether a consent token exists.
The status command should print whether any pending local upload payloads exist.
The status command should not contact the network.
The status command should not validate tokens over the network.

## 9. Payload verification command

v0.5 introduces:

```bash
inferguard telemetry verify-payload <run_id-or-path>
```

This command renders the exact candidate payload for a run.
It is an audit command.
It should work while telemetry is disabled.
It should work without a Touchdown account.
It should not contact the network.
It should identify redaction status.
It should identify schema version.
It should identify DP parameters.
It should identify whether the payload is sendable under current policy.
It should never display prompt text unless the user explicitly saved prompt text locally.
It should never include output content.
It should never include tool argument values.

## 10. Allowed network categories

User-supplied inference endpoint calls are allowed.
User-supplied metrics endpoint calls are allowed.
Localhost proxy calls are allowed.
Localhost daemon control calls are allowed.
Loopback Prometheus scrape endpoints are allowed.
Touchdown-hosted telemetry is not allowed by default.
Touchdown-hosted telemetry is not shipped as a network upload path in v0.5.
Third-party analytics endpoints are not allowed.
Update-check endpoints are not allowed.
License-check endpoints are not allowed.

## 11. Sensitive data posture

Default artifacts do not include prompt text for telemetry.
Default artifacts do not include output token text for telemetry.
Default artifacts do not include tool arguments for telemetry.
Default telemetry payloads must not include file paths.
Default telemetry payloads must not include environment variables.
Default telemetry payloads must not include API keys.
Default telemetry payloads must not include IP addresses.
Default telemetry payloads must not include usernames.
Default telemetry payloads must not include raw KV block IDs.
Default telemetry payloads must not include raw block hashes.

## 12. Operator checklist

Run `inferguard telemetry status` on a fresh install.
Run the grep verification recipe after source changes.
Run `inferguard telemetry verify-payload` before enabling telemetry.
Set `DO_NOT_TRACK=1` in air-gapped or restricted environments.
Set `INFERGUARD_TELEMETRY=disabled` in managed production environments.
Treat unexpected network calls as a release blocker.
Treat unexpected sensitive fields as a release blocker.
Confirm `~/.config/inferguard/secrets/consent.token` is mode `0o600` after enabling telemetry.
Point auditors to this file and `oss/inferguard/docs/telemetry/v1/SPEC.md`.
