"""Validate the current publication overlay without running optimizers."""

from collections import Counter
from copy import deepcopy
import json
import statistics as st

import pytest

from review_comparison import column_publication as p
from review_comparison import manuscript as m


@pytest.fixture(scope="module")
def data():
    return p.load_records()


def test_current_cohort_and_unrelated_records(data):
    records, groups, primary, *_ = data
    old = p.typed_records(m.read(p.BASE / "tables/run_records.csv"))
    assert len(primary) == 700
    assert Counter(r["category"] for r in primary) == {"target_reached": 315, "target_not_reached": 385}
    assert sum(r["evaluations"] for r in primary) == 16067
    for a, b in zip(old, records):
        if not (a["case"] == "column" and a["scope"] == "process" and a["method"] in m.PRIMARY):
            assert a == b
    for c, b in p.CONDITIONS:
        for method in m.PRIMARY:
            assert {r["seed"] for r in groups["process", c, b, method]} == set(range(10))
    assert len([r for r in primary if r["case"] == "dynamic"]) == 300


def test_paired_results_initial_success_and_costs(data):
    _, groups, _, callbacks, *_ = data
    pair = m.process_pair(groups, "column", 13, m.GEN, "dsda")
    assert pair["difference"] == pytest.approx(-0.1)
    assert [pair[k] for k in ("both_success", "new_only_success", "reference_only_success", "neither_success")] == [3, 1, 2, 4]
    for method, hits in zip(m.PRIMARY, [5, 4, 1, 4, 1]):
        rows = groups["process", "column", 13, method]
        assert sum(r["hit"] for r in rows) == hits
        assert next(r for r in rows if r["seed"] == 6)["first_hit"] == 3
    rbf = groups["process", "column", 13, m.GEN]
    assert st.median(r["total_s"] for r in rbf) == pytest.approx(54.603376980521716)
    expensive = [e for e in callbacks if e["method"] == "rbfopt" and json.loads(e["point"]) == [15, 8]]
    assert len(expensive) == 6 and all(e["accepted"] == "False" for e in expensive)
    assert sum(float(e["point_cost_s"]) for e in expensive) == pytest.approx(241.14791500847787)


def test_coverage_and_fallback_reconcile(data):
    _, _, primary, callbacks, lookup, archive, prefix = data
    cover = p.coverage(callbacks, lookup, primary)
    assert len(cover) == 2438
    assert sum(r["accepted"] == "True" for r in cover) == 1266
    assert sum(r["primary_callbacks"] > 0 for r in cover) == 2024
    assert sum(r["primary_callbacks"] for r in cover) == 16067
    column = [r for r in cover if r["case"] == "column"]
    assert len(column) == 64 and sum(r["accepted"] == "True" for r in column) == 29
    proposals = p.fallback_runs(archive, prefix)
    assert sum(r["proposals"] for r in proposals) == 2980
    assert sum(r["fallback"] for r in proposals) == 1576
    assert sum(r["fallback"] for r in proposals if r["case"] == "column") == 86


@pytest.mark.parametrize("kind", ["missing", "duplicate", "budget", "callback_cost", "objective", "initials"])
def test_corrupt_pairing_or_evidence_is_rejected(data, kind):
    old = p.typed_records(m.read(p.BASE / "tables/run_records.csv"))
    runs = [r for r in m.read(p.COLUMN / "replayed/runs.csv") if r["condition"] == "64_B13"]
    callbacks, lookup = deepcopy(data[3]), deepcopy(data[4])
    if kind == "missing":
        runs.pop()
    elif kind == "duplicate":
        runs.append(deepcopy(runs[0]))
    elif kind == "budget":
        runs[0]["budget"] = "16"
    elif kind == "callback_cost":
        callbacks[0]["point_cost_s"] = "0"
    elif kind == "objective":
        next(r for r in callbacks if r["accepted"] == "True")["raw_objective"] = "0"
    elif kind == "initials":
        callbacks[0]["point"] = "[13, 4]"
    with pytest.raises(ValueError):
        p.overlay(old, runs, callbacks, lookup)
