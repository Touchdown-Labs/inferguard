---
title: "inferguard-telemetry/v1 Opt-In Telemetry Specification"
status: "draft-v0.5-normative"
date: "2026-04-30"
purpose: "Define the opt-in telemetry payload, consent token, privacy blocklist, differential privacy posture, revocation flow, audit semantics, and tier boundaries for InferGuard telemetry."
supersedes-policy: "New opt-in telemetry document; default zero-telemetry posture remains oss/inferguard/docs/telemetry/v0/POSTURE.md."
---

# `inferguard-telemetry/v1` Opt-In Telemetry Specification

## 1. Scope

This document specifies the opt-in telemetry contract for InferGuard.
It covers the `inferguard-telemetry/v1` payload.
It covers the consent token shape.
It covers local payload generation.
It covers privacy blocklists.
It covers the v0.5 DP stub and the v0.6 DP target.
It covers the k-anonymity floor for hosted aggregation.
It covers revocation.
It covers GDPR and CCPA handling.
It covers audit trails and `verify-payload` semantics.
It covers the OSS, Hosted, and Enterprise NDA tier boundary.

## 2. Source documents

The canonical architecture is `docs/designs/2026-04-30-inferguard-harness-architecture.md`.
The OpenTelemetry and DP research basis is `docs/research/38-2026-04-30-industry-harness-research.md`.
The zero-telemetry posture is `oss/inferguard/docs/telemetry/v0/POSTURE.md`.
The harness overview is `oss/inferguard/docs/HARNESS.md`.
The agent trace schema is `oss/inferguard/docs/schemas/agent-trace-v1.md`.
The existing CLI spec is `oss/inferguard/docs/SPEC.md`.

## 3. Relationship to v0 posture

Telemetry is disabled by default.
Telemetry requires explicit user action.
`DO_NOT_TRACK=1` is a hard disable.
`INFERGUARD_TELEMETRY=disabled` is a hard disable.
The v0 posture remains true for fresh installs.
The v1 payload is the format that would be used after consent.
v0.5 ships payload generation and audit paths.
v0.5 does not ship real hosted network upload.
v0.5 writes upload-intent payloads to local pending storage.
v0.6 is the planned release for real DP and hosted upload.

## 4. Normative language

The words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative.
A payload producer is the local harness telemetry component.
A payload consumer is a local validator or hosted ingest service.
A data subject is a natural person under GDPR or CCPA framing.
A customer is the operator organization that granted consent.
A deployment is one local site or cluster represented by a consent token.
A run is a benchmark, agent trace, daemon rollup, or metrics rollup event window.

## 5. Locked payload schema

The following payload shape is locked for v0.5.
It is copied verbatim from the build plan and defines the compatibility target.

```json
{
  "schema_version": "inferguard-telemetry/v1",
  "consent_token": "<JWT signed by api.touchdown.ai>",
  "anonymized_deployment_id": "<sha256 of (consent_token + cluster_fingerprint), truncated to 16 hex>",
  "uploaded_at": "2026-04-30T12:05:23Z",
  "payload_kind": "bench-summary" | "agent-trace-summary" | "metrics-rollup",
  "rig_fingerprint": {
    "gpu_model": "H200" | "B200" | "GB200" | "H100",
    "gpu_count_bucket": "8" | "16" | "32" | "64+",
    "engine": "vllm" | "sglang" | "dynamo-vllm",
    "engine_version_major_minor": "0.20"
  },
  "aggregates": {
    "ttft_p50_ms_bucketed": 420,
    "ttft_p99_ms_bucketed": 5500,
    "kv_pressure_p95_bucketed": 0.85,
    "prefix_cache_hit_rate_bucketed": 0.42,
    "tool_stall_pct_bucketed": 0.40,
    "node_counts": {"model_call": 12, "tool_call": 47},
    "concurrency_cliff_estimate": 32
  },
  "dp_params": {
    "epsilon": 1.0,
    "delta": 1e-5,
    "mechanism": "stub" | "laplace" | "gaussian",
    "library": "stub" | "pipelinedp" | "opendp" | "google-dp"
  }
}
```

## 6. v0.5 DP status

v0.5 MUST emit `dp_params.mechanism: "stub"`.
v0.5 MUST emit `dp_params.library: "stub"`.
v0.5 MUST NOT claim real differential privacy was applied.
v0.5 MAY bucket numeric fields before writing a local pending payload.
v0.5 MUST make `verify-payload` show that DP is a stub.
v0.5 MUST keep real hosted upload out of scope.
v0.5 pending payloads SHOULD be written under `~/.config/inferguard/uploads-pending/`.
v0.5 pending payloads MUST be local files only.
v0.5 pending payloads MUST be deletable by `inferguard telemetry disable`.
v0.5 pending payloads MUST be safe to inspect manually.

## 7. v0.6 DP target

v0.6 is expected to replace the stub with a real DP library.
The target source-side library is PipelineDP.
The source research file lists PipelineDP as a higher-level Python E2E DP library.
OpenDP, Google DP, and PyDP remain alternate reviewed libraries.
The default privacy budget target is `epsilon = 1.0`.
The default delta target is `delta = 1e-5`.
Noise MUST be applied at the source before hosted upload.
The hosted service MUST NOT receive un-noised values for DP-protected aggregates.
The local payload MUST report the mechanism used.
The local payload MUST report the library used.
The local payload MUST report epsilon.
The local payload MUST report delta.

## 8. K-anonymity floor

Hosted peer aggregation MUST use a k-anonymity floor.
The floor for v1 telemetry product surfaces is `k >= 5`.
No peer aggregate may be shown to customers when fewer than five deployments contribute.
No peer aggregate may be exported when fewer than five deployments contribute.
No peer aggregate may be used in marketing claims when fewer than five deployments contribute.
Enterprise private peer pools MAY use a stricter floor by contract.
Regulated deployments SHOULD use a stricter floor by contract.
The dashboard MUST mark aggregates that are withheld due to the k floor.
The Ops agent MUST treat withheld aggregates as unavailable evidence.

## 9. Payload field catalog

| Field | Type | Required | Notes |
|---|---|---:|---|
| `schema_version` | string | yes | MUST equal `inferguard-telemetry/v1`. |
| `consent_token` | JWT string | yes | Long-lived token proving explicit consent. |
| `anonymized_deployment_id` | string | yes | 16 hex chars from consent token plus cluster fingerprint hash. |
| `uploaded_at` | RFC 3339 string | yes | Local payload creation or upload attempt time. |
| `payload_kind` | enum | yes | `bench-summary`, `agent-trace-summary`, or `metrics-rollup`. |
| `rig_fingerprint` | object | yes | Coarse hardware and engine identity. |
| `aggregates` | object | yes | Bucketed and redacted aggregate measurements. |
| `dp_params` | object | yes | DP mechanism declaration. |

`schema_version` is the compatibility discriminator.
`consent_token` MUST NOT be logged to stdout except in explicit debug flows.
`anonymized_deployment_id` MUST NOT include raw hostnames.
`uploaded_at` MUST include timezone information.
`payload_kind` determines which aggregate fields are expected.
`rig_fingerprint` MUST use coarse buckets.
`aggregates` MUST be shape-only and numeric or enum-only.
`dp_params` MUST be truthful.

## 10. Consent token JWT shape

The consent token is a JWT signed by `api.touchdown.ai` or an enterprise issuer.
The token MUST be scoped to one customer or enterprise tenant.
The token MUST be scoped to one deployment or site family.
The token MUST include an expiry.
The token MUST be revocable server-side.
The token SHOULD be refreshed yearly for hosted SaaS.
The token SHOULD be stored in the user's InferGuard config directory.
The token MUST NOT be stored in benchmark artifacts.
The token MUST NOT be embedded in agent trace JSONL files.

Recommended JWT header:

```json
{
  "alg": "ES256",
  "typ": "JWT",
  "kid": "touchdown-telemetry-2026-04"
}
```

Recommended JWT claims:

```json
{
  "iss": "https://api.touchdown.ai/",
  "aud": "inferguard-telemetry/v1",
  "sub": "customer_or_site_id",
  "jti": "consent-token-id",
  "iat": 1777569600,
  "exp": 1809105600,
  "scope": ["bench-summary", "agent-trace-summary", "metrics-rollup"],
  "site_label": "operator-provided-label",
  "contact": "operator-provided-contact",
  "policy_version": "2026-04-30"
}
```

`iss` identifies the token issuer.
`aud` binds the token to InferGuard telemetry.
`sub` identifies the consenting customer or site in hosted systems.
`jti` supports revocation and audit logs.
`iat` records issue time.
`exp` enforces refresh.
`scope` limits payload kinds.
`site_label` is operator-provided and SHOULD be optional.
`contact` is used for breakage and policy notifications.
`policy_version` records which consent text was shown.

## 11. Anonymized deployment ID

`anonymized_deployment_id` is a stable local pseudonym.
It is computed from the consent token and a cluster fingerprint.
The locked formula is SHA-256 over `(consent_token + cluster_fingerprint)`.
The emitted value is truncated to 16 lowercase hex characters.
The cluster fingerprint MUST be derived from coarse deployment properties.
The cluster fingerprint MUST NOT include hostnames.
The cluster fingerprint MUST NOT include IP addresses.
The cluster fingerprint MUST NOT include usernames.
The cluster fingerprint MUST NOT include file paths.
The cluster fingerprint MUST NOT include API keys.
Rotating the consent token SHOULD rotate the deployment ID.
Revoking telemetry SHOULD stop future use of the deployment ID.

## 12. Rig fingerprint

`gpu_model` MUST be one of `H200`, `B200`, `GB200`, or `H100` for v1.
Unknown GPUs SHOULD be withheld or mapped only after a schema update.
`gpu_count_bucket` MUST be `8`, `16`, `32`, or `64+`.
Exact GPU counts outside the enum MUST be bucketed.
`engine` MUST be `vllm`, `sglang`, or `dynamo-vllm`.
`engine_version_major_minor` MUST omit patch and build metadata.
The rig fingerprint is intentionally coarse.
The rig fingerprint supports peer comparison without leaking exact fleet topology.

## 13. Aggregate fields

`ttft_p50_ms_bucketed` is median time-to-first-token in milliseconds.
`ttft_p99_ms_bucketed` is p99 time-to-first-token in milliseconds.
`kv_pressure_p95_bucketed` is p95 KV pressure as a ratio or normalized score.
`prefix_cache_hit_rate_bucketed` is a ratio in the range `[0.0, 1.0]`.
`tool_stall_pct_bucketed` is a ratio in the range `[0.0, 1.0]`.
`node_counts` counts agent trace node kinds.
`concurrency_cliff_estimate` is the estimated concurrency threshold where latency degrades.
Numeric aggregate fields SHOULD be bucketed before payload creation.
DP-protected aggregate fields MUST receive source-side noise in v0.6+.
Textual raw fields MUST NOT be included.

## 14. OpenTelemetry relationship

The local harness may map agent trace fields to OpenTelemetry GenAI names.
The research file identifies `gen_ai.client.token.usage` for token counts.
The research file identifies `gen_ai.server.time_to_first_token` for TTFT.
The research file identifies `gen_ai.client.operation.duration` for operation latency.
Telemetry payloads are not raw OpenTelemetry exports.
Telemetry payloads are redacted, bucketed, and consent-scoped summaries.
Operators may configure separate OpenTelemetry export to their own systems.
Touchdown telemetry consent does not imply OpenTelemetry export consent.
OpenTelemetry export consent does not imply Touchdown telemetry consent.

## 15. Never-collected blocklist

The plan-level never-uploaded list is normative.
Never uploaded: prompts, output tokens, tool arguments, file paths, env vars, API keys, IP addresses, usernames, raw KV-block-ids, raw block hashes.
These items MUST NOT appear in `inferguard-telemetry/v1` payloads.
These items MUST NOT be added under alternate field names.
These items MUST NOT be hidden in nested objects.
These items MUST NOT be encoded into opaque strings.
These items MUST NOT be hashed and uploaded unless a later schema and legal review explicitly changes the policy.

## 16. Expanded blocklist from architecture

`messages[*].content` MUST be dropped at source.
`tool_call.arguments` MUST be dropped at source.
`tool_call.result` MUST be dropped at source.
Full endpoint URLs MUST be replaced with coarse endpoint labels.
`cwd` MUST be dropped.
Full `env` maps MUST be dropped.
Any field tagged `_RAW_` MUST be dropped.
Customer secrets MUST be dropped.
Credentials MUST be dropped.
Internal hostnames MUST be dropped.
SSH paths MUST be dropped.
Filesystem layouts MUST be dropped.
PII-bearing free text MUST be dropped.
Error messages MUST be normalized to error types where possible.

## 17. Data allowed after consent

Model name MAY be sent after consent.
Engine name MAY be sent after consent.
Engine major/minor version MAY be sent after consent.
Coarse hardware model MAY be sent after consent.
Coarse GPU count bucket MAY be sent after consent.
Workload class MAY be sent after consent.
Concurrency bucket MAY be sent after consent.
Input token aggregate MAY be sent after consent and DP treatment.
Output token aggregate MAY be sent after consent and DP treatment.
TTFT aggregate MAY be sent after consent and DP treatment.
Latency aggregate MAY be sent after consent and DP treatment.
Tool stall percentage MAY be sent after consent and DP treatment.
Error type MAY be sent after consent.
Consent token MUST be sent only to authenticate an upload path.

## 18. Consent flow

`inferguard telemetry enable` MUST start the consent flow.
The consent flow MUST show the schema before asking for approval.
The consent flow MUST show the never-collected list.
The consent flow MUST show the current DP mechanism.
The consent flow MUST show that v0.5 uses a stub DP mechanism.
The consent flow MUST show whether real hosted upload exists in this release.
The consent flow MUST ask for explicit operator confirmation.
The consent flow SHOULD capture site label and contact email.
The consent flow MUST persist consent state locally only after confirmation.
The consent flow MUST honor hard opt-out environment variables.
The consent flow MUST fail closed when token creation fails.

## 19. Local state

Consent state SHOULD live under the InferGuard config directory.
Pending upload payloads SHOULD live under `~/.config/inferguard/uploads-pending/` in v0.5.
The exact config root MAY follow platform conventions.
Pending payloads MUST be JSON files or JSONL files that users can inspect.
Pending payloads MUST be deletable without breaking the CLI package.
Pending payloads MUST NOT be required for `inferguard analyze`.
Pending payloads MUST NOT be required for `inferguard bench`.
Pending payloads MUST NOT be required for `inferguard agent trace`.

## 20. Upload transport

v0.5 does not ship real upload transport.
v0.5 writes payloads to local pending storage only.
v0.6 may upload to `https://api.touchdown.ai/v1/ingest` after consent.
Enterprise deployments may upload to a customer-controlled endpoint by contract.
Hosted upload MUST use TLS.
Hosted upload MUST use bearer token authentication.
Hosted upload MUST use the consent token or a derived upload credential.
Hosted upload MUST implement retry with backoff.
Hosted upload MUST stop on authorization failure.
Hosted upload MUST surface disabled state after revocation.

## 21. Differential privacy pipeline

The DP pipeline begins after redaction.
The DP pipeline begins before hosted upload.
The DP pipeline operates on aggregates, not raw prompt or output data.
The DP pipeline buckets fields before or during noise addition.
The DP pipeline applies epsilon and delta according to policy.
The default target is `epsilon = 1.0`.
The default target is `delta = 1e-5`.
PipelineDP is the preferred v0.6 source-side implementation.
Laplace or Gaussian mechanisms MAY be used depending on aggregate type.
The payload MUST declare the mechanism.
The payload MUST declare the library.
The payload MUST declare the budget values.
The server MUST not silently reinterpret the budget.

## 22. Privacy budget

A run-level privacy budget SHOULD be tracked.
A daily customer budget SHOULD be tracked in hosted systems.
A monthly customer budget SHOULD be tracked in hosted systems.
The architecture design proposes ε=1.0/run as the tentative default.
The architecture design discusses ε=10.0/customer-day as an open question.
The architecture design discusses ε=30.0/month as a hard-cap candidate.
Until policy is finalized, payloads MUST state their actual applied budget.
When a budget is exhausted, uploads MUST stop or be withheld.
`Denied:DPBudgetExhausted` is the corresponding permission reason code.

## 23. Revocation flow

`inferguard telemetry disable` MUST disable local payload generation.
`inferguard telemetry disable` MUST delete pending v0.5 payloads unless the user asks to keep them.
`inferguard telemetry disable` MUST stop daemon upload workers.
`inferguard telemetry disable` MUST make `telemetry status` report disabled.
Hosted revocation MUST invalidate the consent token by `jti`.
Hosted revocation MUST stop accepting new payloads for that token.
Hosted revocation SHOULD expose an account or API path for deletion requests.
Hosted revocation SHOULD record the revocation time.
Hosted revocation SHOULD preserve only legally required audit metadata.
Re-enable MUST require a fresh consent decision when policy text changed.

## 24. GDPR framework

The hosted service SHOULD treat the customer as controller where appropriate.
Touchdown SHOULD act as processor for customer telemetry in hosted SaaS.
Enterprise terms MAY change this allocation by contract.
The lawful basis is explicit consent or contractual necessity, depending on deployment.
Data minimization is enforced by the blocklist.
Purpose limitation is peer benchmarking, operations diagnosis, and InferKV aggregate research.
Access requests SHOULD be routed through the customer account owner.
Deletion requests SHOULD delete or anonymize hosted telemetry associated with the token.
Retention periods MUST be documented in the hosted policy.
Cross-border transfer terms MUST be handled in the hosted DPA.
HIPAA or regulated deployments require Enterprise terms and a BAA if applicable.

## 25. CCPA framework

The hosted service SHOULD treat telemetry as service-provider data when contracted with a business customer.
Telemetry MUST NOT be sold as personal information.
Telemetry MUST NOT be shared for cross-context behavioral advertising.
Opt-out and deletion requests MUST be supported through customer account workflows.
The blocklist reduces personal information collection by design.
The product should avoid direct identifiers in payloads.
The consent token and deployment ID are pseudonymous operational identifiers.
Enterprise contracts may impose stricter deletion, retention, and access workflows.

## 26. Audit trail

Each consent action SHOULD create a local audit event.
Each enable action SHOULD record timestamp, policy version, scopes, and operator identity if provided.
Each disable action SHOULD record timestamp and reason if provided.
Each verify-payload action SHOULD be optionally loggable locally.
Each hosted upload attempt SHOULD be visible in `inferguard telemetry log`.
The local ring buffer SHOULD show the last 50 telemetry attempts or pending writes.
The hosted service SHOULD store token `jti`, payload schema version, payload kind, and ingest result.
The hosted service SHOULD NOT store raw rejected payloads if they fail blocklist validation.
Audit logs MUST NOT include prompts.
Audit logs MUST NOT include output text.
Audit logs MUST NOT include tool arguments.

## 27. `verify-payload` semantics

`inferguard telemetry verify-payload` MUST be a local-only command.
It MUST accept a run ID or path.
It MUST render the exact candidate `inferguard-telemetry/v1` payload.
It MUST include the schema version.
It MUST include payload kind.
It MUST include rig fingerprint.
It MUST include aggregate values after bucketing.
It MUST include DP parameters.
It MUST show `mechanism: "stub"` and `library: "stub"` in v0.5.
It MUST state whether current policy permits upload.
It MUST state whether `DO_NOT_TRACK=1` blocks upload.
It MUST state whether `INFERGUARD_TELEMETRY=disabled` blocks upload.
It MUST highlight any field dropped by the blocklist.
It MUST fail closed if sensitive data is detected.
It MUST NOT contact the network.
It MUST be usable before telemetry is enabled.

## 28. `telemetry status` semantics

`inferguard telemetry status` MUST be a local-only command.
It MUST print enabled or disabled state.
It MUST print hard override state.
It MUST print consent token presence without printing the token value.
It MUST print pending payload count.
It MUST print the v0 posture reference.
It MUST not check token validity over the network.
It MUST not create a token.
It MUST not modify pending payloads.
It MUST not import optional network clients unless needed.

## 29. Permission reason codes

`Allowed:UserExplicitlyEnabled` means the user ran telemetry enable on this site.
`Allowed:CIWithExplicitFlag` means CI explicitly opted in and provided consent.
`Allowed:HostedDashboardLogin` means a hosted dashboard action authorized consent from this host.
`Denied:Default` means telemetry is disabled by initial state.
`Denied:UserDisabled` means the user disabled telemetry.
`Denied:ConsentExpired` means the token is past expiry.
`Denied:NeverCollectedField` means the payload contains a blocklisted field.
`Denied:DPBudgetExhausted` means the privacy budget is consumed.
`Denied:AirgappedMode` means essential-traffic or equivalent air-gapped mode is active.

## 30. Tier table

This table adapts the monetization split in `docs/designs/2026-04-30-inferguard-harness-architecture.md` §10.
It is included here because telemetry is the boundary between free OSS and hosted value.

| Capability | OSS / Free forever | Hosted SaaS | Enterprise / NDA |
|---|---|---|---|
| `inferguard` CLI | Included; no account | Same client may connect after consent | May be vendored or pinned |
| `inferguard-mcp` | Included; read-only | Can feed hosted context after consent | Can be disabled or isolated |
| `inferguard bench` | Included; local artifacts | Summaries may power dashboards | Private benchmark pools |
| `inferguard analyze` | Included; local reports | Hosted trend context may enrich analysis | Custom retention and evidence packs |
| `inferguard agent trace` | Included; full local trace capture | Summary telemetry powers peer comparisons | Private trace store or no external store |
| `inferguard daemon start` | Included; offline sidecar | Optional hosted rollups after consent | Self-hosted or customer VPC sidecar |
| `telemetry status` | Included; always audit-grade | Included | Included |
| `telemetry verify-payload` | Included; always audit-grade | Included | Included with contractual schema review |
| `telemetry enable` | Creates explicit consent; v0.5 local pending only | Enables dashboard and peer benchmarks | Enables custom endpoint or private pool |
| Peer benchmarks | Not available without upload | Daily or periodic hosted aggregates | Private peer pool under NDA |
| Ops agent diagnosis | Not in OSS | Paid hosted tier | Custom enterprise workflows |
| Canary validator | Not in OSS | Custom or higher tier | Customer-specific validation terms |
| Long-term silicon corpus | Local-only inputs | Aggregated product research | Data partnership under NDA |
| BAA / HIPAA support | Not included | Not standard | Contracted enterprise requirement |
| FedRAMP / SOC2 evidence | OSS source only | SaaS evidence when available | Contracted enterprise requirement |
| Data retention | Local operator control | Hosted policy | Contract-specific |
| Deletion SLA | Local file deletion | Hosted account workflow | Contract-specific |

## 31. Hosted aggregation rules

Hosted dashboards MUST enforce the k-anonymity floor.
Hosted dashboards MUST label withheld peer aggregates.
Hosted dashboards MUST separate customer raw view from peer aggregate view.
Hosted Ops agents MUST cite whether evidence is local or peer-derived.
Hosted Ops agents MUST not expose another customer's telemetry.
Hosted exports MUST preserve DP and k-anonymity constraints.
Hosted marketing claims MUST use aggregate cohorts only.
Hosted research outputs MUST not reveal single-customer facts.

## 32. Enterprise NDA rules

Enterprise customers may require self-hosted ingest.
Enterprise customers may require a private peer pool.
Enterprise customers may require custom retention.
Enterprise customers may require BAA terms.
Enterprise customers may require FedRAMP or SOC2 evidence.
Enterprise customers may require no cross-customer aggregation.
Enterprise customers may require customer-managed keys.
Enterprise customers may require custom deletion attestations.
Enterprise terms MUST be documented outside OSS defaults.
Enterprise terms MUST NOT weaken OSS default privacy posture.

## 33. Security validation

Payload validators MUST reject unknown schema versions by default.
Payload validators MUST reject missing consent tokens for sendable payloads.
Payload validators MUST reject invalid payload kinds.
Payload validators MUST reject exact GPU counts outside the bucket enum.
Payload validators MUST reject full URLs in telemetry payloads when they leak internal hostnames.
Payload validators MUST reject obvious API key patterns.
Payload validators MUST reject prompt-like free text.
Payload validators MUST reject file-system paths.
Payload validators MUST reject environment variable maps.
Payload validators MUST reject raw block identifiers.
Payload validators MUST reject raw block hashes.
Payload validators MUST fail closed.

## 34. Retention

Local v0.5 pending payload retention is controlled by the operator.
`telemetry disable` SHOULD delete pending payloads by default.
Hosted retention MUST be published before real upload ships.
Starter hosted retention may be shorter than enterprise retention.
Enterprise retention may be contractual.
Deletion requests MUST be honored according to the hosted policy.
Research aggregates SHOULD be irreversible before long-term retention.
Raw payload retention SHOULD be minimized.

## 35. Incident response

If a blocklisted field is detected locally, payload generation MUST stop.
If a blocklisted field is detected hosted-side, ingest MUST reject the payload.
If a sensitive field is accidentally accepted, it MUST trigger a security incident workflow.
The incident workflow SHOULD include customer notice when applicable.
The incident workflow SHOULD rotate affected consent tokens when applicable.
The incident workflow SHOULD document root cause and remediation.
The incident workflow SHOULD update validators and tests.

## 36. Examples

Fresh install status:

```bash
inferguard telemetry status
```

Expected posture:

```text
No telemetry. No network calls outside endpoints you pass via flags. Verified: see oss/inferguard/docs/telemetry/v0/POSTURE.md.
```

Payload audit:

```bash
inferguard telemetry verify-payload runs/agent-trace-001
```

Enable consent:

```bash
inferguard telemetry enable
```

Disable and revoke local state:

```bash
inferguard telemetry disable
```

## 37. Non-goals

This spec does not define raw prompt logging.
This spec does not define raw output logging.
This spec does not define raw tool argument logging.
This spec does not define hosted dashboards.
This spec does not define enterprise legal terms.
This spec does not implement real DP in v0.5.
This spec does not authorize default-on telemetry.
This spec does not supersede the zero-telemetry posture.

## 38. Release checklist

Confirm `oss/inferguard/docs/telemetry/v0/POSTURE.md` matches implementation.
Confirm `inferguard telemetry status` is local-only.
Confirm `inferguard telemetry verify-payload` is local-only.
Confirm v0.5 payloads use `mechanism: "stub"`.
Confirm v0.5 payloads use `library: "stub"`.
Confirm never-collected fields are absent.
Confirm hard environment overrides win.
Confirm pending payloads are local files.
Confirm disable clears or stops pending work.
Confirm hosted upload remains out of scope until v0.6.
