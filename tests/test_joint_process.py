"""Validate comparison denominators, workload accounting, and retained data."""

import copy

import pytest

from review_comparison import joint_process as j


@pytest.fixture(scope="module")
def data():
    return j.load(j.ROOT)


def complete_slots():
    dfo = [dict(case=c, budget=b, seed=s, method=m)
           for c, b in j.CONDITIONS for s in range(10) for m in j.METHODS]
    alg = [dict(instance_id=c, method=m)
           for c in {c for c, _ in j.CONDITIONS} for m in j.ALG_METHODS]
    return dfo, alg


@pytest.mark.parametrize("mutation", ["missing_dfo", "duplicate_dfo", "bad_seed", "missing_algebraic", "duplicate_algebraic"])
def test_refuse_incomplete_or_duplicated_runs(mutation):
    dfo, alg = complete_slots()
    if mutation == "missing_dfo":
        dfo.pop()
    elif mutation == "duplicate_dfo":
        dfo.append(dfo[0])
    elif mutation == "bad_seed":
        dfo[0]["seed"] = 10
    elif mutation == "missing_algebraic":
        alg.pop()
    else:
        alg.append(alg[0])
    with pytest.raises(ValueError, match="Missing, duplicate"):
        j.validate_runs(dfo, alg)


def test_nlp_work_retains_rejected_returns_and_excludes_preprocessing():
    assert [j.nlp_work(s) for s in ["accepted", "rejected", "logical_infeasible", "preprocessing_infeasible"]] == [1, 1, 0, 0]
    with pytest.raises(ValueError, match="Unclassified"):
        j.nlp_work("solver_error")


def test_callback_order_and_first_target_work():
    row = dict(case="example", budget=4, seed=0, method="dsda", evaluations=4, first_hit=4)
    statuses = ["preprocessing_infeasible", "rejected", "logical_infeasible", "accepted"]
    inv = {("example", (i,)): dict(status=s, accepted=s == "accepted") for i, s in enumerate(statuses)}
    events = [dict(index=i+1, point=[i], accepted=s == "accepted") for i, s in enumerate(statuses)]
    _, count, first = j.checked_events(list(reversed(events)), row, inv)
    assert count == first == 2
    with pytest.raises(ValueError, match="Missing or duplicate callback"):
        j.checked_events(events[:-1] + [events[0]], row, inv)
    wrong = copy.deepcopy(events)
    wrong[0]["accepted"] = True
    with pytest.raises(ValueError, match="acceptance mismatch"):
        j.checked_events(wrong, row, inv)


def test_publication_counts_and_no_algebraic_replication(data):
    rows, callbacks, _ = data
    assert sum(r["family"] == "DFO" for r in rows) == 700
    assert sum(r["family"] == "algebraic" for r in rows) == 45
    assert len(callbacks) == 16041
    assert sum(r["corresponding_nlp_calls"] for r in callbacks) == 10114
    assert len([r for r in rows if r["family"] == "algebraic" and r["case"] == "dynamic"]) == 5
    assert {r["budget"] for r in rows if r["case"] == "dynamic" and r["family"] == "DFO"} == {12, 15, 20, 30, 37, 50}


def test_algebraic_nlp_missing_is_not_zero_and_unconfirmed_is_separate(data):
    rows = data[0]
    assert all(r["nlp_calls"] == "" for r in rows if r["method"] in ("bigm", "hull"))
    ric = next(r for r in rows if r["case"] == "cstr_30" and r["method"] == "ric")
    assert ric["nlp_calls"] == 370
    assert ric["nlp_unconfirmed_attempts"] == 1
    assert sum(r["nlp_unconfirmed_attempts"] for r in rows if r["family"] == "algebraic") == 2
    assert sum(r["nlp_calls"] for r in rows if r["method"] in ("loa", "gloa", "ric")) == 2236


def test_summary_preserves_single_observations_and_target_rules(data):
    rows = data[0]
    summary = j.summaries(rows)
    assert len(summary) == 70 + 45
    assert all(r["runs"] == 1 and r["completion_q25_s"] == r["completion_q75_s"] == ""
               for r in summary if r["family"] == "algebraic")
    assert all(r["runs"] == 10 for r in summary if r["family"] == "DFO")
    assert {r["target_rule"] for r in rows if r["family"] == "DFO"} == {"absolute_reference_agreement"}
    assert {r["target_rule"] for r in rows if r["family"] == "algebraic"} == {"at_or_below_reference"}
    assert sum(r["bound_conflict"] for r in rows) == 19


def test_nlp_table_and_plot_inputs_cover_all_conditions(data):
    text = j.supplement_tex(j.summaries(data[0]))
    assert text.count("Dynamic &") == 6
    assert "not first-target time" in text
    assert "Internal NLP counts" in text
    assert "not additional runs" in text
    assert "success probability" in text
