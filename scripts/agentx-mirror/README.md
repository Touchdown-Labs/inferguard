# AgentX mirror launchers

DSv4-specific GMI Cloud variants of the AgentX v0.2 launcher pattern from
`SemiAnalysisAI/InferenceX` PR #1258. These are PR-ready drop-ins for
`benchmarks/single_node/agentic/` in InferenceX. Full audit of PR #1258 and
our 6 extension gaps lives at `docs/inferguard/23-2026-05-02-agentx-v0.2-audit-and-our-extensions.md`.

They intentionally cannot run standalone from this InferGuard repository: each
launcher sources InferenceX's `benchmark_lib.sh` and expects AgentX helper
functions (`resolve_trace_source`, `install_agentic_deps`, `wait_for_server_ready`,
`build_replay_cmd`, `write_agentic_result_json`).

For direct GMI execution, use the maintained InferGuard launchers under:

```bash
oss/inferguard/scripts/launch_*_gmi.sh
```

Launcher coverage:

| File | Target |
|---|---|
| `dsv4_fp4_b200.sh` | DSv4-Pro FP4 on B200, vLLM v0.20 + `deep_gemm_mega_moe` |
| `dsv4_fp4_b300.sh` | DSv4-Pro FP4 on B300 with MTP config |
| `dsv4_fp4_gb200.sh` | DSv4-Pro FP4 GB200 P/D, Dynamo-vLLM nightly `1.2.0.dev20260426`, ARM image `v0.20.0-ubuntu2404` |
| `dsv4_fp8_h100.sh` | DSv4-Flash FP8 H100 retarget (DSv4-Pro does not fit on 8×H100-80G) |
| `dsv4_fp8_h200.sh` | DSv4-Pro FP8 H200, image `vllm/vllm-openai:deepseekv4-cu129` |

All launchers apply two fixes relative to PR #1258 reference launchers:
- `--disable-hybrid-kv-cache-manager` guard when `OFFLOADING=cpu` (HMA safety, from Cam Quilici)
- `--reasoning-parser deepseek_v4` dropped (vLLM parser missing `reasoning_start_str`/`reasoning_end_str`; produces 0 output tokens — documented failure in PR #1258 `AGENTIC_TEST_RESULTS.md`, fix tracked in InferenceX PR #1263)
