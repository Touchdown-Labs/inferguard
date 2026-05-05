from inferguard.analyze import AnalyzeOptions, analyze_results


def _write_agentx_cell(root):
    cell_dir = root / "agentx" / "cell"
    cell_dir.mkdir(parents=True)
    (cell_dir / "detailed_results.csv").write_text(
        "success,request_start_time,request_complete_time,ttft,ttlt,itl,input_tokens,output_tokens_expected,output_tokens_actual\n"
        "true,0,2,0.10,2.0,0.02,100,64,50\n"
        "true,1,3,0.20,2.0,0.03,100,64,50\n",
        encoding="utf-8",
    )


def test_tput_per_gpu_requires_gpus_and_computes_when_passed(tmp_path) -> None:
    _write_agentx_cell(tmp_path)

    report_without_gpus = analyze_results(
        tmp_path,
        AnalyzeOptions(output_dir=tmp_path / "report-a", output_format="json"),
    )
    assert "tput_per_gpu" not in report_without_gpus["cells"][0]["metrics"]

    report = analyze_results(
        tmp_path,
        AnalyzeOptions(output_dir=tmp_path / "report-b", output_format="json", gpus=8),
    )

    metrics = report["cells"][0]["metrics"]
    # Duration is max complete 3 - min start 0 = 3s; total tokens = 300.
    assert metrics["total_tput_tps"] == 100
    assert metrics["tput_per_gpu"] == 12.5
    assert metrics["output_tput_per_gpu"] == (100 / 3) / 8
    assert metrics["input_tput_per_gpu"] == (200 / 3) / 8
