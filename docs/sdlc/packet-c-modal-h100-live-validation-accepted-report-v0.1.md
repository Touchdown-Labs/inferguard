# Packet C Modal/H100 live validation accepted report v0.1

Date: 2026-05-09
Repo: `/Users/chen/Projects/inferguard`
Branch: `ocwc/packet-b-l0-lifecycle-overlay`

## Packet

- Packet: C / D1
- Gate: MP lifecycle + L2
- Modal app/run: `https://modal.com/apps/ocwc22/main/ap-mtwMK7Ii611jxjGNQPux3F`
- Remote artifact path: `lmcache-mp-lab:/packet-c/20260509T080022Z`
- Local artifact path: `/Users/chen/Projects/inferguard/modal-out/packet-c/20260509T080022Z`
- Fixture: `tests/fixtures/lmcache_live/packet_c/`

## Result

State: `live_validated`
Score movement: D1 +6, SSoT score `74 / 100` -> `80 / 100`.

The Packet C retry used the current LMCache MP L2 CLI launch contract:

```bash
lmcache server \
  --l2-store-policy skip_l1 \
  --l2-prefetch-policy default \
  --l2-adapter '{"type":"mock","max_size_gb":80,"mock_bandwidth_gb":4}'
```

`lmcache_compat_report.json` accepted with `failure_reasons=[]`.

## Evidence

Required L2 families are populated:

- `l2_counters`: populated
- `l2_throughput`: populated

L2 summary:

```json
{
  "observed": true,
  "store_tasks": 25.0,
  "store_completed": 25.0,
  "load_completed": 23.0,
  "prefetch_load_tasks": 23.0,
  "prefetch_loaded_keys": 184.0,
  "store_backlog": false,
  "load_backlog": false
}
```

## Verification

```text
RED: uv run pytest tests/test_lmcache_mp_modal_packet_lab.py::test_packet_c_wires_current_lmcache_mp_l2_cli_contract_and_strict_report_flags -q
     1 failed before runner patch

GREEN: uv run pytest tests/test_lmcache_mp_modal_packet_lab.py::test_packet_c_wires_current_lmcache_mp_l2_cli_contract_and_strict_report_flags -q
       1 passed

Local gates before H100:
uv run pytest tests/test_lmcache_live_fixtures.py -q       # 3 passed
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q # 28 passed
uv run pytest tests/test_observability_coverage.py -q     # 21 passed

Fixture gate after import:
uv run pytest tests/test_lmcache_live_fixtures.py -q       # 3 passed
```

## Next action

Do not rerun Packet A/B/C. Next score-moving runtime lane is Packet D / E1 OTel after local gates.
