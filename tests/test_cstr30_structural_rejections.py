"""No solver or DFO search: clock, preservation, accounting and original rejection path."""
import json
import os
import shutil
import subprocess
import sys
import zipfile

import pytest

import build_cstr30_structural_rejections as builder
import measure_cstr30_structural_rejections as measure


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    folder = tmp_path_factory.mktemp("structural-bundle")
    archive = folder / "runner.zip"
    builder.build(archive)
    with zipfile.ZipFile(archive) as source:
        source.extractall(folder)
    return folder / "cstr30_structural_runner"


def fake_evaluator(case, point, **kwargs):
    assert case == "cstr" and kwargs["cstr_size"] == 30
    return {"case": case, "cstr_size": 30, "point": list(point), "accepted": False,
            "status": "preprocessing_infeasible", "termination": "not_solved",
            "objective": None, "solve_wall_s": 0.0, "total_wall_s": 1e-9,
            "message": "Synthetic test fixture, never published as measurement"}


def test_one_nanosecond_is_retained_and_allowed_points_never_enter():
    clock = iter((123456789, 123456790))
    row = measure.measure_one(fake_evaluator, (1, 2), "test", "test", clock=lambda: next(clock))
    assert row["elapsed_ns"] == 1 and row["total_wall_s"] == 1e-9
    assert row["objective"] is None and row["solve_wall_s"] == 0
    with pytest.raises(ValueError, match="Only x2>x1"):
        measure.measure_one(lambda *a, **k: pytest.fail("Allowed point evaluated"), (30, 30), "test", "test")


def test_complete_overlay_preserves_all_original_fields_and_budget_failures(bundle, tmp_path):
    original, _, _ = measure.check_inputs(bundle)
    output = tmp_path / "synthetic_test_only"
    (output / "records").mkdir(parents=True)
    shutil.copyfile(bundle / "inputs/cstr_30/evaluations.csv", output / "original_465.csv")
    for index, point in enumerate(measure.POINTS, 1):
        clock = iter((0, index))
        row = measure.measure_one(fake_evaluator, point, output.name, "test", clock=lambda: next(clock))
        measure.write(output / "records" / f"point_{point[0]:02d}_{point[1]:02d}.json", row)
    result = measure.report_results(bundle, output, original, 0)
    assert result["combined_rows"] == 900 and result["measured_structural_points"] == 435
    assert result["dfo"]["missing_before"] == 515
    assert result["dfo"]["supplemented_callbacks"] == 508
    assert result["dfo"]["missing_after"] == 7 and result["dfo"]["complete_cost_runs"] == 33
    events = [json.loads(line) for line in (output / "callbacks_with_timing_supplement.jsonl").read_text().splitlines()]
    originals = {}
    for spec in measure.read(bundle / "inputs/dfo/plan.json"):
        job = spec["job_id"]
        originals[job] = [json.loads(line) for line in (bundle / "inputs/dfo/jobs" / job / "callbacks.jsonl").read_text().splitlines()]
    for event in events:
        old = originals[event["job_id"]][event["index"] - 1]
        assert all(event[k] == v for k, v in old.items())
        if event["budget_overrun"]:
            assert event["reconstructed_process_wall_s"] is None
            assert event["callback_exit"] == "protocol_error"
    runs = measure.rows(output / "cstr30_run_time_comparison.csv")
    assert sum(r["category"] == "execution_failed" for r in runs) == 7
    for run in runs:
        ledger = [e for e in events if e["job_id"] == run["job_id"]]
        filled = [e["reconstructed_process_wall_s"] for e in ledger if e["timing_supplement_applied"]]
        assert float(run["added_structural_cost_per_callback_s"]) == sum(filled)
    assert all(float(r["total_wall_s"]) > 0 for r in measure.rows(output / "structural_rejections.csv"))


def test_changed_input_hash_stops_before_measurement(bundle):
    path = bundle / "inputs/cstr_30/evaluations.csv"
    before = path.read_bytes()
    try:
        path.write_bytes(before + b"\n")
        with pytest.raises(ValueError, match="checksum mismatch"):
            measure.check_inputs(bundle)
    finally:
        path.write_bytes(before)


def test_frozen_real_path_and_execution_guards(bundle):
    # Fresh interpreter ensures the frozen historical gdp_models package is used.
    code = r'''
import json
from pathlib import Path
from unittest.mock import patch
import measure_cstr30_structural_rejections as m
from gdp_models import models
import pyomo.environ as pyo
import subprocess
root=Path.cwd()
original,manifest,_=m.check_inputs(root)
with patch.object(models, 'build_gdp', side_effect=AssertionError('Preflight must not build a model')):
    evaluate,identity=m.prepare_evaluator(root,manifest,strict=False)
with m.no_solver() as calls:
    for point in ((1,2),(15,30),(29,30)):
        result=m.measure_one(evaluate,point,'local_test_only','local_test_only')
        assert result['status']=='preprocessing_infeasible'
        assert result['total_wall_s']>0 and result['solver_called'] is False
        assert 'logic' in result['message'].lower()
assert calls==[]
for attempt in (lambda:pyo.SolverFactory('ipopt'), lambda:subprocess.Popen(['must-not-launch'])):
    with m.no_solver() as calls:
        try: attempt()
        except m.ForbiddenExecution: pass
        else: raise AssertionError('Execution guard did not stop request')
    assert len(calls)==1
print('3 original structural paths and both execution guards passed; no solver/DFO run')
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=bundle,
        env={**os.environ, "PYTHONPATH": str(bundle), "RBFOPT_GDP_SOURCES": str(builder.ROOT / "external")},
        text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
