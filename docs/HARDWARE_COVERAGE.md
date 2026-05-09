# Hardware coverage

InferGuard v0.7.1 ships documentation and templates for the DSv4 6-SKU capability matrix. The matrix covers:

- hardware: `H100`, `H200`, `B200`, `B300`, `GB200`, `GB300`;
- models: `dsv4-flash`, `dsv4-pro`;
- engines: `vllm`, `sglang`;
- workloads: `long_context_chat`, `long_context_coding`.

That is 48 cells total.

AMD ROCm/CDNA planning lives in [reference/amd-cdna-hardware-coverage.md](reference/amd-cdna-hardware-coverage.md). That page is planning-only until ROCm fixtures and live AMD GPU artifacts exist; do not treat it as live AMD support.

## Status counts

| Status | Count | Meaning |
|---|---:|---|
| `WORKING_TEMPLATE` | 28 | A shipped Slurm/template lane exists. Live recommendations still require `validate-completed --strict` and `live_complete` evidence. |
| `INFEASIBLE_DOCUMENTED` | 4 | The lane is rejected with documented capacity/config evidence. |
| `FUTURE_EXTERNAL` | 16 | The lane requires external rack access, orchestration, or hardware validation before a template is claimed. |

All 48 matrix rows are currently `claim_status=inferred`: the matrix documents template/readiness status, not measured benchmark results.

## Summary by hardware and model

| Hardware | DSv4 Flash | DSv4 Pro |
|---|---|---|
| H100 | `WORKING_TEMPLATE` (4/4) | `INFEASIBLE_DOCUMENTED` (4/4) |
| H200 | `WORKING_TEMPLATE` (4/4) | `WORKING_TEMPLATE` (4/4) |
| B200 | `WORKING_TEMPLATE` (4/4) | `WORKING_TEMPLATE` (4/4) |
| B300 | `WORKING_TEMPLATE` (4/4) | `WORKING_TEMPLATE` (4/4) |
| GB200 | `FUTURE_EXTERNAL` (4/4) | `FUTURE_EXTERNAL` (4/4) |
| GB300 | `FUTURE_EXTERNAL` (4/4) | `FUTURE_EXTERNAL` (4/4) |

## Interpretation notes

- H100 × DSv4-Pro is `INFEASIBLE_DOCUMENTED` for the single-node 8-GPU lane because model weights exceed safe HBM capacity before useful long-context KV budget is considered.
- H200, B200, and B300 have `WORKING_TEMPLATE` coverage for DSv4 Flash and DSv4 Pro across vLLM/SGLang and both workload shapes.
- GB200 and GB300 are `FUTURE_EXTERNAL`: they need rack/NVLink-domain access and external orchestration validation before InferGuard should publish working templates.
- A `WORKING_TEMPLATE` is not a measured result. It only says there is a template path to try. Operators still need live request rows, healthcheck, engine metrics, GPU metrics, and validation reports.

## Full 48-cell matrix

| Hardware | Model | Engine | Workload | Status | Claim | Template | Reason |
|---|---|---|---|---|---|---|---|
| H100 | `dsv4-flash` | `vllm` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/h100-vllm-dsv4-flash-long-context-chat.sbatch` | `template_available` |
| H100 | `dsv4-flash` | `vllm` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/h100-vllm-dsv4-flash-long-context-coding.sbatch` | `template_available` |
| H100 | `dsv4-flash` | `sglang` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/h100-sglang-dsv4-flash-long-context-chat.sbatch` | `template_available` |
| H100 | `dsv4-flash` | `sglang` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/h100-sglang-dsv4-flash-long-context-coding.sbatch` | `template_available` |
| H100 | `dsv4-pro` | `vllm` | `long_context_chat` | `INFEASIBLE_DOCUMENTED` | `inferred` | — | `hbm_capacity_exceeded_single_node` |
| H100 | `dsv4-pro` | `vllm` | `long_context_coding` | `INFEASIBLE_DOCUMENTED` | `inferred` | — | `hbm_capacity_exceeded_single_node` |
| H100 | `dsv4-pro` | `sglang` | `long_context_chat` | `INFEASIBLE_DOCUMENTED` | `inferred` | — | `hbm_capacity_exceeded_single_node` |
| H100 | `dsv4-pro` | `sglang` | `long_context_coding` | `INFEASIBLE_DOCUMENTED` | `inferred` | — | `hbm_capacity_exceeded_single_node` |
| H200 | `dsv4-flash` | `vllm` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/h200-vllm-dsv4-flash-long-context-chat.sbatch` | `template_available` |
| H200 | `dsv4-flash` | `vllm` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/h200-vllm-dsv4-flash-long-context-coding.sbatch` | `template_available` |
| H200 | `dsv4-flash` | `sglang` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/h200-sglang-dsv4-flash-long-context-chat.sbatch` | `template_available` |
| H200 | `dsv4-flash` | `sglang` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/h200-sglang-dsv4-flash-long-context-coding.sbatch` | `template_available` |
| H200 | `dsv4-pro` | `vllm` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/h200-vllm-dsv4-pro-long-context-chat.sbatch` | `template_available` |
| H200 | `dsv4-pro` | `vllm` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/h200-vllm-dsv4-pro-long-context-coding.sbatch` | `template_available` |
| H200 | `dsv4-pro` | `sglang` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/h200-sglang-dsv4-pro-long-context-chat.sbatch` | `template_available` |
| H200 | `dsv4-pro` | `sglang` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/h200-sglang-dsv4-pro-long-context-coding.sbatch` | `template_available` |
| B200 | `dsv4-flash` | `vllm` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/b200-vllm-dsv4-flash-long-context-chat.sbatch` | `template_available` |
| B200 | `dsv4-flash` | `vllm` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/b200-vllm-dsv4-flash-long-context-coding.sbatch` | `template_available` |
| B200 | `dsv4-flash` | `sglang` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/b200-sglang-dsv4-flash-long-context-chat.sbatch` | `template_available` |
| B200 | `dsv4-flash` | `sglang` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/b200-sglang-dsv4-flash-long-context-coding.sbatch` | `template_available` |
| B200 | `dsv4-pro` | `vllm` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/b200-vllm-dsv4-pro-long-context-chat.sbatch` | `template_available` |
| B200 | `dsv4-pro` | `vllm` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/b200-vllm-dsv4-pro-long-context-coding.sbatch` | `template_available` |
| B200 | `dsv4-pro` | `sglang` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/b200-sglang-dsv4-pro-long-context-chat.sbatch` | `template_available` |
| B200 | `dsv4-pro` | `sglang` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/b200-sglang-dsv4-pro-long-context-coding.sbatch` | `template_available` |
| B300 | `dsv4-flash` | `vllm` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/b300-vllm-dsv4-flash-long-context-chat.sbatch` | `template_available` |
| B300 | `dsv4-flash` | `vllm` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/b300-vllm-dsv4-flash-long-context-coding.sbatch` | `template_available` |
| B300 | `dsv4-flash` | `sglang` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/b300-sglang-dsv4-flash-long-context-chat.sbatch` | `template_available` |
| B300 | `dsv4-flash` | `sglang` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/b300-sglang-dsv4-flash-long-context-coding.sbatch` | `template_available` |
| B300 | `dsv4-pro` | `vllm` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/b300-vllm-dsv4-pro-long-context-chat.sbatch` | `template_available` |
| B300 | `dsv4-pro` | `vllm` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/b300-vllm-dsv4-pro-long-context-coding.sbatch` | `template_available` |
| B300 | `dsv4-pro` | `sglang` | `long_context_chat` | `WORKING_TEMPLATE` | `inferred` | `slurm/b300-sglang-dsv4-pro-long-context-chat.sbatch` | `template_available` |
| B300 | `dsv4-pro` | `sglang` | `long_context_coding` | `WORKING_TEMPLATE` | `inferred` | `slurm/b300-sglang-dsv4-pro-long-context-coding.sbatch` | `template_available` |
| GB200 | `dsv4-flash` | `vllm` | `long_context_chat` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB200 | `dsv4-flash` | `vllm` | `long_context_coding` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB200 | `dsv4-flash` | `sglang` | `long_context_chat` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB200 | `dsv4-flash` | `sglang` | `long_context_coding` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB200 | `dsv4-pro` | `vllm` | `long_context_chat` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB200 | `dsv4-pro` | `vllm` | `long_context_coding` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB200 | `dsv4-pro` | `sglang` | `long_context_chat` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB200 | `dsv4-pro` | `sglang` | `long_context_coding` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB300 | `dsv4-flash` | `vllm` | `long_context_chat` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB300 | `dsv4-flash` | `vllm` | `long_context_coding` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB300 | `dsv4-flash` | `sglang` | `long_context_chat` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB300 | `dsv4-flash` | `sglang` | `long_context_coding` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB300 | `dsv4-pro` | `vllm` | `long_context_chat` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB300 | `dsv4-pro` | `vllm` | `long_context_coding` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB300 | `dsv4-pro` | `sglang` | `long_context_chat` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |
| GB300 | `dsv4-pro` | `sglang` | `long_context_coding` | `FUTURE_EXTERNAL` | `inferred` | — | `external_nvlink_domain_orchestration_unconfirmed` |

## Publication rule

When quoting hardware support, use the exact status names above. Do not convert `WORKING_TEMPLATE` into "validated" or `FUTURE_EXTERNAL` into "supported". Measured claims require a completed run that passes:

```bash
inferguard validate-completed --results-root <run-root> --strict
```
