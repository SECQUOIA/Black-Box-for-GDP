"""Scientific accounting, oracle isolation and durable overnight execution."""

import math
import subprocess
import sys

import pytest

from overnight_benchmark import analysis, runner, worker
from overnight_benchmark.common import point_key, save


def small_spec(method="dsda"):
    from fmqa_benchmark.protocol import reference_plan
    spec = reference_plan(cases=("small_batch",), seeds=(0,))[0]
    return {**spec, "method": method, "job_id": spec["job_id"] + "_" + method}


def test_plan_only_runs_original_three_methods():
    jobs = runner.plans()
    assert len(jobs) == len({s["job_id"] for s in jobs}) == 417
    for method in ("dsda", "rbfopt", "bam"):
        assert sum(s["method"] == method for s in jobs) == 139
    assert not any(s["method"] == "fmqa_sa" for s in jobs)
    from overnight_benchmark.common import source_files
    assert not any(p.name in {"algorithms.py", "comparison.py", "optimizer.py"} for p in source_files())


def test_original_archives_include_all_nine_exact_models_and_failed_costs():
    from overnight_benchmark.references import archived_fmqa, historical_costs
    fmqa_config, traces = archived_fmqa()
    assert len(traces) == 139 and fmqa_config["epochs"] == 1000
    config = {"solver": "gams_ipopt", "initialization": "auto", "nlp_seconds": 60}
    identity = {"gams_sha256": "11bd33943b5b2542afa73cbf3eb8a1f1b27eb1bde1ba56e85f8a262cfdd29245",
                "versions": {"pyomo": "6.10.0"}}
    costs, audit = historical_costs(config, identity)
    assert len(costs) == 1318
    assert audit["preparations"][0]["total_preparation_wall_s"] > 0
    assert {k[1] for k in costs if k[0] == "cstr"} == {5, 10, 15, 20, 25, 30}
    assert costs[("column", None, (8, 1))]["cost_s"] == pytest.approx(1.3642758801579475)
    assert not costs[("column", None, (8, 1))]["record"]["accepted"]
    keys = set(analysis.requested_points(traces))
    assert keys == {(r["spec"]["case_name"], r["spec"]["grid_size"], tuple(e["point"]))
                    for r in traces for e in r["events"]}
    assert len(keys) < 2599
    wrong, _ = historical_costs({**config, "nlp_seconds": 30}, identity)
    assert not wrong
    wrong, _ = historical_costs({**config, "solver": "baron"}, identity)
    assert not wrong


def fixed_path(monkeypatch):
    from fmqa_benchmark import protocol
    good, bad = (2, 2, 1), (1, 1, 1)
    monkeypatch.setattr(protocol, "problem", lambda _: {
        "objective": lambda p: 10. if tuple(p) == good else math.inf})
    spec = small_spec()
    events = [{"evaluation_index": i, "point": list(p), "objective_wall_s": .1,
               "completed_elapsed_s": elapsed} for i, (p, elapsed) in
              enumerate([(bad, 1), (good, 3), (bad, 8)], 1)]
    run = {"spec": spec, "events": events, "status": "completed", "wall_time_s": 10.,
           "target": 10., "source": "test", "dfo_wall_time_s": 9.5}
    costs = {point_key("small_batch", None, p): {
        "record": {"accepted": accepted, "objective": 10. if accepted else None,
                   "status": "accepted" if accepted else "preprocessing_infeasible", "termination": "not_solved"},
        "cost_s": cost, "source": "test", "source_kind": "measurement"}
        for p, accepted, cost in [(good, True, 2.), (bad, False, .5)]}
    return run, costs


def test_infeasible_and_repeated_coordinates_keep_measured_cost(monkeypatch):
    run, costs = fixed_path(monkeypatch)
    rows, ledger = analysis.timing_tables([run], costs)
    assert [e["nlp_evaluation_wall_s"] for e in ledger] == [.5, 2., .5]
    assert ledger[2]["repeated_coordinate"]
    assert rows[0]["dfo_wall_time_s"] == 9.5
    assert "estimated_total_s" not in rows[0]
    assert rows[0]["callbacks_missing_nlp_measurement"] == 0


def test_missing_infeasible_time_remains_blank(monkeypatch):
    run, costs = fixed_path(monkeypatch)
    del costs[("small_batch", None, (1, 1, 1))]
    rows, ledger = analysis.timing_tables([run], costs)
    assert ledger[0]["nlp_evaluation_wall_s"] is None
    assert rows[0]["callbacks_missing_nlp_measurement"] == 2
    assert rows[0]["dfo_wall_time_s"] == 9.5


def test_nlp_outcomes_do_not_change_dfo_recorded_values_or_clock(monkeypatch):
    run, costs = fixed_path(monkeypatch)
    before, _ = analysis.timing_tables([run], costs)
    costs[("small_batch", None, (2, 2, 1))]["record"].update(accepted=False, objective=None)
    costs[("small_batch", None, (2, 2, 1))]["cost_s"] = 1000.
    after, ledger = analysis.timing_tables([run], costs)
    assert before == after
    assert ledger[1]["nlp_evaluation_wall_s"] == 1000.
    assert not ledger[1]["nlp_accepted"]


def test_online_phase_cannot_be_launched(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["runner", "worker", "--phase", "online"])
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2
    assert not hasattr(worker, "online")


def test_hard_timeout_retains_interrupted_evaluation_and_checksums(monkeypatch, tmp_path):
    original_popen = subprocess.Popen
    spec = small_spec()
    job = tmp_path / "points" / spec["job_id"]
    def helper_popen(command, **kwargs):
        code = (
            "import json,time;from pathlib import Path;"
            f"p=Path({str(job)!r});t=time.monotonic();"
            "(p/'clock.json').write_text(json.dumps({'started_monotonic_s':t}));"
            "(p/'active_evaluation.json').write_text(json.dumps({'evaluation_index':1,'point':[1,1,1],'started_monotonic_s':t}));"
            "time.sleep(30)"
        )
        return original_popen([sys.executable, "-c", code], **kwargs)
    monkeypatch.setattr(runner.subprocess, "Popen", helper_popen)
    result = runner.launch(tmp_path, "points", spec, {"run_seconds": 1, "point_hard_seconds": .25})
    assert result["status"] == "hard_time_limit"
    assert result["interrupted_evaluation_wall_s"] > 0
    assert runner.terminal_valid(job)
    # A terminal limit is a real outcome, not an automatic retry.
    assert runner.launch(tmp_path, "points", spec, {"point_hard_seconds": 1}) == result
    (job / "run.log").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        runner.terminal_valid(job)


def test_result_pack_hashes_snapshot_bytes(tmp_path):
    import hashlib
    import zipfile
    save(tmp_path / "result.json", {"status": "test"})
    archive_path = runner.pack(tmp_path, live=True)
    with zipfile.ZipFile(archive_path) as archive:
        prefix = tmp_path.name + "/"
        assert "Non-atomic" in archive.read(prefix + "LIVE_SNAPSHOT.txt").decode()
        for line in archive.read(prefix + "SHA256SUMS").decode().splitlines():
            digest, relative = line.split("  ", 1)
            assert hashlib.sha256(archive.read(prefix + relative)).hexdigest() == digest
