"""Checks of the D-SDA neighborhood comparison (results/dsda_separable_20261101)."""
import csv
import importlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/dsda_separable_20261101"
sys.path.insert(0, str(ROOT / "experiments/dsda_separable"))


def test_every_run_is_separable_and_passes_its_checks():
    checks = json.loads((RESULTS / "grid_process/checks.json").read_text())
    assert checks["passed"] and checks["jobs"] == 1190
    for order in ["source", "reversed", "backmixing", "random1", "random2", "random3"]:
        plan = json.loads((RESULTS / "lomustine" / order / "plan.json").read_text())
        assert plan["case_options"]["dsda_neighborhood"] == "separable"
        assert {job["method"] for job in plan["jobs"]} == {"dsda"} and len(plan["jobs"]) == 30
        assert all(job["settings"]["diagonal"] is False for job in plan["jobs"])


def test_analysis_reproduces_the_committed_comparison(tmp_path):
    pytest.importorskip("numpy")
    analyze = importlib.import_module("analyze")
    for sub in ["grid_process", "lomustine"]:
        (tmp_path / sub).symlink_to(RESULTS / sub)
    analyze.main(["--results", str(tmp_path)])
    for name in ["conditions.csv", "facts.json", "neighborhood_table.tex"]:
        assert (tmp_path / "analysis" / name).read_text() == (RESULTS / "analysis" / name).read_text(), name


def test_linf_counts_match_the_manuscript_runs():
    facts = json.loads((RESULTS / "analysis/facts.json").read_text())["pooled"]
    assert facts["process"]["hits_linf"] == 79 and facts["cstr"]["hits_linf"] == 16
    rows = list(csv.DictReader((RESULTS / "analysis/conditions.csv").open()))
    grid = {int(r["budget"]): int(r["hits_linf"]) for r in rows if r["scope"] == "grid"}
    assert grid == {10: 13, 30: 78, 50: 91, 70: 101, 100: 101}


def test_lomustine_wrapper_changes_only_the_dsda_neighborhood(monkeypatch):
    monkeypatch.delenv("LOMUSTINE_ORDER", raising=False)
    sys.path.insert(0, str(ROOT / "experiments/lomustine_simulation"))
    case = importlib.import_module("case")
    wrapper = importlib.import_module("lomustine_case")
    assert case.SETTINGS["dsda"]["diagonal"] is True and wrapper.SETTINGS["dsda"]["diagonal"] is False
    assert wrapper.OPTIONS == {**case.OPTIONS, "dsda_neighborhood": "separable"}
    assert (wrapper.BUDGETS, wrapper.N_STARTS, wrapper.LOWER, wrapper.UPPER) == (
        case.BUDGETS, case.N_STARTS, case.LOWER, case.UPPER)
    assert wrapper.reference_values() == case.reference_values()
