import json

from inferguard.analyze.exporters import emit_agentx_shape

REQUIRED_KEYS = {
    "_schema_version",
    "hw",
    "conc",
    "image",
    "model",
    "infmax_model_prefix",
    "framework",
    "precision",
    "spec_decoding",
    "disagg",
    "scenario_type",
    "is_multinode",
    "tp",
    "ep",
    "dp_attention",
    "offloading",
    "num_requests_total",
    "num_requests_successful",
    "mean_qps",
    "median_qps",
    "p90_qps",
    "p99_qps",
    "p99.9_qps",
    "std_qps",
    "mean_ttft",
    "median_ttft",
    "p90_ttft",
    "p99_ttft",
    "p99.9_ttft",
    "std_ttft",
    "mean_e2el",
    "median_e2el",
    "p90_e2el",
    "p99_e2el",
    "p99.9_e2el",
    "std_e2el",
    "mean_itl",
    "median_itl",
    "p90_itl",
    "p99_itl",
    "p99.9_itl",
    "std_itl",
    "mean_tpot",
    "median_tpot",
    "p90_tpot",
    "p99_tpot",
    "p99.9_tpot",
    "std_tpot",
    "mean_intvty",
    "median_intvty",
    "p90_intvty",
    "p99_intvty",
    "p99.9_intvty",
    "std_intvty",
    "mean_input_tokens",
    "median_input_tokens",
    "p90_input_tokens",
    "p99_input_tokens",
    "p99.9_input_tokens",
    "std_input_tokens",
    "mean_output_tokens_actual",
    "median_output_tokens_actual",
    "p90_output_tokens_actual",
    "p99_output_tokens_actual",
    "p99.9_output_tokens_actual",
    "std_output_tokens_actual",
    "input_tput_tps",
    "output_tput_tps",
    "total_tput_tps",
    "duration_seconds",
    "tput_per_gpu",
    "output_tput_per_gpu",
    "input_tput_per_gpu",
}


def test_emit_agentx_shape_has_required_jq_compatible_keys(tmp_path) -> None:
    report = {
        "cells": [
            {
                "cell_id": "h200/cell:1",
                "hardware": "h200",
                "concurrency": 16,
                "image": "img",
                "model": "deepseek-v4",
                "infmax_model_prefix": "deepseek",
                "framework": "vllm",
                "precision": "FP8",
                "topology": {"tp": "8", "ep_size": "8", "dp_attention": "false"},
                "completion": {"num_requests_total": 2, "num_requests_successful": 2},
                "metrics": {"median_tpot": 0.02, "median_intvty": 50.0, "tput_per_gpu": 12.5},
            }
        ]
    }

    paths = emit_agentx_shape(report, tmp_path)

    assert len(paths) == 1
    payload = json.loads(paths[0].read_text())
    assert REQUIRED_KEYS <= payload.keys()
    assert payload["_schema_version"] == "inferguard-agentx-export/v1"
    assert payload["hw"] == "h200"
    assert payload["ep"] == 8
    assert payload["median_intvty"] == 50.0
