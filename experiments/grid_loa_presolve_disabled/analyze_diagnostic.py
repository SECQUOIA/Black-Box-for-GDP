"""Analyze a completed or stopped diagnostic without invoking any solver."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re

from diagnostic import GRIDS, POINTS, TOLERANCE, original_check, read, save, sha


def events(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def analyze(run_dir, output):
    run_dir, output = Path(run_dir), Path(output)
    if output.exists():
        raise ValueError('Use a fresh analysis directory; original analysis is immutable')
    output.mkdir(parents=True)
    base = read(run_dir / 'package/BASELINE.json')
    run = read(run_dir / 'run.json')
    fixed, compared, reference_events = [], [], []
    for grid, point in POINTS:
        job = run_dir / 'fixed' / f'{grid}_{point[0]}_{point[1]}'
        row = read(job / 'result.json') if (job / 'result.json').exists() else {'status': 'not_run'}
        if (job / 'solver_return.json').exists():
            returned = read(job / 'solver_return.json')
            row['independent_original_validation'] = original_check(grid, returned['variables'])
        log = (job / 'run.log').read_text(errors='replace') if (job / 'run.log').exists() else ''
        calls = events(job / 'solver_calls.jsonl')
        row.update(grid_name=grid, point=list(point), journaled_call_attempts=len(calls),
                   confirmed_scip_invocations=len(re.findall(r'^--- Executing SCIP \(', log, re.M)),
                   actual_solver_kinds=dict(Counter(f"{c['solver']}/{c['mtype']}" for c in calls)),
                   active_call=read(job / 'active_solver_call.json') if (job / 'active_solver_call.json').exists() else None)
        fixed.append(row)
    for grid in GRIDS:
        old = next(r for r in base['jobs'] if r['grid_name'] == grid)
        job = run_dir / 'full' / grid / 'loa'
        new = read(job / 'result.json') if (job / 'result.json').exists() else {'status': 'not_run'}
        check = None
        if (job / 'solution.json').exists():
            check = original_check(grid, read(job / 'solution.json')['variables'])
        trace = events(job / 'grid_path.jsonl')
        incumbents = events(job / 'incumbents.jsonl')
        calls = events(job / 'solver_calls.jsonl')
        log = (job / 'run.log').read_text(errors='replace') if (job / 'run.log').exists() else ''
        settings = read(job / 'effective_gdpopt_config.json') if (job / 'effective_gdpopt_config.json').exists() else {}
        for g, point in POINTS:
            if g != grid:
                continue
            entries = [e for e in trace if e.get('grid_point') == list(point)]
            hit = [e for e in incumbents if e.get('grid_point') == list(point) and e.get('has_feasible_solution')
                   and e.get('candidate_objective') is not None and e['candidate_objective'] - old['reference_minimum'] <= TOLERANCE]
            reference_events.append({'grid_name': grid, 'point': list(point), 'events': entries,
                'discrete_selections': sum(e['event'] == 'after_discrete_problem' for e in entries),
                'evaluation_entries': sum(e['event'] == 'before_subproblem' for e in entries),
                'evaluation_returns': sum(e['event'] == 'after_subproblem' for e in entries),
                'target_incumbents': hit, 'presolve': 'bypassed_by_official_option' if settings.get('subproblem_presolve') == 'false' else 'not_verified'})
        compared.append(dict(grid_name=grid, method='loa', old_subproblem_presolve=True,
             old_objective=old['objective_recomputed'], old_termination=old['termination'],
             old_max_violation=old['max_original_violation'], old_worker_s=old['worker_wall_s'],
             old_target_hit=old['target_hit_verified'], old_solver_calls=old['confirmed_scip_invocations'],
             old_reference_evaluations=sum(d['before_subproblem_callbacks'] for d in base['diagnostics'] if d['grid_name']==grid),
             new_reference_evaluations=sum(e['evaluation_entries'] for e in reference_events if e['grid_name']==grid),
             new_reference_selections=sum(e['discrete_selections'] for e in reference_events if e['grid_name']==grid),
             new_reference_target_incumbents=sum(len(e['target_incumbents']) for e in reference_events if e['grid_name']==grid),
             new_status=new['status'], new_subproblem_presolve=settings.get('subproblem_presolve'),
             new_actual_options_verified=settings.get('subproblem_presolve') == 'false' and settings.get('mip_presolve') == 'true',
             new_objective=check['candidate_objective'] if check else None,
             new_termination=new.get('termination'), new_max_violation=check['max_primal_violation'] if check else None,
             new_target_hit=check['target_hit'] if check else None, new_worker_s=new.get('worker_wall_s'),
             new_original_validation=check, reference_minimum=old['reference_minimum'],
             new_reported_lower_bound=new.get('reported_lower_bound'), new_reported_upper_bound=new.get('reported_upper_bound'),
             lower_bound_exceeds_known_feasible_reference=new.get('reported_lower_bound') is not None
                 and new['reported_lower_bound'] > old['reference_minimum'] + TOLERANCE,
             new_solver_call_attempts=len(calls), new_confirmed_scip_invocations=len(re.findall(r'^--- Executing SCIP \(', log, re.M)),
             new_solver_call_kinds=dict(Counter(f"{c['solver']}/{c['mtype']}" for c in calls)),
             network_retry_events=events(job / 'network_recovery.jsonl'),
             global_optimality_certified=False))
    save(output / 'fixed_configurations.json', fixed)
    save(output / 'comparison.json', compared)
    save(output / 'reference_paths.json', reference_events)
    for name, rows in [('fixed_configurations', fixed), ('comparison', compared)]:
        with (output / (name + '.csv')).open('w') as stream:
            fields = list(dict.fromkeys(k for r in rows for k in r))
            writer = csv.DictWriter(stream, fields)
            writer.writeheader()
            writer.writerows({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in r.items()} for r in rows)
    summary = dict(status=run['status'], fixed_call_attempts=sum(r.get('actual_solver_calls', 0) for r in fixed),
         fixed_confirmed_scip_invocations=sum(r['confirmed_scip_invocations'] for r in fixed),
         full_loa_solve_entries=sum((run_dir / 'full' / g / 'loa/effective_gdpopt_config.txt').exists() for g in GRIDS),
         fixed_gates_passed=sum(bool(r.get('gate_passed')) for r in fixed),
         new_target_hits=sum(r['new_target_hit'] is True for r in compared), target_tolerance=TOLERANCE,
         optimization_calls_during_analysis=0, selective_three_problem_validation=True,
         original_21_results_replaced=False)
    save(output / 'summary.json', summary)
    table='\n'.join(f"| {r['grid_name']} | {r['old_objective']:.12g} | {r['old_termination']} | {r['old_max_violation']} | {r['old_worker_s']:.3f} | {r['old_reference_evaluations']} | {r['new_objective']} | {r['new_termination'] or r['new_status']} | {r['new_max_violation']} | {r['new_worker_s']} | {r['new_reference_evaluations']} | {r['new_target_hit']} |" for r in compared)
    text='''# LOA subproblem presolve disabled: returned diagnostic

This is a selective three-problem diagnostic, not a new 21-grid benchmark.
Only subproblem_presolve=False changes the full LOA optimization configuration.
The option also bypasses fixed-variable and trivial-constraint preprocessing, so solver routing and measured time may differ.
Known feasible reference objectives and the 1e-5 acceptance/target tolerance remain unchanged.
The table uses independently evaluated original-GDP objectives from the same returned variable vectors as the residual checks.
An optimal termination string does not certify the original nonconvex GDP, and inconsistent lower bounds are retained in comparison.json.

| Grid | Prior objective | Prior termination | Prior max violation | Prior seconds | Prior reference evaluations | New objective | New termination/status | New max violation | New worker seconds | New reference evaluations | New target |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
'''+table+'\n\n'+f"Fixed call attempts: {summary['fixed_call_attempts']}; confirmed SCIP invocations: {summary['fixed_confirmed_scip_invocations']}; full LOA solve entries: {summary['full_loa_solve_entries']}.\n"+f"Fixed gates passed: {summary['fixed_gates_passed']}/6; run status: {summary['status']}.\n"+'''The reference_paths.json file distinguishes discrete selection, bypassed presolve, evaluation entry, evaluation return and target incumbents for all six diagnostic coordinates.
Missing new values mean that the corresponding stage did not produce a result.
No solver is invoked by this analysis.
'''
    (output / 'README.md').write_text(text)
    inputs={str(p.relative_to(run_dir)):sha(p.read_bytes()) for p in sorted(run_dir.rglob('*'))
            if p.is_file() and not p.is_relative_to(output) and 'analysis' not in p.relative_to(run_dir).parts and p.name!='SHA256SUMS'}
    outputs={p.name:sha(p.read_bytes()) for p in sorted(output.iterdir()) if p.is_file()}
    save(output / 'manifest.json', {'review_revision':base['review_revision'],
        'original_archive_sha256':base['original_archive_sha256'], 'actual_run_settings':run.get('config'),
        'environment':read(run_dir / 'environment.json') if (run_dir / 'environment.json').exists() else None,
        'inputs_sha256':inputs, 'outputs_sha256':outputs,
        'reproduce':'python execution/analyze_diagnostic.py --run-dir <returned run> --output <fresh directory>'})
    return summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    analyze(args.run_dir,args.output)
