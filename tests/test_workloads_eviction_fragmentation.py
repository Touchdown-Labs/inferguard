import asyncio
import json

from inferguard.bench.runner import BenchConfig, poisson_arrival_offsets, run_kv_stress
from inferguard.bench.workloads import generate_kv_stress_specs
from tests.fixtures.mock_vllm_server import start_mock_servers


def test_eviction_probe_warms_pressures_and_retests_prefix() -> None:
    specs = generate_kv_stress_specs(
        context_lengths=[256], output_tokens=8, requests_per_level=6, mode="eviction-probe"
    )

    cache_modes = [spec.metadata["cache_mode"] for spec in specs]
    assert cache_modes == [
        "eviction_warm",
        "eviction_warm",
        "eviction_pressure",
        "eviction_pressure",
        "eviction_pressure",
        "eviction_retest",
    ]
    assert specs[0].prefix_group == specs[-1].prefix_group
    assert {spec.workload_class for spec in specs} >= {
        "prefix-reuse",
        "kv-pressure",
        "session-resume",
    }


def test_fragmentation_probe_interleaves_short_mid_and_long_requests() -> None:
    specs = generate_kv_stress_specs(
        context_lengths=[1024], output_tokens=8, requests_per_level=4, mode="fragmentation-probe"
    )

    assert [spec.metadata["cache_mode"] for spec in specs] == [
        "fragment_short",
        "fragment_long",
        "fragment_mid_resume",
        "fragment_long_after",
    ]
    assert {spec.workload_class for spec in specs} >= {
        "agent-chat",
        "kv-pressure",
        "session-resume",
    }
    prompt_lengths = [len(spec.messages[-1]["content"]) for spec in specs]
    assert prompt_lengths[0] < prompt_lengths[1]
    assert prompt_lengths[2] < prompt_lengths[3]


def test_long_context_bands_generate_without_materializing_huge_test_state() -> None:
    specs = generate_kv_stress_specs(
        context_lengths=[524288, 1048576],
        output_tokens=1,
        requests_per_level=1,
        mode="cold-pressure",
    )

    assert [spec.expected_input_tokens for spec in specs] == [524288, 1048576]
    assert all(
        spec.messages[-1]["content"].endswith(
            f"FINAL_MARKER_cold-pressure_{spec.expected_input_tokens}_0"
        )
        for spec in specs
    )


def test_poisson_offsets_are_deterministic_and_increasing() -> None:
    offsets = poisson_arrival_offsets(4, rate_rps=5)

    assert offsets == poisson_arrival_offsets(4, rate_rps=5)
    assert offsets == sorted(offsets)
    assert offsets[0] > 0


def test_kvcast_poisson_runs_end_to_end_against_mock_vllm(tmp_path) -> None:
    mock = start_mock_servers("b200")
    try:
        result = asyncio.run(
            run_kv_stress(
                BenchConfig(
                    command="kvcast",
                    endpoint=mock.endpoint_url,
                    model="mock-dsv4",
                    context_lengths=[128],
                    concurrency_levels=[2],
                    output_dir=tmp_path / "out",
                    output_tokens=8,
                    requests_per_level=2,
                    kvcast_mode="eviction-probe",
                    arrival_mode="poisson",
                    arrival_rate_rps=100,
                )
            )
        )
    finally:
        mock.teardown()

    assert result["summary"]["request_counts"]["success"] == 2
    config = json.loads((tmp_path / "out" / "config.json").read_text(encoding="utf-8"))
    assert config["arrival_mode"] == "poisson"
    rows = [
        json.loads(line)
        for line in (tmp_path / "out" / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all("scheduled_arrival_time" in row["metadata"] for row in rows)
