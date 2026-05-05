# CLI reference

This page is generated from the v0.7.1 Typer help output and curated with operator notes. Use it with:

```bash
inferguard --help
inferguard <command> --help
inferguard <group> <subcommand> --help
```

From a source checkout, use:

```bash
PYTHONPATH=src python3 -m inferguard.cli --help
```

## High-level workflow

1. `preflight` and/or `simulate-gpu` to prove the local flow.
2. `launch-engine` or an externally managed vLLM/SGLang/Dynamo/LMCache endpoint.
3. `request-profile` to produce per-request evidence.
4. `collect-metrics` to produce engine and GPU timelines.
5. `validate-completed` to decide whether the run can be published.
6. `diagnose-bottleneck`, `classify-failures`, `find-cliffs`, `compute-cost`, and `report-completed` for operator analysis.

## Exit-code conventions

| Code | Typical meaning |
|---:|---|
| `0` | Command succeeded or report was written without a failing threshold. |
| `1` | Strict validation/reporting gate did not pass. |
| `2` | Findings crossed a configured threshold, or all benchmark requests failed. |
| `3` | Input, parsing, endpoint, or artifact-writing failure. |

Check each command's stdout summary and generated JSON for exact status.

## `inferguard`

```text
Usage: inferguard [OPTIONS] COMMAND [ARGS]...                                                                                                                                                                                    
                                                                                                                                                                                                                                                
 InferGuard — read-only disaggregated-serving diagnostics.                                                                                                                                                                                      
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --version          Print version and exit.                                                                                                                                                                                                   │
│ --help             Show this message and exit.                                                                                                                                                                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ preflight            Run read-only launch compatibility checks before a benchmark.                                                                                                                                                           │
│ analyze              Analyze an existing result directory without launching benchmarks.                                                                                                                                                      │
│ emit-bundle          Emit a deployment bundle from a router verdict.                                                                                                                                                                         │
│ validate-completed   Validate completed runs before any publishability or operator claim.                                                                                                                                                    │
│ request-profile      Profile per-request TTFT, TPOT, E2E latency, and failures.                                                                                                                                                              │
│ collect-metrics      Collect normalized engine and GPU metric timelines for live evidence.                                                                                                                                                   │
│ ingest-agentx        Convert AgentX result CSV outputs into canonical InferGuard schemas.                                                                                                                                                    │
│ agentx-ingest        Convert AgentX result CSV outputs into canonical InferGuard schemas.                                                                                                                                                    │
│ launch-engine        Launch or validate a vLLM, SGLang, LMCache, or Dynamo-SGLang engine.                                                                                                                                                    │
│ diagnose-bottleneck  Diagnose one completed job into a bottleneck verdict.                                                                                                                                                                   │
│ classify-failures    Classify failed job evidence into operator-actionable failure classes.                                                                                                                                                  │
│ report-completed     Build a refusal-gated operator recommendation from completed evidence.                                                                                                                                                  │
│ compute-cost         Compute cost-per-useful-task and safe concurrency from run evidence.                                                                                                                                                    │
│ find-cliffs          Find capacity cliffs across completed sweep evidence.                                                                                                                                                                   │
│ simulate-gpu         Generate synthetic GPU/Slurm artifacts for local bundle smoke testing.                                                                                                                                                  │
│ serve-mimic          Serve a tiny fake OpenAI-compatible endpoint for synthetic smoke tests.                                                                                                                                                 │
│ disagg               Disaggregated serving diagnostics.                                                                                                                                                                                      │
│ bench                OpenAI-compatible endpoint benchmarks.                                                                                                                                                                                  │
│ profile              Live endpoint profiler for existing /metrics traffic.                                                                                                                                                                   │
│ agent                Agent trace harness commands.                                                                                                                                                                                           │
│ daemon               Local harness daemon sidecar.                                                                                                                                                                                           │
│ telemetry            Local-only telemetry consent and payload audit commands.                                                                                                                                                                │
│ workload             Pre-flight workload fingerprinting.                                                                                                                                                                                     │
│ router               Rule-based execution-path routing.                                                                                                                                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard preflight`

```text
Usage: inferguard preflight [OPTIONS]                                                                                                                                                                                            
                                                                                                                                                                                                                                                
 Run read-only launch compatibility checks before a benchmark.                                                                                                                                                                                  
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --model                                                                      TEXT     Model family or HF id for compatibility checks. [default: deepseek-ai/DeepSeek-V4-Pro]                                                                 │
│ --engine                                                                     TEXT     Engine hint: vllm, sglang, dynamo, lmcache, llm-d, or auto. [default: vllm]                                                                            │
│ --kv-offloading-backend                                                      TEXT     KV offload backend, e.g. native when OFFLOADING=cpu.                                                                                                   │
│ --disable-hybrid-kv-cache-manager    --no-disable-hybrid-kv-cache-manager             Whether the serving launch disables the hybrid KV cache manager. [default: no-disable-hybrid-kv-cache-manager]                                         │
│ --config                                                                     PATH     Optional config.json/run config containing topology/preflight fields.                                                                                  │
│ --detect-tokenizer-mismatch                                                           Probe client/server tokenizer-count drift before rollout.                                                                                              │
│ --endpoint                                                                   TEXT     Optional OpenAI-compatible /v1/chat/completions endpoint for tokenizer probe.                                                                          │
│ --sample-text                                                                TEXT     Known text sent for tokenizer-mismatch probing. [default: Hello world                                                                                  │
│                                                                                                                                       This is a test of tokenization.]                                                                       │
│ --client-tokenizer                                                           TEXT     Client tokenizer label/version used for preflight evidence. [default: inferguard-estimator]                                                            │
│ --server-tokenizer                                                           TEXT     Optional server tokenizer label/version used for preflight evidence.                                                                                   │
│ --client-token-count                                                         INTEGER  Optional explicit client token count for tokenizer probe/testing.                                                                                      │
│ --json                                                                                Emit machine-readable JSON.                                                                                                                            │
│ --help                                                                                Show this message and exit.                                                                                                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard analyze`

```text
Usage: inferguard analyze [OPTIONS] RESULTS_DIR                                                                                                                                                                                  
                                                                                                                                                                                                                                                
 Analyze an existing result directory without launching benchmarks.                                                                                                                                                                             
                                                                                                                                                                                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    results_dir      PATH  Directory containing benchmark artifacts. [required]                                                                                                                                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --output-dir                                  PATH     Destination for generated reports.                                                                                                                                                    │
│ --format                                      TEXT     Output format: json, md, or both. [default: both]                                                                                                                                     │
│ --fail-on                                     TEXT     Exit threshold: never, warning, or critical. [default: critical]                                                                                                                      │
│ --strict               --best-effort                   Fail on missing required artifacts. [default: best-effort]                                                                                                                            │
│ --timeline-glob                               TEXT     Discovery pattern for timeline JSONL files. [default: **/inferguard_timeline.jsonl]                                                                                                   │
│ --cost-per-gpu-hour                           FLOAT    GPU-hour cost for cost-per-task accounting.                                                                                                                                           │
│ --gpus                                        INTEGER  GPU count for cost-per-task accounting.                                                                                                                                               │
│ --operator-brief       --no-operator-brief             Emit operator_brief.{json,md}; defaults on when --gpus is provided.                                                                                                                   │
│ --cost-currency                               TEXT     Currency label for cost output. [default: USD]                                                                                                                                        │
│ --plots                                                After report writes, render SVG plots into <output-dir>/plots/.                                                                                                                       │
│ --emit-agentx-shape                           PATH     Write per-cell agg_*.json files in AgentX/InferenceX shape.                                                                                                                           │
│ --json                                                 Also print the generated JSON report to stdout.                                                                                                                                       │
│ --help                                                 Show this message and exit.                                                                                                                                                           │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard emit-bundle`

```text
Usage: inferguard emit-bundle [OPTIONS] VERDICT                                                                                                                                                                                  
                                                                                                                                                                                                                                                
 Emit a deployment bundle from a router verdict.                                                                                                                                                                                                
                                                                                                                                                                                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    verdict      PATH  Router verdict JSON from `inferguard router classify`. [required]                                                                                                                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --output        PATH  Destination bundle directory. [required]                                                                                                                                                                            │
│    --target        TEXT  Bundle target. Currently: slurm. [default: slurm]                                                                                                                                                                   │
│    --json                Print bundle manifest JSON to stdout.                                                                                                                                                                               │
│    --help                Show this message and exit.                                                                                                                                                                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard validate-completed`

```text
Usage: inferguard validate-completed [OPTIONS]                                                                                                                                                                                   
                                                                                                                                                                                                                                                
 Validate completed runs before any publishability or operator claim.                                                                                                                                                                           
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --results-root             PATH  Run directory to validate. [required]                                                                                                                                                                    │
│    --matrix-plan              PATH  Override matrix_plan.json location.                                                                                                                                                                      │
│    --artifact-contract        PATH  Override expected_artifact_contract.json location.                                                                                                                                                       │
│    --output-dir               PATH  Output directory for validation artifacts.                                                                                                                                                               │
│    --strict                         Return non-zero unless the run is live_complete.                                                                                                                                                         │
│    --label-overrides          PATH  JSON {claim_id: claim_status} for human-reviewed downgrades.                                                                                                                                             │
│    --json-only                      Skip markdown rendering.                                                                                                                                                                                 │
│    --help                           Show this message and exit.                                                                                                                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard request-profile`

```text
Usage: inferguard request-profile [OPTIONS]                                                                                                                                                                                      
                                                                                                                                                                                                                                                
 Profile per-request TTFT, TPOT, E2E latency, and failures.                                                                                                                                                                                     
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --output-dir                    PATH     Output directory for request-profile artifacts. [required]                                                                                                                                       │
│ *  --endpoint                      TEXT     OpenAI-compatible chat-completions endpoint. [required]                                                                                                                                          │
│ *  --model                         TEXT     Model name sent in profile requests. [required]                                                                                                                                                  │
│ *  --input-jsonl                   PATH     JSONL request/profile input file. [required]                                                                                                                                                     │
│    --concurrency                   TEXT     Closed-loop concurrency level.                                                                                                                                                                   │
│    --timeout-seconds               FLOAT    HTTP timeout per request. [default: 300.0]                                                                                                                                                       │
│    --arrival-mode                  TEXT     Arrival mode: closed_loop or poisson.                                                                                                                                                            │
│    --rate-rps                      FLOAT    Poisson arrival rate in requests per second.                                                                                                                                                     │
│    --max-requests                  INTEGER  Maximum request rows to issue.                                                                                                                                                                   │
│    --api-key                       TEXT     Optional bearer token for the endpoint.                                                                                                                                                          │
│    --stream                                 Use streaming chat completions.                                                                                                                                                                  │
│    --include-usage                          Request OpenAI stream usage when streaming.                                                                                                                                                      │
│    --continuous-usage-stats                 Request continuous usage stats when supported.                                                                                                                                                   │
│    --workload-label                TEXT     Workload label stamped into artifacts.                                                                                                                                                           │
│    --job-id                        TEXT     Optional job id stamped into artifacts.                                                                                                                                                          │
│    --seed                          INTEGER  Deterministic scheduler seed. [default: 0]                                                                                                                                                       │
│    --engine                        TEXT     Engine label stamped into artifacts.                                                                                                                                                             │
│    --model-profile                 TEXT     Model architecture/profile label.                                                                                                                                                                │
│    --help                                   Show this message and exit.                                                                                                                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard collect-metrics`

```text
Usage: inferguard collect-metrics [OPTIONS]                                                                                                                                                                                      
                                                                                                                                                                                                                                                
 Collect normalized engine and GPU metric timelines for live evidence.                                                                                                                                                                          
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --output-dir                   PATH     Output directory for metrics artifacts. [required]                                                                                                                                                │
│ *  --engine                       TEXT     Engine: vllm, sglang, lmcache, or dynamo-sglang. [required]                                                                                                                                       │
│ *  --engine-metrics-url           TEXT     Serving-engine Prometheus metrics URL. [required]                                                                                                                                                 │
│ *  --dcgm-metrics-url             TEXT     DCGM exporter Prometheus metrics URL. [required]                                                                                                                                                  │
│ *  --duration-seconds             INTEGER  Collection duration in seconds. [required]                                                                                                                                                        │
│    --interval-seconds             FLOAT    Engine scrape interval in seconds. [default: 1.0]                                                                                                                                                 │
│    --dcgm-interval-seconds        FLOAT    DCGM timestamp window in seconds. [default: 5.0]                                                                                                                                                  │
│    --lmcache-metrics-url          TEXT     Optional LMCache metrics URL.                                                                                                                                                                     │
│    --label-job-id                 TEXT     Job id label for normalized metrics.                                                                                                                                                              │
│    --label-engine-version         TEXT     Engine version label for normalized metrics.                                                                                                                                                      │
│    --label-hardware               TEXT     Hardware label for normalized metrics.                                                                                                                                                            │
│    --keep-raw-samples                      Keep raw Prometheus samples alongside normalized timelines.                                                                                                                                       │
│    --help                                  Show this message and exit.                                                                                                                                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard ingest-agentx`

```text
Usage: inferguard ingest-agentx [OPTIONS]                                                                                                                                                                                        
                                                                                                                                                                                                                                                
 Convert AgentX result CSV outputs into canonical InferGuard schemas.                                                                                                                                                                           
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --output-dir                PATH  Output directory for canonical InferGuard artifacts. [required]                                                                                                                                         │
│    --agentx-results-dir        PATH  AgentX result directory containing metadata and CSV output.                                                                                                                                             │
│    --agentx-result             PATH  Single AgentX detailed result CSV.                                                                                                                                                                      │
│    --job-id                    TEXT  Optional job id stamped into artifacts.                                                                                                                                                                 │
│    --engine                    TEXT  Engine label stamped into artifacts.                                                                                                                                                                    │
│    --workload-label            TEXT  Workload label stamped into artifacts.                                                                                                                                                                  │
│    --model-profile             TEXT  Model architecture/profile label.                                                                                                                                                                       │
│    --model                     TEXT  Fallback model/profile label for single CSV ingest.                                                                                                                                                     │
│    --concurrency               TEXT  Concurrency label for single CSV ingest.                                                                                                                                                                │
│    --help                            Show this message and exit.                                                                                                                                                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard agentx-ingest`

```text
Usage: inferguard agentx-ingest [OPTIONS]                                                                                                                                                                                        
                                                                                                                                                                                                                                                
 Convert AgentX result CSV outputs into canonical InferGuard schemas.                                                                                                                                                                           
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --output-dir                PATH  Output directory for canonical InferGuard artifacts. [required]                                                                                                                                         │
│    --agentx-results-dir        PATH  AgentX result directory containing metadata and CSV output.                                                                                                                                             │
│    --agentx-result             PATH  Single AgentX detailed result CSV.                                                                                                                                                                      │
│    --job-id                    TEXT  Optional job id stamped into artifacts.                                                                                                                                                                 │
│    --engine                    TEXT  Engine label stamped into artifacts.                                                                                                                                                                    │
│    --workload-label            TEXT  Workload label stamped into artifacts.                                                                                                                                                                  │
│    --model-profile             TEXT  Model architecture/profile label.                                                                                                                                                                       │
│    --model                     TEXT  Fallback model/profile label for single CSV ingest.                                                                                                                                                     │
│    --concurrency               TEXT  Concurrency label for single CSV ingest.                                                                                                                                                                │
│    --help                            Show this message and exit.                                                                                                                                                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard launch-engine`

```text
Usage: inferguard launch-engine [OPTIONS]                                                                                                                                                                                        
                                                                                                                                                                                                                                                
 Launch or validate a vLLM, SGLang, LMCache, or Dynamo-SGLang engine.                                                                                                                                                                           
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --output-dir                         PATH     Output directory for launch artifacts. [required]                                                                                                                                           │
│ *  --engine                             TEXT     Engine: vllm, sglang, lmcache, or dynamo-sglang. [required]                                                                                                                                 │
│    --external-launch                             Validate an already-launched endpoint instead of spawning.                                                                                                                                  │
│    --endpoint-url,--endpoint            TEXT     Endpoint URL for external-launch or healthcheck.                                                                                                                                            │
│    --model-path                         TEXT     Model path or id passed to the serving engine.                                                                                                                                              │
│    --host                               TEXT     Engine bind host.                                                                                                                                                                           │
│    --port                               INTEGER  Engine bind port.                                                                                                                                                                           │
│    --tensor-parallel-size               INTEGER  Tensor parallel size. [default: 1]                                                                                                                                                          │
│    --pipeline-parallel-size             INTEGER  Pipeline parallel size. [default: 1]                                                                                                                                                        │
│    --data-parallel-size                 INTEGER  Data parallel size. [default: 1]                                                                                                                                                            │
│    --max-model-len                      INTEGER  Maximum model context length.                                                                                                                                                               │
│    --gpu-memory-utilization             FLOAT    vLLM GPU memory utilization. [default: 0.9]                                                                                                                                                 │
│    --mem-fraction-static                FLOAT    SGLang static memory fraction. [default: 0.9]                                                                                                                                               │
│    --enable-prefix-caching                       Enable prefix caching when supported.                                                                                                                                                       │
│    --enable-chunked-prefill                      Enable chunked prefill when supported.                                                                                                                                                      │
│    --chunked-prefill-size               INTEGER  Chunked prefill size.                                                                                                                                                                       │
│    --enable-cache-report                         Enable engine cache reporting flags.                                                                                                                                                        │
│    --enable-metrics                              Enable engine metrics flags.                                                                                                                                                                │
│    --kv-cache-dtype                     TEXT     KV cache dtype.                                                                                                                                                                             │
│    --quantization                       TEXT     Quantization mode.                                                                                                                                                                          │
│    --hardware                           TEXT     Hardware label for launch warnings.                                                                                                                                                         │
│    --kv-transfer-config                 TEXT     KV transfer configuration JSON/string.                                                                                                                                                      │
│    --healthcheck-timeout-seconds        INTEGER  Healthcheck timeout in seconds. [default: 600]                                                                                                                                              │
│    --healthcheck-prompt                 TEXT     Healthcheck canary prompt. [default: Hello, are you up?]                                                                                                                                    │
│    --canary-completion-tokens           INTEGER  Healthcheck canary completion tokens. [default: 16]                                                                                                                                         │
│    --extra-args                         TEXT     Extra engine CLI arguments.                                                                                                                                                                 │
│    --help                                        Show this message and exit.                                                                                                                                                                 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard diagnose-bottleneck`

```text
Usage: inferguard diagnose-bottleneck [OPTIONS]                                                                                                                                                                                  
                                                                                                                                                                                                                                                
 Diagnose one completed job into a bottleneck verdict.                                                                                                                                                                                          
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --job-dir                  PATH  Completed job directory to diagnose. [required]                                                                                                                                                          │
│    --validation-report        PATH  Optional validation report path.                                                                                                                                                                         │
│    --rule-config              PATH  Optional bottleneck rule config.                                                                                                                                                                         │
│    --output-dir               PATH  Output directory for diagnosis artifacts.                                                                                                                                                                │
│    --strict                         Return non-zero when evidence is insufficient.                                                                                                                                                           │
│    --json-only                      Skip markdown rendering.                                                                                                                                                                                 │
│    --help                           Show this message and exit.                                                                                                                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard classify-failures`

```text
Usage: inferguard classify-failures [OPTIONS]                                                                                                                                                                                    
                                                                                                                                                                                                                                                
 Classify failed job evidence into operator-actionable failure classes.                                                                                                                                                                         
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --job-dir             PATH     Completed or failed job directory to classify. [required]                                                                                                                                                  │
│    --regex-config        PATH     Optional regex classification config.                                                                                                                                                                      │
│    --max-failures        INTEGER  Maximum ranked failures to emit. [default: 20]                                                                                                                                                             │
│    --output-dir          PATH     Output directory for classification artifacts.                                                                                                                                                             │
│    --json-only                    Skip markdown rendering.                                                                                                                                                                                   │
│    --help                         Show this message and exit.                                                                                                                                                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard report-completed`

```text
Usage: inferguard report-completed [OPTIONS]                                                                                                                                                                                     
                                                                                                                                                                                                                                                
 Build a refusal-gated operator recommendation from completed evidence.                                                                                                                                                                         
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --results-root                   PATH     Completed run root to summarize. [required]                                                                                                                                                     │
│    --output-dir                     PATH     Output directory for recommendation artifacts.                                                                                                                                                  │
│    --strict                                  Return non-zero when recommendation evidence is insufficient.                                                                                                                                   │
│    --json-only                               Skip markdown rendering.                                                                                                                                                                        │
│    --cost-input                     PATH     JSON {"<sku>": <usd_per_gpu_hour>} for cost claims.                                                                                                                                             │
│    --workload-fingerprint           PATH     Optional WorkloadFingerprint JSON.                                                                                                                                                              │
│    --slo                            PATH     Optional SLO JSON.                                                                                                                                                                              │
│    --useful-task-definition         PATH     Optional useful-task criteria JSON.                                                                                                                                                             │
│    --useful-task-min-tokens         INTEGER  Minimum completion tokens for a useful task. [default: 1]                                                                                                                                       │
│    --useful-task-slo-ttft-ms        FLOAT    Useful-task TTFT SLO in milliseconds.                                                                                                                                                           │
│    --slo-ttft-ms                    FLOAT    TTFT SLO in milliseconds.                                                                                                                                                                       │
│    --slo-e2e-ms                     FLOAT    E2E latency SLO in milliseconds.                                                                                                                                                                │
│    --slo-success-rate               FLOAT    Success-rate SLO. [default: 0.95]                                                                                                                                                               │
│    --success-rate-floor             FLOAT    Compatibility alias for --slo-success-rate. [default: 0.95]                                                                                                                                     │
│    --help                                    Show this message and exit.                                                                                                                                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard compute-cost`

```text
Usage: inferguard compute-cost [OPTIONS]                                                                                                                                                                                         
                                                                                                                                                                                                                                                
 Compute cost-per-useful-task and safe concurrency from run evidence.                                                                                                                                                                           
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --results-root                   PATH     Completed run root to price. [required]                                                                                                                                                         │
│ *  --cost-input                     PATH     JSON {"<sku>": <usd_per_gpu_hour>} for cost claims. [required]                                                                                                                                  │
│    --output-dir                     PATH     Output directory for cost artifacts.                                                                                                                                                            │
│    --json-only                               Skip markdown rendering.                                                                                                                                                                        │
│    --slo                            PATH     Optional SLO JSON.                                                                                                                                                                              │
│    --useful-task-definition         PATH     Optional useful-task criteria JSON.                                                                                                                                                             │
│    --useful-task-min-tokens         INTEGER  Minimum completion tokens for a useful task. [default: 1]                                                                                                                                       │
│    --useful-task-slo-ttft-ms        FLOAT    Useful-task TTFT SLO in milliseconds.                                                                                                                                                           │
│    --slo-ttft-ms                    FLOAT    TTFT SLO in milliseconds.                                                                                                                                                                       │
│    --slo-e2e-ms                     FLOAT    E2E latency SLO in milliseconds.                                                                                                                                                                │
│    --slo-success-rate               FLOAT    Success-rate SLO. [default: 0.95]                                                                                                                                                               │
│    --success-rate-floor             FLOAT    Compatibility alias for --slo-success-rate. [default: 0.95]                                                                                                                                     │
│    --help                                    Show this message and exit.                                                                                                                                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard find-cliffs`

```text
Usage: inferguard find-cliffs [OPTIONS]                                                                                                                                                                                          
                                                                                                                                                                                                                                                
 Find capacity cliffs across completed sweep evidence.                                                                                                                                                                                          
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --results-root              PATH   Completed sweep root to analyze. [required]                                                                                                                                                            │
│    --output-dir                PATH   Output directory for capacity cliff artifacts.                                                                                                                                                         │
│    --cliffs                    TEXT   Comma-separated capacity cliff subset; default is all.                                                                                                                                                 │
│    --ttft-p99-floor-ms         FLOAT  TTFT p99 floor in milliseconds. [default: 1000.0]                                                                                                                                                      │
│    --success-rate-floor        FLOAT  Minimum acceptable success rate. [default: 0.95]                                                                                                                                                       │
│    --strict                           Return non-zero when any cliff lacks enough evidence.                                                                                                                                                  │
│    --json-only                        Skip markdown rendering.                                                                                                                                                                               │
│    --help                             Show this message and exit.                                                                                                                                                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard simulate-gpu`

```text
Usage: inferguard simulate-gpu [OPTIONS]                                                                                                                                                                                         
                                                                                                                                                                                                                                                
 Generate synthetic GPU/Slurm artifacts for local bundle smoke testing.                                                                                                                                                                         
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --results-root                            PATH     Run directory where matrix and synthetic GPU artifacts will be written.                                                                                                                   │
│ --plan                                    PATH     Existing matrix_plan.json to simulate. Preserves the legacy gmi_gpu_mimic.py flag.                                                                                                        │
│ --gpu-profiles,--gpu-mimic-profile        PATH     Optional GPU mimic profile catalog JSON.                                                                                                                                                  │
│ --provider                                TEXT     Provider profile. Currently only gmi. [default: gmi]                                                                                                                                      │
│ --cluster-profile                         PATH     Optional standalone JSON/YAML cluster profile.                                                                                                                                            │
│ --stage                                   TEXT     Matrix stage label. [default: single-node-smoke]                                                                                                                                          │
│ --max-jobs                                INTEGER  Maximum jobs to render into the synthetic matrix. [default: 1]                                                                                                                            │
│ --hardware                                TEXT     Hardware alias: h100, h200, b200, b300, gb200, or gb300. [default: b200]                                                                                                                  │
│ --engine                                  TEXT     Engine alias: vllm or sglang. [default: vllm]                                                                                                                                             │
│ --model-profile                           TEXT     Model profile alias, e.g. dsv4-pro or deepseek_v4_pro. [default: dsv4-pro]                                                                                                                │
│ --workload                                TEXT     Workload alias, e.g. long_context_chat. [default: long_context_chat]                                                                                                                      │
│ --context-lengths                         TEXT     Comma-separated context lengths. Defaults to 8192.                                                                                                                                        │
│ --concurrency                             TEXT     Comma-separated concurrency levels. Defaults to 1.                                                                                                                                        │
│ --arrival-mode                            TEXT     Arrival mode label. [default: closed_loop]                                                                                                                                                │
│ --help                                             Show this message and exit.                                                                                                                                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard serve-mimic`

```text
Usage: inferguard serve-mimic [OPTIONS]                                                                                                                                                                                          
                                                                                                                                                                                                                                                
 Serve a tiny fake OpenAI-compatible endpoint for synthetic smoke tests.                                                                                                                                                                        
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --host                 TEXT     Bind host for the synthetic endpoint. [default: 127.0.0.1]                                                                                                                                                   │
│ --port                 INTEGER  Bind port for the synthetic endpoint. [default: 8000]                                                                                                                                                        │
│ --model                TEXT     Model id returned by the OpenAI-compatible endpoint.                                                                                                                                                         │
│ --model-profile        TEXT     Fallback model id/profile label.                                                                                                                                                                             │
│ --help                          Show this message and exit.                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard disagg`

```text
Usage: inferguard disagg [OPTIONS] COMMAND [ARGS]...                                                                                                                                                                             
                                                                                                                                                                                                                                                
 Disaggregated serving diagnostics.                                                                                                                                                                                                             
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ status  Scrape prefill + decode (+ optional transfer) and print findings.                                                                                                                                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard disagg status`

```text
Usage: inferguard disagg status [OPTIONS]                                                                                                                                                                                        
                                                                                                                                                                                                                                                
 Scrape prefill + decode (+ optional transfer) and print findings.                                                                                                                                                                              
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --prefill         TEXT   Prefill endpoint base URL. [required]                                                                                                                                                                            │
│ *  --decode          TEXT   Decode endpoint base URL. [required]                                                                                                                                                                             │
│    --transfer        TEXT   Optional transfer-layer metrics URL.                                                                                                                                                                             │
│    --engine          TEXT   Engine hint: auto, vllm, sglang, dynamo, llm-d. [default: auto]                                                                                                                                                  │
│    --json                   Emit machine-readable JSON instead of a table.                                                                                                                                                                   │
│    --timeout         FLOAT  HTTP timeout per scrape (seconds). [default: 5.0]                                                                                                                                                                │
│    --help                   Show this message and exit.                                                                                                                                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard bench`

```text
Usage: inferguard bench [OPTIONS] COMMAND [ARGS]...                                                                                                                                                                              
                                                                                                                                                                                                                                                
 OpenAI-compatible endpoint benchmarks.                                                                                                                                                                                                         
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ replay         Replay trace JSONL records against a streaming chat-completions endpoint.                                                                                                                                                     │
│ upstream       Run vLLM/SGLang native benchmark CLIs and normalize their artifacts.                                                                                                                                                          │
│ compare        Compare two bench run directories for cross-engine parity.                                                                                                                                                                    │
│ agentx-replay  Run AgentX trace replay and convert detailed_results.csv to InferGuard artifacts.                                                                                                                                             │
│ kv-stress      Generate synthetic KVCast prompts and infer cache pressure from request shape.                                                                                                                                                │
│ kvcast         Run KVCast synthetic cache stress modes.                                                                                                                                                                                      │
│ cold-start     Capture first-60s cold-start ramp from endpoint readiness.                                                                                                                                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard bench replay`

```text
Usage: inferguard bench replay [OPTIONS]                                                                                                                                                                                         
                                                                                                                                                                                                                                                
 Replay trace JSONL records against a streaming chat-completions endpoint.                                                                                                                                                                      
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --endpoint                           TEXT     OpenAI-compatible /v1/chat/completions endpoint. [required]                                                                                                                                 │
│ *  --model                              TEXT     Model name sent in chat requests. [required]                                                                                                                                                │
│ *  --trace-dir                          PATH     Directory containing InferGuard trace JSONL files. [required]                                                                                                                               │
│    --concurrency                        TEXT     Comma-separated concurrency levels, e.g. 1,4,8,16,32. [default: 1,4,8,16,32]                                                                                                                │
│    --output-dir                         PATH     Directory for run.json/config.json/JSONL/summary/report. [default: inferguard_bench_replay]                                                                                                 │
│    --output-tokens                      INTEGER  Fallback max output tokens when trace does not specify expected_output_tokens. [default: 512]                                                                                               │
│    --timeout                            FLOAT    HTTP timeout per request in seconds. [default: 300.0]                                                                                                                                       │
│    --duration-seconds                   FLOAT    Run each concurrency level for this many seconds instead of one finite pass.                                                                                                                │
│    --warmup-seconds                     FLOAT    Exclude this many initial seconds per level from summary metrics. [default: 0.0]                                                                                                            │
│    --metrics-url                        TEXT     Optional engine metrics URL to scrape during the bench.                                                                                                                                     │
│    --metrics-interval                   FLOAT    Seconds between engine metrics scrapes. [default: 5.0]                                                                                                                                      │
│    --metrics-engine                     TEXT     Engine hint for metrics detection: auto, vllm, sglang, dynamo, llm-d. [default: auto]                                                                                                       │
│    --force                                       Allow writing into a non-empty output directory; known artifact files may be overwritten.                                                                                                   │
│    --redact-prompts                              Replace prompt content with <redacted> in requests.jsonl.                                                                                                                                   │
│    --track-cache-lineage                         Track request-level prefix-cache lineage scaffold.                                                                                                                                          │
│    --idle-active-mix-mode                        Alternate active request windows with idle windows for S-14 cost economics.                                                                                                                 │
│    --active-window-seconds              FLOAT    Active traffic window length for --idle-active-mix-mode. [default: 60.0]                                                                                                                    │
│    --idle-window-seconds                FLOAT    Idle traffic window length for --idle-active-mix-mode. [default: 30.0]                                                                                                                      │
│    --inject-giant-prefill-tokens        INTEGER  Inject one oversized prefill request; requires --allow-chaos.                                                                                                                               │
│    --allow-chaos                                 Allow chaos-mode replay injections.                                                                                                                                                         │
│    --canary-eval-set                    TEXT     Held-out eval set path or HuggingFace dataset id for canary quality scoring.                                                                                                                │
│    --tool-call-schema                   PATH     JSON schema describing expected tool-call response format.                                                                                                                                  │
│    --json                                        Print summary JSON to stdout.                                                                                                                                                               │
│    --help                                        Show this message and exit.                                                                                                                                                                 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard bench upstream`

```text
Usage: inferguard bench upstream [OPTIONS] ENGINE                                                                                                                                                                                
                                                                                                                                                                                                                                                
 Run vLLM/SGLang native benchmark CLIs and normalize their artifacts.                                                                                                                                                                           
                                                                                                                                                                                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    engine      TEXT  Upstream engine to run: vllm or sglang. [required]                                                                                                                                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --profile                                        TEXT     Profile: vLLM random|sharegpt|prefix-repetition|sonnet; SGLang random. [required]                                                                                               │
│ *  --model                                          TEXT     Model name passed to the upstream bench. [required]                                                                                                                             │
│    --endpoint                                       TEXT     Engine endpoint base URL, e.g. http://localhost:8000. [default: http://localhost:8000]                                                                                          │
│    --num-prompts                                    INTEGER  Number of prompts passed to the upstream bench. [default: 100]                                                                                                                  │
│    --request-rate                                   FLOAT    Optional upstream request-rate limit.                                                                                                                                           │
│    --dataset-path                                   PATH     Optional upstream dataset path for dataset-backed profiles.                                                                                                                     │
│    --output-dir                                     PATH     Directory for run/config/requests/metrics/summary artifacts. [default: inferguard_bench_upstream]                                                                               │
│    --timeout                                        FLOAT    Subprocess timeout in seconds. [default: 300.0]                                                                                                                                 │
│    --enable-radix-cache    --disable-radix-cache             Set SGLANG_ENABLE_RADIX_CACHE=1/0 for SGLang upstream runs.                                                                                                                     │
│    --force                                                   Allow writing into a non-empty output directory.                                                                                                                                │
│    --json                                                    Print summary JSON to stdout.                                                                                                                                                   │
│    --help                                                    Show this message and exit.                                                                                                                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard bench compare`

```text
Usage: inferguard bench compare [OPTIONS] RUN_A_DIR RUN_B_DIR                                                                                                                                                                    
                                                                                                                                                                                                                                                
 Compare two bench run directories for cross-engine parity.                                                                                                                                                                                     
                                                                                                                                                                                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    run_a_dir      PATH  First InferGuard bench run directory. [required]                                                                                                                                                                   │
│ *    run_b_dir      PATH  Second InferGuard bench run directory. [required]                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --output-dir                  PATH     Directory for compare.json and compare.md. [default: inferguard_bench_compare]                                                                                                                        │
│ --label-a                     TEXT     Display label for the first run, e.g. vllm.                                                                                                                                                           │
│ --label-b                     TEXT     Display label for the second run, e.g. sglang.                                                                                                                                                        │
│ --min-identity-overlap        FLOAT    Required trace_id+turn_index overlap ratio; must be > this value. [default: 0.5]                                                                                                                      │
│ --strict-identity                      Fail instead of warning when trace identity overlap is too low.                                                                                                                                       │
│ --cost-per-gpu-hour           FLOAT    Optional GPU-hour cost for cost-per-task deltas.                                                                                                                                                      │
│ --gpus                        INTEGER  GPU count for cost-per-task deltas.                                                                                                                                                                   │
│ --blue-green                           Treat run A as blue/baseline and run B as green/candidate; emit rollout p99 regression findings.                                                                                                      │
│ --force                                Allow overwriting compare artifacts in a non-empty output directory.                                                                                                                                  │
│ --json                                 Print compare JSON to stdout.                                                                                                                                                                         │
│ --help                                 Show this message and exit.                                                                                                                                                                           │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard bench agentx-replay`

```text
Usage: inferguard bench agentx-replay [OPTIONS]                                                                                                                                                                                  
                                                                                                                                                                                                                                                
 Run AgentX trace replay and convert detailed_results.csv to InferGuard artifacts.                                                                                                                                                              
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --endpoint                   TEXT     OpenAI-compatible API endpoint base URL. [required]                                                                                                                                                 │
│ *  --model                      TEXT     Model label for InferGuard artifacts. [required]                                                                                                                                                    │
│ *  --trace-source               TEXT     Hugging Face dataset name or local trace directory. [required]                                                                                                                                      │
│    --concurrency                INTEGER  AgentX concurrent users; used for start-users and max-users. [default: 1]                                                                                                                           │
│    --duration-seconds           INTEGER  AgentX replay duration in seconds; warns below 900s/15min. [default: 1800]                                                                                                                          │
│    --output-dir                 PATH     Directory for InferGuard AgentX replay artifacts. [default: inferguard_bench_agentx_replay]                                                                                                         │
│    --tester-path                PATH     Path to trace_replay_tester.py or a kv-cache-tester checkout.                                                                                                                                       │
│    --allow-network-clone                 Clone kv-cache-tester into ~/.cache/inferguard/agentx-tester if missing.                                                                                                                            │
│    --json                                Print summary JSON to stdout.                                                                                                                                                                       │
│    --help                                Show this message and exit.                                                                                                                                                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard bench kv-stress`

```text
Usage: inferguard bench kv-stress [OPTIONS]                                                                                                                                                                                      
                                                                                                                                                                                                                                                
 Generate synthetic KVCast prompts and infer cache pressure from request shape.                                                                                                                                                                 
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --endpoint                  TEXT     OpenAI-compatible /v1/chat/completions endpoint. [required]                                                                                                                                          │
│ *  --model                     TEXT     Model name sent in chat requests. [required]                                                                                                                                                         │
│    --context-lengths           TEXT     Comma-separated approximate input token targets. [default: 8192,32768,65536,131072,524288,1048576]                                                                                                   │
│    --concurrency               TEXT     Comma-separated concurrency levels, e.g. 1,4,8,16. [default: 1,4,8,16]                                                                                                                               │
│    --output-tokens             INTEGER  Max streamed output tokens per request. [default: 512]                                                                                                                                               │
│    --mode                      TEXT     KVCast mode: cold-pressure, prefix-reuse, mixed-agent, eviction-probe, or fragmentation-probe. [default: cold-pressure]                                                                              │
│    --requests-per-level        INTEGER  Synthetic requests generated per context length. [default: 4]                                                                                                                                        │
│    --output-dir                PATH     Directory for run.json/config.json/JSONL/summary/report. [default: inferguard_bench_kv_stress]                                                                                                       │
│    --timeout                   FLOAT    HTTP timeout per request in seconds. [default: 300.0]                                                                                                                                                │
│    --duration-seconds          FLOAT    Run each concurrency level for this many seconds instead of one finite pass.                                                                                                                         │
│    --warmup-seconds            FLOAT    Exclude this many initial seconds per level from summary metrics. [default: 0.0]                                                                                                                     │
│    --metrics-url               TEXT     Optional engine metrics URL to scrape during the bench.                                                                                                                                              │
│    --metrics-interval          FLOAT    Seconds between engine metrics scrapes. [default: 5.0]                                                                                                                                               │
│    --metrics-engine            TEXT     Engine hint for metrics detection: auto, vllm, sglang, dynamo, llm-d. [default: auto]                                                                                                                │
│    --force                              Allow writing into a non-empty output directory; known artifact files may be overwritten.                                                                                                            │
│    --redact-prompts                     Replace prompt content with <redacted> in requests.jsonl.                                                                                                                                            │
│    --json                               Print summary JSON to stdout.                                                                                                                                                                        │
│    --help                               Show this message and exit.                                                                                                                                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard bench kvcast`

```text
Usage: inferguard bench kvcast [OPTIONS]                                                                                                                                                                                         
                                                                                                                                                                                                                                                
 Run KVCast synthetic cache stress modes.                                                                                                                                                                                                       
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --endpoint                          TEXT     OpenAI-compatible /v1/chat/completions endpoint. [required]                                                                                                                                  │
│ *  --model                             TEXT     Model name sent in chat requests. [required]                                                                                                                                                 │
│    --context-lengths                   TEXT     Comma-separated approximate input token targets. [default: 8192,32768,65536,131072,524288,1048576]                                                                                           │
│    --concurrency                       TEXT     Comma-separated concurrency levels, e.g. 1,4,8,16. [default: 1,4,8,16]                                                                                                                       │
│    --mode                              TEXT     KVCast mode: cold-pressure, prefix-reuse, mixed-agent, eviction-probe, fragmentation-probe, multi-tenant-storm, or retry-storm. [default: cold-pressure]                                     │
│    --output-tokens                     INTEGER  Max streamed output tokens per request. [default: 512]                                                                                                                                       │
│    --requests-per-level                INTEGER  Synthetic requests generated per context length. [default: 4]                                                                                                                                │
│    --output-dir                        PATH     Directory for run.json/config.json/JSONL/summary/report. [default: inferguard_bench_kvcast]                                                                                                  │
│    --timeout                           FLOAT    HTTP timeout per request in seconds. [default: 300.0]                                                                                                                                        │
│    --duration-seconds                  FLOAT    Run each concurrency level for this many seconds instead of one finite pass.                                                                                                                 │
│    --warmup-seconds                    FLOAT    Exclude this many initial seconds per level from summary metrics. [default: 0.0]                                                                                                             │
│    --arrival-mode                      TEXT     Arrival scheduler: steady or poisson. [default: steady]                                                                                                                                      │
│    --arrival-rate-rps                  FLOAT    Mean request arrivals per second for --arrival-mode poisson.                                                                                                                                 │
│    --metrics-url                       TEXT     Optional engine metrics URL to scrape during the bench.                                                                                                                                      │
│    --metrics-interval                  FLOAT    Seconds between engine metrics scrapes. [default: 5.0]                                                                                                                                       │
│    --metrics-engine                    TEXT     Engine hint for metrics detection: auto, vllm, sglang, dynamo, llm-d. [default: auto]                                                                                                        │
│    --force                                      Allow writing into a non-empty output directory; known artifact files may be overwritten.                                                                                                    │
│    --redact-prompts                             Replace prompt content with <redacted> in requests.jsonl.                                                                                                                                    │
│    --customers                         INTEGER  Customer count for --mode multi-tenant-storm. [default: 1]                                                                                                                                   │
│    --sla-tiers                         TEXT     Comma-separated SLA tier policies, e.g. premium=p99<2s,standard=p99<5s.                                                                                                                      │
│    --track-cache-lineage                        Track request-level prefix-cache lineage scaffold.                                                                                                                                           │
│    --burst-multiplier                  FLOAT    Retry-storm burst QPS multiplier over --baseline-rps. [default: 50.0]                                                                                                                        │
│    --burst-window-seconds              FLOAT    Retry-storm burst duration in seconds. [default: 30.0]                                                                                                                                       │
│    --baseline-rps                      FLOAT    Retry-storm baseline request rate before/after burst. [default: 4.0]                                                                                                                         │
│    --inject-crash-after-seconds        FLOAT    Test-only crash injection delay; requires --allow-chaos.                                                                                                                                     │
│    --allow-chaos                                Allow test-only crash injection scaffolding.                                                                                                                                                 │
│    --json                                       Print summary JSON to stdout.                                                                                                                                                                │
│    --help                                       Show this message and exit.                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard bench cold-start`

```text
Usage: inferguard bench cold-start [OPTIONS]                                                                                                                                                                                     
                                                                                                                                                                                                                                                
 Capture first-60s cold-start ramp from endpoint readiness.                                                                                                                                                                                     
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --endpoint                TEXT     OpenAI-compatible /v1/chat/completions endpoint. [required]                                                                                                                                            │
│ *  --model                   TEXT     Model name sent in chat requests. [required]                                                                                                                                                           │
│    --trace-dir               PATH     Optional InferGuard trace JSONL directory.                                                                                                                                                             │
│    --output-dir              PATH     Directory for cold-start artifacts. [default: inferguard_bench_cold_start]                                                                                                                             │
│    --capture-seconds         FLOAT    Cold-start capture window from process spawn/readiness. [default: 60.0]                                                                                                                                │
│    --context-lengths         TEXT     Synthetic context lengths when --trace-dir is omitted. [default: 1024]                                                                                                                                 │
│    --concurrency             TEXT     Comma-separated concurrency levels. [default: 1]                                                                                                                                                       │
│    --output-tokens           INTEGER  Max streamed output tokens per request. [default: 64]                                                                                                                                                  │
│    --metrics-url             TEXT     Optional engine metrics URL to scrape during cold start.                                                                                                                                               │
│    --metrics-interval        FLOAT    Seconds between engine metrics scrapes. [default: 5.0]                                                                                                                                                 │
│    --metrics-engine          TEXT     Engine hint for metrics detection: auto, vllm, sglang, dynamo, llm-d. [default: auto]                                                                                                                  │
│    --force                            Allow writing into a non-empty output directory.                                                                                                                                                       │
│    --json                             Print summary JSON to stdout.                                                                                                                                                                          │
│    --help                             Show this message and exit.                                                                                                                                                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard profile`

```text
Usage: inferguard profile [OPTIONS] COMMAND [ARGS]...                                                                                                                                                                            
                                                                                                                                                                                                                                                
 Live endpoint profiler for existing /metrics traffic.                                                                                                                                                                                          
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ live   Observe an existing endpoint without generating traffic.                                                                                                                                                                              │
│ retro  Summarize an existing profile/timeline JSONL file.                                                                                                                                                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard profile live`

```text
Usage: inferguard profile live [OPTIONS]                                                                                                                                                                                         
                                                                                                                                                                                                                                                
 Observe an existing endpoint without generating traffic.                                                                                                                                                                                       
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --endpoint          TEXT   Serving endpoint base URL or /metrics URL to observe. [required]                                                                                                                                               │
│    --duration          FLOAT  Sampling window in seconds. [default: 60.0]                                                                                                                                                                    │
│    --interval          FLOAT  Seconds between /metrics scrapes. [default: 2.0]                                                                                                                                                               │
│    --engine            TEXT   Engine hint: auto, vllm, sglang, dynamo, lmcache, llm-d. [default: auto]                                                                                                                                       │
│    --output-dir        PATH   Directory for profile.jsonl/profile_summary.json/profile.md. [default: inferguard_profile_live]                                                                                                                │
│    --format            TEXT   Streaming output format: table or json. [default: table]                                                                                                                                                       │
│    --timeout           FLOAT  HTTP timeout per metrics scrape (seconds). [default: 5.0]                                                                                                                                                      │
│    --help                     Show this message and exit.                                                                                                                                                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard profile retro`

```text
Usage: inferguard profile retro [OPTIONS] INPUT_PATH                                                                                                                                                                             
                                                                                                                                                                                                                                                
 Summarize an existing profile/timeline JSONL file.                                                                                                                                                                                             
                                                                                                                                                                                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    input_path      PATH  Existing profile.jsonl or metrics timeline JSONL file. [required]                                                                                                                                                 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --output-dir        PATH  Directory for profile_summary.json/profile.md. [default: inferguard_profile_retro]                                                                                                                                 │
│ --json                    Print summary JSON to stdout.                                                                                                                                                                                      │
│ --help                    Show this message and exit.                                                                                                                                                                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard agent`

```text
Usage: inferguard agent [OPTIONS] COMMAND [ARGS]...                                                                                                                                                                              
                                                                                                                                                                                                                                                
 Agent trace harness commands.                                                                                                                                                                                                                  
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ trace  Wrap a subprocess and emit a local ``agent-trace/v1`` JSONL file.                                                                                                                                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard agent trace`

```text
Usage: inferguard agent trace [OPTIONS]                                                                                                                                                                                          
                                                                                                                                                                                                                                                
 Wrap a subprocess and emit a local ``agent-trace/v1`` JSONL file.                                                                                                                                                                              
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --framework                            TEXT  Agent framework: langgraph, crewai, autogen, claude_code, cursor_sdk, raw_openai. [default: raw_openai]                                                                                         │
│ --output-dir                           PATH  Directory for agent-trace/v1 JSONL output. [default: inferguard_agent_trace]                                                                                                                    │
│ --save-prompts    --no-save-prompts          Write prompt text to prompts-local.jsonl for local debugging only. [default: no-save-prompts]                                                                                                   │
│ --rig-label                            TEXT  Optional rig label: h100, h200, b200, gb200, auto.                                                                                                                                              │
│ --help                                       Show this message and exit.                                                                                                                                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard daemon`

```text
Usage: inferguard daemon [OPTIONS] COMMAND [ARGS]...                                                                                                                                                                             
                                                                                                                                                                                                                                                
 Local harness daemon sidecar.                                                                                                                                                                                                                  
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ start   Start the foreground harness daemon sidecar.                                                                                                                                                                                         │
│ stop    Stop the recorded foreground daemon process when possible.                                                                                                                                                                           │
│ status  Print daemon state and a one-shot local snapshot.                                                                                                                                                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard daemon start`

```text
Usage: inferguard daemon start [OPTIONS]                                                                                                                                                                                         
                                                                                                                                                                                                                                                
 Start the foreground harness daemon sidecar.                                                                                                                                                                                                   
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --port                                INTEGER  Loopback Prometheus metrics port. [default: 9466]                                                                                                                                             │
│ --host                                TEXT     Metrics bind host; cluster leaders default to 0.0.0.0.                                                                                                                                        │
│ --watch-dir                           PATH     Directory containing agent-trace/v1 JSONL files.                                                                                                                                              │
│ --prometheus       --no-prometheus             Expose loopback /metrics endpoint. [default: prometheus]                                                                                                                                      │
│ --leader                                       Run as a cluster fan-in leader and merge follower ranks.                                                                                                                                      │
│ --follower                            TEXT     Run as a cluster follower and POST snapshots to LEADER_URL.                                                                                                                                   │
│ --cluster-token                       PATH     Path to operator-generated cluster bearer token.                                                                                                                                              │
│ --help                                         Show this message and exit.                                                                                                                                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard daemon stop`

```text
Usage: inferguard daemon stop [OPTIONS]                                                                                                                                                                                          
                                                                                                                                                                                                                                                
 Stop the recorded foreground daemon process when possible.                                                                                                                                                                                     
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --port                             INTEGER  Expected daemon port. [default: 9466]                                                                                                                                                            │
│ --watch-dir                        PATH     Expected watch directory.                                                                                                                                                                        │
│ --prometheus    --no-prometheus             Expected Prometheus state. [default: prometheus]                                                                                                                                                 │
│ --help                                      Show this message and exit.                                                                                                                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard daemon status`

```text
Usage: inferguard daemon status [OPTIONS]                                                                                                                                                                                        
                                                                                                                                                                                                                                                
 Print daemon state and a one-shot local snapshot.                                                                                                                                                                                              
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --port                             INTEGER  Daemon port to report. [default: 9466]                                                                                                                                                           │
│ --watch-dir                        PATH     Optionally load trace files before reporting status.                                                                                                                                             │
│ --prometheus    --no-prometheus             Prometheus endpoint expectation. [default: prometheus]                                                                                                                                           │
│ --help                                      Show this message and exit.                                                                                                                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard telemetry`

```text
Usage: inferguard telemetry [OPTIONS] COMMAND [ARGS]...                                                                                                                                                                          
                                                                                                                                                                                                                                                
 Local-only telemetry consent and payload audit commands.                                                                                                                                                                                       
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ status          Show local telemetry state without contacting the network.                                                                                                                                                                   │
│ enable          Enable local telemetry spooling after explicit consent.                                                                                                                                                                      │
│ disable         Disable telemetry, delete the consent token, and clear local state.                                                                                                                                                          │
│ log             Show recent local telemetry events and pending payload files.                                                                                                                                                                │
│ verify-payload  Render the exact local-only telemetry payload that would be uploaded.                                                                                                                                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard telemetry status`

```text
Usage: inferguard telemetry status [OPTIONS]                                                                                                                                                                                     
                                                                                                                                                                                                                                                
 Show local telemetry state without contacting the network.                                                                                                                                                                                     
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard telemetry enable`

```text
Usage: inferguard telemetry enable [OPTIONS]                                                                                                                                                                                     
                                                                                                                                                                                                                                                
 Enable local telemetry spooling after explicit consent.                                                                                                                                                                                        
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --consent-token        TEXT  Consent token issued out-of-band by Touchdown. [required]                                                                                                                                                    │
│    --help                       Show this message and exit.                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard telemetry disable`

```text
Usage: inferguard telemetry disable [OPTIONS]                                                                                                                                                                                    
                                                                                                                                                                                                                                                
 Disable telemetry, delete the consent token, and clear local state.                                                                                                                                                                            
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard telemetry log`

```text
Usage: inferguard telemetry log [OPTIONS]                                                                                                                                                                                        
                                                                                                                                                                                                                                                
 Show recent local telemetry events and pending payload files.                                                                                                                                                                                  
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --limit        INTEGER  Maximum recent events to show. [default: 50]                                                                                                                                                                         │
│ --help                  Show this message and exit.                                                                                                                                                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard telemetry verify-payload`

```text
Usage: inferguard telemetry verify-payload [OPTIONS] PATH                                                                                                                                                                        
                                                                                                                                                                                                                                                
 Render the exact local-only telemetry payload that would be uploaded.                                                                                                                                                                          
                                                                                                                                                                                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    path      PATH  Payload-pending JSON file or directory. [required]                                                                                                                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard workload`

```text
Usage: inferguard workload [OPTIONS] COMMAND [ARGS]...                                                                                                                                                                           
                                                                                                                                                                                                                                                
 Pre-flight workload fingerprinting.                                                                                                                                                                                                            
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ analyze  Generate a pre-flight workload fingerprint without launching benchmarks.                                                                                                                                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard workload analyze`

```text
Usage: inferguard workload analyze [OPTIONS] LOG_DIR                                                                                                                                                                             
                                                                                                                                                                                                                                                
 Generate a pre-flight workload fingerprint without launching benchmarks.                                                                                                                                                                       
                                                                                                                                                                                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    log_dir      PATH  Directory containing OpenAI-style JSONL logs. [required]                                                                                                                                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --format                     TEXT  Input format. Currently: openai-jsonl. [default: openai-jsonl]                                                                                                                                            │
│ --emit                       PATH  Write workload fingerprint JSON.                                                                                                                                                                          │
│ --emit-md                    PATH  Write human-readable workload report markdown.                                                                                                                                                            │
│ --privacy-class              TEXT  public, private, or regulated. [default: public]                                                                                                                                                          │
│ --latency-sensitivity        TEXT  tight, loose, or batch. [default: loose]                                                                                                                                                                  │
│ --json                             Print fingerprint JSON to stdout.                                                                                                                                                                         │
│ --help                             Show this message and exit.                                                                                                                                                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard router`

```text
Usage: inferguard router [OPTIONS] COMMAND [ARGS]...                                                                                                                                                                             
                                                                                                                                                                                                                                                
 Rule-based execution-path routing.                                                                                                                                                                                                             
                                                                                                                                                                                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ classify  Classify bottlenecks and rank execution paths from run artifacts.                                                                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## `inferguard router classify`

```text
Usage: inferguard router classify [OPTIONS] RUN_DIR                                                                                                                                                                              
                                                                                                                                                                                                                                                
 Classify bottlenecks and rank execution paths from run artifacts.                                                                                                                                                                              
                                                                                                                                                                                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    run_dir      PATH  Directory containing InferGuard or AgentX artifacts. [required]                                                                                                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --workload-fingerprint        PATH  Fingerprint JSON from `inferguard workload analyze`.                                                                                                                                                     │
│ --slo                         TEXT  Comma-separated SLOs, e.g. p95_ttft_ms=1000,error_rate_max=0.01.                                                                                                                                         │
│ --hardware-fleet              TEXT  Comma-separated hardware labels, e.g. h200,b200,gb200.                                                                                                                                                   │
│ --emit                        PATH  Write router verdict JSON.                                                                                                                                                                               │
│ --emit-md                     PATH  Write router verdict markdown.                                                                                                                                                                           │
│ --json                              Print verdict JSON to stdout.                                                                                                                                                                            │
│ --help                              Show this message and exit.                                                                                                                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```
