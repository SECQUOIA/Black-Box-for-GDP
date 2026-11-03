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


def test_order_and_objective_options(monkeypatch):
    monkeypatch.setenv("LOMUSTINE_ORDER", "PFR,CSTR,batch/cont3,cont2,cont1,batchU")
    reordered = load("lomustine_reordered", ROOT / "experiments/lomustine_simulation/case.py")
    table = reordered.table()
    best = min(table, key=lambda p: table[p]["objective"])
    assert best == (0, 2, 3) and reordered.positions(best) == ("PFR", "batch", "batch", "batchU")
    monkeypatch.delenv("LOMUSTINE_ORDER")
    monkeypatch.setenv("LOMUSTINE_OBJECTIVE", "turton_capex")
    capex = load("lomustine_capex", ROOT / "experiments/lomustine_simulation/case.py")
    table = capex.table()
    best = min(table, key=lambda p: table[p]["objective"])
    assert capex.positions(best) == ("batch", "batch", "batch", "batchU")
    assert round(table[best]["objective"]) == 82766


def test_identical_crashes_are_scored_and_different_ones_rejected(tmp_path):
    import json

    analyze = load("lomustine_analyze_crash", ROOT / "experiments/lomustine_simulation/analyze.py")
    calls = [{"point": [0, 1, 2]}, {"point": [1, 1, 2]}]
    for name in ("attempt1.jsonl", "attempt2.jsonl"):
        (tmp_path / name).write_text("".join(json.dumps(c) + "\n" for c in calls))
    assert analyze.identical_attempts(tmp_path, calls)
    (tmp_path / "attempt2.jsonl").write_text(json.dumps(calls[0]) + "\n")
    assert not analyze.identical_attempts(tmp_path, calls)


def test_variant_comparison_reproduces(tmp_path):
    compare = load("lomustine_compare", ROOT / "experiments/lomustine_simulation/compare_variants.py")
    variants = tmp_path / "variants"
    for name in compare.ORDERS + ["capex"]:
        source = RESULTS / ("analysis" if name == "source" else f"variants/{name}/analysis")
        (variants / name / "analysis").mkdir(parents=True)
        for f in ("conditions.csv", "facts.json"):
            (variants / name / "analysis" / f).write_bytes((source / f).read_bytes())
    assert compare.main(["--variants", str(variants), "--output", str(tmp_path / "out")]) == 0
    for name in ("order_summary.csv", "variant_hits.csv", "order_table.tex", "capex_table.tex"):
        assert (tmp_path / "out" / name).read_bytes() == (RESULTS / "variants/comparison" / name).read_bytes()


def test_capex_variant_reproduces_from_its_archive(tmp_path, monkeypatch):
    import json

    with zipfile.ZipFile(RESULTS / "variants/capex/evidence/runs.zip") as z:
        z.extractall(tmp_path)
    options = json.loads((tmp_path / "capex/plan.json").read_text())["case_options"]
    monkeypatch.setenv("LOMUSTINE_OBJECTIVE", options["objective"])
    analyze = load("lomustine_analyze_capex", ROOT / "experiments/lomustine_simulation/analyze.py")
    assert analyze.main(["--runs", str(tmp_path / "capex"), "--output", str(tmp_path / "out")]) == 0
    expected = RESULTS / "variants/capex/analysis/conditions.csv"
    assert (tmp_path / "out/conditions.csv").read_bytes() == expected.read_bytes()
