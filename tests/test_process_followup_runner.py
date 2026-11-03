"""Protocol, data integrity, durable resume, and independent bundle checks."""

import copy
import json
import subprocess
import sys
import zipfile

import pytest

import process_followup_runner as followup
from evaluation_trace import finite_value
from instrumentation import make_result_record
from overnight_benchmark.common import jsonl, read, save, sha


def test_plan_preserves_designs_and_changes_only_requested_settings():
    from fmqa_benchmark.protocol import problem, reference_plan
    jobs = followup.plan()
    assert len(jobs) == len({s["job_id"] for s in jobs}) == 14
    column, batch = jobs[:4], jobs[4:]
    assert {s["method"] for s in column} == {"dsda", "rbfopt", "bam", "fmqa_sa"}
    assert all(s["seed"] == 10 and s["max_evaluations"] == 16 for s in column)
    assert all(s["starting_points"] == [[10, 3], [13, 6], [8, 9]] for s in column)
    assert problem(column[0])["objective"]([13, 6]) < 1e6
    assert [s["seed"] for s in batch] == list(range(10))
    for spec, original in zip(batch, reference_plan(["small_batch"])):
        assert spec["starting_points"] == original["starting_points"]
        assert spec["initial_design_sha256"] == original["initial_design_sha256"]
        assert spec["max_evaluations"] == 10 and spec["n_starts"] == 3
        assert spec["settings"] == {"algorithm": "MSRSM", "global_search_method": "sampling", "rbf": "auto"}
    for spec in jobs:
        followup.frozen_starts(spec)


def bam_initial_trace():
    from fmqa_benchmark.protocol import problem
    spec = followup.plan()[2]
    oracle = problem(spec)["objective"]
    best = oracle([13, 6])
    history = [None, best, best]
    events = []
    for i, point in enumerate(spec["starting_points"]):
        value, kind = finite_value(oracle(point) if i == 1 else float("nan"))
        events.append({"event": "evaluation", "evaluation_index": i + 1, "phase": "initial", "point": point,
                       "requested_point": point, "value": value, "value_kind": kind,
                       "incumbent": history[i], "incumbent_kind": "nan" if i == 0 else "finite",
                       "exception_type": None, "repeated_point": False,
                       "objective_wall_s": .01, "started_elapsed_s": i + .1, "completed_elapsed_s": i + .2})
    record = make_result_record(spec["csv_name"], "BAM", 10, 3, 16, best, [13, 6], 3, 3, False,
                                history, initial_evals=3, adaptive_evals=0, unique_evals=3)
    return spec, record, events


def test_nan_initial_values_and_native_roundoff_do_not_break_valid_trace():
    spec, record, events = bam_initial_trace()
    record["best_value"] += 1e-10
    followup.validate_trace(events, record, spec)
    record["best_value"] += .01
    with pytest.raises(ValueError, match="Final optimizer"):
        followup.validate_trace(events, record, spec)


@pytest.mark.parametrize("mutation", ["coordinate", "value", "incumbent", "repeat", "clock", "best_point"])
def test_corrupted_trace_rejected(mutation):
    spec, record, events = bam_initial_trace()
    if mutation == "coordinate":
        events[0]["point"] = [9, 3]
    elif mutation == "value":
        events[1]["value"] += 1
    elif mutation == "incumbent":
        events[1]["incumbent"] += 1
        record["incumbent_trajectory"][1] += 1
    elif mutation == "repeat":
        events[0]["repeated_point"] = True
    elif mutation == "clock":
        events[1]["started_elapsed_s"] = -1
    else:
        record["best_point"] = [10, 3]
    with pytest.raises(ValueError):
        followup.validate_trace(events, record, spec)


def test_real_dsda_trace_and_durable_writes(tmp_path, monkeypatch):
    calls = []
    original = followup.os.fsync
    monkeypatch.setattr(followup.os, "fsync", lambda fd: (calls.append(fd), original(fd))[1])
    spec = followup.plan()[0]
    result = followup.dfo_lookup(spec, {}, tmp_path)
    entries = jsonl(tmp_path / result["trace"]["path"])
    assert result["status"] == "completed"
    assert len(calls) == len(entries)
    assert entries[-1]["event"] == "run_complete"
    assert result["result_record"]["total_evals"] <= 16
    assert entries[1]["incumbent"] == 1e6
    assert result["result_record"]["incumbent_trajectory"][0] == 1e6
    followup.validate_trace(entries[1:-1], result["result_record"], spec)


def test_real_fmqa_callbacks_and_proposals(tmp_path):
    pytest.importorskip("dimod")
    pytest.importorskip("dwave.samplers")
    spec = copy.deepcopy(followup.plan()[3])
    # Short local integration check, explicitly not one of the benchmark runs.
    spec["max_evaluations"] = 6
    spec["settings"].update(epochs=5, num_reads=3, num_sweeps=20)
    result = followup.fmqa_lookup(spec, {}, tmp_path)
    entries = jsonl(tmp_path / result["trace"]["path"])
    proposals = jsonl(tmp_path / "proposals.jsonl")
    assert result["status"] == "completed"
    assert len(entries[1:-1]) == 6 and len(proposals) == 3
    assert [e["point"] for e in entries[1:4]] == spec["starting_points"]
    assert proposals[-1]["selected_point"] == entries[-2]["point"]
    followup.validate_trace(entries[1:-1], result["result_record"], spec)


def local_run(tmp_path):
    config = {"cpu": None, "dfo_python": sys.executable, "fmqa_python": sys.executable,
              "conda": "", "hard_seconds": 30}
    run = {"kind": followup.KIND, "config": config, "plan": followup.plan(),
           "source_files_sha256": followup.source_hashes()}
    save(tmp_path / "run.json", run)
    return run


def test_resume_reuses_success_and_retries_failure_preserving_evidence(tmp_path, monkeypatch):
    run = local_run(tmp_path)
    spec = run["plan"][0]
    original_command = followup.command
    monkeypatch.setattr(followup, "command", lambda *args: [sys.executable, "-c", "print('partial worker log'); raise RuntimeError('interrupted')"])
    failed = followup.launch(tmp_path, spec, run["config"], False)
    assert failed["status"] == "error"
    assert followup.launch(tmp_path, spec, run["config"], False) == failed
    monkeypatch.setattr(followup, "command", original_command)
    done = followup.launch(tmp_path, spec, run["config"], True)
    assert done["status"] == "completed"
    assert len(list((tmp_path / "previous_attempts").iterdir())) == 1
    monkeypatch.setattr(followup, "command", lambda *args: pytest.fail("Completed job was restarted"))
    assert followup.launch(tmp_path, spec, run["config"], True) == done
    summary = followup.report(tmp_path)
    assert summary["completed_runs"] == 1 and not summary["all_completed"]
    assert summary["evaluation_callbacks"] == done["result_record"]["total_evals"]
    job = tmp_path / "jobs" / spec["job_id"]
    (job / done["trace"]["path"]).write_text("tampered\n")
    with pytest.raises(ValueError, match="Saved job changed"):
        followup.saved_result(job, spec)


def test_extracted_bundle_is_independent_and_checksums_match(tmp_path):
    archive = tmp_path / "runner.zip"
    followup.bundle(archive)
    assert archive.with_suffix(".zip.sha256").read_text().startswith(sha(archive))
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        assert not any("bamlice" in name or ".venv" in name for name in zipped.namelist())
        zipped.extractall(tmp_path / "extract")
    root = tmp_path / "extract/process_followup_runner"
    manifest = read(root / "BUNDLE_MANIFEST.json")
    for relative, digest in manifest["source_files_sha256"].items():
        assert sha(root / relative) == digest
    result = subprocess.run([sys.executable, "process_followup_runner.py", "plan"], cwd=root,
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == followup.plan()
    # Exercise data, imports and DSDA in the extracted directory, outside the repo.
    code = "from fmqa_benchmark.optimizer import optimize; from fmqa_benchmark.protocol import verify_lookup_sources; verify_lookup_sources(); from process_followup_runner import plan, dfo_lookup; from pathlib import Path; d=Path('smoke'); d.mkdir(); r=dfo_lookup(plan()[0], {}, d); assert r['status']=='completed'"
    subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=True)


def test_conda_and_venv_commands_keep_environments_separate(tmp_path):
    dfo, fmqa = tmp_path / "dfo", tmp_path / "fmqa"
    (dfo / "conda-meta").mkdir(parents=True)
    config = {"dfo_python": str(dfo / "bin/python"), "fmqa_python": str(fmqa / "bin/python"), "conda": "/conda"}
    assert followup.command(config, "dfo", "plan")[:6] == ["/conda", "run", "--no-capture-output", "--prefix", str(dfo), "python"]
    assert followup.command(config, "fmqa", "plan")[0] == str(fmqa / "bin/python")
    assert "--prefix" not in followup.command(config, "fmqa", "plan")


def test_watchdog_keeps_partial_log_and_archive_reports_incomplete(tmp_path, monkeypatch):
    run = local_run(tmp_path)
    run["config"]["hard_seconds"] = .5
    spec = run["plan"][0]
    monkeypatch.setattr(followup, "command", lambda *args: [sys.executable, "-c",
                        "import time; print('partial worker log', flush=True); time.sleep(60)"])
    result = followup.launch(tmp_path, spec, run["config"], False)
    assert result["status"] == "hard_time_limit"
    assert "partial worker log" in (tmp_path / "jobs" / spec["job_id"] / "run.log").read_text()
    summary = followup.report(tmp_path)
    assert summary["failed_runs"] == 1 and summary["completed_runs"] == 0 and not summary["all_completed"]
    archive = followup.pack(tmp_path)
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        assert any(name.endswith("/run.log") for name in zipped.namelist())
