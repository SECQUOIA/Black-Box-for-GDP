"""Partial GDP updates cannot invent completion clocks or substitute old solvers."""

import json
import shutil

import pytest

from nlp_cost_analysis import baseline_comparison, baseline_record


def source(path, rows, nlp):
    path.mkdir()
    (path / "summary.json").write_text(json.dumps({"results": rows}))
    (path / "run.json").write_text(json.dumps({"cpu": 2, "host": "dantzig.ecn.purdue.edu",
                                              "created_utc": nlp}))


def row(method, objective, nlp="baron", status="finished"):
    return {"case": "column", "cstr_size": None, "instance_id": "column", "method": method,
            "objective": objective, "has_feasible_solution": True, "status": status,
            "method_wall_s": 2, "template_wall_s": .1,
            "global_optimality_certified": method == "hull", "reported_lower_bound": objective,
            "solver_policy": {"nlp": nlp, "mip": "highs"}}


def test_partial_selection_omits_running_and_old_gdpopt_but_keeps_cross_source_bound_audit(tmp_path):
    new, old = tmp_path / "new", tmp_path / "old"
    source(new, [row("ric", 1), row("gloa", .5, status="running")], "new")
    source(old, [row("ric", 9, "ipopt"), row("gloa", 9, "ipopt"), row("hull", 2)], "old")
    selection = {"sources": [{"directory": str(new), "methods": ["ric", "gloa"]},
                             {"directory": str(old), "methods": ["hull"]}]}
    (tmp_path / "selection.json").write_text(json.dumps(selection))
    rows = baseline_comparison(tmp_path, tmp_path, [{"spec": {"case_name": "column", "grid_size": None}, "target": 1}])
    assert [r["method"] for r in rows] == ["ric", "hull"]
    assert rows[0]["objective"] == 1 and rows[0]["nlp_solver"] == "baron"
    assert rows[0]["measured_total_with_preparation_s"] == 2.1
    assert rows[1]["bound_conflict_with_saved_solution"]
    assert not rows[1]["global_optimality_certified"]


def test_duplicate_selected_methods_are_rejected(tmp_path):
    new, old = tmp_path / "new", tmp_path / "old"
    source(new, [row("ric", 1)], "new")
    source(old, [row("ric", 9, "ipopt")], "old")
    (tmp_path / "selection.json").write_text(json.dumps({"sources": [
        {"directory": str(p), "methods": ["ric"]} for p in (new, old)]}))
    with pytest.raises(ValueError, match="Duplicate GDP"):
        baseline_comparison(tmp_path, tmp_path, [{"spec": {"case_name": "column", "grid_size": None}, "target": 1}])


def test_unselected_historical_incumbent_still_invalidates_a_reported_bound(tmp_path):
    old = tmp_path / "old"
    source(old, [row("ric", 1, "ipopt"), row("hull", 2)], "old")
    (tmp_path / "selection.json").write_text(json.dumps({"sources": [
        {"directory": str(old), "methods": ["hull"]}]}))
    rows = baseline_comparison(tmp_path, tmp_path, [{"spec": {"case_name": "column", "grid_size": None}, "target": 1}])
    assert len(rows) == 1 and rows[0]["method"] == "hull"
    assert rows[0]["bound_conflict_with_saved_solution"]
    assert rows[0]["bound_evidence_method"] == "ric"
    assert rows[0]["bound_evidence_source_directory"] == str(old)


def test_better_than_lookup_counts_as_attainment_without_changing_historical_exact_match():
    record = baseline_record(row("loa", 2.82935061823614), 2.829394057)
    assert record["target_attained"]
    assert not record["target_hit"]
    invalid = row("loa", 1)
    invalid["has_feasible_solution"] = False
    record = baseline_record(invalid, 2)
    assert not record["target_attained"] and not record["target_hit"]


def test_current_selection_reopens_archives_and_preserves_published_evidence(tmp_path, monkeypatch):
    """Exercise all 45 selected results and 63 saved vectors without a solver."""
    pytest.importorskip("pyomo.environ")
    pytest.importorskip("networkx")
    import pyomo.environ as pyo
    from gdp_current_analysis import ROOT, build
    from result_archives import datasets
    from nlp_cost_analysis import sha

    if not all((ROOT / "external" / name / ".git").exists()
               for name in ("dsda-gdp", "ld-sda-dynamic")):
        pytest.skip("Initialize pinned GDP submodules for the saved-vector audit")
    selection_dir = ROOT / "results/gdp_comparison_current"
    sources = json.loads((selection_dir / "selection.json").read_text())["sources"]
    paths = [selection_dir, *((ROOT / s["directory"]).parent for s in sources)]
    archives = [ROOT / entry["archive"] for entry in datasets().values()
                if entry["directory"] in {s["directory"] for s in sources}]

    def snapshot():
        files = [p for root in paths for p in root.rglob("*") if p.is_file()]
        return {str(p): sha(p) for p in [*files, *archives]}

    def no_solver(*args, **kwargs):
        pytest.fail("Saved-vector analysis must not construct a solver")

    monkeypatch.setattr(type(pyo.SolverFactory), "__call__", no_solver)
    before = snapshot()
    for source in sources:
        assert not (ROOT / source["directory"] / "jobs").exists()
    output = tmp_path / "analysis"
    overview = build(selection_dir, output)
    conflicts = overview["bound_conflicts"]
    assert {(r["instance_id"], r["method"]) for r in conflicts if r["method"] == "gloa"} == {
        (f"cstr_{size}", "gloa") for size in (5, 10, 15, 20, 25, 30)}
    assert sum(r["method"] in {"bigm", "hull"} for r in conflicts) == 5
    assert len(conflicts) == 11
    assert overview["complete"] and overview["completed_jobs"] == 45
    assert overview["saved_solutions_independently_rechecked"] == 63
    assert overview["selected_solutions_independently_rechecked"] == 45
    assert overview["max_rechecked_primal_violation"] < 1e-6
    assert [a["directory"] for a in overview["sources"]] == [s["directory"] for s in sources]
    assert all(a["source_archive_verified_byte_for_byte"] for a in overview["sources"])
    assert all(a["source_archive_sha256"] for a in overview["sources"])
    assert (output / "sources/gdp_comparison_20261001/audit.json").is_file()
    assert (output / "sources/gdp_comparison_loa_20261001/audit.json").is_file()
    assert (output / "comparison.csv").read_bytes() == (selection_dir / "analysis/comparison.csv").read_bytes()
    assert snapshot() == before


def test_changed_retained_summary_is_rejected_before_job_audit(tmp_path, monkeypatch):
    pytest.importorskip("pyomo.environ")
    import gdp_current_analysis as analysis
    import result_archives as storage

    entry = storage.datasets()["gdp-oct01"]
    retained = tmp_path / "raw"
    shutil.copytree(storage.ROOT / entry["directory"], retained)
    summary = retained / "summary.json"
    summary.write_bytes(summary.read_bytes() + b"\n")
    original_entry_for_path = storage.entry_for_path
    monkeypatch.setattr(storage, "entry_for_path", lambda path: entry if path == retained
                        else original_entry_for_path(path))
    calls = []
    monkeypatch.setattr(analysis, "_verify_source", lambda *args: calls.append(args))
    with pytest.raises(ValueError, match="Retained GDP source differs from archive: summary.json"):
        analysis.verify_source(retained, ["ric", "gloa"])
    assert calls == []
