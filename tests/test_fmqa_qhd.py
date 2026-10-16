"""Check original PyTorch fitting, paired starts, durable traces and deployment."""

import hashlib
import itertools
import json
import subprocess
import sys
import zipfile

import pytest

import fmqa_qhd_experiment as qhd
import process_followup_runner as runner
from fmqa_benchmark import qhd_surrogate
from fmqa_benchmark.protocol import reference_plan
from overnight_benchmark.common import jsonl, read


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.setattr(qhd, "SCOPE", "small_batch")
    monkeypatch.setattr(qhd, "SEEDS", None)
    monkeypatch.setattr(runner, "EXPERIMENT", qhd)
    return qhd


def native():
    pytest.importorskip("torch")
    pytest.importorskip("dimod")
    pytest.importorskip("dwave.samplers")
    qhd.worker_setup()


def test_saved_initial_coordinates_and_budgets_match_existing_experiments(experiment):
    old_full = read(qhd.ROOT / "results/small_batch_full_domain_20261012/run.json")["plan"]
    old = {s["seed"]: s for s in old_full if s["method"] == "fmqa_sa"}
    assert len(qhd.plan()) == 10
    for spec in qhd.plan():
        assert spec["starting_points"] == old[spec["seed"]]["starting_points"]
        assert spec["initial_design_sha256"] == old[spec["seed"]]["initial_design_sha256"]
        assert spec["max_evaluations"] == 10
        assert qhd.problem(spec)["lower"] == [1, 1, 1]
    qhd.configure("process")
    plan = qhd.plan()
    assert len(plan) == 140
    original = {(s["csv_name"], s["max_evaluations"], s["seed"]): s for s in reference_plan()}
    for spec in plan:
        if spec["case_name"] == "small_batch" or spec["seed"] == 10:
            continue
        previous = original[spec["csv_name"], spec["max_evaluations"], spec["seed"]]
        assert previous["starting_points"] == spec["starting_points"]
        assert previous["initial_design_sha256"] == spec["initial_design_sha256"]
    column = next(s for s in plan if s["case_name"] == "column" and s["seed"] == 10)
    assert column["starting_points"] == [[10, 3], [13, 6], [8, 9]]
    from fmqa_benchmark.grid_protocol import reference_grid_plan
    qhd.configure("grid")
    old_grid = {s["job_id"]: s for s in reference_grid_plan()}
    assert len(qhd.plan()) == 1050
    for spec in qhd.plan():
        previous = old_grid[spec["job_id"].removesuffix("_pytorch")]
        assert spec["starting_points"] == previous["starting_points"]
        assert spec["max_evaluations"] == previous["max_evaluations"]
    qhd.configure("all")
    assert len(qhd.plan()) == 1190


def test_vendor_files_are_exact_github_blobs():
    meta = qhd_surrogate.verify_sources()
    for name, digest in meta["github_blob_sha"].items():
        raw = (qhd_surrogate.VENDOR / name).read_bytes()
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == digest


def test_adapter_matches_direct_native_training_and_bqm_energies():
    native()
    import numpy as np
    import torch
    module, _ = qhd_surrogate.upstream()
    bits, target = ["00", "01", "11"], [1., .5, 0.]
    torch.manual_seed(37)
    direct = module.FMBQM.from_data(np.array([[int(b) for b in x] for x in bits]),
                                  np.array(target), num_epoch=50, learning_rate=.01)
    wrapped = qhd_surrogate.train(bits, target, seed=37, epochs=50, learning_rate=.01)
    repeated = qhd_surrogate.train(bits, target, seed=37, epochs=50, learning_rate=.01)
    assert dict(direct.linear) == dict(wrapped.linear) == dict(repeated.linear)
    assert dict(direct.quadratic) == dict(wrapped.quadratic) == dict(repeated.quadratic)
    assert direct.offset == wrapped.offset == repeated.offset
    assert all(p.dtype == torch.float32 and p.device.type == "cpu" for p in wrapped.fm.parameters())
    bias, linear, quadratic = wrapped.fm.get_bhQ()
    np.fill_diagonal(quadratic, linear)
    scale = np.max(np.abs(quadratic))
    for x in itertools.product((0, 1), repeat=2):
        predicted = wrapped.fm(torch.tensor([x], dtype=torch.float32)).item()
        assert wrapped.energy(dict(enumerate(x))) == pytest.approx(predicted / scale, abs=1e-5)
    assert qhd_surrogate.cpu_settings()["threads"] == qhd_surrogate.cpu_settings()["interop_threads"] == 1


def test_native_paths_are_deterministic_and_infeasible_costs_are_attached(experiment, tmp_path):
    native()
    spec = qhd.plan()[0]
    spec = {**spec, "settings": {**spec["settings"], "epochs": 10, "num_reads": 3, "num_sweeps": 20}}
    runs, events = [], []
    for i in range(2):
        directory = tmp_path / str(i)
        directory.mkdir()
        result = runner.fmqa_lookup(spec, {}, directory)
        runs.append(result)
        events.append(jsonl(directory / result["trace"]["path"])[1:-1])
        assert result["status"] == "completed" and result["result_record"]["method"] == qhd.RESULT_METHOD
    assert [e["point"] for e in events[0]] == [e["point"] for e in events[1]]
    assert len(events[0]) == 10 and [e["point"] for e in events[0][:3]] == spec["starting_points"]
    assert events[0][0]["lookup_feasible"] is False
    callbacks = [{**e, "job_id": spec["job_id"]} for e in events[0]]
    stats = qhd.report_costs(tmp_path, [{**runs[0], "spec": spec}], callbacks)
    assert stats["callbacks_with_point_cost"] == 10 and stats["callbacks_missing_point_cost"] == 0
    proposals = jsonl(tmp_path / "0/proposals.jsonl")
    assert len(proposals) == 7
    assert [p["selected_point"] for p in proposals] == [e["point"] for e in events[0][3:]]


def test_grid_cost_coverage_and_missing_process_costs_are_explicit(experiment, tmp_path):
    points = qhd.measured_points()
    assert sum(key[0] == "grid" for key in points) == 20181
    assert sum(key[0] == "small_batch" for key in points) == 27
    # A missing measurement must never turn into a zero-cost completion estimate.
    spec = {**qhd.plan()[0], "case_name": "column", "csv_name": "column_test.csv"}
    result = {"spec": spec, "status": "completed", "result_record": {
        "total_evals": 1, "wall_time_s": 1., "found_optimum": False}}
    event = {"job_id": spec["job_id"], "point": [99, 99], "objective_wall_s": .01, "lookup_feasible": False}
    summary = qhd.report_costs(tmp_path, [result], [event])
    assert summary["callbacks_missing_point_cost"] == 1
    assert qhd.rows(str(tmp_path / "completion_estimates.csv"))[0]["estimated_completion_s"] == ""


def test_native_grid_callbacks_keep_original_starts_and_have_measured_costs(experiment, tmp_path):
    native()
    qhd.configure("grid", [0])
    spec = next(s for s in qhd.plan() if s["max_evaluations"] == 10)
    spec = {**spec, "settings": {**spec["settings"], "epochs": 10, "num_reads": 3, "num_sweeps": 20}}
    result = runner.fmqa_lookup(spec, {}, tmp_path)
    events = jsonl(tmp_path / result["trace"]["path"])[1:-1]
    assert len(events) == 10
    assert [e["point"] for e in events[:3]] == spec["starting_points"]
    summary = qhd.report_costs(tmp_path, [{**result, "spec": spec}], [{**e, "job_id": spec["job_id"]} for e in events])
    assert summary["callbacks_with_point_cost"] == 10 and summary["callbacks_missing_point_cost"] == 0


def test_fresh_worker_resume_and_extracted_bundle(experiment, tmp_path):
    native()
    # One full-budget seed through the actual coordinator/preflight/worker boundary.
    completed = subprocess.run([sys.executable, "process_followup_runner.py", "run", "--experiment", "fmqa_qhd",
        "--scope", "small_batch", "--seeds", "0", "--allow-other-host", "--fmqa-python", sys.executable,
        "--output-root", str(tmp_path / "runs")], cwd=qhd.ROOT, capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    directory = next(p for p in (tmp_path / "runs").glob("fmqa_qhd_*") if p.is_dir())
    summary = read(directory / "summary.json")
    assert summary["completed_runs"] == 1 and summary["all_completed"]
    assert summary["callbacks_with_point_cost"] == 10
    qhd.configure("small_batch", [0])
    spec = qhd.plan()[0]
    previous = runner.saved_result(directory / "jobs" / spec["job_id"], spec)
    assert runner.launch(directory, spec, read(directory / "run.json")["config"], True) == previous
    bundle = tmp_path / "qhd.zip"
    runner.bundle(bundle)
    with zipfile.ZipFile(bundle) as zipped:
        assert zipped.testzip() is None
        assert not any("bamlice" in n or "/.venv" in n for n in zipped.namelist())
        zipped.extractall(tmp_path / "extract")
    extracted = tmp_path / "extract" / qhd.BUNDLE_FOLDER
    manifest = read(extracted / "BUNDLE_MANIFEST.json")
    for name, digest in manifest["source_files_sha256"].items():
        assert hashlib.sha256((extracted / name).read_bytes()).hexdigest() == digest
    output = subprocess.run([sys.executable, "process_followup_runner.py", "plan", "--experiment", "fmqa_qhd",
                             "--scope", "all"], cwd=extracted, capture_output=True, text=True, check=True)
    assert len(json.loads(output.stdout)) == 1190
