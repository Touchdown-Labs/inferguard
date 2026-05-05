# Security Policy

If you discover a potential security vulnerability, please report it privately to **security@touchdown-labs.ai**.

- Please include clear reproduction steps, affected versions, and impact details.
- We request coordinated disclosure with a default **90-day disclosure window**.
- Please do not open public GitHub issues for unpatched vulnerabilities.

If available, we also encourage using GitHub's **private vulnerability reporting** UI for this repository.

## Supported versions

| Version | Supported          |
|---------|--------------------|
| 0.7.x   | :white_check_mark: |
| < 0.7   | :x:                |

## GitHub Private Vulnerability Reporting

Use the **Report a vulnerability** button on the [Security tab](https://github.com/OCWC22/inferguard/security) for private disclosure.

## Threat model (OSS scope)

**In scope:**
- Code execution from `inferguard <command>` invocation (CLI surface)
- Engine launcher subprocess spawning (vLLM/SGLang/Dynamo)
- Network calls to `--endpoint` URLs (vLLM/SGLang OpenAI-compatible API)
- Network calls to `--metrics-url` Prometheus scrape endpoints
- Path handling for `--results-root`, `--trace-dir`, etc.
- JSON deserialization of `validation_report.json`, `expected_artifact_contract.json`, etc.

**Out of scope (operator responsibility):**
- Model weights provenance (HuggingFace cache integrity)
- Slurm cluster authentication / partition ACLs
- DCGM exporter security (port 9400)
- Engine-side vulnerabilities (vLLM, SGLang, Dynamo) — report upstream

## Vulnerability disclosure SLA

| Severity | Acknowledgment | Initial response | Patch ETA |
|---|---|---|---|
| Critical (RCE, privilege escalation) | 24h | 48h | 7d |
| High | 72h | 7d | 30d |
| Medium | 7d | 14d | 60d |
| Low | 14d | 30d | 90d |

Coordinated disclosure window: 90d default.
