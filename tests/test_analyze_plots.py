from __future__ import annotations

import pytest

pytest.importorskip("matplotlib")

from inferguard.analyze.plots import render_plots


def test_render_plots_writes_expected_svgs(tmp_path):
    report = {
        "schema_version": "inferguard-analyze/v1",
        "cells": [
            {
                "cell_id": "b200-c08",
                "source_format": "inferguard-bench-native",
                "hardware": "b200",
                "concurrency": 8,
                "topology": {"num_prefill_gpu": 4, "num_decode_gpu": 4},
                "metrics": {"p99_ttft": 0.45, "output_tput_tps": 3200.0},
                "cost": {"cost_per_completed_session": 0.012},
            },
            {
                "cell_id": "b200-c16",
                "source_format": "inferguard-bench-native",
                "hardware": "b200",
                "concurrency": 16,
                "topology": {"num_prefill_gpu": 4, "num_decode_gpu": 4},
                "metrics": {"p99_ttft": 0.72, "output_tput_tps": 5600.0},
                "cost": {"cost_per_completed_session": 0.016},
            },
        ],
    }

    written = render_plots(report, tmp_path)

    expected = {
        tmp_path / "ttft_vs_concurrency.svg",
        tmp_path / "throughput_per_gpu.svg",
        tmp_path / "cost_per_task.svg",
    }
    assert set(written) == expected
    for path in expected:
        assert path.exists()
        assert path.stat().st_size > 0
