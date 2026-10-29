"""Audit the first RIC recovery return without rerunning optimization."""

import argparse
from collections import Counter
from datetime import datetime
import importlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import sys
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import analyze_grid_gdpopt_scip_return as first  # noqa: E402
from scripts import probe_grid_scip_presolve as probe  # noqa: E402

old = first.old
read, journal, require = first.read, first.journal, first.require
save, csvwrite, digest = first.save, first.csvwrite, first.digest
ARCHIVE = 'grid_gdpopt_scip_20261025_180435_dv1cn3et.zip'
SHA256 = '12cb50af02ef7621aca15dbc73b3972256ad8ca209f876a670badec52ce1abad'
PACKAGES = ROOT / 'results/runners/grid_gdpopt_scip_recovery_20261025'
POLICY = 'grid-scip-network-and-bohachevsky2-v1'
BASE_REVISION = '647019991f16d931c3f9f1905b35de885bc0bcd0'


def verify_selection(selection, baseline):
    """Reject survivor selection and bind each recovery to its original error."""
    expected = {r['grid_name']: r for r in baseline if r['status'] == 'error'}
    selected = selection['jobs']
    require(len(selected) == len(expected) and len({r['grid_name'] for r in selected}) == len(selected),
            'Missing or duplicate recovery selection')
    require({r['grid_name'] for r in selected} == set(expected), 'Recovery selection differs from original errors')
    for row in selected:
        original = expected[row['grid_name']]
        for key in ('method', 'status', 'failure_kind', 'result_sha256', 'target_hit_verified'):
            require(row[key] == original[key], 'Selection changes original result: ' + key)
    return expected


def sources_verified(archive, prefix, run):
    entry = next(r for r in json.loads((PACKAGES / 'BUILD_MANIFEST.json').read_text()) if r['method'] == 'ric')
    path = PACKAGES / entry['archive']
    require(digest(path.read_bytes()) == entry['sha256'], 'Delivered recovery package changed')
    with zipfile.ZipFile(path) as z:
        p = path.stem + '/'
        first.archive_integrity(z, p)
        expected = {r['path']: r['sha256'] for r in read(z, p + 'PACKAGE_MANIFEST.json')['files']}
        expected['PACKAGE_MANIFEST.json'] = digest(z.read(p + 'PACKAGE_MANIFEST.json'))
        require(run['source_sha256'] == expected, 'Executed recovery source inventory changed')
        for name, sha in expected.items():
            data = archive.read(prefix + 'source/' + name)
            require(digest(data) == sha and data == z.read(p + name), 'Executed source changed: ' + name)
        provenance = read(z, p + 'RECOVERY_PROVENANCE.json')
        for name, sha in provenance['unchanged_base_files'].items():
            require(digest(z.read(p + name)) == sha, 'Historical model/interface source changed')
        selection = read(z, p + 'RECOVERY_SELECTION.json')
    for name in ['gdp_models/grid.py', *[f'benchmark_grids/{g}.csv' for g in old.GRID_NAMES]]:
        require(archive.read(prefix + 'source/' + name) == (ROOT / name).read_bytes(), 'Independent audit model changed')
    return selection, dict(delivered_package=str(path.relative_to(ROOT)), delivered_sha256=entry['sha256'],
                           executed_source_files_verified=len(expected),
                           unchanged_base_files_verified=len(provenance['unchanged_base_files']))


def summary(rows):
    return dict(jobs=len(rows), target_hits=sum(r['target_hit_verified'] for r in rows),
                target_hits_without_error=sum(r['target_hit_verified'] and r['status'] != 'error' for r in rows),
                errors=sum(r['status'] == 'error' for r in rows),
                optimal=sum(r['termination'] == 'optimal' for r in rows),
                time_limits=sum(r['termination'] == 'maxTimeLimit' for r in rows),
                worker_wall_s=sum(r['worker_wall_s'] for r in rows))


def target_diagnostic(grid, point, trace, log, config):
    """Separate returned trace evidence from a solver-free local witness/probe."""
    model = old.build_grid_gdp(grid)
    model.x.set_value(old.pyo.value(model.gx[point[0]]))
    model.y.set_value(old.pyo.value(model.gy[point[1]]))
    for choices, chosen in zip((model.Xchoice, model.Ychoice), point):
        for index, disjunct in choices.items():
            disjunct.indicator_var.set_value(index == chosen)
    objective = float(old.pyo.value(model.obj))
    synthetic = dict(variables={v.name: v.value for v in model.component_data_objects(
        old.pyo.Var, descend_into=(old.pyo.Block, old.Disjunct))}, objective=objective)
    witness = old.verify_solution(grid, synthetic, dict(objective=objective, grid_point=point, target_hit=True))
    model, util = probe.setup(grid, point)
    error = None
    try:
        probe.fbbt(model, integer_tol=config.integer_tolerance,
                   feasibility_tol=config.constraint_tolerance, max_iter=config.max_fbbt_iterations)
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
    model, util = probe.setup(grid, point)
    with probe.preprocess_subproblem(util, config) as allowed:
        passes = bool(allowed)
    events = [e for e in trace if e.get('grid_point') == point]
    lines = log.splitlines()
    discrete = [e for e in events if e['event'] == 'after_discrete_problem']
    excerpts = []
    for event in discrete:
        pattern = re.compile(r'^\s*' + str(event['iteration']) + r'\s+discrete\s')
        matches = [(i, line) for i, line in enumerate(lines, 1) if pattern.match(line)]
        excerpts.extend(dict(line_number=i, text=line) for i, line in matches)
    return dict(grid_name=grid, point=point, original_gdp_witness=witness,
                witness_origin='Constructed locally at a fixed reference coordinate; not a returned solution or new solve.',
                returned_trace_events=events, returned_log_iteration_rows=excerpts,
                discrete_selections=len(discrete), before_subproblem_callbacks=sum(e['event'] == 'before_subproblem' for e in events),
                local_fbbt_error=error, local_presolve_allows_solver=passes,
                local_probe_scope='Common GDPopt preprocessing under RIC default tolerances; not a full Dantzig rerun.',
                optimization_solver_calls=0)


def analyze(output):
    require(not output.exists() or not any(output.iterdir()), 'Use a fresh output directory')
    output.mkdir(parents=True, exist_ok=True)
    require(importlib.metadata.version('pyomo') == '6.10.0', 'Local diagnostic requires recorded Pyomo version')
    # Construct only a configuration; never call solve, and block all later factories.
    config = old.pyo.SolverFactory('gdpopt.ric').config
    with patch.object(type(old.pyo.SolverFactory), '__call__', side_effect=AssertionError('Optimization forbidden in return audit')):
        baseline, _, baseline_inventory = first.analyze_archive('ric', first.ARCHIVES['ric'])
        path = ROOT / 'results/archives' / ARCHIVE
        require(digest(path.read_bytes()) == SHA256, 'Recovery archive identity mismatch')
        jobs, paired, diagnostics, trajectory_targets, times = [], [], [], [], []
        with zipfile.ZipFile(path) as archive:
            prefix = path.stem + '/'
            count = first.archive_integrity(archive, prefix)
            run = read(archive, prefix + 'run.json')
            selection, source = sources_verified(archive, prefix, run)
            originals = verify_selection(selection, baseline)
            require(selection['original_archive'] == baseline_inventory['archive']
                    and selection['original_archive_sha256'] == baseline_inventory['sha256'], 'Original archive binding differs')
            plan = json.loads((PACKAGES / 'PLAN_RIC.json').read_text())
            require(all(run['config'][k] == v for k, v in plan['config'].items()), 'Executed plan differs from delivery')
            runtime = run['runtime']
            require(runtime['gams_version'] == [52, 2, 0, 0] and runtime['gams_sha256'] == baseline_inventory['runtime']['gams_sha256'],
                    'GAMS identity differs')
            require(runtime['versions'] == baseline_inventory['runtime']['versions']
                    and runtime['python'] == baseline_inventory['runtime']['python'], 'Runtime versions differ')
            require(runtime['affinity']['effective_cpus'] == [12]
                    and all(v == '1' for v in runtime['thread_environment'].values()), 'CPU/thread policy differs')
            require(run['preflight_status'] == 'passed' and run['mode'] == 'run', 'Preflight or execution mode differs')
            names = archive.namelist()
            expected = {prefix + f'benchmark/{g}/ric/result.json' for g in originals}
            require({n for n in names if '/benchmark/' in n and n.endswith('/result.json')} == expected, 'Missing/extra recovery jobs')
            require(not any('/previous_attempts/' in n for n in names), 'Replaced job found')
            returned_summary = read(archive, prefix + 'summary.json')
            returned_rows = {r['grid_name']: r for r in returned_summary['results']}
            require(len(returned_rows) == len(returned_summary['results']) == len(originals), 'Duplicate summary row')
            for grid in plan['config']['grids']:
                job = prefix + f'benchmark/{grid}/ric/'
                result = read(archive, job + 'result.json')
                seal = read(archive, job + 'terminal.json')['files_sha256']
                members = {n[len(job):] for n in names if n.startswith(job)} - {'terminal.json'}
                require(members == set(seal), 'Missing or unsealed artifact')
                for name, sha in seal.items():
                    require(digest(archive.read(job + name)) == sha, 'Terminal seal mismatch')
                require(all(returned_rows[grid][k] == v for k, v in result.items()), 'Summary/result mismatch')
                require(result['status'] == 'finished' and result['worker_returncode'] == 0
                        and not result['hard_time_limit_reached'], 'Unexpected execution failure in this supplied RIC recovery')
                checked = old.verify_solution(grid, read(archive, job + 'solution.json'), result)
                calls = journal(archive, job + 'solver_calls.jsonl')
                log = archive.read(job + 'run.log').decode()
                evidence = first.call_evidence(calls, None, log, 'none')
                require(not any(n in seal for n in ('network_recovery.jsonl', 'active_solver_call.json')), 'Unexpected retry or unfinished call')
                require(len(calls) == result['solver_calls'] and all(c['status'] == 'returned' for c in calls), 'Call journal/result mismatch')
                require(abs(evidence['sum_journaled_call_wall_s'] - result['sum_solver_call_wall_s']) < 1e-6, 'Call timing mismatch')
                policy = read(archive, job + 'recovery_policy.json')
                require(policy['policy'] == result['recovery_policy'] == POLICY
                        and policy['max_attempts_per_network_call'] == 3
                        and policy['backoff_seconds'] == [5.0, 15.0]
                        and policy['time_limit'] == result['time_limit_s'] == 1800.0
                        and policy['warmstart'] is False, 'Recovery policy differs')
                trace = journal(archive, job + 'grid_path.jsonl')
                gdp = journal(archive, job + 'gdp_path.jsonl')
                require(len(trace) == len(gdp), 'Coordinate/binary trajectory length mismatch')
                for a, b in zip(trace, gdp):
                    require(all(b[k] == v for k, v in a.items()), 'Coordinate/binary trajectory mismatch')
                    n = a['completed_solver_calls']
                    require(0 <= n <= len(calls), 'Invalid callback call index')
                    if 'last_solver_call' in b:
                        require(n > 0 and b['last_solver_call'] == calls[n-1], 'Callback solver status mismatch')
                incumbents = journal(archive, job + 'incumbents.jsonl')
                eligible = [r for r in incumbents if r.get('has_feasible_solution') and r.get('candidate_objective') is not None]
                require(eligible and abs(min(r['candidate_objective'] for r in eligible) - checked['objective_recomputed']) <= 1e-8,
                        'Returned solution is not the best recorded feasible incumbent')
                hit_times = [r['elapsed_s'] for r in eligible if abs(r['candidate_objective'] - checked['reference_minimum']) <= 1e-5]
                points = result['grid_preparation']['audit']['csv_minimizers']
                for event in trace:
                    if event.get('grid_point') in points:
                        trajectory_targets.append(dict(grid_name=grid, **event))
                if result['termination'] == 'optimal' and not checked['target_hit_verified']:
                    diagnostics.extend(target_diagnostic(grid, point, trace, log, config) for point in points)
                process = read(archive, job + 'process.json')
                start = datetime.fromisoformat(process['utc']).timestamp()
                times.append((start, start + result['worker_wall_s']))
                before = [e for e in trace if e['event'] == 'before_subproblem']
                row = dict(grid_name=grid, method='ric', status=result['status'], termination=result['termination'], **checked, **evidence,
                           optimal_but_misses_target=result['termination'] == 'optimal' and not checked['target_hit_verified'],
                           reported_lower_bound=result['reported_lower_bound'], reported_upper_bound=result['reported_upper_bound'],
                           global_optimality_certified=result['global_optimality_certified'],
                           worker_wall_s=result['worker_wall_s'], method_wall_s=result['method_wall_s'],
                           first_target_incumbent_s=min(hit_times) if hit_times else None,
                           grid_path_events=len(trace), before_subproblem_callbacks=len(before),
                           distinct_before_subproblem_points=len({tuple(e['grid_point']) for e in before if e.get('grid_point') is not None}),
                           network_retries=0, bohachevsky2_fixed_exponent_bound_resets=result['bohachevsky2_fixed_exponent_bound_resets'],
                           started_utc=process['utc'], result_sha256=seal['result.json'], solution_sha256=seal['solution.json'],
                           grid_path_sha256=seal['grid_path.jsonl'])
                jobs.append(row)
                previous = originals[grid]
                require(previous['reference_minimum'] == checked['reference_minimum'], 'Reference changed')
                paired.append(dict(grid_name=grid, method='ric', old_status=previous['status'], new_status=row['status'],
                                   old_failure_kind=previous['failure_kind'], new_termination=row['termination'],
                                   old_target=previous['target_hit_verified'], new_target=row['target_hit_verified'],
                                   old_objective=previous['objective_recomputed'], new_objective=row['objective_recomputed'],
                                   old_grid_point=previous['grid_point'], new_grid_point=row['grid_point'],
                                   old_worker_wall_s=previous['worker_wall_s'], new_worker_wall_s=row['worker_wall_s'],
                                   objective_change=row['objective_recomputed'] - previous['objective_recomputed']))
            require(all(a[1] <= b[0] for a, b in zip(times, times[1:])), 'Workers overlap')
            require(returned_summary['planned_jobs'] == returned_summary['completed_jobs'] == len(jobs)
                    and returned_summary['all_jobs_finished']
                    and returned_summary['feasible_jobs'] == returned_summary['solutions_returned'] == len(jobs), 'Completion/solution counts differ')
            require(returned_summary['actual_benchmark_solver_calls'] == {'scip/mip': sum(j['journaled_call_attempts'] for j in jobs)},
                    'Summary call inventory differs')
            preflight = [c for n in names if '/preflight/' in n and n.endswith('/solver_calls.jsonl') for c in journal(archive, n)]
            require(Counter((c['solver'], c['mtype']) for c in preflight) == {('scip', 'mip'): 1, ('scip', 'nlp'): 2}, 'Preflight inventory differs')
            require(all(c['status'] == 'returned' for c in preflight), 'Preflight call failed')
            inventory = dict(archive=ARCHIVE, sha256=SHA256, bytes=path.stat().st_size, internal_checksums=count, **source,
                             config=run['config'], runtime=runtime, created_utc=run['created_utc'], preflight_calls=preflight)

    overlay = [next((n for n in jobs if n['grid_name'] == b['grid_name']), b) for b in baseline]
    descriptive = [dict(grid_name=r['grid_name'], method='ric',
                        attempt_cohort='recovery' if r['grid_name'] in originals else 'retained_first_attempt',
                        archive=ARCHIVE if r['grid_name'] in originals else baseline_inventory['archive'],
                        target_hit=r['target_hit_verified'], status=r['status'], termination=r['termination'],
                        objective=r['objective_recomputed'], worker_wall_s=r['worker_wall_s'],
                        result_sha256=r['result_sha256']) for r in overlay]
    overall = dict(recovery=summary(jobs), original_selected_errors=summary(list(originals.values())),
                   original_ric_21=summary(baseline), descriptive_ric_21_after_error_recovery=summary(overlay),
                   both_hit=sum(r['old_target'] and r['new_target'] for r in paired),
                   new_only=sum(not r['old_target'] and r['new_target'] for r in paired),
                   old_only=sum(r['old_target'] and not r['new_target'] for r in paired),
                   neither=sum(not r['old_target'] and not r['new_target'] for r in paired),
                   maximum_original_violation=max(r['max_original_violation'] for r in jobs),
                   maximum_objective_error=max(r['saved_objective_abs_error'] for r in jobs),
                   benchmark_scip_mip_calls=sum(r['confirmed_scip_invocations'] for r in jobs), benchmark_nlp_calls=0,
                   benchmark_interface_errors=0, network_retry_events=0, separate_preflight_mip_calls=1, separate_preflight_nlp_calls=2,
                   target_tolerance=1e-5, elapsed_first_worker_to_last_worker_s=times[-1][1] - times[0][0],
                   cumulative_ric_worker_s_all_original_and_recovery_attempts=sum(r['worker_wall_s'] for r in baseline + jobs),
                   recorded_optimal_target_mismatches=[r['grid_name'] for r in jobs if r['optimal_but_misses_target']],
                   unprovided_recovery_methods=['gloa', 'loa'], optimization_calls_during_analysis=0,
                   overlay_note='Descriptive mixture of nine retained first attempts and twelve recovery attempts; not a uniform new 21-job experiment.')
    for name, rows in [('jobs', jobs), ('paired_runs', paired)]:
        save(output / (name + '.json'), rows)
        csvwrite(output / (name + '.csv'), rows)
    csvwrite(output / 'ric_21_descriptive.csv', descriptive)
    save(output / 'target_path_events.json', trajectory_targets)
    save(output / 'target_mismatch_diagnostics.json', diagnostics)
    save(output / 'summary.json', overall)
    modules = ['pyomo.contrib.fbbt.fbbt', 'pyomo.contrib.fbbt.interval', 'pyomo.contrib.gdpopt.solve_subproblem']
    save(output / 'manifest.json', dict(source_base_revision=BASE_REVISION, archive=inventory, baseline=baseline_inventory,
         analysis_python=platform.python_version(), analysis_pyomo=importlib.metadata.version('pyomo'),
         analysis_sources_sha256={str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in [Path(__file__), Path(first.__file__), Path(old.__file__), Path(probe.__file__)]},
         local_diagnostic_modules_sha256={n: digest(Path(importlib.import_module(n).__file__).read_bytes()) for n in modules},
         diagnostic_ric_tolerances={k: config[k] for k in ('integer_tolerance', 'constraint_tolerance', 'max_fbbt_iterations')},
         outer_checksum_note='Computed from the supplied local ZIP; no independent server checksum sidecar was supplied.',
         original_provider_manifests_unchanged=True, target_definition='Normalized CSV objective minus unchanged CSV minimum <= 1e-5.',
         optimization_calls=0))
    save(output / 'verification.json', dict(all_archive_checksums_passed=True, all_terminal_files_present_and_verified=True,
         executed_source_equals_delivered_package=True, error_only_selection_verified=True, returned_solutions_verified=len(jobs),
         original_points_checked=961 * len(jobs), callbacks_linked_to_solver_journal=True, worker_intervals_sequential=True,
         original_21_run_denominator_preserved=True, no_original_result_replaced=True, no_optimization_calls=True))
    print(json.dumps(overall, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    analyze(parser.parse_args().output)
