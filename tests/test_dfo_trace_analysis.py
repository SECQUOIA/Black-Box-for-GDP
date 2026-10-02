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
