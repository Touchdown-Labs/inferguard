# Packet D/E/F Modal H100 live validation accepted report v0.1

Date: 2026-05-09
Status: accepted
Scope: E1 Packet D OTel, E2 Packet E trace replay, F1 Packet F cache_salt + IsolatedLRU + lookup-hash

## Recovery

The previous validation agent stalled during Packet F after starting:

```bash
INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache \
INFERGUARD_VLLM_LOCAL_SOURCE=/Users/chen/Projects/vllm \
modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_f
```

Recovery checked the Modal volume before rerun and found `lmcache-mp-lab:/packet-f/20260509T084753Z`, so Packet F was not rerun.

## Accepted evidence

### Packet D / E1 OTel

- Modal run: `https://modal.com/apps/ocwc22/main/ap-9W64hscDSk9k252A5jEHNX`
- Remote artifact: `lmcache-mp-lab:/packet-d/20260509T082322Z`
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/packet-d/20260509T082322Z/20260509T082322Z`
- Fixture: `tests/fixtures/lmcache_live/packet_d/`
- Metrics: `span_count=49`, `mp_span_count=33`, `request_span_count=16`, `mp.store=17`, `mp.lookup_prefetch=16`
- Status: `failure_reasons=[]`, fixture accepted by `tests/test_lmcache_live_fixtures.py`

### Packet E / E2 trace replay

- Modal run: `https://modal.com/apps/ocwc22/main/ap-zZmiralX1wMTxr5cITIGTp`
- Remote artifact: `lmcache-mp-lab:/packet-e/20260509T083910Z`
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/packet-e/20260509T083910Z/20260509T083910Z`
- Fixture: `tests/fixtures/lmcache_live/packet_e/`
- Metrics: `rows_seen=71`, `failed_rows=0`, `duration_s=114.1273729801178`, `sm_config_digest=0ed88aff036abdcb3c43c08199a899f151abc6b674167f221d6c9f9848efd537`
- Status: `failure_reasons=[]`, fixture accepted by `tests/test_lmcache_live_fixtures.py`

### Packet F / F1 cache_salt + IsolatedLRU + lookup-hash

- Modal run: not recovered from stalled RepoPrompt session or Modal volume metadata
- Remote artifact: `lmcache-mp-lab:/packet-f/20260509T084753Z`
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/packet-f/20260509T084753Z`
- Fixture: `tests/fixtures/lmcache_live/packet_f/`
- Metrics: `cache_salt_values=[tenant-0, tenant-1]`, `cache_salt_cardinality=2`, `lookup_requested=45568/34816`, `lookup_hit=24064/22016`, `lookup_hash.row_count=24`, `l1_memory_usage_bytes=5.47356672e+09`
- Launch proof: `lmcache server --eviction-policy IsolatedLRU --lookup-hash-log-dir ... --metrics-sample-rate 1.0`
- Status: `failure_reasons=[]`, fixture accepted by `tests/test_lmcache_live_fixtures.py`

## Gates run after import

```bash
uv run pytest tests/test_lmcache_live_fixtures.py -q
# 3 passed

uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
# 28 passed

uv run pytest tests/test_observability_coverage.py -q
# 21 passed
```

## Score movement

Touchdown SSoT `docs/sdlc/195-2026-05-07-lmcache-vllm-inferguard-100-coverage-ssot.md` moves from 80/100 to 92/100 because E1, E2, and F1 are all accepted live fixtures.

Remaining gaps: G1 diagnostic calibration, H1/H2/H3 embedded/advanced live validation, and I1 release readiness.
