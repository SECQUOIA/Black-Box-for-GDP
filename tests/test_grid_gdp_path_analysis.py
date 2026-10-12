"""Scientific cost accounting: repeats, missing costs, failures and restarts."""
import math

import pytest

from scripts.analyze_grid_gdp_paths import charge_run, cdf_points, tts_summary, gdp_runs


def example(lookup=.5, costs=None):
    points = [[0, 0], [0, 1], [1, 0], [0, 0], [1, 1]]
    values = [1., .8, .5, 1., 0.]
    grids = {"toy": dict(zip(map(tuple, points), values))}
    events = [{"point": p, "value": v, "phase": "initial" if i < 3 else "adaptive"}
              for i, (p, v) in enumerate(zip(points, values))]
    record = {"total_evals": 5, "best_value": 0., "incumbent_trajectory": [1., .8, .5, .5, 0.]}
    if costs is None:
        costs = {("toy", (0, 0)): 2., ("toy", (0, 1)): 3.,
                 ("toy", (1, 0)): 7., ("toy", (1, 1)): 11.}
    return charge_run("dsda", "toy", 0, 5, events, 10., lookup, record, "test",
                      grids, {("toy", 0): points[:3]}, costs)


def test_actual_costs_include_initial_and_repeated_callbacks():
    run, charges = example()
    assert run["sum_point_wall_s"] == 25  # 2 + 3 + 7 + 2 + 11, not unique cost 23
    assert run["estimated_total_s"] == 34.5  # measured lookup replaced, not counted twice
    assert run["first_hit_evaluation"] == 5
    assert run["unique_evals"] == 4
    assert [r["repeated_point"] for r in charges] == [False, False, False, True, False]


def test_missing_point_cost_cannot_be_filled_by_an_average():
    with pytest.raises(KeyError):
        example(costs={("toy", (0, 0)): 1.})


def test_dsda_unknown_lookup_time_remains_explicit():
    run, _ = example(lookup=None)
    assert run["estimated_total_s"] == 35
    assert run["recorded_lookup_wall_s"] == ""
    assert not run["lookup_cost_removed"]


def test_failed_and_all_failed_runs_remain_in_cdf_denominator():
    xs, ys = cdf_points([3, 3, 8, math.inf], 10)
    assert xs == [0, 3, 8, 10]
    assert ys == [0, .5, .75, .75]
    assert cdf_points([math.inf] * 4, 10) == ([0., 10], [0., 0.])


def test_tts99_uses_all_seed_costs_and_preserves_zero_hit_groups():
    rows = [dict(grid_name="toy", method="a", max_evals=10,
                 target_hit=hit, estimated_total_s=t) for hit, t in [(True, 1), (False, 9)]]
    row = tts_summary(rows)[0]
    assert row["median_completion_s"] == 5 and row["runs_99"] == 7
    assert row["tts99_s"] == 35
    rows[0]["target_hit"] = False
    assert math.isinf(tts_summary(rows)[0]["tts99_s"])
    rows[0]["target_hit"] = rows[1]["target_hit"] = True
    assert tts_summary(rows)[0]["tts99_s"] == 5


def test_gdp_selection_preserves_unsupported_and_time_limit_incumbents():
    rows, _ = gdp_runs()
    assert len(rows) == 105
    assert sum(r["profile"] == "pyomo610-grid-v1" for r in rows) == 10
    unsupported = [r for r in rows if r["status"] == "unsupported_expression"]
    assert len(unsupported) == 32
    assert all(math.isinf(r["completion_cost_s"]) for r in unsupported)
    camel = [r for r in rows if r["grid_name"] == "camel3" and r["method"] in ("ric", "gloa", "loa")]
    assert len(camel) == 3 and all(r["target_hit"] and r["termination"] == "maxTimeLimit" for r in camel)
