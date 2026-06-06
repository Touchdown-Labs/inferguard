# NVFP4 KV Diagnostics

NVFP4 KV cache stores each element as 4-bit e2m1 data plus an fp8 block scale per
16 elements: about 72 bytes per token per head against fp8's 128, a roughly 1.78x
capacity ceiling. The capacity win is large, but the quality impact is
model-dependent and there is no engine-native way to tell whether it is safe for a
given model. These three checks answer that.

The path matters by GPU generation:

- **SM100 (B200)** uses native trtllm-gen NVFP4-KV cubins; the Tensor Core
  dequantizes inside the MMA pipeline.
- **SM120 (RTX PRO 6000 / RTX 5090)** has no such cubins, so NVFP4 KV routes
  through FlashInfer's FA2 kernel, which dequantizes in registers. These checks
  target that SM120 path.

All checks are read-only and call only the endpoints you pass. No telemetry.

## Checks

### `inferguard nvfp4 sm120-compat`

Is the serving GPU on the SM120 FA2 NVFP4-KV path?

```bash
# Probe locally (uses torch if available):
inferguard nvfp4 sm120-compat

# Or pass the compute capability explicitly:
inferguard nvfp4 sm120-compat --cc 12.0
```

Verdicts: `qualified` (SM120), `needs_review` (SM100 / unknown), `not_qualified`
(other arch). Whether the FA2 backend and B2 de-swizzle are actually active is a
server-config fact that cannot be confirmed over HTTP, so that line is reported as
`not_proven`; confirm it in the server logs.

### `inferguard nvfp4 kv-capacity`

How much KV pool does NVFP4 buy vs fp8?

```bash
# Parse the NVFP4 server's /metrics and compare to a known fp8 baseline:
inferguard nvfp4 kv-capacity --endpoint http://localhost:8002 --fp8-tokens 1663988

# Or pass both token counts directly:
inferguard nvfp4 kv-capacity --nvfp4-tokens 2960263 --fp8-tokens 1663988
```

Passes when the ratio clears the worth-it threshold (`default` 1.4x). Token counts
are parsed from `vllm:num_gpu_blocks` x `block_size` when present.

### `inferguard nvfp4 quality`

Is NVFP4 quality acceptable for this model? Runs a battery against the NVFP4
endpoint, comparing to an fp8 reference.

```bash
# Two servers: one fp8 baseline, one NVFP4 candidate
vllm serve MODEL --kv-cache-dtype fp8   --port 8001 &
vllm serve MODEL --kv-cache-dtype nvfp4 --port 8002 &

inferguard nvfp4 quality \
    --model MODEL \
    --nvfp4-endpoint http://localhost:8002 \
    --fp8-endpoint   http://localhost:8001 \
    --profile default \
    --out ./nvfp4-report
```

Battery and thresholds (`--profile default | strict | relaxed`):

| Check | Metric | default pass |
|---|---|---|
| PPL regression | worst delta nats vs fp8 | < 0.05 |
| Greedy divergence | median first-divergence token | > 10 |
| Retrieval accuracy | needle-in-haystack vs fp8 | >= 0.95 ratio |
| Decode speed | tok/s vs fp8 | >= 0.85 ratio |

Capacity is gated by the `kv-capacity` check (>= 1.4x default).

## Exit codes

`0` qualified, `1` not qualified, `2` needs review. Use these to gate a deploy in
CI.

## Output

With `--out DIR`, each check writes `nvfp4_qualification.json` (schema
`inferguard-nvfp4-qualification/v1`) and `nvfp4_qualification.md`. Add `--json` to
print the JSON to stdout instead of the console summary.

## Background

Methodology and the SM120 vs B200 walkthrough live in the Touchdown Labs research
package `docs/research/49-2026-06-06-nvfp4-kv-sm120-qualification`.
