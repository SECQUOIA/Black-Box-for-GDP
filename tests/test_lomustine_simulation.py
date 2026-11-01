"""Check the lomustine simulation case and reproduce its analysis from the run archive."""

import importlib.util
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/lomustine_simulation_20261031"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


case = load("lomustine_case", ROOT / "experiments/lomustine_simulation/case.py")


def test_table_covers_the_box_in_source_order():
    table = case.table()
    assert len(table) == 36 and all(r["accepted"] for r in table.values())
    best = min(table, key=lambda p: table[p]["objective"])
    assert best == (2, 0, 0) and case.positions(best) == ("PFR", "batch", "batch", "batchU")
    assert round(table[best]["objective"], 3) == -487.842
    assert {r["simulations"] for r in table.values()} == {60}
    assert {r["continuous_variables"] for r in table.values()} == {12, 14, 16}


def test_shared_starts_are_distinct_and_reproducible():
    for seed in range(10):
        starts = case.shared_starts(seed)
        assert starts == case.shared_starts(seed) and len({tuple(p) for p in starts}) == 3
        assert all(case.in_box(p) for p in starts)


def test_evaluator_charges_the_inner_optimization_once(tmp_path):
    evaluator = case.Evaluator(tmp_path / "cache.sqlite")
    first, again = evaluator((2, 0, 0)), evaluator((2, 0, 0))
    assert first["solve_wall_s"] == 208.0 and not first["cached"] and again["cached"]
    assert evaluator.live_solves == 1


def test_analysis_reproduces_from_the_archive(tmp_path):
    with zipfile.ZipFile(RESULTS / "evidence/lomustine_runs.zip") as z:
        z.extractall(tmp_path)
    analyze = load("lomustine_analyze", ROOT / "experiments/lomustine_simulation/analyze.py")
    assert analyze.main(["--runs", str(tmp_path / "lomustine_full"), "--output", str(tmp_path / "out")]) == 0
    for name in ("conditions.csv", "runs.csv", "hits_table.tex"):
        assert (tmp_path / "out" / name).read_bytes() == (RESULTS / "analysis" / name).read_bytes()
