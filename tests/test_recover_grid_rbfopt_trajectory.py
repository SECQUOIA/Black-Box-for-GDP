"""Check recovery proofs against exhaustive assignments and archived evidence."""

import itertools
import json
import math

import pytest

import recover_grid_rbfopt_trajectory as recovery


def test_parser_does_not_consume_next_line_after_discarded():
    text = "\n".join(
        (
            recovery.HEADER,
            " 0 0 Initialization 0.250000 0.00 100.00 *",
            " 1 0 Discarded                         0.50",
            " 2 0 GlobalStep 0.125000 0.75 100.00 *",
            "Summary: iters 3 evals 2 noisy_evals 0 obj 0.125000 gap 100.00",
        )
    )
    block = recovery.parse_log(text)[0]
    assert [e["printed_objective"] for e in block["events"]] == ["0.250000", "0.125000"]
    assert [e["log_line"] for e in block["events"]] == [2, 4]


def test_alternating_path_uniqueness_matches_exhaustive_search():
    # All nonempty domains for three variables over four possible coordinates.
    points = [(i, 0) for i in range(4)]
    subsets = [
        set(combo)
        for size in range(1, 5)
        for combo in itertools.combinations(points, size)
    ]
    for domains in itertools.product(subsets, repeat=3):
        injective = [p for p in itertools.product(*domains) if len(set(p)) == 3]
        for required in (None, *points):
            possible = [p for p in injective if required is None or required in p]
            if not possible:
                with pytest.raises(ValueError):
                    recovery.matching(domains, required)
                continue
            baseline = recovery.matching(domains, required)
            assert tuple(baseline) in possible
            for i in range(3):
                alternative = recovery.alternative(domains, baseline, i, required)
                expected = any(p[i] != baseline[i] for p in possible)
                assert (alternative is not None) == expected
                if alternative is not None:
                    assert tuple(alternative) in possible
                    assert alternative[i] != baseline[i]


@pytest.fixture(scope="module")
def archive_recovery():
    records, blocks, designs, grids, sources = recovery.read_inputs()
    cases = [
        recovery.recover_case(
            record,
            block,
            designs[record["csv_name"], int(record["seed"])],
            grids[record["csv_name"]],
        )
        for record, block in zip(records, blocks)
    ]
    return records, cases, designs, grids


def test_complete_cases_independently_reproduce_all_saved_results(archive_recovery):
    records, cases, designs, grids = archive_recovery
    expected = (
        {
            ("shubert", seed, budget)
            for seed in range(10)
            for budget in (10, 30, 50, 70, 100)
        }
        | {("hosaki", seed, 10) for seed in (1, 7)}
        | {("rosenbrock", seed, 10) for seed in (4, 7)}
    )
    recovered = [c for c in cases if c["status"] == "recovered"]
    assert {(c["grid_name"], c["seed"], c["budget"]) for c in recovered} == expected
    assert len(cases) == 1050
    assert sum(c["recovered_evaluations"] for c in cases) == 12387
    assert sum(c["total_evaluations"] for c in recovered) == 2640
    for record, case in zip(records, cases):
        grid = grids[record["csv_name"]]
        if case["status"] != "recovered":
            continue
        points = [case["forced"][i] for i in range(case["total_evaluations"])]
        assert points[:3] == designs[record["csv_name"], case["seed"]]
        assert len(set(points)) == int(record["unique_evals"])
        values = [grid[p] for p in points]
        running_min = list(itertools.accumulate(values, min))
        assert running_min == pytest.approx(
            json.loads(record["incumbent_trajectory"]), abs=1e-12, rel=0
        )
        assert min(values) == pytest.approx(
            float(record["best_value"]), abs=1e-12, rel=0
        )
        assert points[case["final_best_evaluation_index"] - 1] == tuple(
            json.loads(record["best_point"])
        )
        for event, value in zip(case["events"], values):
            assert abs(value - float(event["printed_objective"])) <= 0.5e-6 + 1e-12


def test_partial_cases_never_fill_ambiguous_coordinates(archive_recovery):
    records, cases, designs, grids = archive_recovery
    for case in cases:
        assert len(case["forced"]) == case["recovered_evaluations"]
        assert set(case["forced"]) <= set(range(case["aligned_evaluations"]))
        if case["status"] == "partial_ambiguous":
            assert case["ambiguous_evaluations"] > 0
            witness = case["ambiguity_witness"]
            assert witness is not None
            i = witness["changed_evaluation_index"] - 1
            assert i not in case["forced"]
            assert witness["assignment_a"][i] != witness["assignment_b"][i]
    restarted = [c for c in cases if c["status"] == "partial_restart_alignment"]
    assert {(c["grid_name"], c["seed"], c["budget"]) for c in restarted} == {
        ("alpine1", seed, 100) for seed in (1, 3, 4, 6, 7, 8)
    }
    assert all(c["unaligned_evaluations"] > 0 for c in restarted)
    assert all(
        e["log_line"] < min(c["restart_lines"]) for c in restarted for e in c["events"]
    )


def test_rounded_value_does_not_select_an_arbitrary_symmetric_point(archive_recovery):
    records, cases, designs, grids = archive_recovery
    case = next(c for c in cases if c["case_id"] == "grid_ackley_B10_seed0_rbfopt")
    assert case["status"] == "partial_ambiguous"
    assert case["forced"][4] == (
        15,
        17,
    )  # Saved final-best coordinate, not a tie guess.
    assert any(
        len(domain) > 1 and i not in case["forced"]
        for i, domain in enumerate(case["domains"])
    )
    assert math.isfinite(case["max_incumbent_abs_error"])
