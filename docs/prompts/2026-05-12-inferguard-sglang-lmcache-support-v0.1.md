# InferGuard SGLang + LMCache Support Spec v0.1

Generated: 2026-05-12T01:17:37Z
Owner: Touchdown Labs / InferGuard
Repo: `/Users/chen/Projects/inferguard`
Branch target: current feature branch unless agent determines a cleaner branch is needed.

## Task

Add first-class SGLang support as the next backend-expansion lane after the vLLM + LMCache PR3255 downstream release.

This is not a broad rewrite. The goal is to turn existing partial SGLang support into source-backed, fixture-tested, docs-visible support for:

1. SGLang native `/metrics` parsing and coverage reporting.
2. SGLang + LMCache embedded mode launched with `--enable-lmcache`.
3. SGLang KV events generated through LMCache `enable_kv_events` and SGLang `--kv-events-config`.
4. SGLang cache surfaces: Radix/prefix cache, HiCache where present, queue/running requests, token usage, generation throughput, KV transfer counters if present.
5. Conservative docs and SDLC status that clearly separates fixture-supported, source-backed, and live-validated claims.

## Current repo state discovered

Existing support already present:

- `src/inferguard/collect_metrics/normalize.py`
  - `SGLANG_LOCKED_METRICS` includes prompt/generation tokens, token usage, cache hit rate, queue/running requests, latency, function latency, estimated FLOPs.
  - `ENGINE_SOURCE_METRICS` maps SGLang into prefill, decode, queue, kv_cache, prefix_cache.
  - KV transfer names are already recognized for `sglang:kv_transfer_sent_bytes_total`, `sglang:kv_transfer_recv_bytes_total`, `sglang:kv_transfer_errors_total`.
- `tests/test_collect_metrics.py`
  - `test_parse_sglang_fixture`
  - `test_sglang_engine_groups`
- `tests/fixtures/sglang.txt`
- `tests/fixtures/sglang_hicache.txt`
- `src/inferguard/launch_engine/sglang.py`
  - launch command builder exists.
  - defaults include `--enable-cache-report`.
- `tests/test_launch_engine_sglang.py`
  - verifies launch command behavior and B200 FP8 chunked prefill guardrails.
- `docs/guides/observability-coverage-matrix.md`
  - SGLang queue: `supported`
  - SGLang prefix cache: `partial`
  - SGLang KV transfer: `supported` if present
  - SGLang embedded LMCache: `partial`
  - SGLang LMCache MP evidence: `missing`
- `CHANGELOG.md`
  - records SGLang HiCache field extensions as inferred and needing live validation.

External source-backed facts gathered:

- LMCache quickstart documents SGLang with LMCache via:
  - `uv pip install --prerelease=allow lmcache "sglang"`
  - `LMCACHE_CONFIG_FILE=$PWD/lmc_config.yaml`
  - `python -m sglang.launch_server --model-path Qwen/Qwen3-8B --host 0.0.0.0 --port 30000 --enable-lmcache`
- LMCache SGLang sample config:
  - `chunk_size: 8` for demo only
  - `local_cpu: true`
  - `use_layerwise: true`
  - `max_local_cpu_size: 10`
- LMCache docs describe SGLang runtime logs with:
  - `Prefill batch, #new-seq, #new-token, #cached-token, token usage, #running-req, #queue-req`
  - `Decode batch, #running-req, #token, token usage, gen throughput, #queue-req`
  - `LMCache INFO: Stored ... out of total ... tokens`
- LMCache KV cache events docs describe SGLang support via:
  - `enable_kv_events: true` in LMCache config
  - SGLang launch `--kv-events-config '{"publisher": "zmq", "topic": "kv-events"}'`
  - event payloads include `BlockStored` with `block_hashes`, `parent_block_hash`, `token_ids`, `block_size`, `lora_id`.

## Classification

### AUTO

Implement without human review:

1. Add/repair source-backed SGLang fixture parsing for current metric names.
2. Add fixture tests for SGLang + LMCache embedded logs/metrics and SGLang KV event payload redaction/parsing.
3. Add observability coverage rows and report fields for SGLang embedded LMCache and SGLang KV events.
4. Add CLI flags only if needed for existing commands, but do not invent engine runtime flags that upstream does not document.
5. Update docs to mark fixture-supported lanes as `supported` or `partial`, not `live_validated`.
6. Run focused tests and docs build.
7. Commit and push only intended files.

### REVIEW

Needs founder/maintainer review before claiming publicly:

1. Marking any SGLang lane as `live_validated`.
2. Publishing a release note that implies customer-ready SGLang + LMCache support.
3. Treating SGLang LMCache MP as supported if current upstream docs only prove embedded `--enable-lmcache`.
4. Any claim that SGLang performs better, cheaper, or more reliably with LMCache.

### MANUAL / EXPENSIVE

Do not run automatically unless credentials/GPU budget are already configured and clearly safe:

1. Modal H100/B200 SGLang live run.
2. Full SGLang installation with GPU kernels if local machine lacks CUDA kernels, e.g. `sgl_kernel` failures.
3. Upstream SGLang or LMCache PRs.

## Implementation plan

### Phase 1: inventory and source-backed contract

1. Inspect these files:
   - `src/inferguard/collect_metrics/normalize.py`
   - `src/inferguard/observability_coverage.py`
   - `src/inferguard/compat.py`
   - `src/inferguard/launch_engine/sglang.py`
   - `tests/test_collect_metrics.py`
   - `tests/test_observability_coverage.py`
   - `tests/test_launch_engine_sglang.py`
   - `tests/fixtures/sglang.txt`
   - `tests/fixtures/sglang_hicache.txt`
   - `docs/guides/observability-coverage-matrix.md`
2. Confirm actual parser support and identify any mismatch between fixture names and normalization aliases.
3. Record source references in docs comments or docs text, not as unsupported claims.

### Phase 2: metrics and coverage parser work

Add/confirm support for these SGLang metric families:

- Core latency:
  - `sglang:time_to_first_token_seconds`
  - `sglang:e2e_request_latency_seconds`
  - `sglang:time_per_output_token_seconds`
  - `sglang:func_latency_seconds`
- Token throughput:
  - `sglang:prompt_tokens_total`
  - `sglang:generation_tokens_total`
  - `sglang:gen_throughput`
  - `sglang:estimated_flops_per_gpu_total`
- Queue/scheduler:
  - `sglang:num_running_reqs`
  - `sglang:num_queue_reqs`
  - `sglang:num_preemptions_total` if present
- Cache/radix/HiCache:
  - `sglang:cache_hit_rate`
  - `sglang:token_usage`
  - `sglang:num_used_tokens`
  - `sglang:hicache_l1_hit_count_total`
  - `sglang:hicache_l2_hit_count_total`
  - `sglang:hicache_l3_hit_count_total`
  - `sglang:hicache_lookup_count_total`
  - `sglang:hicache_l2_bytes`
  - `sglang:hicache_l3_bytes`
- KV transfer if present:
  - `sglang:kv_transfer_sent_bytes_total`
  - `sglang:kv_transfer_recv_bytes_total`
  - `sglang:kv_transfer_errors_total`

Acceptance:

- `normalize_engine_sample("sglang", fixture)` surfaces measured fields in the correct groups.
- `observability-coverage --expected-engine sglang` produces deterministic report statuses.
- HiCache support remains marked source-backed/fixture-backed unless live validated.

### Phase 3: SGLang + LMCache embedded support

Add fixture coverage for the documented LMCache/SGLang embedded mode:

- SGLang launch contract:
  - `python -m sglang.launch_server --model-path <model> --host 0.0.0.0 --port 30000 --enable-lmcache`
  - `LMCACHE_CONFIG_FILE=<path>`
- LMCache config contract:
  - `local_cpu: true`
  - `use_layerwise: true`
  - `max_local_cpu_size: <GB>`
  - `chunk_size` demo values must be documented as demo-only.
- Logs to parse or preserve as evidence:
  - `Prefill batch ... #cached-token ... token usage ... #running-req ... #queue-req`
  - `Decode batch ... gen throughput ...`
  - `LMCache INFO: Stored ... out of total ... tokens`

Acceptance:

- InferGuard can produce a coverage/compat report for a SGLang metrics file plus embedded LMCache evidence.
- Docs say embedded SGLang + LMCache is parser/fixture-supported and awaiting live validation.
- No MP claim unless source/liveness supports it.

### Phase 4: SGLang KV event redacted evidence

Add a SGLang KV-event evidence parser or normalize through an existing evidence path.

Required safety:

- Accept event metadata needed to prove event flow.
- Redact or reject raw token IDs by default.
- Do not persist `token_ids` in report artifacts unless explicitly configured for local unsafe debug. Default must be no raw tokens.
- Record counts:
  - event batches
  - `BlockStored` count
  - `BlockRemoved` count if present
  - block count
  - has_parent relationships
  - forbidden/raw fields seen and rejected/redacted

Suggested schema:

```json
{
  "schema_version": "inferguard-sglang-kv-events-evidence/v1",
  "source_engine": "sglang",
  "publisher": "zmq",
  "topic": "kv-events",
  "event_batch_count": 1,
  "block_stored_count": 16,
  "block_removed_count": 0,
  "raw_token_ids_recorded": false,
  "raw_block_hashes_recorded": false,
  "claim_status": "measured|synthetic|not_proven"
}
```

Acceptance:

- Fixture includes representative SGLang KV event payload from docs with raw token IDs present in source fixture, but the normalized output must prove `raw_token_ids_recorded=false`.
- `observability-coverage` can consume the normalized evidence and mark SGLang KV events as `partial`/`supported` depending on actual parser path.
- Tests fail if report output contains raw `token_ids` or raw block hashes.

### Phase 5: docs and release discipline

Update:

- `docs/guides/observability-coverage-matrix.md`
- `docs/CLI_REFERENCE.md` only if commands/flags changed
- `CHANGELOG.md` unreleased section or add release-note draft
- `README.md` only if current public capability needs a short mention

Required wording:

- Use `source-available/BUSL-1.1` language.
- Do not call SGLang + LMCache support `live_validated` until there is a real runtime artifact.
- Do not claim speedup, cost reduction, or better hit rate without live benchmark proof.
- Make the current state clear:
  - native SGLang metrics: supported/fixture-tested
  - SGLang + LMCache embedded: source-backed + fixture-tested, pending live validation
  - SGLang KV events: source-backed + parser-tested, pending live validation
  - SGLang + LMCache MP: unsupported/missing unless upstream source proves a stable MP path

### Phase 6: verification

Run at minimum:

```bash
cd /Users/chen/Projects/inferguard
uv run --with pytest --with pytest-asyncio --with aiohttp --with msgpack pytest -q \
  tests/test_collect_metrics.py \
  tests/test_observability_coverage.py \
  tests/test_launch_engine_sglang.py
uv run mkdocs build
```

If broader changes touch compat/CLI:

```bash
uv run --with pytest --with pytest-asyncio --with aiohttp --with msgpack pytest -q \
  tests/test_lmcache_metrics_adapter.py \
  tests/test_collect_metrics.py \
  tests/test_observability_coverage.py \
  tests/test_launch_engine_sglang.py
```

## Output requirements

Agent must return:

1. Commit SHA and branch pushed, or explicit reason no push happened.
2. Files changed.
3. Test commands and pass/fail output.
4. Exact claim status after change:
   - native SGLang metrics
   - SGLang + LMCache embedded
   - SGLang KV events
   - SGLang + LMCache MP
5. Any blockers, especially kernel/install blockers like `ModuleNotFoundError: No module named 'sgl_kernel'`.

## Non-claims

Do not claim:

- SGLang support is 100% complete.
- SGLang + LMCache is live-validated unless real artifacts exist.
- LMCache makes SGLang faster.
- MP mode works with SGLang unless verified by source and live artifact.
- Raw token/block data is safe to persist.
