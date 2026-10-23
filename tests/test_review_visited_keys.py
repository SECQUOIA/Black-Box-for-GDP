"""Coverage regressions: selected campaigns, complete traces and deduplication."""

from collections import Counter, defaultdict
import json

import pytest

from review_comparison import visited_keys as v


@pytest.fixture(scope="module")
def evidence():
    return v.audit()[0]


def test_current_campaign_and_historical_reconciliation(evidence):
    s = evidence["summary.json"]
    assert (s["primary_runs"], s["primary_callbacks"], s["primary_visited"]) == (700, 16252, 2050)
    assert (s["historical_runs"], s["historical_callbacks"], s["historical_visited"]) == (560, 12822, 1790)
    assert (s["historical_only"], s["primary_only"], s["shared_visited"]) == (51, 311, 1739)
    assert s["historical_visited"] - s["historical_only"] + s["primary_only"] == s["primary_visited"]
    assert s["primary_outcomes"]["execution_failed"] == 1
    assert {r["method"] for r in evidence["runs.csv"]} == set(v.PRIMARY)
    assert v.SOL not in {r["method"] for r in evidence["runs.csv"]}


def test_rebuild_union_independently_from_run_membership(evidence):
    configs = set()
    cases = defaultdict(set)
    for row in evidence["runs.csv"]:
        for point in json.loads(row["visited_coordinates"]):
            configs.add((row["case"], tuple(point)))
            cases[row["case"]].add(tuple(point))
    ledger = {(r["case"], tuple(json.loads(r["coordinates"])))
              for r in evidence["configuration_coverage.csv"] if r["primary_callbacks"]}
    assert configs == ledger
    assert len(cases["dynamic"]) == 72  # Six budgets share the same coordinate domain.
    assert ("cstr_5", (1, 2)) in configs and ("cstr_10", (1, 2)) in configs
    assert len(configs) < sum(r["distinct_configurations"] for r in evidence["method_summary.csv"])
    assert len(configs) < sum(r["distinct_configurations"] for r in evidence["runs.csv"])


def test_condition_seeds_and_failure_callbacks_retained(evidence):
    counts = Counter((r["case"], r["budget"], r["method"]) for r in evidence["runs.csv"])
    assert len(counts) == 70 and set(counts.values()) == {10}
    failed = [r for r in evidence["runs.csv"] if r["category"] == "execution_failed"]
    assert len(failed) == 1 and failed[0]["callbacks"] == 3
    assert sum(r["primary_callbacks"] for r in evidence["configuration_coverage.csv"] if r["accepted"] == "False") > 0


@pytest.mark.parametrize("change", ["missing", "duplicate", "wrong_seed"])
def test_reject_incomplete_or_duplicated_runs(change):
    rows = [dict(scope="process", case=case, budget=budget, seed=seed, method=method)
            for case, budget in v.CONDITIONS for seed in range(10) for method in v.PRIMARY]
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows.append(rows[0])
    else:
        rows[0] = rows[0] | {"seed": 10}
    with pytest.raises(ValueError, match="coverage mismatch|Duplicate primary run"):
        v.primary_runs(rows)


@pytest.mark.parametrize("indexes,expected", [([1, 3], 3), ([1, 1, 3], 3), ([2, 1, 3], 3)])
def test_reject_missing_duplicate_or_unordered_callbacks(indexes, expected):
    with pytest.raises(ValueError, match="Callback count|callback index"):
        v.checked_trace([{"index": i} for i in indexes], expected, ("column", 16, 0, "dsda"))


def test_coordinate_normalization_preserves_integer_identity():
    assert v.coordinate("[1.0, 2]") == v.coordinate([1, 2])
    with pytest.raises(ValueError, match="Noninteger"):
        v.coordinate([1.5, 2])
