"""Do not manufacture GDP costs from missing or ambiguous historical rows."""

import csv
import json

import pytest

import case_study_benchmark as cases
from trace_analysis import analyze, legacy_cost


def test_legacy_cost_does_not_sum_cumulative_time_or_choose_a_duplicate():
    assert legacy_cost([{"Time": "2.5", "Global_Time": "999"}], "cstr") == (2.5, "single_record")
    assert legacy_cost([], "cstr") == (None, "missing_record")
    assert legacy_cost([], "dynamic") == (None, "no_timing_table")
    assert legacy_cost([{"Time": "2.5"}, {"Time": "5"}], "cstr") == (None, "duplicate_records")
    assert legacy_cost([{"Time": "nan"}], "column") == (None, "invalid_time")
    assert legacy_cost([{"Time": "2.5", "Status": "Optimal"},
                        {"Time": "1.5", "Status": "Final"}], "column") == (
                            2.5, "enumeration_record_excluding_final")
    assert legacy_cost([{"Time": "1.5", "Status": "Final"}], "column") == (None, "final_only")


def test_real_traces_join_exact_coordinates_without_filling_missing_costs(tmp_path):
    records, path = cases.run_case_study_benchmark(
        methods=("dsda",), seeds=(0,), column_seeds=(1,),
        cstr_grid_sizes=(5,), dynamic_budgets=(12,),
        output=tmp_path / "cases.csv", trace_evaluations=True,
    )
    summary = analyze([path], tmp_path / "analysis")
    assert summary["runs"] == 4
    assert summary["objective_calls"] == sum(r["total_evals"] for r in records)
    with (tmp_path / "analysis/run_summary.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    dynamic = next(r for r in rows if r["case_name"] == "dynamic")
    assert dynamic["legacy_full_call_cost_estimate_s"] == ""
    assert dynamic["legacy_cost_covered_calls"] == "0"
    with (tmp_path / "analysis/evaluation_points.csv").open() as handle:
        points = list(csv.DictReader(handle))
    assert all(isinstance(json.loads(p["point"]), list) for p in points)
    with pytest.raises(ValueError, match="Duplicate run"):
        analyze([path, path], tmp_path / "duplicate")
    manifest_path = path.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text())
    name = next(iter(manifest["provenance"]["data_files_sha256"]))
    manifest["provenance"]["data_files_sha256"][name] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Lookup/timing input changed"):
        analyze([path], tmp_path / "changed_data")
