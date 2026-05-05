# Example 02: profile a real endpoint

This example shows the same `request-profile` command against either a real vLLM/SGLang endpoint or InferGuard's local mock endpoint.

## Prerequisites

```bash
pip install inferguard
```

For a real GPU run, you need an OpenAI-compatible `/v1/chat/completions` endpoint.

## Option A: use the local mock endpoint

Terminal 1:

```bash
inferguard serve-mimic --port 8800 --model doc-mock
```

Terminal 2:

```bash
rm -rf /tmp/inferguard-profile-doc

inferguard request-profile \
  --output-dir /tmp/inferguard-profile-doc \
  --endpoint http://127.0.0.1:8800/v1/chat/completions \
  --model doc-mock \
  --input-jsonl examples/requests/profile-mock.jsonl \
  --concurrency 1 \
  --stream \
  --workload-label docs-mock
```

Expected stdout shape:

```text
inferguard request-profile: requests=2 success=2 failures=0 ttft_p50=... tpot_p50=... e2e_p99=... tokens_per_sec=...
```

Expected files:

```text
/tmp/inferguard-profile-doc/
  requests_profile.jsonl
  requests_summary.json
```

## Option B: use a real vLLM endpoint

```bash
inferguard request-profile \
  --output-dir runs/request-profile-vllm-001 \
  --endpoint http://<host>:8000/v1/chat/completions \
  --model deepseek-ai/DeepSeek-V4-Flash \
  --input-jsonl examples/requests/profile-mock.jsonl \
  --concurrency 1 \
  --stream \
  --workload-label smoke-vllm
```

If the endpoint requires auth, use the relevant runtime option or environment setup for your deployment. Do not put secrets in the endpoint URL query string.

## Inspect the results

```bash
python3 -m json.tool /tmp/inferguard-profile-doc/requests_summary.json
head -n 1 /tmp/inferguard-profile-doc/requests_profile.jsonl | python3 -m json.tool
```

Fields to check:

- `success_count`
- `failure_count`
- `ttft_ms`
- `tpot_ms`
- `tokens_per_sec_aggregate`
- row-level `claim_status_per_field`

## Gotchas

- Without endpoint `usage` fields, token counts may be `inferred`.
- `request-profile` alone does not make a run `live_complete`; pair it with `collect-metrics`, `launch-engine`/external healthcheck, and `validate-completed`.
- Use `--timeout-seconds` for very long prefill workloads.
