"""Lookup-harness checks for the NOMAD and MISO experiment; solver tests skip without the solvers."""

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import zipfile

import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "experiments/mixed_integer_dfo/run.py"
JOBS = ["grid_ackley_B10_seed0", "cstr_30_B43_seed0", "column_logical_B13_seed6", "dynamic_B12_seed2"]


def load_runner():
    spec = importlib.util.spec_from_file_location("mixed_integer_dfo", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(tmp_path, methods, jobs=JOBS):
    runner = load_runner()
    out = tmp_path / "_".join(methods)
    assert runner.main(["--cpu", "none", "--no-zip", "--output", str(out), "--methods", *methods, "--jobs", *jobs]) == 0
    return out


def results(out, method, jobs=JOBS):
    return {j: json.loads((out / "runs" / f"{j}__{method}" / "result.json").read_text()) for j in jobs}


def test_uniform_harness_accounting(tmp_path):
    out = run(tmp_path, ["uniform"])
    for job, r in results(out, "uniform").items():
        events = [json.loads(x) for x in (out / "runs" / f"{job}__uniform" / "callbacks.jsonl").read_text().splitlines()]
        assert [e["point"] for e in events[:3]] == r["spec"]["starts"]
        assert r["evaluations"] == len(events) == r["spec"]["budget"]
        assert r["point_cost_s"] == pytest.approx(sum(e["point_cost_s"] for e in events))
        assert r["nlp_solves"] <= r["evaluations"]
    # Seeds whose shared initial design contains the target hit at a shared start.
    assert results(out, "uniform")["column_logical_B13_seed6"]["first_hit"] <= 3
    assert results(out, "uniform")["cstr_30_B43_seed0"]["first_hit"] <= 3


def test_point_costs_match_published_records():
    """Archived D-SDA paths priced with the runner's tables reproduce the published point costs."""
    runner = load_runner()
    shared = runner.shared
    published = {(r["scope"], r["case"], r["budget"], r["seed"]): float(r["point_cost_s"])
                 for r in csv.DictReader(open(runner.PUBLISHED)) if r["method"] == "dsda"}
    grid_costs = {(r["grid_name"], tuple(json.loads(r["point"]))): float(r["point_wall_s"])
                  for r in shared.read_csv(runner.GRID_COSTS)}
    coverage = {(r["case"], tuple(json.loads(r["coordinates"]))): r["status"] for r in shared.read_csv(runner.COVERAGE)}
    with tempfile.TemporaryDirectory() as scratch:
        package, _ = shared.extract_package(shared.ARCHIVE, scratch)
        jobs = {j["spec"]["job_id"]: j for j in shared.read_json(package / "inputs/jobs.json")}
        for job_id in ["cstr_30_B43_seed0_dsda", "dynamic_B50_seed3_dsda", "column_logical_B13_seed6_dsda",
                       "grid_ackley_B100_seed4_dsda", "grid_rosenbrock_B30_seed7_dsda"]:
            job = jobs[job_id]
            _, costs, _ = runner.load_responses(job, package, grid_costs, coverage)
            with zipfile.ZipFile(shared.ARCHIVE) as z:
                lines = z.read(f"{shared.PREFIX}runs/{job_id}/callbacks.jsonl").decode().splitlines()
            points = [tuple(json.loads(x)["point"]) for x in lines]
            s = job["spec"]
            assert sum(costs[p] for p in points) == pytest.approx(published[s["scope"], s["case"], str(s["budget"]), str(s["seed"])])


@pytest.mark.parametrize("method,module", [("nomad", "PyNomad"), ("miso", "soogo")])
def test_solver_runs_are_valid_and_reproducible(tmp_path, method, module):
    pytest.importorskip(module)
    jobs = ["grid_ackley_B30_seed0", "cstr_15_B22_seed1"]
    first = run(tmp_path / "a", [method], jobs)
    second = run(tmp_path / "b", [method], jobs)
    for job in jobs:
        a = (first / "runs" / f"{job}__{method}" / "callbacks.jsonl").read_text().splitlines()
        b = (second / "runs" / f"{job}__{method}" / "callbacks.jsonl").read_text().splitlines()
        assert [json.loads(x)["point"] for x in a] == [json.loads(x)["point"] for x in b]
        r = results(first, method, [job])[job]
        assert 3 <= r["evaluations"] <= r["spec"]["budget"] and r["overruns"] == 0 and not r["invalid_points"]


def test_miso_design_spans_three_dimensional_space(tmp_path):
    pytest.importorskip("soogo")
    job = "small_batch_B10_seed0"
    out = run(tmp_path, ["miso"], [job])
    r = results(out, "miso", [job])[job]
    events = [json.loads(x) for x in (out / "runs" / f"{job}__miso" / "callbacks.jsonl").read_text().splitlines()]
    assert r["status"] == "completed" and r["solver"]["design_points"] == 4
    assert [e["origin"] for e in events[:4]] == ["shared_start"] * 3 + ["miso_design"]
    assert r["evaluations"] == r["spec"]["budget"] and r["overruns"] == 0 and not r["invalid_points"]


def test_native_crash_is_recorded_as_failure(tmp_path):
    """A worker killed by a signal keeps its evaluations and counts as an execution failure."""
    import os
    import signal

    runner = load_runner()
    shared = runner.shared

    def crashing(lookup, seed, log):
        runner.shared_starts(lookup)
        os.kill(os.getpid(), signal.SIGSEGV)

    runner.ADAPTERS["crash"] = crashing
    grid_costs = {(r["grid_name"], tuple(json.loads(r["point"]))): float(r["point_wall_s"])
                  for r in shared.read_csv(runner.GRID_COSTS)}
    coverage = {(r["case"], tuple(json.loads(r["coordinates"]))): r["status"] for r in shared.read_csv(runner.COVERAGE)}
    with tempfile.TemporaryDirectory() as scratch:
        package, _ = shared.extract_package(shared.ARCHIVE, scratch)
        job = next(j for j in shared.read_json(package / "inputs/jobs.json")
                   if j["spec"]["job_id"] == "cstr_15_B22_seed1_dsda")
        with shared.sealed_modules(package) as (_, hit):
            result = runner.execute(job, "crash", package, tmp_path, grid_costs, coverage, hit, 60)
    assert result["status"] == f"crashed_exit_{-signal.SIGSEGV}"
    assert result["category"] == "execution_failed" and not result["hit"]
    assert result["evaluations"] == 3 and result["completion_s"] is None


def test_nomad_crash_is_accepted_only_after_identical_rerun(tmp_path):
    """A rerun with a larger cache cap replaces a crash only if it evaluates the same path."""
    import os
    import signal

    runner = load_runner()
    shared = runner.shared

    def flaky(lookup, seed, log):
        runner.shared_starts(lookup)
        lookup.evaluate([5, 5], "nomad")
        if not runner.NOMAD_EXTRA:
            os.kill(os.getpid(), signal.SIGSEGV)
        return {}

    runner.ADAPTERS["nomad"] = flaky
    grid_costs = {(r["grid_name"], tuple(json.loads(r["point"]))): float(r["point_wall_s"])
                  for r in shared.read_csv(runner.GRID_COSTS)}
    coverage = {(r["case"], tuple(json.loads(r["coordinates"]))): r["status"] for r in shared.read_csv(runner.COVERAGE)}
    with tempfile.TemporaryDirectory() as scratch:
        package, _ = shared.extract_package(shared.ARCHIVE, scratch)
        job = next(j for j in shared.read_json(package / "inputs/jobs.json")
                   if j["spec"]["job_id"] == "cstr_15_B22_seed1_dsda")
        with shared.sealed_modules(package) as (_, hit):
            result = runner.execute(job, "nomad", package, tmp_path, grid_costs, coverage, hit, 60)
    assert result["status"] == "completed_after_verified_rerun"
    assert result["evaluations"] == 4 and result["category"] != "execution_failed"
    reruns = result["solver"]["reruns"]
    assert reruns[0]["status"].startswith("crashed") and reruns[1]["same_path_as_crash"]
