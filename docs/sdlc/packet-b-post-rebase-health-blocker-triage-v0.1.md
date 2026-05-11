# Packet B post-rebase health blocker triage v0.1

Date: 2026-05-11
Scope: InferGuard Packet B / standalone LMCache MP post-rebase health blocker
Constraint: no Modal/H100 launch in this triage; no staging, commit, push, or PR.

## Summary

Likely root cause: InferGuard's Packet B Modal runner is polling stale LMCache MP HTTP routes under `/api/*`. The rebased LMCache server exposes health and status at `/healthcheck` and `/status`, while the runner waits on `http://127.0.0.1:8080/api/healthcheck`.

Fix target: `inferguard_runner_fix`.

The failed Modal run was not a server startup failure. The existing run artifact shows LMCache HTTP came up, initialized the ZMQ cache server, and then returned repeated `404 Not Found` responses for `GET /api/healthcheck` until the runner timed out.

## Evidence ledger

### Triage prompt

- Prompt executed: `/Users/chen/Projects/inferguard/docs/prompts/2026-05-11-packet-b-post-rebase-health-blocker-triage-v0.1.md`.
- Modal/H100 was not launched.
- No git staging, commit, push, or PR was performed.
- Existing unrelated dirty files were preserved.

### Initial repo state observed

InferGuard dirty state before report write:

```text
 M docs/getting-started/quick-start.md
 M uv.lock
?? docs/prompts/2026-05-11-packet-b-post-rebase-health-blocker-triage-v0.1.md
?? docs/prompts/inferguard-rebase-smoke-verification-v0.1.md
```

LMCache dirty state:

```text
?? .DS_Store
```

vLLM dirty state: clean.

Expected LMCache branch/head confirmed:

```text
branch: ocwc/l0-boundary-evidence
HEAD: f2a6a037c2af2f91dae958ec9f94aacd1f34984b
upstream/dev: 588ee83c10c1910396d3702dbc1cbd0fd9b582dd
```

### InferGuard runner code

File inspected: `/Users/chen/Projects/inferguard/scripts/lmcache_mp_modal_packet_lab.py`.

The runner defines:

```python
LMCACHE_HTTP_BASE_URL = f"http://127.0.0.1:{LMCACHE_HTTP_PORT}"
LMCACHE_HEALTH_URL = f"{LMCACHE_HTTP_BASE_URL}/api/healthcheck"
```

The Packet B launch command is built as:

```text
lmcache server --host 127.0.0.1 --port 6555 --http-port 8080 ...
```

The runner waits on `LMCACHE_HEALTH_URL` before scraping metrics or launching vLLM.

Safe HTTP capture also uses stale mixed routes:

```text
healthcheck.json -> /api/healthcheck
status.json      -> /api/status
quota.json       -> /api/quota
```

Only quota is currently `/api`-prefixed in the inspected LMCache source.

### LMCache HTTP source

Files inspected:

- `/Users/chen/Projects/LMCache/lmcache/v1/multiprocess/http_server.py`
- `/Users/chen/Projects/LMCache/lmcache/v1/multiprocess/config.py`
- `/Users/chen/Projects/LMCache/lmcache/cli/commands/server.py`
- `/Users/chen/Projects/LMCache/lmcache/v1/multiprocess/http_apis/healthcheck_api.py`
- `/Users/chen/Projects/LMCache/tests/v1/multiprocess/test_http_api_registry.py`

Observed route contract in current branch:

```text
GET /healthcheck
GET /status
GET /
POST /clear-cache
GET /api/quota
GET/PUT/DELETE /api/quota/{cache_salt}
```

The current test contract confirms expected routes include:

```python
expected = {"/", "/healthcheck", "/clear-cache", "/status"}
```

`upstream/dev` also exposes health and status at `/healthcheck` and `/status`, not `/api/healthcheck` or `/api/status`.

### LMCache branch diffs vs upstream/dev

Focused diff inspected for:

- `lmcache/integration/vllm/vllm_multi_process_adapter.py`
- `lmcache/v1/mp_observability/subscribers/metrics/l0_lifecycle.py`
- `lmcache/v1/multiprocess/server.py`
- `lmcache/v1/multiprocess/http_server.py`
- `lmcache/v1/multiprocess/config.py`
- `lmcache/cli/commands/server.py`
- relevant tests

Diff stat for the focused set:

```text
lmcache/integration/vllm/vllm_multi_process_adapter.py |  37 ++++++
lmcache/v1/mp_observability/subscribers/metrics/l0_lifecycle.py | 72 ++++++++++++
lmcache/v1/multiprocess/server.py | 37 ++++++
tests/v1/mp_observability/subscribers/metrics/test_l0_lifecycle.py | 127 ++++++++++++++++++++-
```

No focused diff changed the LMCache HTTP route, host, port, or CLI startup path. The branch diff adds L0 boundary evidence and metrics wiring only.

### Existing Modal run output and artifact

Modal run: `https://modal.com/apps/ocwc22/main/ap-YPfI7S59z2PU0TW1mNOJxJ`.

Modal CLI logs were retrievable by app/run id attempt and included the top-level traceback:

```text
RuntimeError: LMCache HTTP did not become healthy at http://127.0.0.1:8080/api/healthcheck
```

Existing run artifact was retrievable from the Modal volume without launching H100:

```bash
modal volume ls lmcache-mp-lab /packet-b-lifecycle-reuse-eviction
modal volume get --force lmcache-mp-lab /packet-b-lifecycle-reuse-eviction/20260511T050110Z /tmp/inferguard-packet-b-triage
```

Relevant pulled artifact path:

```text
/tmp/inferguard-packet-b-triage/20260511T050110Z
```

`health.log` shows startup followed by endpoint mismatch:

```text
curl: (7) Failed to connect to 127.0.0.1 port 8080 ... Connection refused
curl: (22) The requested URL returned error: 404
curl: (22) The requested URL returned error: 404
...
```

`lmcache.log` shows successful server startup:

```text
Starting LMCache HTTP server on http://0.0.0.0:8080
Application startup complete.
Uvicorn running on http://0.0.0.0:8080
```

`lmcache.log` then shows repeated stale-route requests:

```text
GET /api/healthcheck HTTP/1.1 404 Not Found
GET /api/healthcheck HTTP/1.1 404 Not Found
...
```

This proves the HTTP server became reachable; the readiness probe was wrong.

## Likely root cause

InferGuard Packet B runner stale health URL:

```text
http://127.0.0.1:8080/api/healthcheck
```

Correct LMCache MP health URL for the inspected source:

```text
http://127.0.0.1:8080/healthcheck
```

The runner fails before vLLM launch, traffic, metrics capture, or InferGuard compatibility checks, so this failure does not implicate:

- LMCache L0 lifecycle subscriber logic;
- vLLM connector overlay logic;
- Packet B workload generation;
- Modal GPU allocation;
- H100 runtime capacity.

## Classification

Fix target: `inferguard_runner_fix`.

Not selected:

- `lmcache_branch_fix`: no branch diff changed health/status routing, and current/upstream route tests agree on `/healthcheck` and `/status`.
- `vllm_overlay_fix`: vLLM is not launched before the failure.
- `modal_environment_fix`: HTTP server starts and serves 404s, so the environment is not the primary blocker.
- `unknown_needs_rerun_logs`: logs and artifact were retrievable and sufficient.

## Exact patch plan

1. Update `scripts/lmcache_mp_modal_packet_lab.py`:
   - change `LMCACHE_HEALTH_URL` from `/api/healthcheck` to `/healthcheck`;
   - change safe HTTP capture `healthcheck.json` endpoint from `/api/healthcheck` to `/healthcheck`;
   - change safe HTTP capture `status.json` endpoint from `/api/status` to `/status`;
   - keep quota at `/api/quota`, because current LMCache quota routes are `/api/quota*`.
2. Update InferGuard packet tests to assert the current LMCache route contract, especially the health URL and safe capture map.
3. Audit docs that currently state `/api/healthcheck` or `/api/status`; update only the runner-facing Packet B/MP contract if required by the code patch.
4. Do not modify LMCache or vLLM for this blocker unless the patched runner reaches a later LMCache/vLLM failure.

## Local non-H100 tests run

InferGuard focused tests:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
# 28 passed in 0.27s

uv run pytest tests/test_lmcache_live_fixtures.py -q
# 4 passed in 0.23s

uv run pytest tests/test_observability_coverage.py -q
# 21 passed in 0.36s
```

LMCache local test attempt:

```bash
cd /Users/chen/Projects/LMCache
uv run pytest tests/v1/mp_observability/subscribers/metrics/test_l0_lifecycle.py \
  tests/v1/multiprocess/test_http_api_registry.py \
  tests/v1/multiprocess/test_free_locks.py \
  tests/test_vllm_mp_adapter.py -q
```

Result: blocked on macOS ARM dependency resolution before tests ran:

```text
cupy-cuda12x==14.0.1 ... doesn't have a source distribution or wheel for macosx_26_0_arm64
```

Static inspection substituted for LMCache runtime tests on this host.

## Exact tests to run before the next H100 launch

After applying the InferGuard runner patch, run:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
uv run pytest tests/test_lmcache_live_fixtures.py -q
uv run pytest tests/test_observability_coverage.py -q
uv run mkdocs build
```

Optional if a Linux/CUDA-capable LMCache environment is available:

```bash
cd /Users/chen/Projects/LMCache
pytest tests/v1/multiprocess/test_http_api_registry.py \
  tests/v1/mp_observability/subscribers/metrics/test_l0_lifecycle.py \
  tests/test_vllm_mp_adapter.py -q
```

## Exact H100 rerun command once fixed

Do not run until after the patch and local gates above pass.

```bash
cd /Users/chen/Projects/inferguard
INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache \
modal run scripts/lmcache_mp_modal_packet_lab.py --packet b
```

## PR implications

- InferGuard: patch runner route constants/capture map and tests. This is the likely required PR/change target.
- LMCache: do not PR for this blocker. Current source and upstream/dev agree on `/healthcheck` and `/status`.
- vLLM: do not PR for this blocker. The failure occurs before vLLM launch.
- Kuntia/Kuntai message: wait until Packet B is green after the InferGuard runner fix, unless a later rerun exposes a real LMCache branch issue.

## Next command

Patch the InferGuard runner route contract locally:

```bash
cd /Users/chen/Projects/inferguard
python - <<'PY'
from pathlib import Path
p = Path('scripts/lmcache_mp_modal_packet_lab.py')
s = p.read_text()
s = s.replace('LMCACHE_HEALTH_URL = f"{LMCACHE_HTTP_BASE_URL}/api/healthcheck"',
              'LMCACHE_HEALTH_URL = f"{LMCACHE_HTTP_BASE_URL}/healthcheck"')
s = s.replace('"healthcheck.json": "/api/healthcheck",',
              '"healthcheck.json": "/healthcheck",')
s = s.replace('"status.json": "/api/status",',
              '"status.json": "/status",')
p.write_text(s)
PY
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
```
