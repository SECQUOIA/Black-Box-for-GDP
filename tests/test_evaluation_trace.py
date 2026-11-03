"""Trace correctness matters for replaying costly GDP subproblem evaluations."""

import csv
import json
import math

import pytest

import case_study_benchmark as cases
from evaluation_trace import EvaluationTrace, ACTIVE_TRACE, validate_trace_artifacts
from instrumentation import TrackedObjective, make_result_record


def test_trace_preserves_raw_values_repeats_failures_and_initial_calls(tmp_path):
    clock = iter(range(100))
    key = {"n_starts": 3}
    values = iter((math.nan, math.inf, 4.123456789123, 6.0))
    objective = TrackedObjective(lambda x: next(values))
    with EvaluationTrace(tmp_path / "cases.csv", key, timer=lambda: next(clock)) as trace:
        for point in ([1, 2], [2, 3], [3, 4], [3, 4]):
            objective(point)
        record = make_result_record(
            csv_name="test", method="BAM", seed=0, n_starts=3, max_evals=4,
            best_value=objective.incumbent, best_point=[3, 4], total_evals=4,
            wall_time_s=9, found_optimum=True, initial_evals=3,
            incumbent_trajectory=objective.incumbent_trajectory,
        )
        trace.complete(record)
    entries = [json.loads(line) for line in trace.path.read_text().splitlines()]
    events = entries[1:-1]
    assert [e["point"] for e in events] == [[1, 2], [2, 3], [3, 4], [3, 4]]
    assert [e["value_kind"] for e in events] == ["nan", "+inf", "finite", "finite"]
    assert events[2]["value"] == 4.123456789123
    assert events[3]["incumbent"] == 4.123456789123
    assert [e["repeated_point"] for e in events] == [False, False, False, True]
    assert [e["phase"] for e in events] == ["initial"] * 3 + ["adaptive"]
    assert [e["completed_elapsed_s"] for e in events] == [2, 4, 6, 8]
    assert ACTIVE_TRACE.get() is None


def test_exception_retains_interrupted_coordinate_and_resets_context(tmp_path):
    def fail(point):
        raise RuntimeError("private solver detail")
    objective = TrackedObjective(fail)
    with pytest.raises(RuntimeError):
        with EvaluationTrace(tmp_path / "cases.csv", {"n_starts": 3}) as trace:
            objective([3, 1])
    entries = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert ".partial.jsonl" in trace.path.name
    assert entries[1]["point"] == [3, 1]
    assert entries[1]["exception_type"] == "RuntimeError"
    assert "private solver detail" not in trace.path.read_text()
    assert ACTIVE_TRACE.get() is None


def test_real_dsda_all_cases_trace_roundtrips_optional_reporting_fields(tmp_path):
    records, path = cases.run_case_study_benchmark(
        methods=("dsda",), seeds=(0,), column_seeds=(1,),
        cstr_grid_sizes=(5,), dynamic_budgets=(12,),
        output=tmp_path / "cases.csv", trace_evaluations=True,
    )
    assert len(records) == 4
    manifest = json.loads(path.with_suffix(".manifest.json").read_text())
    with path.open() as handle:
        reader = csv.DictReader(handle)
        reloaded = [cases._deserialize_result_record(row) for row in reader]
        assert manifest["schema"]["fields"] == reader.fieldnames
    for original, restored in zip(records, reloaded):
        assert restored["target_reached"] is original["target_reached"]
        assert restored["observed_best_value"] == original["observed_best_value"]
    artifacts = validate_trace_artifacts(manifest, path, reloaded)
    assert len(artifacts) == 4
    for artifact, record in zip(artifacts, records):
        events = [json.loads(line) for line in (path.parent / artifact["path"]).read_text().splitlines()][1:-1]
        assert len(events) == record["total_evals"]
        assert len({tuple(e["point"]) for e in events}) == record["unique_evals"]


def test_resume_requires_intact_traces_and_skips_completed_runs(tmp_path):
    output = tmp_path / "resume.csv"
    actual = cases.CASE_RUNNERS["cstr"]["dsda"]
    def fail_second(**kwargs):
        if kwargs["seed"] == 1:
            raise RuntimeError("interrupted")
        return actual(**kwargs)
    kwargs = dict(cases=("cstr",), methods=("dsda",), seeds=(0, 1),
                  cstr_grid_sizes=(5,), output=output, trace_evaluations=True)
    with pytest.raises(RuntimeError):
        cases.run_case_study_benchmark(**kwargs, runners={"cstr": {"dsda": fail_second}})
    partial_manifest = output.with_suffix(".partial.manifest.json")
    manifest = json.loads(partial_manifest.read_text())
    trace_path = tmp_path / manifest["evaluation_traces"][0]["path"]
    original = trace_path.read_bytes()
    trace_path.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="trace checksum"):
        cases.run_case_study_benchmark(**kwargs, resume=True)
    trace_path.write_bytes(original)
    calls = []
    def resumed(**kwargs):
        calls.append(kwargs["seed"])
        return actual(**kwargs)
    records, _ = cases.run_case_study_benchmark(
        **kwargs, resume=True, runners={"cstr": {"dsda": resumed}},
    )
    assert calls == [1]
    assert len(records) == 2
    assert trace_path.read_bytes() == original
    assert all(isinstance(record["target_reached"], bool) for record in records)
    from case_study_analysis import load_case_study_results
    frame = load_case_study_results(output)
    assert frame["target_reached"].tolist() == [r["target_reached"] for r in records]
    assert frame["observed_best_value"].tolist() == [r["observed_best_value"] for r in records]
