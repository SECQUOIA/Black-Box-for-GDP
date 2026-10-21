"""No licensed solvers: immutable inputs, callbacks, sampling, resume and reports."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from review_comparison import build, runner, worker
from review_comparison.common import check_settings, read, save, sha, verify


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    if (root / "inventory.json").exists():
        return root
    temporary = tmp_path_factory.mktemp("comparison-package")
    package = build.build(temporary / "bundle.zip")
    with zipfile.ZipFile(package) as z:
        z.extractall(temporary / "extracted")
    return temporary / "extracted/review_comparison_runner"


def test_complete_frozen_plan_cost_inventory_and_protocol(bundle):
    report = runner.check_inputs(bundle)
    assert report["planned_jobs"] == 3430
    assert report["methods"] == {
        "rbfopt_msrsm_genetic": 1190,
        "uniform_without_replacement": 1190,
        "bam_predetermined_uniform": 1050,
    }
    assert report["pilot_jobs"] == 24
    assert not report["missing_costs"]
    assert (
        sum(
            r["points"]
            for r in report["coordinate_inventory"]
            if r["scope"] == "process"
        )
        == 2455
    )
    assert (
        sum(r["points"] for r in report["coordinate_inventory"] if r["scope"] == "grid")
        == 20181
    )
    assert not report["server_runtime_verified"]
    plans = read(bundle / "plan.json")
    assert {j["seed"] for j in plans} == set(range(10))
    for j in plans:
        assert j["starts"] == j["original_spec"].get(
            "starts", j["original_spec"].get("starting_points")
        )
        assert j["reference_settings"]["global_search_method"] == "solver"
        assert j["hard_seconds"] == (0 if j["scope"] == "grid" else 2100)


def test_uniform_stream_and_archived_bam_prefix_preserve_repeats(bundle):
    jobs = read(bundle / "plan.json")
    for job in jobs:
        if job["method"] == "rbfopt_msrsm_genetic":
            continue
        points, settings = worker.sampling_points(job)
        assert points[:3] == job["starts"]
        prefix = 3 + (
            len(job["predetermined"])
            if job["method"] == "bam_predetermined_uniform"
            else 0
        )
        assert len(points) == job["budget"]
        assert len({tuple(p) for p in points[prefix:]}) == len(points[prefix:])
        assert not {tuple(p) for p in points[:prefix]} & {
            tuple(p) for p in points[prefix:]
        }
        assert worker.sampling_points(job) == (points, settings)
    # Do not deduplicate a predetermined visit even when it repeats an initial point.
    job = copy.deepcopy(
        next(
            j
            for j in jobs
            if j["method"] == "bam_predetermined_uniform" and j["budget"] == 30
        )
    )
    job["starts"][0] = job["predetermined"][0]
    points, _ = worker.sampling_points(job)
    assert points[0] == points[3]
    assert len(points) == 30


def test_settings_gate_rejects_any_extra_change():
    old = {"global_search_method": "solver", "rbf": "auto", "max_evaluations": 10}
    new = {**old, "global_search_method": "genetic"}
    assert check_settings(old, new) == {"global_search_method": ["solver", "genetic"]}
    with pytest.raises(ValueError, match="Unexpected"):
        check_settings(old, {**new, "max_evaluations": 9})


@pytest.mark.parametrize(
    "case,budget,method",
    [
        ("cstr_5", 8, "uniform_without_replacement"),
        ("column", 16, "uniform_without_replacement"),
        ("dynamic", 50, "uniform_without_replacement"),
        ("ackley", 30, "bam_predetermined_uniform"),
    ],
)
def test_real_sampling_through_frozen_callbacks(bundle, tmp_path, case, budget, method):
    job = next(
        j
        for j in read(bundle / "plan.json")
        if j["case"] == case
        and j["budget"] == budget
        and j["method"] == method
        and j["seed"] == 0
    )
    config = {"cpu": None, "bonmin": "unused", "ipopt": "unused"}
    save(tmp_path / "spec.json", job)
    save(tmp_path / "config.json", config)
    # New interpreter isolates the archived modules, import guards and trace context.
    script = """from pathlib import Path
from review_comparison.common import read
from review_comparison.worker import run
import sys
root,temp=map(Path,sys.argv[1:])
run(root,read(temp/'spec.json'),read(temp/'config.json'),temp/'attempt',validate_runtime=False)
"""
    proc = subprocess.run(
        [sys.executable, "-c", script, str(bundle), str(tmp_path)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(bundle)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    r = read(tmp_path / "attempt/result.json")
    events = [
        json.loads(line)
        for line in (tmp_path / "attempt/evaluations.jsonl").read_text().splitlines()
    ]
    assert len(events) == r["evaluations"] == budget
    assert not r["missing_cost_callbacks"]
    assert r["sum_point_cost_s"] == sum(e["historical_point_cost_s"] for e in events)
    assert (
        r["retained_search_wall_s"] == r["recorded_search_wall_s"] - r["lookup_wall_s"]
    )
    assert r["incumbent_extraction_wall_s"] >= 0
    if job["scope"] == "process":
        assert events[-1]["callback_exit"] == "budget_stop"
        assert events[-1]["value_returned_to_optimizer"] is False
        assert r["status"] == "budget_completed"
    if case == "column":
        assert any(not e["accepted"] for e in events)
        assert all(e["method_value"] == 1e6 for e in events if not e["accepted"])
    if case == "cstr_5":
        assert any(e["method_value_kind"] == "+inf" for e in events)


def test_terminal_observation_missing_cost_and_repeated_cost(bundle, monkeypatch):
    job = next(j for j in read(bundle / "plan.json") if j["case"] == "column")
    rows = {(7, 1): (1.0, {"objective": "3", "accepted": "True", "status": "accepted"})}
    monkeypatch.setattr(worker, "cost_data", lambda *a: (rows, 0.0))
    events = [
        {
            "index": i,
            "point": [7, 1] if i < 3 else [8, 2],
            "accepted": i < 3,
            "raw_objective": 3.0 if i < 3 else None,
            "lookup_wall_s": 0.01,
            "value_returned_to_optimizer": False,
        }
        for i in (1, 2, 3)
    ]
    job = {**job, "starts": [[7, 1], [7, 1], [8, 2]], "budget": 3}
    ledger, result = worker.summarize_events(
        bundle,
        job,
        events,
        {"status": "budget_completed", "recorded_search_wall_s": 1.0},
    )
    assert (
        ledger[0]["historical_point_cost_s"]
        == ledger[1]["historical_point_cost_s"]
        == 1.0
    )
    assert result["sum_point_cost_s"] is None and result["missing_cost_callbacks"] == 1
    assert result["best_objective"] == 3 and result["target_observed"]
    assert result["reconstructed_total_s"] is None


def test_resume_first_failure_preserved_and_checksum_tampering_fails(tmp_path):
    job = {"job_id": "test"}
    a = tmp_path / "jobs/test/attempt_1"
    a.mkdir(parents=True)
    save(a / "job.json", job)
    save(a / "result.json", {"status": "execution_failed"})
    save(a / "seal.json", {n: sha(a / n) for n in ("job.json", "result.json")})
    b = tmp_path / "jobs/test/attempt_2"
    b.mkdir()
    save(b / "job.json", job)
    save(b / "result.json", {"status": "completed"})
    save(b / "seal.json", {n: sha(b / n) for n in ("job.json", "result.json")})
    assert runner.selected_result(tmp_path, job)[0] == a
    save(a / "result.json", {"status": "completed"})
    with pytest.raises(ValueError, match="modified"):
        runner.selected_result(tmp_path, job)


def test_lock_prevents_duplicate_controller(tmp_path):
    with runner.locked(tmp_path):
        with pytest.raises(RuntimeError, match="active"):
            with runner.locked(tmp_path):
                pass


def test_package_source_changes_fail_before_resume(bundle, tmp_path):
    save(
        tmp_path / "inventory.json",
        {"files_sha256": {"plan.json": sha(bundle / "plan.json")}},
    )
    (tmp_path / "plan.json").write_bytes((bundle / "plan.json").read_bytes() + b"\n")
    with pytest.raises(ValueError, match="changed"):
        verify(tmp_path)


def test_old_analysis_does_not_imply_new_runs_complete(bundle, tmp_path):
    from review_comparison.analysis import historical, summarize

    records = historical(bundle)
    assert len(records) == 4760
    p = [r for r in records if r["scope"] == "process"]
    assert sum(r["category"] == "target_reached" for r in p) == 291
    assert sum(r["category"] == "execution_failed" for r in p) == 1
    output = summarize(bundle, tmp_path, read(bundle / "plan.json"))
    report = read(output / "interpretation.json")
    assert not report["new_data_complete"]
    assert read(output / "progress.json")["status_counts"] == {"not_run": 3430}


def test_cluster_bootstrap_preserves_one_problem_vector():
    from review_comparison.analysis import paired_interval

    # With a single Grid problem, resampling intact clusters cannot resample its seeds.
    assert paired_interval([[1, -1] * 5], clustered=True) == (0, 0)
    lo, hi = paired_interval([[1, -1] * 5], clustered=False)
    assert lo < 0 < hi


def test_unknown_attempt_time_not_zero_filled(tmp_path):
    job = {"job_id": "partial"}
    attempt = tmp_path / "jobs/partial/attempt_1"
    attempt.mkdir(parents=True)
    save(attempt / "process.json", {"pid": 123})
    assert runner.attempt_costs(tmp_path, job)["all_attempts_worker_wall_s"] is None
    assert runner.attempt_costs(tmp_path, job)["attempts_with_unknown_worker_time"] == 1


def test_environment_gate_rejects_different_binary(monkeypatch):
    import cpu_affinity

    monkeypatch.setattr(cpu_affinity, "pin_cpu", lambda cpu: cpu)
    monkeypatch.setattr(worker.platform, "python_version", lambda: "3.11.16")
    monkeypatch.setattr(worker.platform, "node", lambda: "dantzig.ecn.purdue.edu")
    for key, value in worker.THREADS.items():
        monkeypatch.setenv(key, value)
    job = {
        "method": "rbfopt_msrsm_genetic",
        "reference_runtime": {
            "versions": {},
            "python": "3.11.16",
            "host": "dantzig.ecn.purdue.edu",
            "solvers": {"bonmin": "wrong"},
        },
        "reference_settings": {"minlp_solver_path": sys.executable},
    }
    with pytest.raises(ValueError, match="bonmin executable path/hash"):
        worker.runtime(
            job, {"cpu": 0, "bonmin": sys.executable, "ipopt": sys.executable}
        )


def test_no_accepted_observation_retains_original_failure_category(bundle, monkeypatch):
    job = next(j for j in read(bundle / "plan.json") if j["case"] == "column")
    monkeypatch.setattr(
        worker,
        "cost_data",
        lambda *args: (
            {
                (7, 1): (
                    1.0,
                    {
                        "accepted": "False",
                        "objective": "",
                        "status": "logical_infeasible",
                    },
                ),
                (8, 1): (
                    2.0,
                    {"accepted": "True", "objective": "3", "status": "accepted"},
                ),
            },
            0.0,
        ),
    )
    events = [
        {
            "index": 1,
            "point": [7, 1],
            "accepted": False,
            "raw_objective": None,
            "lookup_wall_s": 0.01,
            "value_returned_to_optimizer": True,
        }
    ]
    job = {**job, "starts": [[7, 1], [8, 1], [8, 2]]}
    _, result = worker.summarize_events(
        bundle, job, events, {"status": "completed", "recorded_search_wall_s": 1.0}
    )
    assert result["category"] == "execution_failed"
    assert result["status"] == "completed"
    assert result["error"] == "no_accepted_observation"
