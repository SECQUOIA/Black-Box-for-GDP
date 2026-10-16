"""Check completed Dantzig evidence and all-outcome scientific accounting."""

from collections import Counter
import hashlib
import math
import zipfile

import pytest

import dfo_trace_analysis as analysis


@pytest.fixture(scope="module")
def audited():
    with analysis.verified_snapshot(analysis.ARCHIVE, analysis.ARCHIVE_SHA) as (directory, source):
        result = analysis.audit(directory)
    return result, source


def test_completed_snapshot_has_exact_plan_full_trace_and_positive_costs(audited):
    (_, traces, costs, rows, ledger, collection, coverage), source = audited
    assert source["verified_files"] == 7968
    assert Counter(r["method"] for r in rows) == dict.fromkeys(("dsda", "rbfopt", "bam", "fmqa_sa"), 139)
    assert len(traces) == 556 and len(ledger) == 12778
    assert len(costs) == 1779 and coverage["missing_coordinate_measurements"] == 0
    assert len(collection) == 703
    assert all(r["outcome"] == "preprocessing_infeasible" and r["solver_invocation_s"] == 0 for r in collection)
    assert all(item["cost_s"] > 0 for item in costs.values())
    assert Counter(analysis.outcome(item["record"]) for item in costs.values()) == {
        "accepted": 456, "preprocessing_infeasible": 728, "solver_reported_infeasible": 592, "other_rejected": 3}


def test_attached_costs_count_rejections_and_repeats_without_changing_dfo(audited):
    (_, traces, costs, rows, ledger, _, _), _ = audited
    old = [(r["dfo_wall_time_s"], r["recorded_best_point"], r["recorded_best_value"]) for r in rows]
    rows, ledger = analysis.attach_costs(traces, costs, [dict(r) for r in rows], [dict(e) for e in ledger])
    assert old == [(r["dfo_wall_time_s"], r["recorded_best_point"], r["recorded_best_value"]) for r in rows]
    assert sum(r["repeated_callbacks"] for r in rows) == 384
    assert math.fsum(r["attached_nlp_evaluation_s"] for r in rows) == pytest.approx(
        math.fsum(e["nlp_evaluation_wall_s"] for e in ledger))
    assert all(r["attached_nlp_evaluation_s"] == pytest.approx(
        math.fsum(r[f"attached_{k}_s"] for k in analysis.OUTCOMES)) for r in rows)
    # Original finite penalties are algorithm inputs, not feasible objectives.
    penalties = [e for e in ledger if e["dfo_recorded_value"] == 1e6]
    assert len(penalties) == 633 and all(not e["lookup_feasible"] for e in penalties)
    assert all("estimated_total_s" not in r for r in rows)


def test_successful_retries_use_only_retry_cost_without_changing_lookup_runs(audited):
    (_, traces, original, old_rows, _, _, _), _ = audited
    costs, retry_audit = analysis.successful_retry_costs(original)
    assert retry_audit["available_successful_retries"] == 7
    assert retry_audit["visited_successful_retries"] == 6
    key = ("cstr", 30, (5, 1))
    assert not original[key]["record"]["accepted"]
    assert costs[key]["record"]["accepted"]
    assert costs[key]["cost_s"] == pytest.approx(1.8747676881030202)
    changed = {k for k in costs if costs[k] != original[k]}
    assert changed == {("cstr", 30, p) for p in ((5, 1), (5, 3), (6, 2), (23, 2), (26, 2), (29, 3))}
    rows, ledger = analysis.timing_tables(traces, costs)
    rows, ledger = analysis.attach_costs(traces, costs, rows, ledger)
    assert [(r["dfo_wall_time_s"], r["recorded_best_point"], r["recorded_best_value"]) for r in rows] == [
        (r["dfo_wall_time_s"], r["recorded_best_point"], r["recorded_best_value"]) for r in old_rows]
    repaired = [e for e in ledger if e["nlp_measurement_source_kind"] == "historical_successful_retry"]
    assert repaired and all(e["nlp_accepted"] and e["accepted_objective_matches_lookup"] for e in repaired)
    for event in repaired:
        record = costs[analysis.point_key(event["case"], event["cstr_size"], event["point"])]["record"]
        assert event["nlp_evaluation_wall_s"] == record["total_wall_s"]
        assert event["nlp_solve_wall_s"] == record["solve_wall_s"]
    comparison = analysis.lookup_comparison(costs)
    assert Counter(r["case"] for r in comparison) == {"dynamic": 37, "small_batch": 12}
    assert all(r["matches_tolerance"] for r in comparison)


def test_changed_internal_file_is_rejected_even_with_matching_outer_digest(tmp_path):
    path = tmp_path / "tampered.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("run/result.json", "changed")
        archive.writestr("run/SHA256SUMS", hashlib.sha256(b"original").hexdigest() + "  result.json\n")
    with pytest.raises(ValueError, match="Internal checksum"):
        with analysis.verified_snapshot(path, analysis.sha(path)):
            pytest.fail("Corrupt evidence accepted")


def test_unsafe_member_is_rejected(tmp_path):
    path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("run/../escape", "bad")
    with pytest.raises(ValueError, match="Unsafe"):
        with analysis.verified_snapshot(path, analysis.sha(path)):
            pytest.fail("Unsafe archive accepted")


def test_current_search_changes_do_not_invalidate_archived_source(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, "ROOT", tmp_path / "current")
    directory = tmp_path / "snapshot"
    name = "case_studies/column_dsda.py"
    archived = directory / "source" / name
    archived.parent.mkdir(parents=True)
    archived.write_text("# original search\n")
    current = analysis.ROOT / name
    current.parent.mkdir(parents=True)
    current.write_text("# corrected search for future runs\n")
    hashes = {name: analysis.sha(archived)}
    analysis.verify_source_snapshot(directory, hashes)

    # The historical search itself must remain byte-for-byte intact.
    archived.write_text("# changed historical evidence\n")
    with pytest.raises(ValueError, match="Archived source changed"):
        analysis.verify_source_snapshot(directory, hashes)


@pytest.mark.parametrize("name", [
    "case_studies/column_case.py", "case_studies/dynamic_case.py",
    "case_study_data/column/compl_enum_column_17_baron.csv",
    "fmqa_benchmark/protocol.py", "fmqa_benchmark/reference/initial_designs.json",
    "gdp_models/models.py", "evaluation_trace.py",
])
def test_live_audit_inputs_must_still_match_snapshot(tmp_path, monkeypatch, name):
    monkeypatch.setattr(analysis, "ROOT", tmp_path / "current")
    directory = tmp_path / "snapshot"
    archived = directory / "source" / name
    current = analysis.ROOT / name
    for path in (archived, current):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("original input\n")
    hashes = {name: analysis.sha(archived)}
    analysis.verify_source_snapshot(directory, hashes)
    current.write_text("changed audit input\n")
    with pytest.raises(ValueError, match="Original benchmark input changed"):
        analysis.verify_source_snapshot(directory, hashes)
