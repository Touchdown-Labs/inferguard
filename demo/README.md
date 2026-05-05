# inferguard demo

Offline Prometheus fixture server for testing `inferguard disagg status`
without a real GPU or network egress.

## Run two instances (prefill + decode) in two terminals

```bash
# Terminal 1 — prefill side (port 18000)
python -m inferguard.demo.mock_endpoint --role prefill --engine vllm --scenario prefill_pressure

# Terminal 2 — decode side (port 18001)
python -m inferguard.demo.mock_endpoint --role decode --engine vllm --scenario decode_pressure
```

## Drive inferguard at the fixtures

```bash
inferguard disagg status --prefill http://127.0.0.1:18000 --decode http://127.0.0.1:18001
```

## Available scenarios

| name | what it simulates |
|---|---|
| `healthy` | Normal operation, balanced load |
| `kv_pressure` | KV cache saturation with preemption |
| `transfer_errors` | Nonzero `kv_transfer_errors_total` |
| `stall` | Transfer counters flat with active requests |
| `decode_pressure` | Decode side overloaded vs prefill |
| `prefill_pressure` | Prefill side overloaded vs decode |

## SGLang variant

```bash
python -m inferguard.demo.mock_endpoint --engine sglang --role prefill --scenario kv_pressure
```
