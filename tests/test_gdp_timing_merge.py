"""Protect coordinate joins, failure costs, source identity and published coverage."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import merge_gdp_timings as merge


def attempt(kind, *, accepted=False, seconds=1.25, solver="gams_ipopt", point=(5, 3)):
    return {"attempt_id": f"{kind}/{solver}/{point}", "attempt_kind": kind,
            "record": {"case": "cstr", "cstr_size": 30, "point": list(point), "solver": solver,
                       "accepted": accepted, "objective": 3.13 if accepted else None,
                       "max_primal_violation": 1e-10, "feasibility_tolerance": 1e-5,
                       "gams_solve_status": 1, "gams_model_status": 2 if accepted else 5,
                       "total_wall_s": seconds, "source": {"commit": "same-original-model"}}}


def test_retry_preserves_prior_cost_and_keeps_solvers_separate():
    old, new = attempt("initial"), attempt("retry", accepted=True, seconds=1.9)
    other = attempt("initial", accepted=True, solver="conopt", seconds=0.8)
    inputs = [old, new, other]
    before = copy.deepcopy(inputs)
    rows = merge.select_points(inputs)
    ipopt = next(r for r in rows if r["solver"] == "gams_ipopt")
    assert ipopt["total_wall_s"] == 1.9
    assert ipopt["all_attempts_total_wall_s"] == pytest.approx(3.15)
    assert ipopt["attempt_count"] == 2
    assert ipopt["worker_process_wall_s"] is None
    assert inputs == before
    assert next(r for r in rows if r["solver"] == "conopt")["total_wall_s"] == 0.8


@pytest.mark.parametrize("change", ["source", "success", "solver", "point"])
def test_bad_retry_cannot_replace_an_original_point(change):
    old, new = attempt("initial"), attempt("retry", accepted=True)
    if change == "source":
        new["record"]["source"] = {"commit": "different"}
    elif change == "success":
        new["record"]["accepted"] = False
    elif change == "solver":
        new["record"]["solver"] = "conopt"
    else:
        new["record"]["point"] = [7, 3]
    with pytest.raises(ValueError):
        merge.select_points([old, new])


def test_missing_time_and_duplicate_records_are_errors():
    original = attempt("initial")
    with pytest.raises(ValueError, match="Duplicate"):
        merge.select_points([original, original])
    original["record"]["total_wall_s"] = None
    with pytest.raises(ValueError, match="Missing evaluation time"):
        merge.select_points([original])


def test_small_cstr_records_are_rejected():
    row = attempt("initial")
    row["record"]["cstr_size"] = 5
    with pytest.raises(ValueError, match="Only CSTR30"):
        merge.select_points([row])


def test_source_checksum_validation(tmp_path):
    manifest = tmp_path / "run.json"
    manifest.write_text('{}\n')
    checks = tmp_path / "SHA256SUMS"
    checks.write_text(f"{merge.digest(manifest)}  run.json\n")
    assert merge.checked_source(tmp_path)[2] == {}
    manifest.write_text('{"changed": true}\n')
    with pytest.raises(ValueError, match="checksum mismatch"):
        merge.checked_source(tmp_path)


def test_published_table_rebuilds_from_preserved_attempts():
    root = Path(__file__).resolve().parents[1] / "results/gdp_point_timings_20260922"
    attempts = [json.loads(s) for s in (root / "attempts.jsonl").read_text().splitlines()]
    points = [json.loads(s) for s in (root / "points.jsonl").read_text().splitlines()]
    assert merge.select_points(attempts) == points
    assert len(attempts) == 1786 and len(points) == 1779
    assert merge.summarize(points, attempts) == json.loads((root / "summary.json").read_text())
    assert len({merge.point_key(r) for r in points}) == len(points)
    assert {r["cstr_size"] for r in points if r["case"] == "cstr"} == {30}
    cstr = [r for r in points if r["case"] == "cstr" and r["solver"] == "gams_ipopt"]
    assert len(cstr) == 465 and all(r["accepted"] for r in cstr)
    assert {tuple(r["point"]) for r in cstr if r["selection"] == "successful_retry"} == merge.RETRY_POINTS
    assert sum(r["all_attempts_total_wall_s"] for r in cstr) > sum(r["total_wall_s"] for r in cstr)
    prep = json.loads((root / "dynamic_preparation.json").read_text())
    assert len(prep) == 1 and len(prep[0]["source_files"]) == 3
    assert all(r["preparation_id"] == prep[0]["record"]["preparation_id"]
               for r in points if r["case"] == "dynamic")
    for line in (root / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    assert not list(root.rglob("*.sh"))
    assert merge.digest(Path(merge.__file__)) == json.loads((root / "provenance.json").read_text())["merge_script_sha256"]
