# InferGuard operator recommendation

- [measured] Schema: `inferguard-operator-recommendation/v1`
- [measured] Executive status: `live_complete`

## Executive verdict

[measured] recommend B200 on sglang for the measured workload Evidence: validation_report.json, matrix_plan.json, expected_artifact_contract.json

## Measured vs inferred vs synthetic

| Claim | Label | Evidence |
|---|---|---|
| executive_verdict | [measured] | validation_report.json, matrix_plan.json, expected_artifact_contract.json |
| best_gpu_sku | [measured] | jobs/job-b200-sglang/diagnosis/bottleneck_diagnosis.json, jobs/job-b200-sglang/diagnosis/failure_classification.json, jobs/job-b200-sglang/launch/healthcheck.json, jobs/job-b200-sglang/metrics/metrics_summary.json, jobs/job-b200-sglang/operator_profile.json, jobs/job-b200-sglang/request_profile/requests_summary.json |
| best_engine | [measured] | jobs/job-b200-sglang/diagnosis/bottleneck_diagnosis.json, jobs/job-b200-sglang/diagnosis/failure_classification.json, jobs/job-b200-sglang/launch/healthcheck.json, jobs/job-b200-sglang/metrics/metrics_summary.json, jobs/job-b200-sglang/operator_profile.json, jobs/job-b200-sglang/request_profile/requests_summary.json |
| best_model_config | [inferred] | jobs/job-b200-sglang/diagnosis/bottleneck_diagnosis.json, jobs/job-b200-sglang/diagnosis/failure_classification.json, jobs/job-b200-sglang/launch/healthcheck.json, jobs/job-b200-sglang/metrics/metrics_summary.json, jobs/job-b200-sglang/operator_profile.json, jobs/job-b200-sglang/request_profile/requests_summary.json |
| bottleneck | [measured] | jobs/job-b200-sglang/diagnosis/bottleneck_diagnosis.json, jobs/job-b200-sglang/diagnosis/failure_classification.json, jobs/job-b200-sglang/launch/healthcheck.json, jobs/job-b200-sglang/metrics/metrics_summary.json, jobs/job-b200-sglang/operator_profile.json, jobs/job-b200-sglang/request_profile/requests_summary.json |
| capacity_envelope | [not_proven] | not_proven evidence gate |
| failure_summary | [measured] | jobs/job-b200-sglang/diagnosis/failure_classification.json, jobs/job-h200-vllm/diagnosis/failure_classification.json |
| cost_notes | [not_proven] | jobs/job-b200-sglang/request_profile/requests_summary.json, jobs/job-h200-vllm/request_profile/requests_summary.json, jobs/job-b200-sglang/request_profile/requests_profile.jsonl, jobs/job-h200-vllm/request_profile/requests_profile.jsonl |
| lmcache_verdict | [not_proven] | jobs/job-b200-sglang/metrics/metrics_summary.json, jobs/job-h200-vllm/metrics/metrics_summary.json, jobs/job-b200-sglang/metrics/engine_metrics_timeline.jsonl, jobs/job-h200-vllm/metrics/engine_metrics_timeline.jsonl, jobs/job-b200-sglang/metrics/gpu_metrics_timeline.jsonl, jobs/job-h200-vllm/metrics/gpu_metrics_timeline.jsonl |
| gb200_justification | [not_proven] | not_proven evidence gate |

## Best GPU SKU

[measured] B200 has the strongest measured score among comparable SKUs. Evidence: jobs/job-b200-sglang/diagnosis/bottleneck_diagnosis.json, jobs/job-b200-sglang/diagnosis/failure_classification.json, jobs/job-b200-sglang/launch/healthcheck.json, jobs/job-b200-sglang/metrics/metrics_summary.json, jobs/job-b200-sglang/operator_profile.json, jobs/job-b200-sglang/request_profile/requests_summary.json

## Best engine

[measured] sglang has the strongest measured score among comparable engines. Evidence: jobs/job-b200-sglang/diagnosis/bottleneck_diagnosis.json, jobs/job-b200-sglang/diagnosis/failure_classification.json, jobs/job-b200-sglang/launch/healthcheck.json, jobs/job-b200-sglang/metrics/metrics_summary.json, jobs/job-b200-sglang/operator_profile.json, jobs/job-b200-sglang/request_profile/requests_summary.json

## Best model config

[inferred] Config is inferred from the measured decode_bound bottleneck and launch/profile artifacts. Evidence: jobs/job-b200-sglang/diagnosis/bottleneck_diagnosis.json, jobs/job-b200-sglang/diagnosis/failure_classification.json, jobs/job-b200-sglang/launch/healthcheck.json, jobs/job-b200-sglang/metrics/metrics_summary.json, jobs/job-b200-sglang/operator_profile.json, jobs/job-b200-sglang/request_profile/requests_summary.json

## Bottleneck

[measured] Bottleneck verdict: decode_bound. Evidence: jobs/job-b200-sglang/diagnosis/bottleneck_diagnosis.json, jobs/job-b200-sglang/diagnosis/failure_classification.json, jobs/job-b200-sglang/launch/healthcheck.json, jobs/job-b200-sglang/metrics/metrics_summary.json, jobs/job-b200-sglang/operator_profile.json, jobs/job-b200-sglang/request_profile/requests_summary.json

## Capacity envelope

[not_proven] No capacity envelope: not_proven — see capacity_cliffs.json

## Failure summary

[measured] Top failure class: none. Evidence: jobs/job-b200-sglang/diagnosis/failure_classification.json, jobs/job-h200-vllm/diagnosis/failure_classification.json

## Cost notes

[not_proven] No cost claim: not_proven — cost input not supplied

## Recommended next run

[measured] Run find-cliffs to establish max concurrency and max context before operator sign-off. Evidence: validation_report.json, matrix_plan.json, expected_artifact_contract.json

## Evidence artifacts

[measured] expected_artifact_contract.json Evidence: expected_artifact_contract.json
[measured] jobs/job-b200-sglang/diagnosis/bottleneck_diagnosis.json Evidence: jobs/job-b200-sglang/diagnosis/bottleneck_diagnosis.json
[measured] jobs/job-b200-sglang/diagnosis/failure_classification.json Evidence: jobs/job-b200-sglang/diagnosis/failure_classification.json
[measured] jobs/job-b200-sglang/launch/healthcheck.json Evidence: jobs/job-b200-sglang/launch/healthcheck.json
[measured] jobs/job-b200-sglang/metrics/engine_metrics_timeline.jsonl Evidence: jobs/job-b200-sglang/metrics/engine_metrics_timeline.jsonl
[measured] jobs/job-b200-sglang/metrics/gpu_metrics_timeline.jsonl Evidence: jobs/job-b200-sglang/metrics/gpu_metrics_timeline.jsonl
[measured] jobs/job-b200-sglang/metrics/metrics_summary.json Evidence: jobs/job-b200-sglang/metrics/metrics_summary.json
[measured] jobs/job-b200-sglang/operator_profile.json Evidence: jobs/job-b200-sglang/operator_profile.json
[measured] jobs/job-b200-sglang/preflight/ib_state.txt Evidence: jobs/job-b200-sglang/preflight/ib_state.txt
[measured] jobs/job-b200-sglang/request_profile/requests_profile.jsonl Evidence: jobs/job-b200-sglang/request_profile/requests_profile.jsonl
[measured] jobs/job-b200-sglang/request_profile/requests_summary.json Evidence: jobs/job-b200-sglang/request_profile/requests_summary.json
[measured] jobs/job-h200-vllm/diagnosis/bottleneck_diagnosis.json Evidence: jobs/job-h200-vllm/diagnosis/bottleneck_diagnosis.json
[measured] jobs/job-h200-vllm/diagnosis/failure_classification.json Evidence: jobs/job-h200-vllm/diagnosis/failure_classification.json
[measured] jobs/job-h200-vllm/launch/healthcheck.json Evidence: jobs/job-h200-vllm/launch/healthcheck.json
[measured] jobs/job-h200-vllm/metrics/engine_metrics_timeline.jsonl Evidence: jobs/job-h200-vllm/metrics/engine_metrics_timeline.jsonl
[measured] jobs/job-h200-vllm/metrics/gpu_metrics_timeline.jsonl Evidence: jobs/job-h200-vllm/metrics/gpu_metrics_timeline.jsonl
[measured] jobs/job-h200-vllm/metrics/metrics_summary.json Evidence: jobs/job-h200-vllm/metrics/metrics_summary.json
[measured] jobs/job-h200-vllm/operator_profile.json Evidence: jobs/job-h200-vllm/operator_profile.json
[measured] jobs/job-h200-vllm/preflight/ib_state.txt Evidence: jobs/job-h200-vllm/preflight/ib_state.txt
[measured] jobs/job-h200-vllm/request_profile/requests_profile.jsonl Evidence: jobs/job-h200-vllm/request_profile/requests_profile.jsonl
[measured] jobs/job-h200-vllm/request_profile/requests_summary.json Evidence: jobs/job-h200-vllm/request_profile/requests_summary.json
[measured] matrix_plan.json Evidence: matrix_plan.json
[measured] validation_report.json Evidence: validation_report.json
