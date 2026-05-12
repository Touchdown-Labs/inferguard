# Packet C Modal/H100 live validation blocked report v0.1

Date: 2026-05-09
Repo: `/Users/chen/Projects/inferguard`
Branch: `ocwc/packet-b-l0-lifecycle-overlay`
InferGuard HEAD at run start: `4f4891de3d5c78a9212029a6feb99b65734065a9`

## Packet

- Packet: C / D1
- Gate: MP lifecycle + L2
- Modal app/run: `https://modal.com/apps/ocwc22/main/ap-RYykIAS2bdjtVXG6QBnHnc`
- Remote artifact path: `lmcache-mp-lab:/packet-c/20260509T074644Z`
- Local artifact path: `/Users/chen/Projects/inferguard/modal-out/packet-c/20260509T074644Z`
- LMCache source: local checkout `/Users/chen/Projects/LMCache` (`lmcache-0.4.5.dev83` in the Modal image)
- vLLM source: local connector overlay `/Users/chen/Projects/vllm`

## Result

State: `blocked`
Score movement: none. D1 remains 0/6.

The Packet C runner completed enough of the runtime path to capture launch/config, HTTP, vLLM metrics, LMCache metrics, trace recording, trace replay, lookup-hash evidence, and `lmcache_compat_report.json`. The strict InferGuard gate failed at:

```bash
inferguard lmcache-compat \
  --engine-metrics-file /out/packet-c/20260509T074644Z/vllm_metrics_loaded.prom \
  --lmcache-metrics-file /out/packet-c/20260509T074644Z/lmcache_metrics_loaded.prom \
  --expect-mode mp \
  --mp-prometheus-port 9090 \
  --mp-event-bus-queue-size 10000 \
  --mp-metrics-sample-rate 1.0 \
  --mp-trace-recording-enabled \
  --l2-configured \
  --fail-on missing-required
```

Exit code: `1`.

## Exact missing telemetry

From `modal-out/packet-c/20260509T074644Z/lmcache_compat_report.json`:

```json
[
  {
    "code": "lmcache_mp_family_missing",
    "family": "l2_counters",
    "message": "expected LMCache MP family 'l2_counters' was missing"
  },
  {
    "code": "lmcache_mp_family_missing",
    "family": "l2_throughput",
    "message": "expected LMCache MP family 'l2_throughput' was missing"
  }
]
```

L2 summary in the same report:

```json
{
  "observed": true,
  "store_tasks": 0,
  "store_completed": 0,
  "store_throughput_gbs": null,
  "load_completed": 0,
  "load_throughput_gbs": null,
  "prefetch_load_tasks": 0,
  "prefetch_loaded_keys": 0,
  "num_inflight_l2_stores": 0,
  "num_inflight_l2_loads": 0,
  "active_prefetch_jobs": 0.0
}
```

Observed non-L2 proof from the same run:

- `lmcache_mp` detected: yes.
- `vllm` detected: yes.
- `lmcache_http`: complete.
- `lmcache_logs`: complete.
- `lmcache_trace_recording`: complete.
- `lmcache_trace_replay`: complete.
- `lmcache_lookup_hash`: complete.
- `vllm_prefix_cache`: complete.
- `lmcache_mp` surface: partial, with L2 families missing.

## Runner configuration evidence

The runner wrote `/out/packet-c/20260509T074644Z/lmcache_l2_config.json`:

```json
{
  "adapter": "fs",
  "claim_status": "runner_configured_unvalidated_until_modal_packet_runs",
  "path": "/out/packet-c/20260509T074644Z/l2-fs"
}
```

And set:

```json
{
  "LMCACHE_CONFIG_FILE": "/out/packet-c/20260509T074644Z/lmcache_l2_config.json",
  "LMCACHE_L2_ADAPTER": "fs",
  "LMCACHE_L2_PATH": "/out/packet-c/20260509T074644Z/l2-fs"
}
```

Local LMCache source search found an upstream multiprocess L2 script using CLI flags rather than this JSON/env contract:

```bash
lmcache server \
  --l2-store-policy skip_l1 \
  --l2-prefetch-policy default \
  --l2-adapter '{"type":"mock","max_size_gb":80,"mock_bandwidth_gb":4}'
```

## Next patch target

Patch target: `scripts/lmcache_mp_modal_packet_lab.py` Packet C L2 launch contract.

TDD next step:

1. Add or update a unit test in `tests/test_lmcache_mp_modal_packet_lab.py` that fails until Packet C `lmcache server` command includes the current LMCache MP L2 CLI contract:
   - `--l2-store-policy skip_l1`
   - `--l2-prefetch-policy default`
   - `--l2-adapter` JSON with `type=mock` or another source-confirmed supported adapter
2. Update `_build_lmcache_command()` and Packet C metadata minimally.
3. Re-run local gates:
   - `uv run pytest tests/test_lmcache_live_fixtures.py -q`
   - `uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q`
   - `uv run pytest tests/test_observability_coverage.py -q`
4. Only after those gates pass, run exactly one new Packet C H100 attempt for the changed runtime telemetry state:
   - `INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_c`

## Cost gate decision

No Packet D, E, F, G1, H1, H2, H3, I1, or DLM H100 runs were performed after this blocker. Packet C is the first new score-moving packet after accepted Packet A and Packet B, and it revealed a runtime L2 contract blocker. Per the all-packets cost-gated spec, H100 spending stops until this Packet C L2 launch contract is fixed and local gates pass.

## DLM classification

Search evidence in `/Users/chen/Projects/inferguard` found no literal `DLM` code path or packet runner. The repo does contain generic disaggregated-serving and `llm-d` references under docs/schemas/CLI, but no LMCache/vLLM/DLM packet runtime equivalent to C-F.

State: `not_started` for DLM-specific LMCache/vLLM packet validation.

Future DLM integration prompt/spec:

> Define an InferGuard DLM/llm-d LMCache validation packet only after the repo has a concrete DLM runtime contract. The packet must identify prefill/decode endpoints, transfer metrics, LMCache connector mode, cache/offload telemetry, safe collection endpoints, required fixtures, and the same collect-lmcache -> lmcache-compat -> observability-coverage -> diagnose-bottleneck acceptance chain used for Packet A-F. Do not score DLM coverage from generic disagg docs alone.

## Verification run before H100

```text
uv run pytest tests/test_lmcache_live_fixtures.py -q       # 3 passed
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q # 28 passed
uv run pytest tests/test_observability_coverage.py -q     # 21 passed
```
