"""Audit the three October 25 actual-SCIP Grid returns without optimization."""
import argparse
from collections import Counter
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
from scripts import analyze_grid_scip_return as old  # noqa: E402

ARCHIVES = {
    'gloa': ('grid_gdpopt_scip_20261025_072708_qh55t7wf.zip', '14f458f773a4c9f0ede9861f84e1bcbcd7050a282632e69a860c628fe52291bc', 16),
    'loa': ('grid_gdpopt_scip_20261025_072657_vzeme2eq.zip', 'ee1f588b9a98ef3bdd805742dd3b44ddbb53492c053df5321dc2809ba06b983f', 14),
    'ric': ('grid_gdpopt_scip_20261025_072643_lhdbfn9e.zip', '4f9338643dc40f30d1c41daa0f125fae820c031c32462a44af851fed77ac90d1', 12),
}
PACKAGES = ROOT / 'results/runners/grid_gdpopt_scip_split_20261025'
require, read, journal = old.require, old.read_json, old.journal
save, csvwrite, digest = old.save_json, old.save_csv, old.digest


def failure_kind(result, log):
    if result['status'] == 'error':
        if 'Error when trying to close network session' in log:
            return 'gams_network_session_close'
        if 'Error when trying to start network session' in log:
            return 'gams_network_session_start'
        if 'IntervalException: Cannot raise a negative variable to a fractional power.' in result.get('message', ''):
            return 'pyomo_fbbt_interval'
        return 'unclassified_error'
    if result['termination'] == 'maxTimeLimit':
        return 'worker_watchdog' if result['status'] == 'hard_time_limit' else 'time_limit'
    return 'none'


def call_evidence(calls, active, log, kind):
    require([c['index'] for c in calls] == list(range(1, len(calls)+1)), 'Missing/duplicate call indices')
    require(all(c['solver'] == 'scip' and c['mtype'] == 'mip' and c['threads'] == 1 for c in calls), 'Unexpected solver route')
    require(all(c['solver_option_file'] == ['gams/mipstart = 0', 'timing/clocktype = 2'] for c in calls), 'Changed SCIP options')
    require(all(c['status'] in {'returned', 'error'} for c in calls), 'Unclosed journal entry')
    returned = sum(c['status'] == 'returned' for c in calls)
    errors = len(calls)-returned
    require(errors == int(kind.startswith('gams_network_session_')), 'Error classification and calls disagree')
    versions = re.findall(r'^SCIP version (.+)$', log, re.M)
    executions = re.findall(r'^--- Executing SCIP \(', log, re.M)
    # Indented error-log echoes must not count as another solver invocation.
    require(len(versions) == len(executions), 'SCIP invocation log markers disagree')
    require(not versions or set(versions) == {'9.2.4 (a94f778ac8)'}, 'SCIP version differs')
    require(len(versions) == returned + int(kind == 'gams_network_session_close'), 'Solver/interface accounting differs')
    if active:
        require(active['index'] == len(calls)+1 and active['status'] == 'running'
                and active['solver'] == 'scip' and active['mtype'] == 'mip', 'Invalid active call')
        require(kind == 'worker_watchdog', 'Unexpected unclosed call outside watchdog')
    return dict(journaled_call_attempts=len(calls), returned_calls=returned, error_calls=errors,
                active_unjournaled_attempts=int(bool(active)), started_interface_attempts=len(calls)+int(bool(active)),
                confirmed_scip_invocations=len(versions), benchmark_nlp_calls=0,
                sum_journaled_call_wall_s=sum(c['wall_s'] for c in calls),
                failed_call_wall_s=sum(c['wall_s'] for c in calls if c['status'] == 'error'))


def archive_integrity(archive, prefix):
    names = archive.namelist()
    require(len(names) == len(set(names)) and archive.testzip() is None, 'Duplicate member or CRC failure')
    require(all(n.startswith(prefix) and '..' not in Path(n).parts for n in names), 'Unsafe member path')
    entries = [line.split('  ', 1) for line in archive.read(prefix+'SHA256SUMS').decode().splitlines()]
    require({n for _,n in entries} == {n[len(prefix):] for n in names} - {'SHA256SUMS'}, 'Incomplete checksums')
    for checksum, name in entries:
        require(digest(archive.read(prefix+name)) == checksum, 'Checksum failure: '+name)
    return len(entries)


def sources_verified(archive, prefix, run, method):
    build = json.loads((PACKAGES/'BUILD_MANIFEST.json').read_text())
    entry = next(r for r in build['packages'] if r['method'] == method)
    package_path = PACKAGES/entry['archive']
    require(digest(package_path.read_bytes()) == entry['sha256'], 'Delivered ZIP changed')
    with zipfile.ZipFile(package_path) as package:
        package_prefix = package_path.stem+'/'
        archive_integrity(package, package_prefix)
        inventory = read(package, package_prefix+'PACKAGE_MANIFEST.json')['files']
        expected = {r['path']:r['sha256'] for r in inventory}
        expected['PACKAGE_MANIFEST.json'] = digest(package.read(package_prefix+'PACKAGE_MANIFEST.json'))
        require(run['source_sha256'] == expected, 'Executed source inventory differs from delivered package')
        for name, checksum in expected.items():
            data = archive.read(prefix+'source/'+name)
            require(digest(data) == checksum and data == package.read(package_prefix+name), 'Executed bytes differ: '+name)
        provenance = read(package, package_prefix+'SPLIT_PROVENANCE.json')
        for name, checksum in provenance['unchanged_base_files'].items():
            require(digest(package.read(package_prefix+name)) == checksum, 'Base source identity mismatch')
    for name in ['gdp_models/grid.py', *[f'benchmark_grids/{g}.csv' for g in old.GRID_NAMES]]:
        require(archive.read(prefix+'source/'+name) == (ROOT/name).read_bytes(), 'Independent model/input differs: '+name)
    return dict(delivered_package=str(package_path.relative_to(ROOT)), delivered_sha256=entry['sha256'],
                executed_source_files_verified=len(expected), unchanged_base_files_verified=len(provenance['unchanged_base_files']))


def analyze_archive(method, spec):
    name, checksum, cpu = spec
    path = ROOT/'results/archives'/name
    require(digest(path.read_bytes()) == checksum, 'Return archive identity mismatch')
    jobs, failures = [], []
    with zipfile.ZipFile(path) as archive:
        prefix = path.stem+'/'
        internal = archive_integrity(archive, prefix)
        run = read(archive, prefix+'run.json')
        config = run['config']
        require(config['methods'] == [method] and config['grids'] == list(old.GRID_NAMES)
                and config['planned_jobs'] == 21, 'Run scope changed')
        require(config['time_limit'] == 1800 and config['relative_gap'] == 1e-5
                and config['threads'] == 1 and config['mip_solver'] == config['nlp_solver'] == 'scip', 'Solver settings changed')
        require(config['cpu'] == cpu and run['runtime']['affinity']['effective_cpus'] == [cpu], 'CPU assignment differs')
        require(all(v == '1' for v in run['runtime']['thread_environment'].values()), 'Thread environment differs')
        require(run['preflight_status'] == 'passed' and run['mode'] == 'run', 'Preflight or execution mode incorrect')
        source = sources_verified(archive, prefix, run, method)
        summary = read(archive, prefix+'summary.json')
        summary_jobs = {r['grid_name']:r for r in summary['results']}
        expected = {prefix+f'benchmark/{g}/{method}/result.json' for g in old.GRID_NAMES}
        actual = {n for n in archive.namelist() if '/benchmark/' in n and n.endswith('/result.json')}
        require(actual == expected and not any('/previous_attempts/' in n for n in archive.namelist()), 'Missing, duplicate or retried job')
        for grid in old.GRID_NAMES:
            job = prefix+f'benchmark/{grid}/{method}/'
            result = read(archive, job+'result.json')
            terminal = read(archive, job+'terminal.json')['files_sha256']
            present = {n[len(job):] for n in archive.namelist() if n.startswith(job)} - {'terminal.json'}
            require(present <= set(terminal), 'Unsealed job artifact')
            omitted = sorted(set(terminal)-present)
            require(all(Path(n).parts[0].startswith('gams-') for n in omitted), 'Missing non-temporary sealed artifact')
            for member, checksum in terminal.items():
                if member in present:
                    require(digest(archive.read(job+member)) == checksum, 'Job seal mismatch')
            require(all(summary_jobs[grid][k] == v for k,v in result.items()), 'Result and summary disagree')
            checked = old.verify_solution(grid, read(archive, job+'solution.json'), result)
            require(result['has_feasible_solution'] and result['grid_validation'] == 'passed', 'Runner feasibility differs')
            log = archive.read(job+'run.log').decode()
            kind = failure_kind(result, log)
            require(kind != 'unclassified_error', 'Unclassified failure')
            calls = journal(archive, job+'solver_calls.jsonl')
            active = read(archive, job+'active_solver_call.json') if job+'active_solver_call.json' in archive.namelist() else None
            evidence = call_evidence(calls, active, log, kind)
            # Watchdog reports can lack final method-level counters.
            require(result.get('solver_calls', len(calls)) == len(calls), 'Journal/result call mismatch')
            trace = journal(archive, job+'grid_path.jsonl')
            gdp = journal(archive, job+'gdp_path.jsonl')
            require(len(trace) == len(gdp), 'Grid/GDP callback count differs')
            for a,b in zip(trace,gdp):
                require(all(b[k] == v for k,v in a.items()), 'Coordinate and binary trajectory disagree')
                n = a['completed_solver_calls']
                require(0 <= n <= len(calls), 'Callback refers to an unavailable solver call')
                if 'last_solver_call' in b:
                    require(b['last_solver_call'] == calls[n-1], 'Callback solver status differs from journal')
                if a.get('grid_point') is not None:
                    require(len(a['grid_point']) == 2 and all(isinstance(x,int) and 0 <= x <= 30 for x in a['grid_point']), 'Invalid callback coordinates')
            before = [r for r in trace if r['event'] == 'before_subproblem']
            after = [r for r in trace if r['event'] == 'after_subproblem']
            visited = {tuple(r['grid_point']) for r in before if r.get('grid_point') is not None}
            incumbents = journal(archive, job+'incumbents.jsonl')
            eligible = [r for r in incumbents if r.get('has_feasible_solution') and r.get('candidate_objective') is not None]
            require(eligible and abs(min(r['candidate_objective'] for r in eligible)-checked['objective_recomputed']) <= 1e-8, 'Saved incumbent differs from history')
            hit_times = [r['elapsed_s'] for r in eligible if abs(r['candidate_objective']-checked['reference_minimum']) <= 1e-5]
            row = dict(grid_name=grid,method=method,archive=name,status=result['status'],termination=result['termination'],
                failure_kind=kind,solution_returned=True,**checked,
                target_hit_without_error=checked['target_hit_verified'] and result['status'] != 'error',
                optimal_but_misses_target=result['termination']=='optimal' and not checked['target_hit_verified'],
                lower_bound_exceeds_known_minimum=result.get('reported_lower_bound') is not None
                    and result['reported_lower_bound'] > checked['reference_minimum']+1e-5,
                global_optimality_certified=result['global_optimality_certified'],
                reported_lower_bound=result.get('reported_lower_bound'),reported_upper_bound=result.get('reported_upper_bound'),
                worker_wall_s=result['worker_wall_s'],method_wall_s=result.get('method_wall_s'),**evidence,
                grid_path_events=len(trace),before_subproblem_callbacks=len(before),after_subproblem_callbacks=len(after),
                distinct_before_subproblem_points=len(visited),
                exact_reference_minimizer_seen=any(tuple(p) in visited for p in checked['reference_minimizers']),
                recorded_first_target_incumbent_s=min(hit_times) if hit_times else None,
                first_grid_callback=trace[0].get('grid_point') if trace else None,
                omitted_sealed_temporary_files={n:terminal[n] for n in omitted},
                grid_path_sha256=terminal['grid_path.jsonl'],gdp_path_sha256=terminal['gdp_path.jsonl'],
                result_sha256=terminal['result.json'],solution_sha256=terminal['solution.json'])
            jobs.append(row)
            if kind != 'none':
                relevant = [dict(line=i,text=line.strip()) for i,line in enumerate(log.splitlines(),1)
                            if ('*** Error: Error when trying to' in line or line.startswith('Curl error:')
                                or line.startswith('pyomo.common.errors.IntervalException:'))]
                last = calls[-1]
                failures.append(dict(method=method,grid_name=grid,failure_kind=kind,target_hit=checked['target_hit_verified'],
                    message=result.get('message'),log_member=job+'run.log',evidence_lines=relevant,
                    final_journaled_call=last,active_unjournaled_call=active,
                    error_listing_present=job+f"call_{last['index']:05d}_error.lst" in archive.namelist()))
        require(summary['completed_jobs'] == len(jobs) == summary['planned_jobs'] and summary['all_jobs_finished'], 'Completion count incorrect')
        require(summary['solutions_returned'] == summary['feasible_jobs'] == len(jobs), 'Solution count incorrect')
        require(summary['actual_benchmark_solver_calls'] == {'scip/mip':sum(r['journaled_call_attempts'] for r in jobs)}, 'Summary calls differ')
        preflight = []
        for n in archive.namelist():
            if '/preflight/' in n and n.endswith('/solver_calls.jsonl'):
                preflight.extend(journal(archive,n))
        require(len(preflight) == 3 and all(c['solver'] == 'scip' for c in preflight), 'Preflight inventory differs')
        inventory = dict(archive=name,sha256=spec[1],bytes=path.stat().st_size,internal_checksums=internal,**source,
            config=config,runtime=run['runtime'],created_utc=run['created_utc'],preflight_calls=preflight,
            outer_checksum_note='Computed locally; server checksum sidecars were not provided.')
    return jobs, failures, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    jobs, failures, inventories, baseline, baseline_inventory = [], [], [], [], []
    with patch.object(type(old.pyo.SolverFactory),'__call__',side_effect=AssertionError('Optimization forbidden in return audit')):
        for method,spec in ARCHIVES.items():
            j,f,i = analyze_archive(method,spec)
            jobs.extend(j)
            failures.extend(f)
            inventories.append(i)
        for name, checksum in old.ARCHIVES.items():
            if 'minlp' not in name:
                j,i = old.audit_archive(ROOT/'results/archives'/name,checksum)
                baseline.extend(j)
                baseline_inventory.append(i)
    paired = []
    previous = {(r['grid_name'],r['method']):r for r in baseline}
    require(len(previous) == len(jobs) == 63,'Comparison denominator changed')
    for r in jobs:
        b = previous[r['grid_name'],r['method']]
        require(r['reference_minimum'] == b['reference_minimum'], 'Reference changed')
        paired.append(dict(grid_name=r['grid_name'],method=r['method'],old_target=b['target_hit_verified'],new_target=r['target_hit_verified'],
            old_objective=b['objective_recomputed'],new_objective=r['objective_recomputed'],
            old_grid_point=b['grid_point'],new_grid_point=r['grid_point'],
            old_status=b['status'],new_status=r['status'],new_failure_kind=r['failure_kind'],
            old_worker_s=b['worker_wall_s'],new_worker_s=r['worker_wall_s'],
            old_actual_solvers=b['actual_solver_counts'],new_actual_route='scip/mip'))
    methods = []
    for method in ARCHIVES:
        group = [r for r in jobs if r['method']==method]
        pair = [r for r in paired if r['method']==method]
        methods.append(dict(method=method,jobs=len(group),solutions_verified=len(group),
            target_hits=sum(r['target_hit_verified'] for r in group),
            target_hits_without_error=sum(r['target_hit_without_error'] for r in group),
            optimal=sum(r['termination']=='optimal' for r in group),errors=sum(r['status']=='error' for r in group),
            time_limits=sum(r['termination']=='maxTimeLimit' for r in group),
            network_start_failures=sum(r['failure_kind']=='gams_network_session_start' for r in group),
            network_close_failures=sum(r['failure_kind']=='gams_network_session_close' for r in group),
            fbbt_failures=sum(r['failure_kind']=='pyomo_fbbt_interval' for r in group),
            old_target_hits=sum(r['old_target'] for r in pair),both_hit=sum(r['old_target'] and r['new_target'] for r in pair),
            old_only=sum(r['old_target'] and not r['new_target'] for r in pair),new_only=sum(not r['old_target'] and r['new_target'] for r in pair),
            neither=sum(not r['old_target'] and not r['new_target'] for r in pair),
            old_worker_wall_s=sum(r['old_worker_s'] for r in pair),
            **{k:sum(r[k] for r in group) for k in ['worker_wall_s','journaled_call_attempts','returned_calls','error_calls',
              'active_unjournaled_attempts','started_interface_attempts','confirmed_scip_invocations','benchmark_nlp_calls',
              'failed_call_wall_s','grid_path_events']}))
    summary = dict(jobs=len(jobs),returned_solutions_verified=len(jobs),
        target_hits=sum(r['target_hit_verified'] for r in jobs),target_hits_without_error=sum(r['target_hit_without_error'] for r in jobs),
        status_counts=dict(Counter(r['status'] for r in jobs)),termination_counts=dict(Counter(r['termination'] for r in jobs)),
        failure_counts=dict(Counter(r['failure_kind'] for r in jobs)),
        maximum_original_violation=max(r['max_original_violation'] for r in jobs),
        maximum_objective_error=max(r['saved_objective_abs_error'] for r in jobs),
        benchmark_calls={k:sum(r[k] for r in jobs) for k in ['journaled_call_attempts','returned_calls','error_calls',
            'active_unjournaled_attempts','started_interface_attempts','confirmed_scip_invocations','benchmark_nlp_calls']},
        separate_preflight_calls=sum(len(i['preflight_calls']) for i in inventories),
        preflight_mip_calls=sum(c['mtype']=='mip' for i in inventories for c in i['preflight_calls']),
        preflight_nlp_calls=sum(c['mtype']=='nlp' for i in inventories for c in i['preflight_calls']),
        normalized_target_tolerance=1e-5,old_target_hits=sum(r['old_target'] for r in paired),
        original_63_job_combined_run='Not provided; left running by the user and not combined with these independent split runs.',
        optimization_calls_during_analysis=0)
    csvwrite(args.output/'jobs.csv',jobs)
    csvwrite(args.output/'methods.csv',methods)
    csvwrite(args.output/'paired_highs_scip.csv',paired)
    save(args.output/'jobs.json',jobs)
    save(args.output/'failures.json',failures)
    save(args.output/'summary.json',summary)
    save(args.output/'manifest.json',dict(archives=inventories,historical_comparison_archives=baseline_inventory,
        source_baseline_revision='d9bb8a9218c44c96dae544b504693d66a3daae5b',
        analysis_python=platform.python_version(),analysis_pyomo=importlib.metadata.version('pyomo'),
        analysis_source_sha256=digest(Path(__file__).read_bytes()),
        solution_verifier_sha256=digest(Path(old.__file__).read_bytes()),
        target_definition='CSV normalized objective minus fixed CSV minimum <= 1e-5; all 21 attempts retained per method.',
        execution_revision_note='Exact delivered package and source hashes identify execution; no new Git provider revision is invented.'))
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
