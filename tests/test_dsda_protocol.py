"""Behavioral checks for maintained D-SDA protocol, without external solvers."""

import csv
import importlib
import math

import pytest

from dsda_protocol import ObservedObjective, common_target_reached, improves
from grid_dsda import dsda_from_csv, run_dsda_from_best_starting_points
from instrumentation import save_results_csv


def descent(grid, start=(0,), **kwargs):
    return dsda_from_csv('synthetic.csv', start, grid=grid, verbose=False, **kwargs)


def multi(grid, starts, **kwargs):
    return run_dsda_from_best_starting_points('synthetic.csv', starts, grid=grid,
                                             verbose=False, **kwargs)


@pytest.mark.parametrize('delta,accepted', [
    (math.nextafter(1e-5, 0), False), (1e-5, False),
    (math.nextafter(1e-5, math.inf), True),
])
@pytest.mark.parametrize('maximize', [False, True])
def test_strict_representable_movement_boundary(delta, accepted, maximize):
    sign = 1 if maximize else -1
    assert improves(sign * delta, 0, maximize=maximize) is accepted
    result = descent({(0,): 0., (1,): sign * delta}, maximize=maximize)
    assert ((1,) in result['path']) is accepted
    # Use zero as the line-search base so subtraction has the identical strict boundary.
    result = descent({(0,): -sign, (1,): 0., (2,): sign * delta}, maximize=maximize)
    assert ((2,) in result['path']) is accepted
    assert result['history'][1]['line_search_points'][1][2] == ('accepted' if accepted else 'rejected')


def test_no_relative_improvement_and_ties_remain_independent():
    assert improves(1e8 - 0.01, 1e8)
    result = descent({(0, 0): 1., (-1, -1): 0.100001, (0, 1): 0.1},
                     start=(0, 0), diagonal=True, tie_break='first')
    assert result['path'][1] == (0, 1)  # Difference < movement tolerance is not a tie.
    result = descent({(0, 0): 1., (-1, -1): 0.1 + 5e-13, (0, 1): 0.1},
                     start=(0, 0), diagonal=True, tie_break='first')
    assert result['path'][1] == (-1, -1)


@pytest.mark.parametrize('tol', [-1., math.nan, math.inf, -math.inf, '1e-5', True])
@pytest.mark.parametrize('option', ['tol', 'improvement_abs_tol'])
def test_invalid_tolerances_fail_before_callbacks(tol, option):
    tracker = ObservedObjective(lambda p: pytest.fail('Must validate before calling objective'))
    with pytest.raises(ValueError, match='finite and nonnegative'):
        descent({(0,): 0.}, tracked_objective=tracker, **{option: tol})
    with pytest.raises(ValueError, match='finite and nonnegative'):
        multi({(0,): 0.}, [(0,)], tracked_objective=tracker, **{option: tol})


@pytest.mark.parametrize('invalid', [math.nan, math.inf, -math.inf])
def test_nonfinite_response_is_neither_move_nor_target(invalid):
    assert not improves(invalid, 1.)
    assert improves(1., invalid)
    assert not common_target_reached(invalid, 0.)
    assert not common_target_reached(0., invalid)
    tracker = ObservedObjective(lambda p: {(0,): invalid, (1,): 3., (2,): 2.}[p])
    for p in ((0,), (1,), (2,)):
        tracker(p)
    assert tracker.incumbent_trajectory == [None, 3., 2.]
    assert tracker.call_count == 3


@pytest.mark.parametrize('invalid', [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize('maximize', [False, True])
@pytest.mark.parametrize('cached', [False, True])
def test_descent_records_finite_recovery_from_invalid_start(invalid, maximize, cached):
    grid = {(0,): invalid, (1,): 1.}
    kwargs = {'start_value': invalid} if cached else {}
    result = descent(grid, maximize=maximize, **kwargs)
    assert result['path'] == [(0,), (1,)]
    trajectory = result['result_record']['incumbent_trajectory']
    # The start (0,) is a neighbor of (1,); its stored value is reused without a call.
    assert trajectory == [None, 1.]
    assert result['result_record']['best_value'] == 1.
    assert result['result_record']['total_evals'] == (1 if cached else 2)
    assert result['revisits'] == 1
    historical = descent(grid, maximize=maximize, reevaluate_explored=True, **kwargs)
    assert historical['result_record']['incumbent_trajectory'] == [None, 1., 1.]
    assert historical['result_record']['total_evals'] == (2 if cached else 3)
    legacy = descent(grid, maximize=maximize, improvement_abs_tol=None, **kwargs)
    first = legacy['result_record']['incumbent_trajectory'][0]
    assert math.isnan(first) if math.isnan(invalid) else first == invalid


def test_descent_local_trajectory_excludes_declared_failure_penalty():
    grid = {(0,): 1e6, (1,): 1.}
    tracker = ObservedObjective(lambda p: grid[p], penalty=1e6)
    result = descent(grid, tracked_objective=tracker)
    assert result['result_record']['incumbent_trajectory'] == [None, 1.]
    tracker = ObservedObjective(lambda p: grid[p], penalty=1e6)
    result = descent(grid, tracked_objective=tracker, reevaluate_explored=True)
    assert result['result_record']['incumbent_trajectory'] == [None, 1., 1.]


@pytest.mark.parametrize('target', [0., 0.5, 32., -32.])
def test_target_boundary_and_nonzero_scaling_match_adopted_analysis(target):
    from review_comparison.dsda_publication import hit

    radius = 1e-5 * max(1., abs(target))
    boundary = target + radius
    for value in (target, boundary, math.nextafter(boundary, target),
                  math.nextafter(boundary, math.inf), target + 2 * radius):
        assert common_target_reached(value, target) == hit(value, target)
    assert common_target_reached(target + radius / 2, target)
    assert not common_target_reached(target + radius * 2, target)
    if target == 0:
        assert common_target_reached(radius, target)  # Inclusive exact boundary.
        assert not common_target_reached(math.nextafter(radius, math.inf), target)


def test_observed_rejected_move_checkpoint_and_budget_precedence():
    grid = {(0,): 1.1e-5, (1,): 9e-6, (2,): 2.}
    starts = [(0,), (2,), (2,)]
    result = multi(grid, starts, max_points_explored=8)
    assert result['runs'][0]['path'] == [(0,)]
    assert result['best_value'] == 1.1e-5
    assert result['observed_best_value'] == 9e-6
    assert result['result_record']['target_reached']
    assert result['result_record']['found_optimum']
    assert result['target_stop_checks'] == [dict(
        descent_index=1, callback=4, observed_incumbent=9e-6, target=0., reached=True)]
    # On an exhausted budget, target reporting remains true but budget wins as reason.
    result = multi(grid, starts, max_points_explored=4)
    # A natural completion at B retains the saved protocol's checkpoint.
    assert result['stop_reason'] == 'target_common_success'
    assert result['target_stop_checks'][0]['callback'] == 4
    # An improving terminal evaluation exercises the interruption budget branch.
    budget_grid = {(0,): 1., (1,): 0., (2,): 2.}
    result = multi(budget_grid, starts, max_points_explored=4)
    assert result['stop_reason'] == 'max_points_explored'
    assert result['target_stop_checks'] == []
    assert result['target_reached']


def test_target_mid_descent_does_not_stop_callback_immediately():
    grid = {(0,): 1., (-1,): 0., (1,): 2., (5,): 3.}
    result = multi(grid, [(0,), (5,), (5,)], max_points_explored=20)
    # Target is callback 4; the remaining neighbor (1,) is callback 5, and the
    # descent from (-1,) revisits (0,) without a call before the checkpoint.
    assert result['target_stop_checks'][0]['callback'] == 5
    assert result['total_point_evaluations_including_initial_ranking'] == 5
    assert result['stop_reason'] == 'target_common_success'
    historical = multi(grid, [(0,), (5,), (5,)], max_points_explored=20, reevaluate_explored=True)
    assert historical['target_stop_checks'][0]['callback'] == 6


def test_grid_ranked_restarts_initial_order_repeats_and_legacy():
    grid = {(0,): 3., (3,): 2., (6,): 1.}
    events = []
    tracker = ObservedObjective(lambda p: events.append(p) or grid[p])
    result = multi(grid, [(0,), (3,), (6,)], tracked_objective=tracker, target_value=-1.)
    assert events == [(0,), (3,), (6,)]
    assert [r['start_point'] for r in result['runs']] == [(6,), (3,), (0,)]
    result = multi({(0,): 0., (1,): -5e-6}, [(0,), (0,), (0,)],
                   improvement_abs_tol=None, target_stop=None, target_value=-5e-6)
    assert result['runs'][0]['path'] == [(0,), (1,)]
    assert result['initial_points_evaluated'] == 3
    assert 'target_stop_checks' not in result
    assert result['stop_reason'] is None
    new = multi({(0,): 0., (1,): -5e-6}, [(0,), (0,), (0,)], target_value=-5e-6)
    assert new['runs'][0]['path'] == [(0,)]
    assert new['stop_reason'] == 'target_common_success'


def test_grid_benchmark_preserves_common_success_and_csv(tmp_path):
    from benchmark import run_dsda_benchmark_case

    csv_path = tmp_path / 'tiny.csv'
    csv_path.write_text('x,y,z_norm\n0,0,0.000011\n1,0,0.000009\n2,0,2\n')
    result = run_dsda_benchmark_case(csv_path, [(0, 0), (2, 0), (2, 0)],
                                     seed=0, n_starts=3, max_evals=20, target_value=0.)
    record = result['result_record']
    assert record['best_value'] > 1e-5
    assert record['found_optimum'] and record['target_reached']
    save_results_csv([record], tmp_path / 'output.csv')
    with (tmp_path / 'output.csv').open() as stream:
        assert next(csv.DictReader(stream))['target_reached'] == 'True'


@pytest.mark.parametrize('case', ['cstr', 'column', 'dynamic', 'small_batch'])
def test_process_public_wrappers_use_single_start_and_preserve_success_meanings(case, monkeypatch):
    module = importlib.import_module('case_studies.' + case + '_dsda')
    target = 10.
    if case == 'cstr':
        monkeypatch.setattr(module, 'load_cstr_case_data', lambda size: dict(
            upper_bounds=(3, 3), feasible_objectives={}, known_best_point=(3, 3),
            known_best_value=target, csv_name='synthetic.csv'))
    else:
        monkeypatch.setattr(module, 'KNOWN_BEST_VALUE', target)
        monkeypatch.setattr(module, 'KNOWN_BEST_POINT', (3, 3))
        monkeypatch.setattr(module, 'LOWER_BOUNDS', (1, 1))
        monkeypatch.setattr(module, 'UPPER_BOUNDS', (3, 3))
    events = []
    def objective(point, **kwargs):
        events.append(tuple(point))
        return target + (2e-5 if tuple(point) == (2, 2) else 2.)
    monkeypatch.setattr(module, case + '_objective', objective)
    original = module.dsda_from_csv
    calls = []
    def recording(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, 'dsda_from_csv', recording)
    starts = [(1, 1), (2, 2), (3, 3)]
    result = getattr(module, 'run_' + case + '_dsda')(
        starting_points=starts, max_evaluations=20)
    assert events[:3] == starts
    assert len(calls) == 1
    assert calls[0]['improvement_abs_tol'] == 1e-5
    assert 'target_stop' not in calls[0]
    assert result['selected_start'] == (2, 2)
    assert result['result_record']['target_reached']
    assert not result['result_record']['found_optimum']
    assert len(events) == 11  # Initial 3 + all 8 neighbors; no target stop/restart.


def test_replay_rejects_missing_response_and_invalid_pairing():
    from review_comparison.dsda_protocol_replay import read_response, response_table, validate_jobs
    with pytest.raises(KeyError, match='Missing stored lookup'):
        read_response({}, (1, 2))
    with pytest.raises(ValueError, match='Inconsistent stored response'):
        response_table([dict(point=[1], raw_objective=v, accepted=True) for v in (1., 2.)])
    jobs = [dict(spec=dict(scope='grid', case=f'f{c}', budget=b, seed=s, method='dsda',
                           starts=[[0], [0], [0]], job_id=f'{c}_{b}_{s}'))
            for c in range(21) for b in (10, 30, 50, 70, 100) for s in range(10)]
    validate_jobs(jobs, 'grid')
    with pytest.raises(ValueError, match='Incomplete'):
        validate_jobs(jobs[:-1], 'grid')
    with pytest.raises(ValueError, match='Duplicate'):
        validate_jobs(jobs[:-1] + [jobs[0]], 'grid')
    jobs[0]['spec']['method'] = 'rbfopt'
    with pytest.raises(ValueError, match='Wrong scope or method'):
        validate_jobs(jobs, 'grid')
    jobs[0]['spec']['scope'] = 'process'
    with pytest.raises(ValueError, match='Wrong scope or method'):
        validate_jobs(jobs, 'grid')


def test_no_configuration_is_evaluated_twice():
    """Like the original D-SDA and LD-SDA, revisits reuse stored values for free."""
    grid = {(x,): float((x - 7) ** 2) for x in range(0, 12)}
    calls = []
    tracker = ObservedObjective(lambda p: calls.append(p) or grid[p])
    result = descent(grid, start=(2,), tracked_objective=tracker, diagonal=True)
    assert len(calls) == len(set(calls))
    assert result['best_point'] == (7,)
    assert result['revisits'] > 0
    calls.clear()
    tracker = ObservedObjective(lambda p: calls.append(p) or grid[p])
    historical = descent(grid, start=(2,), tracked_objective=tracker, diagonal=True, reevaluate_explored=True)
    assert len(calls) > len(set(calls))
    assert historical['path'] == result['path']


def test_known_values_are_shared_and_not_charged():
    grid = {(x,): float(abs(x - 3)) for x in range(0, 7)}
    calls = []
    tracker = ObservedObjective(lambda p: calls.append(p) or grid[p])
    known = {(2,): 1., (6,): 3.}
    result = descent(grid, start=(6,), start_value=3., tracked_objective=tracker, known_values=known,
                     max_points_explored=3)
    # (5,), (4,), (3,) are new; the line search reaches the known (2,) and stops for free.
    assert calls == [(5,), (4,), (3,)] and result['best_point'] == (3,)
    assert known[(5,)] == 2. and known[(3,)] == 0.


def test_multistart_never_repeats_across_descents():
    grid = {(x,): float(min(abs(x - 2), abs(x - 9) - 0.5)) for x in range(0, 12)}
    calls = []
    tracker = ObservedObjective(lambda p: calls.append(p) or grid[p])
    multi(grid, [(4,), (6,), (11,)], tracked_objective=tracker, target_value=-10., max_points_explored=40)
    assert len(calls) == len(set(calls))
