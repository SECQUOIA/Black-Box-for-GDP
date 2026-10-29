"""Verify the adopted primary cohort without running optimizers or NLP solvers."""

from collections import Counter
from copy import deepcopy
import json
import math

import pytest

from review_comparison import cstr30_publication as p
from review_comparison import manuscript as m


@pytest.fixture(scope="module")
def publication():
    return p.load_records()


def test_missing_duplicate_and_wrong_condition_are_rejected():
    row = dict(scope="process", case="cstr_30", budget=43, seed=0, method="dsda")
    expected = {p.key(row)}
    with pytest.raises(ValueError, match="Missing or unexpected"):
        p.validate_slots([], expected, "test")
    with pytest.raises(ValueError, match="Duplicate"):
        p.validate_slots([row, row], expected, "test")
    with pytest.raises(ValueError, match="Missing or unexpected"):
        p.validate_slots([dict(row, budget=42)], expected, "test")


def test_complete_primary_cohort_and_failures_keep_denominator(publication):
    _, groups, primary, _, _ = publication
    assert len(primary) == 700
    assert Counter(r["category"] for r in primary) == {
        "target_reached": 314, "target_not_reached": 385, "execution_failed": 1,
    }
    assert sum(r["evaluations"] for r in primary) == 16206
    for case, budget in m.CONDITIONS:
        for method in m.PRIMARY:
            rows = groups["process", case, budget, method]
            assert len(rows) == 10 and {r["seed"] for r in rows} == set(range(10))
    failure = next(r for r in primary if r["category"] == "execution_failed")
    assert (failure["case"], failure["method"], failure["seed"]) == ("column", "dsda", 0)
    assert not failure["hit"] and failure["total_s"] > 0


def test_only_intended_historical_records_are_overlaid(publication):
    records, _, _, _, _ = publication
    old, _, _ = m.load()
    for before, after in zip(old, records):
        changed_slot = (before["scope"] == "process" and
                        ((before["case"].startswith("cstr_") and before["method"] in ("dsda", m.GEN))
                         or (before["case"] == "cstr_30" and before["method"] in m.PRIMARY)))
        if not changed_slot:
            assert after == before
    # The two historical alternative-candidate-search cohorts remain untouched.
    assert all(a == b for a, b in zip(old, records) if a["method"] == m.SOL)


def test_new_searches_use_new_costs_and_charge_repeated_callbacks(publication):
    _, _, primary, callbacks, evaluations = publication
    points = {tuple(json.loads(r["point"])): r for r in evaluations}
    new = {(r["method"], r["seed"]): r for r in primary if r["case"] == "cstr_30"}
    repeated = 0
    for slot, row in new.items():
        events = [e for e in callbacks if (e["method"], e["seed"]) == slot]
        seen = set()
        costs = []
        for event in events:
            coordinate = tuple(json.loads(event["point"]))
            repeated += coordinate in seen
            seen.add(coordinate)
            source = points[coordinate]
            assert event["evaluation_record_sha256"] == source["record_sha256"]
            assert event["accepted"] == (source["accepted"] == "True")
            assert event["point_cost_s"] == float(source["total_wall_s"])
            costs.append(event["point_cost_s"])
        assert len(events) == row["evaluations"]
        assert math.fsum(costs) == pytest.approx(row["point_cost_s"], abs=1e-10)
        assert row["total_s"] == pytest.approx(row["search_s"] + math.fsum(costs), abs=1e-10)
    assert repeated > 0
    assert len(evaluations) == 900
    assert sum(r["accepted"] == "True" for r in evaluations) == 464
    assert all(tuple(json.loads(r["point"])) != (27, 10) for r in callbacks)


def test_rbfopt_minus_dsda_pairing_and_condition_separation(publication):
    _, groups, _, _, _ = publication
    result = m.process_pair(groups, "cstr_30", 43, m.GEN, "dsda")
    assert result["difference"] == pytest.approx(0.7)
    assert (result["low"], result["high"]) == pytest.approx((0.4, 1.0))
    assert [result[k] for k in ("both_success", "new_only_success",
                                "reference_only_success", "neither_success")] == [2, 7, 0, 1]
    summaries = p.condition_summary(groups)
    assert len(summaries) == 70
    assert len([r for r in summaries if r["case"] == "dynamic"]) == 30
    assert all(r["runs"] == 10 for r in summaries)


def test_first_hit_uses_new_accepted_callbacks(publication):
    _, _, primary, callbacks, _ = publication
    pairs = {(p.METHOD_MAP[r["method"]], int(r["seed"])): r
             for r in m.read(p.INITIALIZATION / "returned/paired_runs.csv")}
    for row in primary:
        if row["case"] != "cstr_30":
            continue
        target = float(pairs[row["method"], row["seed"]]["new_target"])
        events = [e for e in callbacks if (e["method"], e["seed"]) == (row["method"], row["seed"])]
        hits = [e["index"] for e in events if e["accepted"] and
                abs(e["objective"] - target) <= 1e-5 * max(1, abs(target))]
        assert row["first_hit"] == (hits[0] if hits else None)
        assert row["hit"] == bool(hits)


def test_coverage_replaces_old_cstr30_and_reconciles_callbacks(publication):
    _, _, primary, callbacks, evaluations = publication
    coverage = p.coverage(callbacks, evaluations, primary)
    assert len(coverage) == 2455
    assert sum(r["primary_callbacks"] > 0 for r in coverage) == 2040
    assert sum(r["primary_callbacks"] > 0 for r in coverage if r["case"] == "cstr_30") == 673
    assert sum(r["accepted"] == "True" for r in coverage) == 1266
    changed = deepcopy(callbacks)
    changed.pop()
    with pytest.raises(ValueError, match="Coverage callbacks differ"):
        p.coverage(changed, evaluations, primary)


def test_fmqa_fallback_counts_use_new_cstr30_proposals(publication):
    _, _, primary, _, _ = publication
    rows = p.fmqa_fallback(primary)
    assert len(rows) == 140
    assert sum(r["proposals"] for r in rows) == 3010
    assert sum(r["fallback"] for r in rows) == 1572
    cstr = [r for r in rows if r["case"].startswith("cstr_")]
    assert sum(r["proposals"] for r in cstr) == 1350
    assert sum(r["fallback"] for r in cstr) == 369
    assert all((p.ARCHIVE.name in r["archive"]) == (r["case"] == "cstr_30") for r in rows)
