"""The full GDP domain must expose and charge infeasible evaluations fairly."""

import csv
import hashlib
import itertools
import json
import math
import subprocess
import sys
from types import SimpleNamespace
import zipfile

import pytest

import process_followup_runner as runner
import small_batch_full_domain as full
from overnight_benchmark.common import jsonl, read, save


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.setattr(runner, "EXPERIMENT", full)
    return full


def test_original_enumeration_covers_27_and_15_rejection_costs():
    ref = full.reference()
    assert len(ref["points"]) == 27
    feasible = [p for p in ref["points"] if p["lookup_value"] is not None]
    rejected = [p for p in ref["points"] if p["lookup_value"] is None]
    assert len(feasible) == 12 and len(rejected) == 15
    assert all(p["measurement"]["status"] == "preprocessing_infeasible" for p in rejected)
    assert all(p["measurement"]["solve_wall_s"] == 0 < p["measurement"]["total_wall_s"] for p in rejected)
    assert sum(p["measurement"]["total_wall_s"] for p in rejected) == pytest.approx(.6828773934394121)


def test_all_methods_share_full_domain_designs_without_seed_selection(experiment):
    specs = runner.plan()
    assert len(specs) == len({s["job_id"] for s in specs}) == 40
    for seed in range(10):
        group = [s for s in specs if s["seed"] == seed]
        assert {s["method"] for s in group} == set(full.METHODS)
        assert all(s["starting_points"] == group[0]["starting_points"] for s in group)
        for spec in group:
            runner.frozen_starts(spec)
            oracle = runner.problem(spec)
            assert oracle["lower"] == [1, 1, 1] and oracle["upper"] == [3, 3, 3]
            assert 1 <= sum(math.isfinite(oracle["objective"](p)) for p in spec["starting_points"]) <= 2
            assert spec["max_evaluations"] == 10


def test_dsda_evaluates_infeasible_neighbors_instead_of_filtering_them(experiment, tmp_path, monkeypatch):
    import grid_dsda
    original = grid_dsda.get_neighbors
    observed = []

    def all_neighbors(point, grid, diagonal=True):
        assert set(grid) == set(itertools.product(range(1, 4), repeat=3))
        assert all(value is None for value in grid.values())
        candidates = original(point, grid, diagonal=diagonal)
        observed.extend(candidates)
        return candidates

    monkeypatch.setattr(grid_dsda, "get_neighbors", all_neighbors)
    spec = next(s for s in runner.plan() if s["seed"] == 0 and s["method"] == "dsda")
    result = runner.dfo_lookup(spec, {}, tmp_path)
    events = jsonl(tmp_path / result["trace"]["path"])[1:-1]
    assert len(events) == 10 and observed
    assert any(e["phase"] == "adaptive" and e["value"] == full.PENALTY for e in events)
    runner.validate_trace(events, result["result_record"], spec)
    summary = full.report_costs(tmp_path, [{**result, "spec": spec}],
                               [{**e, "job_id": spec["job_id"], "method": "dsda", "seed": 0} for e in events])
    assert summary["infeasible_callbacks"] > 2 and summary["callbacks_with_point_cost"] == 10
    with (tmp_path / "completion_estimates.csv").open() as f:
        estimate = next(csv.DictReader(f))
    ref = {tuple(p["point"]): p["measurement"]["total_wall_s"] for p in full.reference()["points"]}
    expected = result["result_record"]["wall_time_s"] + sum(ref[tuple(e["point"])] - e["objective_wall_s"] for e in events)
    assert float(estimate["estimated_completion_s"]) == pytest.approx(expected)


def test_bam_gets_nan_for_infeasible_points_and_full_bounds(experiment, tmp_path, monkeypatch):
    bam = pytest.importorskip("bam")
    monkeypatch.setattr(bam, "set_license_file", lambda path: None)
    spec = next(s for s in runner.plan() if s["seed"] == 0 and s["method"] == "bam")

    def minimize(objective, x0, bounds, integrality, options):
        assert bounds == [(1., 3.)] * 3 and integrality == [1] * 3 and x0 is None
        assert options["max_evals"] == 7
        assert sum(math.isnan(v) for v in options["f_evaluated"]) == 2
        for point in list(itertools.product(range(1, 4), repeat=3))[:7]:
            assert math.isnan(objective(point))
        return SimpleNamespace(fun=float(options["f_evaluated"][1]), x=options["x_evaluated"][1],
                               nfev=7, nit=7, status=35, message="mock budget completion")

    monkeypatch.setattr(bam, "minimize", minimize)
    result = runner.dfo_lookup(spec, {"bam_license": "test"}, tmp_path)
    events = jsonl(tmp_path / result["trace"]["path"])[1:-1]
    assert len(events) == 10 and events[0]["value_kind"] == "nan"
    assert sum(e["value_kind"] == "nan" for e in events) == 9


def test_fmqa_keeps_frozen_full_domain_points_and_infeasibility(experiment, tmp_path):
    pytest.importorskip("dimod")
    pytest.importorskip("dwave.samplers")
    spec = next(s for s in runner.plan() if s["seed"] == 0 and s["method"] == "fmqa_sa")
    spec = {**spec, "settings": {**spec["settings"], "epochs": 5, "num_reads": 3, "num_sweeps": 20}}
    result = runner.fmqa_lookup(spec, {}, tmp_path)
    events = jsonl(tmp_path / result["trace"]["path"])[1:-1]
    assert result["status"] == "completed" and len(events) == 10
    assert [e["point"] for e in events[:3]] == spec["starting_points"]
    assert events[0]["lookup_feasible"] is False and events[0]["raw_value"] is None
    assert events[0]["value"] == full.PENALTY


def test_full_domain_survives_subprocess_resume_and_bundle(experiment, tmp_path):
    config = {"cpu": None, "dfo_python": sys.executable, "fmqa_python": sys.executable,
              "conda": "", "hard_seconds": 30, "experiment": "small_batch_full_domain"}
    run = {"kind": runner.experiment_kind(), "config": config, "plan": runner.plan(),
           "source_files_sha256": runner.source_hashes()}
    directory = tmp_path / "result"
    save(directory / "run.json", run)
    spec = run["plan"][0]
    result = runner.launch(directory, spec, config, False)
    assert result["status"] == "completed"
    assert runner.launch(directory, spec, config, True) == result
    summary = runner.report(directory)
    assert summary["planned_runs"] == 40 and summary["completed_runs"] == 1
    assert summary["callbacks_missing_point_cost"] == 0
    archive = tmp_path / "runner.zip"
    runner.bundle(archive)
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        assert not any(".venv" in n or "bamlice" in n for n in zipped.namelist())
        zipped.extractall(tmp_path / "extract")
    extracted = tmp_path / "extract" / full.BUNDLE_FOLDER
    manifest = read(extracted / "BUNDLE_MANIFEST.json")
    for relative, digest in manifest["source_files_sha256"].items():
        assert hashlib.sha256((extracted / relative).read_bytes()).hexdigest() == digest
    completed = subprocess.run([sys.executable, "process_followup_runner.py", "plan", "--experiment", "small_batch_full_domain"],
                               cwd=extracted, capture_output=True, text=True, check=True)
    assert json.loads(completed.stdout) == runner.plan()
