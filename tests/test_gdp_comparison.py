"""Reformulation parity, original GDP validation and bounded process recovery."""
# ruff: noqa: E402 -- GDP dependencies are optional for the base benchmark.

import ast
import csv
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import zipfile

import pytest

pytest.importorskip("pyomo.environ")
pytest.importorskip("networkx")
import pyomo.environ as pyo
from pyomo.gdp import Disjunct, Disjunction
from pyomo.opt import SolverResults, TerminationCondition as tc

import gdp_compare as runner
from gdp_models import comparison as impl


def toy():
    m = pyo.ConcreteModel()
    m.x = pyo.Var(bounds=(0, 4), initialize=1)
    m.a = Disjunct()
    m.a.c = pyo.Constraint(expr=m.x >= 1)
    m.b = Disjunct()
    m.b.c = pyo.Constraint(expr=m.x >= 3)
    m.choice = Disjunction(expr=[m.a, m.b])
    m.obj = pyo.Objective(expr=m.x)
    m.a.indicator_var.set_value(True)
    m.b.indicator_var.set_value(False)
    return m


def test_original_gdp_validation_checks_only_chosen_disjunct_and_integer_logic():
    m = toy()
    assert impl.validate_original(m)["has_feasible_solution"]
    m.a.indicator_var.set_value(False)
    m.b.indicator_var.set_value(True)
    assert not impl.validate_original(m)["has_feasible_solution"]
    m.x.set_value(3)
    assert impl.validate_original(m)["has_feasible_solution"]
    m.a.indicator_var.set_value(True)
    assert not impl.validate_original(m)["has_feasible_solution"]
    m.a.indicator_var.set_value(False)
    m.b.binary_indicator_var.set_value(0.5)
    assert not impl.validate_original(m)["has_feasible_solution"]


def test_missing_candidate_values_cannot_reuse_previous_incumbent():
    reference, source = toy(), toy()
    assert impl.validate_original(reference)["has_feasible_solution"]
    source.x.set_value(None)
    impl.transfer_values(source, reference)
    assert reference.x.value is None
    assert not impl.validate_original(reference)["has_feasible_solution"]


def test_small_batch_exponential_bounds_are_implied_by_original_volume_and_time_constraints():
    import math
    template = impl.build_template("small_batch")
    m = template.model
    for i in m.i:
        maximum_batch_log = min(math.log(pyo.value(m.vupp) / pyo.value(m.s[i, j])) for j in m.j)
        maximum_cycle_log = maximum_batch_log + math.log(pyo.value(m.h) / pyo.value(m.q[i]))
        assert m.b[i].ub <= maximum_batch_log + 1e-9
        assert m.tl[i].ub <= maximum_cycle_log + 1e-9
    assert template.metadata["globally_implied_bounds"]


@pytest.mark.parametrize("case,size", [("cstr", n) for n in runner.CSTR_SIZES]
                         + [(c, None) for c in impl.CASES if c != "cstr"])
def test_full_original_models_write_both_reformulations_without_fixing_choices(case, size, tmp_path):
    template = impl.build_template(case, cstr_size=size or 30)
    if case == "cstr":
        assert len(template.model.N) == len(template.model.YF) == len(template.model.YR) == size
        assert template.metadata["cstr_size"] == size
        assert template.metadata["instance_id"] == f"cstr_{size}"
        if size < 30:
            assert template.metadata["initialization"] == f"gdp/dsda/cstr_{size}_initialization.json"
    choices_before = [v.name for v in template.model.component_data_objects(pyo.Var, descend_into=impl.DESCEND)
                      if v.is_binary() and not v.fixed]
    assert choices_before
    for method in ("bigm", "hull"):
        model = template.model.clone()
        impl.reformulate(model, method)
        assert not list(model.component_data_objects(Disjunction, active=True))
        assert any(v.is_binary() and not v.fixed for v in model.component_data_objects(pyo.Var))
        model.write(str(tmp_path / f"{case}_{method}.gms"), format="gams",
                    io_options={"solver": "baron", "mtype": "minlp"})
    if case == "dynamic":
        second = impl.build_template(case)
        assert second.metadata["dynamic_preparation"]["preparation_id"] == template.metadata["dynamic_preparation"]["preparation_id"]
        assert not second.metadata["dynamic_preparation"]["included_in_point_total_wall_s"]


def test_gams_wrapper_honors_executable_remaining_budget_and_raw_time_limit(tmp_path, monkeypatch):
    context = impl.SolveContext("/explicit/gams", tmp_path, time.monotonic() + 20)
    monkeypatch.setattr(impl, "CONTEXT", context)
    calls = []

    def solve(self, model, **kw):
        calls.append(kw)
        assert self.executable() == "/explicit/gams"
        assert kw["solver"] == "ipopt" and "option threads=1;" in kw["add_options"]
        assert "linear_solver mumps" in (Path(kw["tmpdir"]) / "ipopt.opt").read_text()
        (Path(kw["tmpdir"]) / "resultsstat.dat").write_text("name value\nSOLVESTAT 3\nMODELSTAT 2\n")
        result = SolverResults()
        result.solver.termination_condition = tc.locallyOptimal
        result.solver.status = "ok"
        result.problem.lower_bound = 0
        result.problem.upper_bound = 1
        return result

    monkeypatch.setattr(impl.GAMSShell, "solve", solve)
    result = impl.TimedGAMS().solve(toy(), solver="ipopt", mtype="nlp", load_solutions=False)
    assert result.solver.termination_condition == tc.maxTimeLimit
    assert context.calls[0]["limit_s"] < 20
    context.deadline -= 5
    impl.TimedGAMS().solve(toy(), solver="ipopt", mtype="nlp", load_solutions=False)
    assert context.calls[1]["limit_s"] < context.calls[0]["limit_s"] - 4
    assert len((tmp_path / "solver_calls.jsonl").read_text().splitlines()) == 2


def test_baron_records_numerical_options_and_preserves_failure_diagnostics(tmp_path, monkeypatch):
    context = impl.SolveContext("/explicit/gams", tmp_path, time.monotonic() + 20,
                                baron_options=("LPSol 3", "NLPSol 9", "LBTTDo 0"))
    monkeypatch.setattr(impl, "CONTEXT", context)

    def solve(self, model, **kw):
        path = Path(kw["tmpdir"])
        assert not kw["warmstart"]
        assert (path / "baron.opt").read_text().splitlines() == list(context.baron_options)
        (path / "resultsstat.dat").write_text("name value\nSOLVESTAT 4\nMODELSTAT 19\n")
        (path / "output.lst").write_text("diagnostic listing")
        result = SolverResults()
        result.solver.termination_condition = tc.infeasible
        result.solver.status = "ok"
        return result

    monkeypatch.setattr(impl.GAMSShell, "solve", solve)
    result = impl.TimedGAMS().solve(toy(), solver="baron", mtype="minlp")
    assert result.solver.termination_condition == tc.internalSolverError
    assert context.calls[0]["solver_option_file"] == list(context.baron_options)
    assert (tmp_path / "call_00001_diagnostic.lst").read_text() == "diagnostic listing"


def stalled_worker(template, method, directory, config, deadline):
    os.setsid()
    runner.save(directory / "result.json", {"case": "small_batch", "method": method,
                "status": "running", "has_feasible_solution": True, "objective": 1.0,
                "global_optimality_certified": False})
    time.sleep(30)


def finished_worker(template, method, directory, config, deadline):
    os.setsid()
    runner.save(directory / "result.json", {"case": "small_batch", "method": method,
                "status": "finished", "has_feasible_solution": True, "objective": 1.0,
                "global_optimality_certified": False})


@pytest.mark.skipif("fork" not in runner.multiprocessing.get_all_start_methods(), reason="POSIX runner")
@pytest.mark.parametrize("case,size", [("small_batch", None), ("cstr", 5)])
def test_watchdog_preserves_incumbent_and_next_job_and_zip(tmp_path, case, size):
    instance_id = f"cstr_{size}" if size else case
    config = {"time_limit": 0.25, "cases": [case], "cstr_sizes": [5], "methods": ["ric", "gloa"]}
    runner.save(tmp_path / "run.json", {"kind": runner.KIND, "config": config})
    template = SimpleNamespace(metadata={"case": case, "cstr_size": size, "instance_id": instance_id})
    first = runner.run_job(template, "ric", tmp_path / "jobs" / instance_id / "ric", config, target=stalled_worker)
    assert first["hard_time_limit_reached"] and first["has_feasible_solution"]
    assert first["objective"] == 1 and not first["global_optimality_certified"]
    assert first["instance_id"] == instance_id and first["cstr_size"] == size
    second = runner.run_job(template, "gloa", tmp_path / "jobs" / instance_id / "gloa", config, target=finished_worker)
    assert second["status"] == "finished" and first["worker_pid"] != second["worker_pid"]
    summary = runner.pack(tmp_path)
    assert summary["complete"] and summary["feasible_jobs"] == 2
    with zipfile.ZipFile(tmp_path.with_name(tmp_path.name + ".zip")) as archive:
        assert archive.testzip() is None
        for line in archive.read(tmp_path.name + "/SHA256SUMS").decode().splitlines():
            expected, name = line.split("  ", 1)
            assert hashlib.sha256(archive.read(tmp_path.name + "/" + name)).hexdigest() == expected


def test_comparison_bundle_is_small_and_contains_no_results_or_solver_licenses(tmp_path):
    path = tmp_path / "comparison.zip"
    runner.bundle(path)
    assert path.stat().st_size < 100_000
    with zipfile.ZipFile(path) as archive:
        assert all(name.startswith("gdp_comparison_runner/") for name in archive.namelist())
        assert "gdp_comparison_runner/cpu_affinity.py" in archive.namelist()
        assert not any("/results/" in name or name.endswith(".lic") for name in archive.namelist())
        for line in archive.read("gdp_comparison_runner/COMPARISON_RUNNER_SHA256SUMS").decode().splitlines():
            expected, name = line.split("  ", 1)
            assert hashlib.sha256(archive.read("gdp_comparison_runner/" + name)).hexdigest() == expected


def test_empty_archive_keeps_pending_jobs(tmp_path):
    runner.save(tmp_path / "run.json", {"kind": runner.KIND,
                "config": {"cases": ["cstr"], "methods": ["bigm", "hull"]}})
    summary = runner.pack(tmp_path)
    assert not summary["complete"] and summary["completed_jobs"] == 0
    assert len(summary["pending_jobs"]) == 2
    assert json.loads((tmp_path / "summary.json").read_text()) == summary


def test_unfinished_checkpoint_is_not_counted_as_completed(tmp_path):
    runner.save(tmp_path / "run.json", {"kind": runner.KIND,
                "config": {"cases": ["cstr"], "methods": ["ric"]}})
    job = tmp_path / "jobs/cstr/ric"
    job.mkdir(parents=True)
    runner.save(job / "result.json", {"case": "cstr", "method": "ric", "status": "running",
                "has_feasible_solution": True, "global_optimality_certified": False, "objective": 3.0})
    summary = runner.pack(tmp_path)
    assert not summary["complete"] and summary["completed_jobs"] == 0
    assert summary["feasible_jobs"] == 1 and summary["pending_jobs"] == [["cstr", "ric"]]


def test_default_matrix_matches_dfo_cstr_sizes_and_contains_36_distinct_jobs():
    tree = ast.parse((runner.ROOT / "case_study_benchmark.py").read_text())
    sizes = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "DEFAULT_CSTR_GRID_SIZES" for t in node.targets))
    assert runner.CSTR_SIZES == sizes == (5, 10, 15, 20, 25, 30)
    specs = runner.planned_instances({"cases": runner.CASES, "cstr_sizes": runner.CSTR_SIZES})
    jobs = {(s["instance_id"], method) for s in specs for method in runner.METHODS}
    assert len(jobs) == 36
    assert [s["cstr_size"] for s in specs if s["case"] == "cstr"] == list(sizes)


def test_size_specific_results_stay_distinct_in_summary_csv_and_archive(tmp_path):
    runner.save(tmp_path / "run.json", {"kind": runner.KIND,
                "config": {"cases": ["cstr"], "cstr_sizes": [5, 30], "methods": ["ric", "hull"]}})
    for size in (5, 30):
        job = tmp_path / f"jobs/cstr_{size}/ric"
        job.mkdir(parents=True)
        runner.save(job / "result.json", {"case": "cstr", "cstr_size": size,
                    "instance_id": f"cstr_{size}", "method": "ric", "status": "finished",
                    "objective": float(size), "has_feasible_solution": True})
    summary = runner.pack(tmp_path)
    assert summary["planned_jobs"] == 4 and summary["completed_jobs"] == 2
    assert summary["pending_jobs"] == [["cstr_30", "hull"], ["cstr_5", "hull"]]
    with (tmp_path / "summary.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert {(r["instance_id"], r["cstr_size"]) for r in rows} == {("cstr_5", "5"), ("cstr_30", "30")}
    with zipfile.ZipFile(tmp_path.with_name(tmp_path.name + ".zip")) as archive:
        assert f"{tmp_path.name}/jobs/cstr_5/ric/result.json" in archive.namelist()
        assert f"{tmp_path.name}/jobs/cstr_30/ric/result.json" in archive.namelist()
    bad = summary["results"][0].copy()
    bad["cstr_size"] = 99
    runner.save(tmp_path / f"jobs/{bad['instance_id']}/ric/result.json", bad)
    with pytest.raises(ValueError, match="planned model size"):
        runner.summarize(tmp_path)
