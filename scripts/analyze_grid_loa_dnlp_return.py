"""Audit the three returned LOA jobs without rerunning any optimization solver."""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import importlib
import importlib.metadata
import io
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = 'grid_loa_dnlp_20261025_result.zip'
ARCHIVE_SHA = 'fd6ca5b560f1e3ed280e3b1f031b26b2bede5e88e84969454fa319363da128db'
DELIVERY = 'grid_loa_dnlp_dantzig_20261025'
DELIVERY_SHA = '2d50162aebced5b299c8ef40248ab626a59bf95650182066b12524b58ad46d3d'
SOURCE_REVISION = '20b080417ca6d9409f85cfcd7004fded55e79c21'
GRIDS = ('holder_table', 'michalewicz', 'shubert')
POINTS = (('holder_table', (3, 1)), ('holder_table', (3, 29)),
          ('holder_table', (27, 1)), ('holder_table', (27, 29)),
          ('michalewicz', (21, 15)), ('shubert', (17, 22)))
TOLERANCE = 1e-5


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def members(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        require(archive.testzip() is None and len(names) == len(set(names)), 'Corrupt or duplicate ZIP entries')
        require(all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in names), 'Unsafe archive path')
        roots = [n[:-len('run.json')] for n in names if n.endswith('/run.json') and n.count('/') == 1]
        require(len(roots) == 1 and all(n.startswith(roots[0]) for n in names), 'Unexpected result roots')
        files = {n[len(roots[0]):]: archive.read(n) for n in names}
    inventory = {n: digest for digest, n in (line.split('  ', 1) for line in files['SHA256SUMS'].decode().splitlines())}
    require(set(inventory) == {n for n in files if Path(n).name != 'SHA256SUMS'}, 'Incomplete archive inventory')
    require(all(sha(files[n]) == digest for n, digest in inventory.items()), 'Archive checksum mismatch')
    return files, roots[0], inventory


def jsonlines(content):
    return [json.loads(line) for line in content.decode().splitlines()]


def effective_options(log, expected_presolve='false', expected_mtype='dnlp'):
    """Recover the actual GDPopt config from tee output, not requested CLI options."""
    headers = list(re.finditer(r'^Starting GDPopt version .+ using LOA algorithm$', log, re.M))
    require(len(headers) == 1, 'Expected exactly one actual LOA entry')
    text = log[headers[0].start():].split('\nIf you use this software', 1)[0]
    options = {}
    section = None
    for line in text.splitlines()[1:]:
        match = re.fullmatch(r'([A-Za-z_]+):\s*(.*)', line)
        if match:
            key, value = match.groups()
            options[key] = value if value else {}
            section = key if not value else None
        elif section and (match := re.fullmatch(r'\s+(\w+):\s*(\S+)', line)):
            options[section][match[1]] = match[2]
    require(options.get('subproblem_presolve') == expected_presolve, 'Actual presolve option differs')
    require(options.get('mip_presolve') == 'true', 'MIP presolve was changed')
    require(options.get('nlp_solver_args') == {'mtype': expected_mtype, 'solver': 'scip'}, 'Actual NLP route differs')
    require(options.get('mip_solver_args') == {'mtype': 'mip', 'solver': 'scip'}, 'Actual MIP route differs')
    require(options.get('bound_tolerance') == '1e-05' and options.get('init_algorithm') == 'set_covering',
            'Target-related option or initialization differs')
    # Function addresses and logger representations are retained in raw config text only.
    stable = {k: v for k, v in options.items() if not k.startswith('call_') and k not in ('logger', 'subproblem_initialization_method')}
    return stable, text


def call_accounting(calls, log, active=None):
    require([c['index'] for c in calls] == list(range(1, len(calls) + 1)), 'Missing/duplicate solver-call indices')
    if active:
        require(active['index'] == len(calls) + 1 and active['status'] == 'running', 'Unexpected interrupted call')
    count = Counter((c['mtype'], c['status']) for c in calls)
    starts = Counter(re.findall(r'^--- Executing (\w+) \(', log, re.M))
    require(set(starts) <= {'SCIP'}, 'Unexpected optimizer invocation')
    versions = sorted(set(re.findall(r'^SCIP version (.+)$', log, re.M)))
    require(versions == ['9.2.4 (a94f778ac8)'], 'SCIP runtime version differs')
    require(all(c['solver'] == 'scip' and c['threads'] == 1 for c in calls + ([active] if active else [])),
            'Solver or thread setting differs')
    return dict(journaled_interface_attempts=len(calls), started_interface_attempts=len(calls) + bool(active),
                completed_mip_calls=count['mip', 'returned'], completed_dnlp_calls=count['dnlp', 'returned'],
                error_interface_attempts=sum(c['status'] == 'error' for c in calls),
                active_unjournaled_attempts=int(bool(active)), active_attempt=active,
                confirmed_scip_invocations=starts['SCIP'], scip_versions=versions,
                journaled_interface_wall_s=sum(c['wall_s'] for c in calls),
                failed_interface_wall_s=sum(c['wall_s'] for c in calls if c['status'] == 'error'),
                gams_solve_time_s=sum(c.get('gams_statistics', {}).get('ETSOLVE', 0) for c in calls),
                no_marginals_messages=log.count('Solver did not provide marginals'))


@contextmanager
def original_models(files):
    """Use the preserved original model code and block all optimization execution."""
    prefixes = ('gdp_models', 'diagnostic')
    def selected(name):
        return any(name == p or name.startswith(p + '.') for p in prefixes)
    previous = {n: m for n, m in sys.modules.items() if selected(n)}
    old_path = sys.path[:]
    with TemporaryDirectory(prefix='loa-dnlp-audit-') as temporary:
        root = Path(temporary)
        for name, content in files.items():
            if name.startswith(('package/original_source/', 'package/execution/')):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(content)
        try:
            for name in previous:
                del sys.modules[name]
            sys.path[:0] = [str(root / 'package/original_source'), str(root / 'package/execution')]
            diagnostic = importlib.import_module('diagnostic')
            grid = importlib.import_module('gdp_models.grid')
            comparison = importlib.import_module('gdp_models.comparison')
            import pyomo.environ as pyo
            with patch('subprocess.Popen', side_effect=AssertionError('No subprocess in return analysis')), \
                 patch.object(type(pyo.SolverFactory), '__call__', side_effect=AssertionError('No solver in return analysis')), \
                 patch.object(comparison.TimedGAMS, 'solve', side_effect=AssertionError('No GAMS solve in return analysis')):
                yield diagnostic, grid
        finally:
            sys.path[:] = old_path
            for name in list(sys.modules):
                if selected(name):
                    del sys.modules[name]
            sys.modules.update(previous)


def analyze(output):
    require(not output.exists(), 'Use a fresh output directory')
    data = (ROOT / 'results/archives' / ARCHIVE).read_bytes()
    require(sha(data) == ARCHIVE_SHA, 'Unexpected returned archive')
    files, root_name, inventory = members(data)
    def read(name):
        return json.loads(files[name])
    delivery = ROOT / 'results/grid_loa_dnlp_20261025' / (DELIVERY + '.zip')
    require(sha(delivery.read_bytes()) == DELIVERY_SHA, 'Delivery bytes changed')
    with zipfile.ZipFile(delivery) as package:
        source_count = 0
        for name in package.namelist():
            relative = name[len(DELIVERY) + 1:]
            require(files['package/' + relative] == package.read(name), 'Executed package changed: ' + relative)
            source_count += 1
    manifest = read('package/DIAGNOSTIC_MANIFEST.json')
    for name, digest in manifest['original_source_sha256'].items():
        require(sha(files['package/original_source/' + name]) == digest, 'Historical source changed: ' + name)
        if name != 'gdp_models/comparison.py':
            require(files['package/original_source/' + name] == files['package/execution/' + name], 'Unexpected existing-source change: ' + name)
    previous, _, previous_inventory = members(files['predecessor_result.zip'])
    require(sha(files['predecessor_result.zip']) == '303012e48a2480ddcabb5388fe2a7d1c6f83082795484bd13b7f0130671a1b1a', 'Wrong predecessor')
    require(json.loads(previous['run.json'])['actual_full_loa_runs'] == 0, 'Unexpected predecessor full run')
    run, base, env = read('run.json'), read('package/BASELINE.json'), read('environment.json')
    original_archive = ROOT / 'results/archives' / base['original_archive']
    require(sha(original_archive.read_bytes()) == base['original_archive_sha256'], 'Original LOA archive changed')
    for key in ('host', 'python', 'gams_version', 'gams_sha256', 'affinity', 'versions', 'thread_environment'):
        require(env['actual'][key] == env['expected'][key], 'Environment differs: ' + key)
    require(run['pyomo_modules_unchanged'], 'Pyomo modules changed during run')
    ledger = jsonlines(files['launch_ledger.jsonl'])
    expected = [('fixed', g, list(p), 60) for g, p in POINTS] + [('full', g, None, 1800) for g in GRIDS]
    require([(r['kind'], r['grid_name'], r['point'], r['time_limit_s']) for r in ledger] == expected, 'Scope/order/call caps differ')
    require(run['status'] == 'completed' and run['full_loa_worker_launches'] == 3, 'Incomplete sequence')
    compile_summary = read('compile_preflight/summary.json')
    require([(r['grid_name'], tuple(r['point'])) for r in compile_summary['results']] == list(POINTS), 'Compile scope differs')
    require(all(r['passed'] and r['confirmed_optimizer_starts'] == 0 and 'action=c' in r['command'] for r in compile_summary['results']), 'Compile gate differs')
    fixed, comparison_rows, reference_rows, options, calls_by_grid, structures = [], [], [], {}, {}, []
    output.mkdir(parents=True)
    with original_models(files) as (d, grid_module):
        for grid, point in POINTS:
            prefix = f'fixed/{grid}_{point[0]}_{point[1]}/'
            result, probe = read(prefix + 'result.json'), read(prefix + 'baseline_probe.json')
            check = d.original_check(grid, read(prefix + 'solver_return.json')['variables'])
            counts = call_accounting(jsonlines(files[prefix + 'solver_calls.jsonl']), files[prefix + 'run.log'].decode())
            require(check['target_hit'] and check['has_feasible_solution'] and check['grid_point'] == list(point), 'Fixed original-GDP gate fails')
            require(result['actual_solver_calls'] == counts['confirmed_scip_invocations'] == counts['completed_dnlp_calls'] == 1, 'Fixed call cap differs')
            require(result['gate_passed'] and result['returned_solution_count'] == 1 and result['unchanged_subproblem_structure'], 'Incomplete fixed gate')
            require(not probe['default_presolve_allows_solver'] and probe['optimization_calls'] == 0, 'Unexpected default probe')
            require(probe['subproblem_before_option_sha256'] == probe['subproblem_after_option_sha256'], 'Fixed algebra changed')
            settings = read(prefix + 'effective_gdpopt_config.json')
            require(settings['subproblem_presolve'] is False and settings['mip_presolve'] is True and settings['nlp_solver_args'] == {'solver': 'scip', 'mtype': 'dnlp'}, 'Fixed options differ')
            fixed.append(dict(grid_name=grid, point=list(point), original_validation=check, actual_options=settings,
                              default_probe=probe, call_accounting=counts, worker_wall_s=result['worker_wall_s'],
                              termination=result['termination'], gate_passed=True))
        for grid in GRIDS:
            prefix = f'full/{grid}/loa/'
            result, solution = read(prefix + 'result.json'), read(prefix + 'solution.json')
            log = files[prefix + 'run.log'].decode()
            settings, text = effective_options(log)
            old_settings, _ = effective_options(base['original_effective_gdpopt_config_logs'][grid], 'true', 'nlp')
            require(settings.keys() == old_settings.keys(), 'Actual config keys differ from baseline')
            delta = {k: {'old': old_settings[k], 'new': v} for k, v in settings.items() if v != old_settings[k]}
            require(set(delta) == {'subproblem_presolve', 'nlp_solver_args'}, 'Unexpected actual option change')
            options[grid] = settings
            (output / (grid + '_actual_config.txt')).write_text(text.rstrip() + '\n')
            check = d.original_check(grid, solution['variables'])
            require(check['has_feasible_solution'] and check['target_hit'], 'Full returned original-GDP solution fails')
            require(abs(solution['objective'] - check['candidate_objective']) <= TOLERANCE, 'Saved objective differs from returned variables')
            initial = read(f'initial_templates/{grid}.json')
            fresh = grid_module.build_grid_gdp(grid)
            require(json.loads(json.dumps(d.structure(fresh))) == initial['structure'] and d.values(fresh) == initial['values'], 'Changed algebra/bounds or warm-started initial model')
            structures.append(dict(grid_name=grid, original_structure_sha256=d.structure(fresh)['sha256'],
                                   returned_initial_structure_matches_original=True,
                                   all_initial_values_match_fresh_constructor=True,
                                   initial_x=initial['values']['x'], initial_y=initial['values']['y']))
            calls = jsonlines(files[prefix + 'solver_calls.jsonl'])
            active = read(prefix + 'active_solver_call.json') if prefix + 'active_solver_call.json' in files else None
            counts = call_accounting(calls, log, active)
            calls_by_grid[grid] = counts
            require(counts['confirmed_scip_invocations'] == counts['completed_mip_calls'] + counts['completed_dnlp_calls'], 'SCIP banners and returns disagree')
            events = jsonlines(files[prefix + 'gdp_path.jsonl'])
            incumbents = jsonlines(files[prefix + 'incumbents.jsonl'])
            hits = [e for e in incumbents if e['event'] == 'gdpopt_feasible_subproblem' and e['has_feasible_solution'] and e['candidate_objective'] - check['reference_minimum'] <= TOLERANCE]
            require(hits, 'No recorded target subproblem')
            # Re-evaluate every recorded target vector from its actual physical values and binary indicators.
            hit_checks = []
            for event in hits:
                same = [e for e in events if e['iteration'] == event['iteration'] and e['event'] == 'before_subproblem']
                require(len(same) == 1, 'Ambiguous target evaluation entry')
                variables = dict(same[0]['binary_values'], x=event['physical_point'][0], y=event['physical_point'][1])
                verified = d.original_check(grid, variables)
                require(verified['target_hit'], 'Recorded first/target incumbent fails independent check')
                hit_checks.append(dict(event=event, original_validation=verified))
            for g, point in POINTS:
                if g != grid:
                    continue
                selected = [e for e in events if e.get('grid_point') == list(point)]
                path_counts = Counter(e['event'] for e in selected)
                require(path_counts['after_discrete_problem'] == path_counts['before_subproblem'] == path_counts['after_subproblem'] == 1, 'Reference path not fully evaluated')
                old_path = next(x for x in base['diagnostics'] if x['grid_name'] == grid and x['point'] == list(point))
                reference_rows.append(dict(grid_name=grid, point=list(point), old_discrete_selections=old_path['discrete_selections'],
                    old_evaluation_entries=old_path['before_subproblem_callbacks'], new_path_counts=dict(path_counts),
                    presolve_bypassed_in_actual_config=True, events=selected,
                    independently_checked_target_returns=[h for h in hit_checks if h['event']['grid_point'] == list(point)]))
            old = next(x for x in base['jobs'] if x['grid_name'] == grid)
            network = jsonlines(files.get(prefix + 'network_recovery.jsonl', b''))
            mips = [c for c in calls if c['mtype'] == 'mip' and c['status'] == 'returned']
            lower_values = sorted({c['lower_bound'] for c in mips})
            old_lower = old['reported_lower_bound']
            new_lower = result.get('reported_lower_bound')
            final_time = datetime.fromisoformat(read(prefix + 'process.json')['utc']) + timedelta(seconds=result['worker_wall_s'])
            row = dict(grid_name=grid, method='loa', old_objective=old['objective_recomputed'], new_objective=check['candidate_objective'],
                old_target_hit=old['target_hit_verified'], new_target_hit=check['target_hit'], old_termination=old['termination'],
                new_wrapper_status=result['status'], new_termination=result.get('termination'),
                new_termination_provenance='parent_watchdog' if result['hard_time_limit_reached'] else 'GDPopt_solver_results',
                old_max_violation=old['max_original_violation'], new_max_violation=check['max_primal_violation'],
                old_worker_wall_s=old['worker_wall_s'], new_worker_wall_s=result['worker_wall_s'],
                worker_wall_delta_s=result['worker_wall_s'] - old['worker_wall_s'], first_target_elapsed_s=hits[0]['elapsed_s'],
                first_target_iteration=hits[0]['iteration'], first_target_grid_point=hits[0]['grid_point'],
                time_after_first_target_s=result['worker_wall_s'] - hits[0]['elapsed_s'],
                final_grid_point=check['grid_point'], original_validation=check,
                reference_minimum=check['reference_minimum'], tolerance=TOLERANCE,
                old_reported_lower_bound=old_lower, old_reported_upper_bound=old['reported_upper_bound'],
                old_lower_bound_exceeds_known_reference=old_lower > check['reference_minimum'] + TOLERANCE,
                new_reported_lower_bound=new_lower, new_reported_upper_bound=result.get('reported_upper_bound'),
                new_lower_bound_exceeds_known_reference=None if new_lower is None else new_lower > check['reference_minimum'] + TOLERANCE,
                last_discrete_lower_bound=mips[-1]['lower_bound'], distinct_discrete_lower_bounds=lower_values,
                mip_rows_grow_one_per_iteration=all(c['gams_statistics']['NUMEQU'] == 127 + i for i, c in enumerate(mips)),
                completed_evaluation_entries=sum(e['event'] == 'after_subproblem' for e in events),
                discrete_selections=sum(e['event'] == 'after_discrete_problem' for e in events),
                old_confirmed_scip_invocations=old['confirmed_scip_invocations'], old_benchmark_nlp_calls=old['benchmark_nlp_calls'],
                call_accounting=counts, network_recovery=network,
                actual_options_verified_from_run_log=True, sidecar_actual_config_present=prefix + 'effective_gdpopt_config.json' in files,
                actual_option_delta_from_baseline=delta,
                original_reported_option_verified=result['actual_option_verified'], global_optimality_certified=False,
                started_utc=read(prefix + 'process.json')['utc'], ended_utc_from_worker_duration=final_time.isoformat())
            comparison_rows.append(row)
    actual_runs = len(options)
    require(actual_runs == len(run['full']) == 3 and len(fixed) == 6, 'Actual run scope differs')
    summary = dict(status='audited_completed', actual_fixed_solver_calls=sum(f['call_accounting']['started_interface_attempts'] for f in fixed),
        confirmed_fixed_scip_invocations=sum(f['call_accounting']['confirmed_scip_invocations'] for f in fixed),
        fixed_gates_passed=sum(f['gate_passed'] for f in fixed), actual_full_loa_runs=actual_runs,
        raw_reported_full_loa_runs=run['actual_full_loa_runs'], full_config_sidecars_present=sum(r['sidecar_actual_config_present'] for r in comparison_rows),
        old_target_hits=sum(r['old_target_hit'] for r in comparison_rows), new_target_hits=sum(r['new_target_hit'] for r in comparison_rows),
        full_started_interface_attempts=sum(c['started_interface_attempts'] for c in calls_by_grid.values()),
        full_confirmed_scip_invocations=sum(c['confirmed_scip_invocations'] for c in calls_by_grid.values()),
        full_completed_mip_calls=sum(c['completed_mip_calls'] for c in calls_by_grid.values()),
        full_completed_dnlp_calls=sum(c['completed_dnlp_calls'] for c in calls_by_grid.values()),
        full_error_interface_attempts=sum(c['error_interface_attempts'] for c in calls_by_grid.values()),
        full_active_unjournaled_attempts=sum(c['active_unjournaled_attempts'] for c in calls_by_grid.values()),
        old_total_worker_s=sum(r['old_worker_wall_s'] for r in comparison_rows), new_total_worker_s=sum(r['new_worker_wall_s'] for r in comparison_rows),
        fixed_total_worker_s=sum(f['worker_wall_s'] for f in fixed), compile_only_total_wall_s=sum(r['wall_s'] for r in compile_summary['results']),
        compile_only_calls=len(compile_summary['results']), compile_optimizer_calls=0,
        actual_option_verification_source='GDPopt effective-config block in each original run.log',
        maximum_original_violation=max(r['new_max_violation'] for r in comparison_rows),
        analysis_optimizer_calls=0, retry_or_new_package_needed_for_this_audit=False,
        whole_21_problem_results_replaced=False, global_optimality_certified=False)
    for name, value in [('summary.json', summary), ('comparison.json', comparison_rows), ('fixed_configurations.json', fixed),
                        ('reference_paths.json', reference_rows), ('actual_options.json', options), ('model_preservation.json', structures),
                        ('environment.json', env), ('compile_preflight.json', compile_summary)]:
        save(output / name, value)
    for name in ('run.json', 'launch_ledger.jsonl', 'predecessor_verification.json', 'analysis/summary.json', 'analysis/README.md'):
        path = output / 'returned_evidence' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(files[name])
    save(output / 'archive_inventory.json', dict(archive=ARCHIVE, root=root_name, files_sha256=inventory))
    write_report(output, summary, comparison_rows)
    save(output / 'manifest.json', dict(review_revision=base['review_revision'], execution_source_revision=SOURCE_REVISION,
        execution_preparation_base_revision=manifest['preparation_base_revision'], analysis_base_revision=SOURCE_REVISION,
        archive=ARCHIVE, archive_sha256=ARCHIVE_SHA, archive_bytes=len(data), archive_root=root_name,
        verified_archive_files=len(inventory), verified_predecessor_files=len(previous_inventory),
        original_archive=base['original_archive'], original_archive_sha256=base['original_archive_sha256'],
        delivery_sha256=DELIVERY_SHA, verified_delivery_files=source_count, original_source_files=len(manifest['original_source_sha256']),
        execution_matches_delivered_source=True, algorithm_option_delta=manifest['algorithm_option_delta'],
        actual_options=options, environment=env['actual'], scip_version='9.2.4 (a94f778ac8)',
        analysis_environment={'python': sys.version, 'pyomo': importlib.metadata.version('pyomo'), 'platform': sys.platform},
        acceptance_tolerance=TOLERANCE, target_rule='feasible original GDP and objective - unchanged reference minimum <= 1e-5',
        source_sha256=sha(Path(__file__).read_bytes()), optimization_calls_during_analysis=0,
        reproduction_command='python scripts/analyze_grid_loa_dnlp_return.py --output /tmp/grid_loa_dnlp_audit_fresh',
        outputs_sha256={str(p.relative_to(output)): sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
    return summary


def write_report(output, summary, rows):
    table = '\n'.join(f"| {r['grid_name']} | {r['old_objective']:.12g} | {r['new_objective']:.12g} | {r['first_target_elapsed_s']:.3f} | {r['old_worker_wall_s']:.3f} | {r['new_worker_wall_s']:.3f} | {r['new_max_violation']:.3g} | {r['new_wrapper_status']} / {r['new_termination']} |" for r in rows)
    counts = '\n'.join(f"| {r['grid_name']} | {r['call_accounting']['completed_mip_calls']} | {r['call_accounting']['completed_dnlp_calls']} | {r['call_accounting']['error_interface_attempts']} | {r['call_accounting']['active_unjournaled_attempts']} | {r['call_accounting']['confirmed_scip_invocations']} | {r['last_discrete_lower_bound']:.12g} |" for r in rows)
    delta = summary['new_total_worker_s'] - summary['old_total_worker_s']
    (output / 'README.md').write_text('''# Selective SCIP/DNLP LOA follow-up: returned Dantzig results

All six fixed configurations return SCIP solutions that pass independent checks against the unchanged original GDP and the existing 1e-5 target criterion.
All three full LOA runs also return feasible target solutions, changing the paired target count from 0/3 to 3/3.
There are three new-only target hits and no both-hit, old-only-hit or both-miss pair.
This is evidence of recovered target configurations, not improved termination time or a global optimality certificate.
This follow-up combines subproblem_presolve=False and nlp_solver_args.mtype=dnlp with solver=scip.
The preceding single-option experiment failed at GAMS NLP compilation and remains preserved separately.
The effect cannot be attributed to the presolve flag alone independently of the export-type change.

| Problem | Prior objective | New objective | First target seconds | Prior worker seconds | New worker seconds | New maximum original violation | New wrapper / termination |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
''' + table + f'''

The prior three runs all reported optimal but missed the known feasible reference objective of zero.
Their lower bounds exceeded that reference and remain recorded as inconsistent bounds for the original GDP.
The new three runs all reach their time limits; finished for Michalewicz and Shubert means normal worker completion with GDPopt maxTimeLimit, not optimal termination.
Holder table is stopped by the parent watchdog, so its maxTimeLimit is a parent classification and no final GDPopt bound pair was returned.
Its last discrete lower bound is kept separately and is not substituted into a missing final bound field.
The new total worker time is {summary['new_total_worker_s']:.3f} seconds ({summary['new_total_worker_s']/60:.3f} minutes), versus {summary['old_total_worker_s']:.3f} seconds previously.
This is an increase of {delta:.3f} seconds ({100*delta/summary['old_total_worker_s']:.2f}%), with different successful versus unsuccessful outcomes.
First-target times are measured from the method start using feasible-subproblem events, not from the final incumbent timestamp or the end of the worker.
Holder table first reaches the tolerance at [3,29] before replacing it with a numerically smaller value at [3,1].
Worker timing includes slightly more setup than the event clock, so time-after-target differences are descriptive rather than a separate solver timing measurement.

The default-presolve probes reject all six original-feasible reference configurations without solver calls.
With the recorded bypass, all six reference configurations are selected once, enter subproblem evaluation once and return target solutions once in the full runs.
All six fixed SCIP calls and all three full jobs are recorded in the launch ledger in the intended order.
The returned initial templates match fresh original constructor values and model structure, including objectives, constraints, bounds and logic.
No fixed diagnostic solution is used to warm-start a full run.
The original midpoint values are [0,0], [pi/2,pi/2] and [5,5] for holder_table, michalewicz and shubert respectively.

| Problem | Completed SCIP MIP | Completed SCIP DNLP | Failed interface attempts | Interrupted interface attempts | Confirmed SCIP starts | Last discrete lower bound |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
''' + counts + f'''

The full runs start {summary['full_started_interface_attempts']} solver-interface attempts, with {summary['full_confirmed_scip_invocations']} confirmed SCIP invocations.
The difference consists of one Shubert network-session start failure and one Holder table interface attempt interrupted before a SCIP banner was recorded.
The interrupted Holder table attempt is not counted as a confirmed SCIP solve, and its unrecorded duration is not fabricated.
Shubert retries the failed interface call once under the preserved network policy after a five-second backoff within the original shared deadline.
That recovery is not a second full LOA job or a replacement of a failed benchmark run.
Adding the six fixed solves gives {summary['full_confirmed_scip_invocations'] + summary['confirmed_fixed_scip_invocations']} confirmed SCIP invocations in this new experiment.
The six GAMS action=c checks use no optimization solver and take {summary['compile_only_total_wall_s']:.3f} seconds in total.
The six fixed workers take {summary['fixed_total_worker_s']:.3f} seconds in total.

Every completed SCIP call logs that GAMS received no marginals, and each problem's discrete lower bound remains unchanged throughout the recorded run.
The exported MIP equation count increases by one per iteration, consistent with exclusion cuts rather than stronger objective bounds.
Pyomo 6.10.0 LOA skips an OA linearization when its subproblem constraint has no dual value, which is a plausible explanation for this observed lack of bound progress.
This is a source-and-log inference; the archive does not directly snapshot the internal dual suffix or OA-cut collection.
It is not a controlled test of an alternative solver or cut policy, and no such change is made here.
This was inspected in the installed Pyomo 6.10.0 source and agrees with the [official LOA source documentation](https://pyomo.readthedocs.io/en/stable/_modules/pyomo/contrib/gdpopt/loa.html), whose current page identifies version 6.10.1.
The option also bypasses fixed-variable and trivial-constraint preprocessing, so solver routing and cost differ from the default run.

The original run.json incorrectly reports actual_full_loa_runs=0 and actual_option_verified=false for each full job.
The custom capture handler was removed while GDPopt configured tee logging, leaving the expected sidecar files absent.
The behavior is reproduced in a solver-free test of the installed Pyomo 6.10.0 logging context and is also visible in the [official logging utility source](https://pyomo.readthedocs.io/en/stable/_modules/pyomo/contrib/gdpopt/util.html).
The counter incorrectly used those missing files as evidence that no solve entered.
The actual effective configurations remain in all three run.log files and show subproblem_presolve=false, mip_presolve=true and SCIP/DNLP subproblems.
The launch ledger, LOA headers, call journals, SCIP banners, trajectory events and returned variables independently establish three actual full runs.
The audit corrects the derived count and option verification without editing any returned file or historical manifest.
The original erroneous summary and report are retained under returned_evidence, while the complete original logs remain in the immutable return ZIP.
No rerun or new package is required to recover this information.

The server matches the recorded Python 3.11.16, Pyomo 6.10.0, GAMS 52.2.0 executable hash and SCIP 9.2.4 (a94f778ac8).
CPU affinity is [14] and all recorded thread settings are one, as in the prior LOA experiment.
Affinity is not an exclusive reservation, so these single-run wall times should not be treated as replicated speed estimates.
The recorded Pyomo module hashes stay unchanged during execution.
The original 1800-second job limit, set-covering initialization, bound tolerance and network recovery policy remain in place.
The actual GDPopt time_limit is 1789 seconds because the original wrapper reserves time within the shared 1800-second worker budget.
The stable effective configuration fields differ from the original logged configuration only in subproblem_presolve and nlp_solver_args.mtype.

This selected three-problem diagnostic does not replace the original 21-grid experiment or recompute its ranking.
RIC, GLOA, direct MINLP, process GDPs and DFO experiments are not rerun.
Manuscript, Overleaf, representative figures and historical performance tables remain unchanged.
Adopting this result as a paper's representative experiment remains a separate review decision.
The archive, source package, input hashes, effective options, original-model checks, reference paths and output hashes are recorded in manifest.json and the accompanying JSON files.
The result archive is ../archives/grid_loa_dnlp_20261025_result.zip.
The analysis invokes no optimization solver and can be reproduced with the following command in a fresh output directory.

```bash
python scripts/analyze_grid_loa_dnlp_return.py --output /tmp/grid_loa_dnlp_audit_fresh
```
''')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(analyze(parser.parse_args().output), indent=2))
