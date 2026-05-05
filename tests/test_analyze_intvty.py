import json

from inferguard.analyze import AnalyzeOptions, analyze_results


def test_intvty_median_is_inverse_of_tpot_median(tmp_path) -> None:
    cell_dir = tmp_path / "agentx" / "cell"
    cell_dir.mkdir(parents=True)
    (cell_dir / "detailed_results.csv").write_text(
        "success,request_start_time,request_complete_time,ttft,ttlt,itl,input_tokens,output_tokens_expected,output_tokens_actual\n"
        "true,0,2,0.10,2.0,0.01,100,64,50\n"
        "true,1,3,0.20,2.0,0.03,100,64,50\n",
        encoding="utf-8",
    )

    report = analyze_results(
        tmp_path, AnalyzeOptions(output_dir=tmp_path / "report", output_format="json")
    )

    metrics = report["cells"][0]["metrics"]
    assert metrics["median_tpot"] == 0.02
    assert metrics["median_intvty"] == 1 / metrics["median_tpot"]
    persisted = json.loads((tmp_path / "report" / "report.json").read_text())
    assert persisted["schema_version"] == "inferguard-analyze/v1.1"
