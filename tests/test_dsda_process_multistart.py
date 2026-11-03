"""Replay checks for the process D-SDA multistart experiment."""

import importlib.util
import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "experiments/dsda_process_multistart/run.py"
JOBS = ["cstr_30_B43_seed0_dsda", "dynamic_B50_seed3_dsda", "column_logical_B13_seed6_dsda"]


def load_runner():
    spec = importlib.util.spec_from_file_location("dsda_process_multistart", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def output(tmp_path_factory):
    runner = load_runner()
    out = tmp_path_factory.mktemp("multistart") / "run"
    status = runner.main(["--cpu", "none", "--no-zip", "--output", str(out), "--jobs", *JOBS])
    assert status == 0
    return out


def result(output, job, variant):
    return json.loads((output / "runs" / f"{job}__{variant}" / "result.json").read_text())


def test_single_replays_archived_runs(output):
    checks = json.loads((output / "checks.json").read_text())
    assert checks["replay_passed"] and len(checks["replay"]) == len(JOBS)
    assert checks["first_descent_matches_single"]
    assert not checks["execution_failures"]


def test_multistart_respects_budget_and_order(output):
    for job in JOBS:
        single = result(output, job, "single")
        for variant in ("ranked", "ranked_random"):
            r = result(output, job, variant)
            assert single["evaluations"] <= r["evaluations"] <= r["spec"]["budget"]
            assert r["descents"][0]["origin"] == "shared_start_rank_1"
            # Multistart never returns a worse incumbent than its own first descent.
            assert r["best_objective"] <= single["best_objective"]
        assert result(output, job, "ranked_random")["unused_budget"] == 0


def test_random_restarts_are_reproducible(output, tmp_path):
    runner = load_runner()
    again = tmp_path / "again"
    job = JOBS[0]
    assert runner.main(
        ["--cpu", "none", "--no-zip", "--output", str(again), "--jobs", job, "--variants", "ranked_random"]
    ) == 0
    first = (output / "runs" / f"{job}__ranked_random" / "callbacks.jsonl").read_text().splitlines()
    second = (again / "runs" / f"{job}__ranked_random" / "callbacks.jsonl").read_text().splitlines()
    assert [json.loads(x)["point"] for x in first] == [json.loads(x)["point"] for x in second]


def test_sealed_modules_do_not_leak():
    load_runner()
    assert all(not str(p).endswith("/reproduction") for p in sys.path)
