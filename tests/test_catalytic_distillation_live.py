"""Checks of the live catalytic distillation harness with a fake NLP solver."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

np = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "experiments/catalytic_distillation_live"
sys.path.insert(0, str(LIVE))
import case  # noqa: E402

spec = importlib.util.spec_from_file_location("catdist_live", LIVE / "run.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)
GAMS = os.environ.get("GAMS_EXE") or shutil.which("gams")


def fake_solve(config):
    """Accepts configurations with an even boil-up stage; objective is a smooth bowl."""
    target = (4, 4, 6, 8, 8, 10)
    ok = config[-1] % 2 == 0
    return dict(zip(case.pilot.FIELDS, config), solver="fake", returncode=0, wall_s=0.01,
                modelstat=2 if ok else 5, solvestat=1, zobj=float(sum((a - b) ** 2 for a, b in zip(config, target))),
                resusd=0.0)


def job(method, budget, seed=0):
    return dict(job_id=f"{method}_B{budget}_seed{seed}", method=method, seed=seed, budget=budget,
                starts=case.shared_starts(seed), lower=case.LOWER, upper=case.UPPER, settings=live.SETTINGS[method])


def test_gap_coordinates_map_the_admissible_configurations():
    pool = [p for p in case.box_points() if case.admissible(p)]
    assert len(pool) == 54_159
    for p in pool[::97]:
        f1, c1, c2, c3, f2, b = case.positions(p)
        assert 2 <= f1 <= c1 < c2 < c3 <= f2 <= b <= 21
        assert case.gaps_of(case.positions(p)) == p
    assert case.gaps_of((4, 4, 6, 8, 8, 10)) == (2, 0, 1, 1, 0, 2)
    assert not case.admissible((6, 6, 6, 0, 0, 0))


def test_shared_starts_are_reproducible_admissible_and_span_the_space():
    for seed in range(3):
        starts = case.shared_starts(seed)
        assert starts == case.shared_starts(seed) and len(starts) == 7
        assert len({tuple(p) for p in starts}) == 7 and all(case.admissible(p) for p in starts)
        assert np.linalg.matrix_rank(np.c_[np.ones(7), np.array(starts)]) == 7
    assert case.shared_starts(0) != case.shared_starts(1)


@pytest.mark.parametrize("method", ["uniform", "dsda"])
def test_oracle_charges_every_callback_and_solves_each_point_once(tmp_path, method):
    solves = []
    evaluator = case.Evaluator(tmp_path / "cache.sqlite", None, solve=lambda c: solves.append(c) or fake_solve(c))
    spec_ = job(method, 30)
    oracle = live.LiveOracle(spec_, evaluator, tmp_path)
    try:
        live.optimize(spec_, oracle, {})
    except live.BudgetStop:
        pass
    events = oracle.events
    assert [e["point"] for e in events[:7]] == spec_["starts"]
    assert len(events) <= 30 and not oracle.budget_overrun
    if method == "uniform":
        assert len(events) == 30
    rejected = [e for e in events if e["status"] == "logical_infeasible"]
    assert all(e["point_cost_s"] == 0 and not e["solved_now"] for e in rejected)
    assert len(solves) == len({tuple(e["point"]) for e in events if case.admissible(tuple(e["point"]))})
    assert all((e["method_value"] == e["raw_objective"]) == e["accepted"] for e in events if e["accepted"])
    assert all(e["method_value"] == live.PENALTY for e in events if not e["accepted"])
    # A second run reuses the cache without solving again.
    again = live.LiveOracle(spec_, evaluator, tmp_path / "again")
    (tmp_path / "again").mkdir()
    for p in spec_["starts"]:
        again(p)
    assert len(solves) == len({tuple(e["point"]) for e in events if case.admissible(tuple(e["point"]))})


def test_oracle_rejects_a_changed_initial_order(tmp_path):
    evaluator = case.Evaluator(tmp_path / "cache.sqlite", None, solve=fake_solve)
    spec_ = job("rbfopt", 25)
    oracle = live.LiveOracle(spec_, evaluator, tmp_path)
    with pytest.raises(ValueError, match="shared initial order"):
        oracle(spec_["starts"][1])


@pytest.mark.parametrize("method,module", [("nomad", "PyNomad"), ("miso", "soogo")])
def test_mixed_integer_adapters_run_on_live_responses(tmp_path, method, module):
    pytest.importorskip(module)
    pytest.importorskip("pandas")
    spec_ = job(method, 25)
    status, events, details = live.run_midfo(
        spec_, lambda: case.Evaluator(tmp_path / "cache.sqlite", None, solve=fake_solve), tmp_path)
    assert status == "completed", details
    assert [e["point"] for e in events[:7]] == spec_["starts"] and 7 < len(events) <= 25


@pytest.mark.skipif(not GAMS, reason="GAMS not available")
def test_worker_solves_live_configurations(tmp_path):
    output = tmp_path / "campaign"
    assert live.main(["plan", "--output", str(output), "--methods", "uniform", "--budgets", "8", "--seeds", "0"]) == 0
    assert live.main(["run", "--output", str(output), "--gams", GAMS, "--cpus", "0"]) == 0
    result = json.loads((output / "runs/uniform_B8_seed0/result.json").read_text())
    assert result["status"] == "completed" and result["evaluations"] == 8
    assert result["solved_now"] + result["logical_rejections"] == result["distinct_points"]
