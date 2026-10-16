"""Preserve the original experiment while proving auxiliary-solver use."""

import json
import subprocess
import sys
from types import SimpleNamespace
import zipfile

import pytest

import process_followup_runner as runner
import small_batch_full_domain as full
import small_batch_rbfopt_solver as experiment
from overnight_benchmark.common import jsonl, read, sha


def test_changes_only_rbfopt_search_with_same_full_domain_starts_and_budget(monkeypatch):
    originals = [spec for spec in full.plan() if spec["method"] == "rbfopt"]
    planned = experiment.plan()
    assert len(planned) == 10
    monkeypatch.setattr(runner, "EXPERIMENT", experiment)
    for old, new in zip(originals, planned):
        assert new == {**old, "settings": {**old["settings"], "global_search_method": "solver"},
                       "job_id": old["job_id"] + "_solver"}
        runner.frozen_starts(new)
    assert [spec["seed"] for spec in planned] == list(range(10))
    assert experiment.RUNTIME_ROLES == ("dfo",)


def test_solver_audit_preserves_arguments_options_return_and_exception(tmp_path, monkeypatch):
    import pyomo.environ  # noqa: F401
    import pyomo.opt
    returned = SimpleNamespace(solver=SimpleNamespace(status="ok", termination_condition="optimal"))
    seen = []

    def fake_factory(name, *args, **kwargs):
        def solve(*solve_args, **solve_kwargs):
            seen.append((name, args, kwargs, solve_args, solve_kwargs))
            if name == "ipopt":
                raise RuntimeError("native solver failure")
            return returned
        return SimpleNamespace(solve=solve, executable=lambda: kwargs["executable"], options={"max_cpu_time": 20})

    monkeypatch.setattr(pyomo.opt, "SolverFactory", fake_factory)
    path = tmp_path / "solver_calls.jsonl"
    with experiment.solver_audit(path):
        solver = pyomo.opt.SolverFactory("bonmin", executable="/solvers/bonmin", solver_io="nl")
        assert solver.solve("model", keepfiles=False, tee=False) is returned
        solver = pyomo.opt.SolverFactory("ipopt", executable="/solvers/ipopt")
        with pytest.raises(RuntimeError, match="native solver failure"):
            solver.solve("nlp")
    assert pyomo.opt.SolverFactory is fake_factory
    assert seen == [("bonmin", (), {"executable": "/solvers/bonmin", "solver_io": "nl"},
                     ("model",), {"keepfiles": False, "tee": False}),
                    ("ipopt", (), {"executable": "/solvers/ipopt"}, ("nlp",), {})]
    events = jsonl(path)
    assert events[0]["options"] == {"max_cpu_time": 20}
    assert events[-1]["exception_type"] == "RuntimeError"
    result = {"spec": experiment.plan()[0], "solver_trace": experiment.solver_trace(path)}
    assert result["solver_trace"]["calls_by_solver"] == {"bonmin": 1, "ipopt": 1}
    assert result["solver_trace"]["exceptions"] == 1
    experiment.validate_saved_result(tmp_path, result)
    path.write_text(path.read_text().replace('"max_cpu_time": 20', '"max_cpu_time": 21'))
    with pytest.raises(ValueError, match="checksum"):
        experiment.validate_saved_result(tmp_path, result)


def test_missing_or_interrupted_solver_calls_cannot_count_as_complete(tmp_path):
    path = tmp_path / "solver_calls.jsonl"
    with pytest.raises(ValueError, match="Missing or incomplete"):
        experiment.solver_trace(path)
    path.write_text('{"event":"solver_start"}\n')
    with pytest.raises(ValueError, match="Missing or incomplete"):
        experiment.solver_trace(path)


def test_bundle_is_independent_and_check_needs_no_fmqa_python(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "EXPERIMENT", experiment)
    archive = tmp_path / "runner.zip"
    runner.bundle(archive)
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        assert not any(".venv" in name or "bamlice" in name for name in zipped.namelist())
        zipped.extractall(tmp_path / "extract")
    extracted = tmp_path / "extract" / experiment.BUNDLE_FOLDER
    manifest = read(extracted / "BUNDLE_MANIFEST.json")
    assert manifest["plan"] == experiment.plan()
    for relative, digest in manifest["source_files_sha256"].items():
        assert sha(extracted / relative) == digest
    completed = subprocess.run([sys.executable, "process_followup_runner.py", "plan",
                                "--experiment", "small_batch_rbfopt_solver"],
                               cwd=extracted, capture_output=True, text=True, check=True)
    assert json.loads(completed.stdout) == experiment.plan()
    checked = []
    monkeypatch.setattr(runner, "check_environments", lambda directory, config: checked.append(config))
    assert runner.main(["check", "--experiment", "small_batch_rbfopt_solver",
                        "--output-root", str(tmp_path / "checks")]) == 0
    assert checked[0]["fmqa_python"] == ""
