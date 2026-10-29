"""Audit the four October 26 Process returns and historical BARON pairs, without solving."""
import argparse
from collections import Counter
from contextlib import ExitStack
import csv
import json
import logging
from pathlib import Path, PurePosixPath
import platform
import re
import sys
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import analyze_process_scip_return as prior  # noqa: E402

require, sha, save_json, save_csv = prior.require, prior.digest, prior.save_json, prior.save_csv
METHODS = ('bigm', 'hull', 'gloa', 'loa', 'ric')
GROUPS = {'minlp': ('bigm', 'hull'), 'ric': ('ric',), 'loa': ('loa',), 'gloa': ('gloa',)}
HASHES = {
    'minlp': '545bb77ffad8bf605b71b4e188333874a58796db365865b2ef87877e147bae54',
    'ric': '25018592854d4832df322c828f35979b4b368ae45ca33ddd898a6b51818bcca5',
    'loa': 'd462ab49e5713358b497e5d17f7e186c876703bf5acd98f45a5bb3a41592b577',
    'gloa': '3c5f6f856ef71a7eae96fbfd0f06f30d4d61bebe7e101bab53fa8699d65d3c44',
}
REVISION = 'dfde838896b4ce350771f7691f973d28a58f8f43'
DATA_FILES = ('jobs.csv', 'paired_baron_scip.csv', 'paired_highs_scip.csv', 'methods.csv',
              'solver_calls.csv', 'solution_checks.json', 'issues.json', 'summary.json', 'manifest.json', 'README.md')


def read(z, name):
    return json.loads(z.read(name))


def journal(z, name):
    return [json.loads(line) for line in z.read(name).decode().splitlines()] if name in z.namelist() else []


def verify_inventory(z, prefix, checksum_name='SHA256SUMS', complete=False):
    checked = {}
    for line in z.read(prefix + checksum_name).decode().splitlines():
        digest, name = line.split('  ', 1)
        require(name not in checked and '..' not in PurePosixPath(name).parts and not name.startswith('/'), 'Unsafe/duplicate checksum entry')
        require(sha(z.read(prefix + name)) == digest, 'Checksum mismatch: ' + prefix + name)
        checked[name] = digest
    if complete:
        require(set(checked) == {n[len(prefix):] for n in z.namelist() if not n.endswith('/')} - {checksum_name}, 'Incomplete inventory')
    return checked


def verify_return(z, group):
    names = z.namelist()
    require(len(names) == len(set(names)) and z.testzip() is None, 'ZIP CRC/duplicate failure')
    prefix = names[0].split('/')[0] + '/'
    require(all(n.startswith(prefix) and '..' not in PurePosixPath(n).parts for n in names), 'Unsafe archive path')
    checked = verify_inventory(z, prefix, complete=True)
    manifest = read(z, prefix + 'package/MANIFEST.json')
    # The result packer replaces nested SHA256SUMS files with its complete outer inventory.
    package_checked = manifest['files_sha256']
    for name, digest in manifest['files_sha256'].items():
        require(sha(z.read(prefix + 'package/' + name)) == digest, 'Package manifest mismatch')
    baseline = read(z, prefix + 'package/BASELINE.json')
    for name, digest in baseline['original_source_sha256'].items():
        require(sha(z.read(prefix + 'package/source/' + name)) == digest, 'Frozen source mismatch')
    original_manifest = read(z, prefix + 'package/source/PACKAGE_MANIFEST.json')
    for entry in original_manifest['files']:
        require(sha(z.read(prefix + 'package/source/' + entry['path'])) == entry['sha256'], 'Original package mismatch')
    run = read(z, prefix + 'run.json')
    config = run['config']
    require(run['status'] == 'completed' and run['preflight_status'] == 'passed', 'Incomplete package')
    require(config['methods'] == list(GROUPS[group]) and config['time_limit'] == 1800 and config['threads'] == 1, 'Changed design')
    require(config['mip_solver'] == config['nlp_solver'] == config['minlp_solver'] == 'scip', 'Configured solver mismatch')
    require(manifest['baseline_revision'] == run['baseline_revision'] == REVISION, 'Baseline revision mismatch')
    environment = read(z, prefix + 'environment.json')
    require(environment['differences'] == {} and environment['actual'] == run['runtime'], 'Environment gate mismatch')
    require(run['runtime']['versions']['pyomo'] == '6.10.0' and run['runtime']['gams_version'] == [52, 2, 0, 0], 'Wrong server version')
    require(all(v == '1' for v in run['runtime']['thread_environment'].values()), 'Non-single-thread execution')
    ledger = journal(z, prefix + 'launch_ledger.jsonl')
    expected = [(i, m) for i in prior.INSTANCES for m in GROUPS[group]]
    require([(r['instance_id'], r['method']) for r in ledger] == expected, 'Missing/duplicate launches')
    summary = read(z, prefix + 'summary.json')
    require([(r['instance_id'], r['method']) for r in summary['results']] == expected, 'Missing/duplicate results')
    require(summary['completed_jobs'] == summary['planned_jobs'] == run['completed_jobs'] == len(expected), 'Count mismatch')
    preflight = read(z, prefix + 'preflight/solver_checks.json')
    require(preflight['scip_versions'] == ['9.2.4 (a94f778ac8)'], 'Wrong SCIP version')
    compilation = read(z, prefix + 'preflight/compilation.json')
    require(len(compilation) == (18 if group == 'minlp' else 0), 'Compile-only count mismatch')
    require(all(c['passed'] and c['confirmed_optimizer_starts'] == 0 for c in compilation), 'Compilation failure')
    metadata = {'archive_sha256': HASHES[group], 'root': prefix, 'internal_checksums': len(checked),
        'package_checksums': len(package_checked), 'package_source_files': len(baseline['original_source_sha256']),
        'run': run, 'preflight': preflight, 'compile_only_calls': len(compilation),
        'execution_source_sha256': manifest['files_sha256'],
        'executed_repository_revision': None,
        'revision_note': 'The standalone runner was uncommitted when delivered; exact executed hashes and its baseline revision are preserved.'}
    return prefix, summary, baseline, metadata


def clock(result):
    if result.get('method_wall_s') is not None:
        return result['method_wall_s'], 'method_wall_s'
    require(result.get('worker_wall_s') is not None, 'Missing measured clock')
    return result['worker_wall_s'], 'worker_wall_s_watchdog'


def paired(old, new):
    value = float(old['objective']) if old['objective'] not in ('', None) else None
    target = new['target_value']
    require(prior.hit(value, target) == (old['target_hit'] == 'True'), 'Historical target rule/flag mismatch')
    require(prior.attained(value, target) == (old['target_attained'] == 'True'), 'Historical attainment rule/flag mismatch')
    old_time = float(old.get('measured_total_with_preparation_s', old.get('total_with_preparation_s')))
    return {'instance_id': new['instance_id'], 'method': new['method'], 'target_value': target,
        'old_objective': value, 'new_objective': new['objective'],
        'new_minus_old_objective': new['objective'] - value if new['objective'] is not None and value is not None else None,
        'old_target_hit': prior.hit(value, target), 'new_target_hit': new['target_hit'],
        'old_target_attained': prior.attained(value, target), 'new_target_attained': new['target_attained'],
        'old_status': old['status'], 'old_termination': old['termination'],
        'new_status': new['status'], 'new_termination': new['termination'],
        'old_completion_s': old_time, 'new_completion_s': new['total_with_preparation_s'],
        'new_over_old_completion_ratio': new['total_with_preparation_s'] / old_time,
        'pair_class': ('both' if prior.hit(value, target) else 'new_only') if new['target_hit'] else ('old_only' if prior.hit(value, target) else 'neither')}


def analyze(output):
    output.mkdir(parents=True, exist_ok=True)
    with patch.object(prior, 'METHODS', METHODS):
        historical, inputs, history = prior.historical_inputs()
    old_scip_path = ROOT / 'results/process_gdpopt_scip_20261025/jobs.csv'
    old_scip = {(r['instance_id'], r['method']): r for r in csv.DictReader(old_scip_path.open())}
    inputs[str(old_scip_path.relative_to(ROOT))] = sha(old_scip_path.read_bytes())
    for p in (Path(__file__), ROOT / 'scripts/analyze_process_scip_return.py'):
        inputs[str(p.relative_to(ROOT))] = sha(p.read_bytes())
    rows, pairs, intermediate, calls_detail, checks, issues, records = [], [], [], [], [], [], {}
    old_vectors = {}
    for h in history:
        with zipfile.ZipFile(ROOT / h['archive']) as z:
            prefix = Path(h['archive']).stem + '/'
            for instance in prior.INSTANCES:
                for method in h['methods']:
                    old_vectors[instance, method] = read(z, prefix + f'jobs/{instance}/{method}/solution.json')
    with ExitStack() as stack:
        archives = {}
        baseline_source = None
        for group in GROUPS:
            path = ROOT / f'results/archives/process_scip_{group}_20261026_result.zip'
            require(sha(path.read_bytes()) == HASHES[group], 'Return archive identity mismatch')
            inputs[str(path.relative_to(ROOT))] = HASHES[group]
            z = stack.enter_context(zipfile.ZipFile(path))
            prefix, summary, baseline, metadata = verify_return(z, group)
            if baseline_source is None:
                baseline_source = baseline['original_source_sha256']
            require(baseline_source == baseline['original_source_sha256'], 'Different model source across packages')
            archives[group] = (z, prefix, summary, baseline)
            records[group] = metadata
        z0, p0, _, _ = archives['minlp']
        with prior.frozen_models(z0, p0 + 'package/') as build:
            for group, (z, prefix, summary, baseline) in archives.items():
                sealed_files = 0
                for result in summary['results']:
                    instance, method = result['instance_id'], result['method']
                    key = (instance, method)
                    old = historical[key]
                    job = prefix + f'benchmark/{instance}/{method}/'
                    require(read(z, job + 'result.json') == result, 'Summary/result mismatch')
                    seals = read(z, job + 'terminal.json')['files_sha256']
                    for name, digest in seals.items():
                        require(sha(z.read(job + name)) == digest, 'Missing/modified terminal evidence: ' + job + name)
                        sealed_files += 1
                    raw = old['raw_result']
                    require(all(raw[k] == result[k] for k in ('source', 'initialization', 'globally_implied_bounds')), 'Model/initialization/bounds changed across BARON pair')
                    old_check = prior.verify_solution(build(raw), old_vectors[key], raw)
                    checks.append({'cohort': 'baron', 'instance_id': instance, 'method': method, **old_check})
                    returned = job + 'solution.json' in z.namelist()
                    require(returned == result['has_feasible_solution'], 'Returned-vector flag mismatch')
                    checked = None
                    if returned:
                        checked = prior.verify_solution(build(result), read(z, job + 'solution.json'), result)
                        server_check = result['original_validation']
                        require(all(checked[k] == server_check[k] for k in
                            ('original_gdp_feasible', 'variables_checked', 'model_variables', 'checks',
                             'missing_unreferenced_variables', 'selected_disjuncts', 'selected_booleans')),
                            'On-server/local validation structure differs')
                        differences = {k: {'local': checked[k], 'server': server_check[k]} for k in checked if checked[k] != server_check[k]}
                        checks.append({'cohort': 'scip', 'instance_id': instance, 'method': method,
                            **checked, 'cross_platform_evaluation_differences': differences})
                    calls = journal(z, job + 'solver_calls.jsonl')
                    require([c['index'] for c in calls] == list(range(1, len(calls)+1)), 'Call journal sequence mismatch')
                    active = read(z, job + 'active_solver_call.json') if job + 'active_solver_call.json' in z.namelist() else None
                    require(active is None or active['index'] == len(calls)+1, 'Unjournaled call mismatch')
                    counts = Counter(f"{c['solver']}/{c['mtype']}" for c in calls)
                    allowed = {'scip/minlp'} if method in ('bigm', 'hull') else {'scip/mip', 'scip/nlp'}
                    require(set(counts) <= allowed and all(c['threads'] == 1 for c in calls), 'Unexpected solver/thread actually used')
                    log = z.read(job + 'run.log').decode(errors='replace')
                    actual = len(re.findall(r'^--- Executing SCIP \(', log, re.M))
                    retries = journal(z, job + 'network_recovery.jsonl')
                    not_executed = set()
                    for retry in retries:
                        if 'failed_call_index' not in retry:
                            continue
                        delta = z.read(job + 'run.log')[retry['log_start_byte']:retry['log_end_byte']]
                        require(sha(delta) == retry['log_delta_sha256'], 'Transport-error log segment changed')
                        if not re.search(rb'^--- Executing SCIP \(', delta, re.M):
                            not_executed.add(retry['failed_call_index'])
                    active_executed = actual - (len(calls)-len(not_executed))
                    require(active_executed in (0, 1) and active_executed <= int(bool(active)), 'Unexplained solver/banner accounting difference')
                    require(actual == result['execution_evidence']['confirmed_scip_invocations'], 'Saved banner count differs')
                    require(not re.search(r'^--- Executing (?:BARON|HiGHS|IPOPT) \(', log, re.M), 'Unexpected external solver invocation')
                    require(set(re.findall(r'^SCIP version (.+)$', log, re.M)) == {'9.2.4 (a94f778ac8)'}, 'Benchmark SCIP version mismatch')
                    if method not in ('bigm', 'hull'):
                        options = read(z, job + 'effective_gdpopt_config.json')
                        require(options['mip_solver_args'] == {'solver': 'scip', 'mtype': 'mip'} and
                                options['nlp_solver_args'] == {'solver': 'scip', 'mtype': 'nlp'}, 'Effective solver options differ')
                        require(options['force_subproblem_nlp'] == options['subproblem_presolve'] == options['mip_presolve'] == 'true', 'Effective presolve/NLP options differ')
                    value = checked['objective_recomputed'] if checked else None
                    target = float(old['target_value'])
                    require(target == baseline['references'][instance], 'Target changed')
                    duration, clock_source = clock(result)
                    events = journal(z, job + 'gdp_path.jsonl')
                    incumbents = journal(z, job + 'incumbents.jsonl')
                    row = {'group': group, 'instance_id': instance, 'method': method, 'status': result['status'],
                        'termination': result['termination'], 'normalized_outcome': 'time_limit' if result['termination'] == 'maxTimeLimit' else result['status'],
                        'solution_returned': returned, 'original_gdp_feasible': bool(checked), 'objective': value,
                        'target_value': target, 'target_hit': prior.hit(value, target), 'target_attained': prior.attained(value, target),
                        'better_than_reference_but_absolute_miss': prior.attained(value, target) and not prior.hit(value, target),
                        'signed_relative_target_gap': (value-target)/max(1, abs(target)) if value is not None else None,
                        'max_original_violation': checked['max_original_violation'] if checked else None,
                        'completion_s': duration, 'clock_source': clock_source, 'worker_wall_s': result['worker_wall_s'],
                        'template_wall_s': result['template_wall_s'], 'total_with_preparation_s': duration+result['template_wall_s'],
                        'logged_solver_calls': len(calls), 'unlogged_started_calls': int(bool(active)), 'actual_scip_invocations': actual,
                        'failed_interface_calls_before_solver': len(not_executed), 'active_solver_start_confirmed': bool(active_executed),
                        'solver_calls_by_type': dict(counts), 'logged_solver_wall_s': sum(c['wall_s'] for c in calls),
                        'reported_lower_bound': result.get('reported_lower_bound'), 'reported_upper_bound': result.get('reported_upper_bound'),
                        'raw_worker_global_optimality_certified': read(z, job + 'worker_result.json').get('global_optimality_certified'),
                        'global_optimality_certified': False, 'path_events': len(events),
                        'before_subproblem_events': sum(e['event'] == 'before_subproblem' for e in events),
                        'path_sha256': sha(z.read(job + 'gdp_path.jsonl')) if events else None,
                        'initialization': result['initialization'], 'archive': f'results/archives/process_scip_{group}_20261026_result.zip',
                        'job_member': job, 'retry_events': len(retries)}
                    require(row['target_hit'] == result['execution_evidence']['target_hit'], 'Archived target result differs')
                    rows.append(row)
                    pair = paired(old, row)
                    pair.update(baron_source=old['source_directory'], same_model_initialization_and_bounds=True,
                                baron_solvers=old['raw_solver_counts'])
                    pairs.append(pair)
                    if key in old_scip:
                        intermediate.append(paired(old_scip[key], row))
                    for call in calls + ([active] if active else []):
                        calls_detail.append({'instance_id': instance, 'method': method, **{k:call.get(k) for k in
                            ('index', 'solver', 'mtype', 'status', 'termination', 'wall_s', 'limit_s', 'threads', 'lower_bound', 'upper_bound')},
                            'journaled': call is not active,
                            'actual_solver_start_confirmed': bool(active_executed) if call is active else call['index'] not in not_executed,
                            'gams_statistics': call.get('gams_statistics'),
                            'solver_option_file': call.get('solver_option_file')})
                    if not returned or row['normalized_outcome'] == 'time_limit':
                        issues.append({'instance_id': instance, 'method': method, 'type': 'missing_solution' if not returned else 'time_limit',
                            'message': result.get('message'), 'last_incumbent_validation': incumbents[-1] if incumbents else None,
                            'active_unjournaled_call': active, 'last_journaled_call': calls[-1] if calls else None,
                            'gams_statistics': result.get('gams_statistics'), 'job_member': job})
                    if retries:
                        issues.append({'instance_id': instance, 'method': method, 'type': 'recovered_network_error',
                            'events': retries, 'failed_before_solver_indices': sorted(not_executed), 'job_member': job})
                records[group]['terminal_files_verified'] = sealed_files
                records[group]['terminal_jobs_verified'] = len(summary['results'])
    rows.sort(key=lambda r: (prior.INSTANCES.index(r['instance_id']), METHODS.index(r['method'])))
    for row in rows:
        witness = min((r for r in rows if r['instance_id'] == row['instance_id'] and r['original_gdp_feasible']), key=lambda r:r['objective'])
        lower = row['reported_lower_bound']
        conflict = lower is not None and lower > witness['objective'] + prior.TOLERANCE * max(1, abs(witness['objective']))
        row.update(bound_conflict=conflict, best_verified_objective=witness['objective'], bound_witness_method=witness['method'])
        if conflict:
            issues.append({'instance_id': row['instance_id'], 'method': row['method'], 'type': 'bound_conflict',
                'reported_lower_bound': lower, 'verified_feasible_objective': witness['objective'],
                'witness_method': witness['method'], 'gap': lower-witness['objective'], 'job_member': row['job_member']})
    methods = []
    for method in METHODS:
        rr = [r for r in rows if r['method'] == method]
        pp = [p for p in pairs if p['method'] == method]
        aa = [p for p in intermediate if p['method'] == method]
        methods.append({'method': method, 'jobs': len(rr), 'baron_feasible': len(pp), 'scip_feasible': sum(r['original_gdp_feasible'] for r in rr),
            'baron_target_hits': sum(p['old_target_hit'] for p in pp), 'scip_target_hits': sum(r['target_hit'] for r in rr),
            'baron_target_attained': sum(p['old_target_attained'] for p in pp), 'scip_target_attained': sum(r['target_attained'] for r in rr),
            'both_hit': sum(p['pair_class'] == 'both' for p in pp), 'scip_only_hit': sum(p['pair_class'] == 'new_only' for p in pp),
            'baron_only_hit': sum(p['pair_class'] == 'old_only' for p in pp), 'neither_hit': sum(p['pair_class'] == 'neither' for p in pp),
            'baron_completion_s_sum': sum(p['old_completion_s'] for p in pp), 'scip_completion_s_sum': sum(p['new_completion_s'] for p in pp),
            'new_over_baron_time_ratio': sum(p['new_completion_s'] for p in pp)/sum(p['old_completion_s'] for p in pp),
            'scip_time_limits': sum(r['normalized_outcome'] == 'time_limit' for r in rr),
            'scip_errors': sum(r['normalized_outcome'] in ('error', 'worker_error', 'subproblem_incomplete') for r in rr),
            'bound_conflicts': sum(r['bound_conflict'] for r in rr),
            'previous_highs_scip_hits': sum(p['old_target_hit'] for p in aa) if aa else None,
            'previous_highs_scip_completion_s': sum(p['old_completion_s'] for p in aa) if aa else None})
    total_calls = Counter(f"{c['solver']}/{c['mtype']}" for c in calls_detail if c['actual_solver_start_confirmed'])
    new_checks = [c for c in checks if c['cohort'] == 'scip']
    summary = {'jobs': len(rows), 'returned_feasible_solutions': len(new_checks),
        'baron_target_hits': sum(m['baron_target_hits'] for m in methods), 'scip_target_hits': sum(r['target_hit'] for r in rows),
        'baron_target_attained': sum(m['baron_target_attained'] for m in methods), 'scip_target_attained': sum(r['target_attained'] for r in rows),
        'baron_completion_s_sum': sum(m['baron_completion_s_sum'] for m in methods),
        'scip_completion_s_sum': sum(m['scip_completion_s_sum'] for m in methods),
        'scip_worker_wall_s_sum': sum(r['worker_wall_s'] for r in rows),
        'scip_method_or_watchdog_wall_s_sum': sum(r['completion_s'] for r in rows),
        'time_limits': sum(m['scip_time_limits'] for m in methods), 'errors': sum(m['scip_errors'] for m in methods),
        'actual_benchmark_solver_invocations': dict(total_calls), 'unlogged_started_calls': sum(not c['journaled'] for c in calls_detail),
        'started_interface_attempts': len(calls_detail),
        'recovered_network_errors': sum(e['decision'] == 'retry_same_interface_call' for i in issues if i['type'] == 'recovered_network_error' for e in i['events']),
        'network_backoff_s': sum(e.get('backoff_s', 0) for i in issues if i['type'] == 'recovered_network_error' for e in i['events']),
        'actual_preflight_solver_invocations': sum(v['preflight']['confirmed_scip_invocations'] for v in records.values()),
        'compile_only_preflight_calls': sum(v['compile_only_calls'] for v in records.values()),
        'new_optimizer_calls_during_analysis': 0, 'max_new_original_violation': max(c['max_original_violation'] for c in new_checks),
        'new_variables_checked': sum(c['variables_checked'] for c in new_checks),
        'bound_conflicts': [i for i in issues if i['type'] == 'bound_conflict'], 'by_method': methods}
    manifest = {'analysis_baseline_revision': REVISION, 'input_sha256': inputs, 'returned_packages': records,
        'historical_selection': history, 'reference_rule': 'abs(objective-reference) <= 1e-5 * max(1, abs(reference))',
        'attainment_rule': 'objective <= reference + 1e-5 * max(1, abs(reference))',
        'timing_rule': 'method_wall_s, or watchdog worker_wall_s when absent, plus per-job template_wall_s',
        'analysis_python': platform.python_version(), 'analysis_pyomo': '6.10.0',
        'analysis_solver_calls': 0, 'server_sidecars_received': False,
        'output_hash_inventory': 'artifact_checksums.json',
        'sidecar_provenance': 'Local SHA256 sidecars calculated from the four received ZIPs; internal server SHA256SUMS verified.',
        'reproduction_command': 'python scripts/analyze_process_scip_four_return.py --output /tmp/process-scip-four-reproduced'}
    for name, data in [('jobs.csv', rows), ('paired_baron_scip.csv', pairs), ('paired_highs_scip.csv', intermediate),
                       ('methods.csv', methods), ('solver_calls.csv', calls_detail)]:
        save_csv(output / name, data)
    for name, data in [('solution_checks.json', checks), ('issues.json', issues), ('summary.json', summary), ('manifest.json', manifest)]:
        save_json(output / name, data)
    (output / 'README.md').write_text(report(summary, rows, methods))
    return summary


def report(summary, rows, methods):
    lines = ['# Four Process SCIP returns and paired BARON comparison', '',
        f"All {summary['jobs']} planned jobs have terminal records, with {summary['returned_feasible_solutions']} independently verified returned solution vectors, {summary['time_limits']} time-limited runs and {summary['errors']} execution errors.",
        'This is one run per method and instance, so percentages across instances are coverage rates rather than repeated-seed success probabilities.',
        'The direct Big-M/Hull jobs actually call SCIP MINLP, while all three GDPopt methods actually call SCIP for both MIP and NLP.',
        'The selected BARON baseline is the unchanged current comparison selection: September 25 Big-M/Hull and October 1 GDPopt.',
        'The BARON GDPopt baseline uses HiGHS MIP and BARON NLP with CLP/IPOPT subsolvers, while direct BARON uses CPLEX/IPOPT subsolvers.',
        'The older October 25 intermediate cohort uses HiGHS MIP plus SCIP NLP and is reported separately.', '',
        '## Method-level comparison', '',
        '| Method | BARON absolute hits | SCIP absolute hits | BARON at-or-below | SCIP at-or-below | SCIP feasible | BARON completion s | SCIP completion s | SCIP/BARON time |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for m in methods:
        lines.append(f"| {m['method']} | {m['baron_target_hits']}/9 | {m['scip_target_hits']}/9 | {m['baron_target_attained']}/9 | {m['scip_target_attained']}/9 | {m['scip_feasible']}/9 | {m['baron_completion_s_sum']:.2f} | {m['scip_completion_s_sum']:.2f} | {m['new_over_baron_time_ratio']:.3f} |")
    lines += ['', f"Absolute-reference hits change from {summary['baron_target_hits']}/45 to {summary['scip_target_hits']}/45, while minimization attainment changes from {summary['baron_target_attained']}/45 to {summary['scip_target_attained']}/45.",
        f"The summed completion-plus-preparation cost changes from {summary['baron_completion_s_sum']:.3f} to {summary['scip_completion_s_sum']:.3f} seconds, a decrease of {100*(1-summary['scip_completion_s_sum']/summary['baron_completion_s_sum']):.2f}%.",
        'Completion costs are not time-to-first-target, and the sum across parallel packages is not their end-to-end elapsed duration.',
        'The source, solver adapter, solver options, CPU allocation and tracing differ across historical cohorts, so these observed costs are not a controlled causal estimate of solver speed.',
        'CPU affinity is provenance rather than a claimed explanation of performance.', '',
        '## Fixed targets and objective quality', '',
        'The primary rule remains abs(objective-reference) <= 1e-5*max(1,abs(reference)); the separate minimization rule accepts values at or below reference plus that tolerance.',
        'No target, feasibility tolerance, historical selection, original model or initialization is changed.',
        'SCIP Big-M CSTR5/CSTR10 and Hull CSTR15/CSTR20/CSTR25 return lower accepted objectives outside the absolute reference band.',
        'Their absolute misses must not be described as worse objective values or silently converted into absolute hits.',
        'These small CSTR objective differences coexist with residuals near 1e-6 and are numerical accepted-vector differences, not demonstrated improvements of the exact physical optimum.',
        'BARON already has a corresponding better-than-reference absolute miss at Big-M CSTR10 and LOA CSTR15.',
        'LOA CSTR15 changes from a lower BARON objective to a reference-matching SCIP objective, so that additional absolute hit is not an objective improvement.', '',
        '## Instance results', '',
        'An asterisk denotes an absolute-reference hit, T denotes time-limit termination, and B denotes a lower-bound conflict with a verified feasible vector from these new returns.',
        'Each cell contains the verified original-GDP objective and measured method/watchdog completion seconds, excluding template preparation.', '',
        '| Instance | Big-M | Hull | GLOA | LOA | RIC |', '|---|---|---|---|---|---|']
    for instance in prior.INSTANCES:
        cells = []
        for method in METHODS:
            r = next(r for r in rows if r['instance_id'] == instance and r['method'] == method)
            value = f"{r['objective']:.10g}" if r['objective'] is not None else 'no accepted vector'
            flags = (' *' if r['target_hit'] else '') + (' T' if r['normalized_outcome'] == 'time_limit' else '') + (' B' if r['bound_conflict'] else '')
            cells.append(f"{value}; {r['completion_s']:.2f}{flags}")
        lines.append('| ' + instance + ' | ' + ' | '.join(cells) + ' |')
    lines += ['', '## Findings requiring care', '',
        'CSTR15 Big-M returns a solver candidate objective 2.8222510013618556, but the archived original-GDP check rejects its 0.0009636850434195932 violation against the unchanged 1e-5 acceptance criterion.',
        'That candidate is not a returned accepted solution and is not counted as a target hit; its complete variable vector was not saved, so the aggregate rejection is reported from the original incumbent record rather than reconstructed.',
        'Column Big-M reaches its time limit with GAMS MODELSTAT=14 and no SCIP solution, so neither the original initialization nor a solver bound is substituted for a returned vector.',
        'Both cases retain their full denominator and measured cost.',
        'Direct SCIP Hull reaches at-or-below targets for all six CSTR sizes and improves the old CSTR30 Hull result, while direct Big-M loses accepted/reference-quality outcomes on CSTR15, CSTR20 and CSTR25.',
        'Direct SCIP Big-M reaches the Dynamic target at approximately -212.008790892, compared with the old BARON Big-M value -207.626116094.',
        'Dynamic Hull returns a feasible value -196.931186772 and reports optimal with lower bound -196.931186782, but that lower bound exceeds the independently validated Big-M feasible value by about 15.077604.',
        'The Dynamic Hull bound therefore cannot certify the original GDP globally; the exact solver, transformation or numerical cause is not established by these saved artifacts.',
        'All six CSTR GLOA runs again report optimal after two NLP attempts while their lower bounds exceed independently checked feasible objectives.',
        'Their short completion times are not evidence of correct global solution of those CSTRs.',
        f"The unchanged tolerance-based bound screen flags {len(summary['bound_conflicts'])} comparisons in total: six CSTR GLOA cases, Dynamic Hull, and twelve additional CSTR Hull/LOA/RIC discrepancies between approximately 3.35e-5 and 1.24e-4.",
        'The twelve small discrepancies concern tolerance-accepted numerical vectors and must not be assigned the same structural cause as the much larger GLOA and Dynamic Hull conflicts.',
        'For both GDPopt LOA and RIC, CSTR15/CSTR20/CSTR25 newly match the fixed reference relative to the selected BARON runs.',
        'CSTR30 LOA and RIC do not match the reference; RIC reaches the hard watchdog with a saved feasible incumbent and one unfinished journal return.',
        'CSTR30 uses the original constructor initialization, not the separate material-balance/zero-recycle publication experiment.',
        'All three GDPopt Column/Dynamic runs spend their budget on the first SCIP NLP and return suboptimal feasible incumbents before continued exploration.',
        'No extra solve or automatic replacement is justified merely by a time-limit result; CSTR15 Big-M acceptance loss and the Dynamic Hull/CSTR GLOA bound conflicts warrant targeted diagnosis before treating them as certified performance results.', '',
        '## Intermediate HiGHS/SCIP cohort', '',
        '| Method | Previous HiGHS/SCIP hits | New SCIP/SCIP hits | Previous completion s | New completion s |',
        '|---|---:|---:|---:|---:|']
    for m in methods:
        if m['previous_highs_scip_hits'] is not None:
            lines.append(f"| {m['method']} | {m['previous_highs_scip_hits']}/9 | {m['scip_target_hits']}/9 | {m['previous_highs_scip_completion_s']:.2f} | {m['scip_completion_s_sum']:.2f} |")
    lines += ['', 'The previous and new GDPopt cohorts each have 13/27 absolute-reference hits, so changing the MIP master to SCIP does not increase the aggregate target count in this observation.',
        f"The observed GDPopt completion sum increases by {100*(sum(m['scip_completion_s_sum'] for m in methods if m['previous_highs_scip_completion_s'] is not None)/sum(m['previous_highs_scip_completion_s'] or 0 for m in methods)-1):.2f}% relative to that intermediate cohort; transport retries and the earlier CSTR20 RIC error make this an uncontrolled comparison.",
        'RIC gains CSTR20 relative to the earlier network-error run and loses the earlier CSTR30 target hit; the other method hit sets are unchanged.',
        'The new Column RIC vector is saved and independently feasible, whereas the earlier cohort had no saved vector for that job.',
        'The three Dynamic GDPopt objectives worsen from approximately -119.383102745 to -117.074383038, while still missing the reference in both cohorts.', '',
        '## Solver calls, environment and integrity', '',
        f"The benchmark has {summary['started_interface_attempts']} interface attempts and {sum(summary['actual_benchmark_solver_invocations'].values())} confirmed solver invocations: {dict(summary['actual_benchmark_solver_invocations'])}.",
        'Two failed network-start attempts never reach the SCIP execution banner, and the final CSTR30 RIC NLP interface attempt is interrupted before any new SCIP banner or terminal journal record appears.',
        f"Five transient network errors are recovered inside their existing deadlines, with {summary['network_backoff_s']:.0f} seconds of recorded backoff and no whole-job retries.",
        f"Preflight adds {summary['actual_preflight_solver_invocations']} separate tiny SCIP solves and {summary['compile_only_preflight_calls']} compile-only calls; these are excluded from benchmark counts and costs.",
        'The benchmark calls are confirmed from actual SCIP execution banners as well as journals, with no external BARON, HiGHS or IPOPT benchmark invocation.',
        'SCIP may internally link Ipopt; that is not a GDPopt nlp_solver=ipopt configuration.',
        'The unused minlp_solver=baron default displayed in the RIC configuration is not an actual BARON call because force_subproblem_nlp=True and both active solver argument blocks specify SCIP.',
        'Actual GDPopt configuration records retain subproblem_presolve=True, mip_presolve=True, set_covering initialization, and the original NLP export.',
        'The special Grid presolve-disabled/DNLP diagnostic is not applied to these Process runs.',
        'All returns record Dantzig, GAMS 52.2.0, SCIP 9.2.4, Python 3.11.16, Pyomo 6.10.0 and single-thread settings, matching the environment gate.',
        'The four CPUs are 18, 20, 22 and 24 on separate physical cores, without an exclusive whole-server reservation.',
        'The original model source, saved initialization, initialization label and template bound tightening match the corresponding BARON records for all 45 pairs.',
        'All original ZIP members, package hashes and all 45 terminal seals are verified, including interrupted GAMS scratch files previously omitted by the old packer.',
        f"The independent local audit validates {summary['returned_feasible_solutions']} new vectors and all 45 selected BARON vectors, with maximum new original-GDP violation {summary['max_new_original_violation']:.16g}.",
        'The local audit uses Python 3.13.12 and Pyomo 6.10.0 solely to evaluate saved vectors and guards against optimizer construction.',
        'Machine-precision differences between Linux and macOS objective/residual evaluation are recorded in solution_checks.json; all saved-vector checks retain their existing acceptance criteria.',
        'The original archives, historical reports, manuscript, Overleaf material and figures are preserved.',
        'No installed Pyomo code, solver option, model constraint or returned execution record is modified by this analysis.',
        'The report does not automatically replace manuscript representative results or claim new global certificates.', '',
        '## Reproduction', '', '```bash',
        'python scripts/analyze_process_scip_four_return.py --output /tmp/process-scip-four-reproduced',
        'python -m pytest tests/test_process_scip_four_return.py tests/test_process_scip_return.py -q', '```', '',
        'The four unchanged returned ZIPs and locally computed sidecars are stored under results/archives/process_scip_METHOD_20261026_result.zip, with METHOD=minlp, ric, loa or gloa.',
        '[jobs.csv](jobs.csv) retains every new job, including both missing vectors and all time limits.',
        '[paired_baron_scip.csv](paired_baron_scip.csv) contains all 45 BARON pairs and [paired_highs_scip.csv](paired_highs_scip.csv) contains the 27 intermediate-cohort pairs.',
        '[solution_checks.json](solution_checks.json), [issues.json](issues.json) and [solver_calls.csv](solver_calls.csv) preserve independent validation, failure/bound evidence and actual call accounting.',
        '[manifest.json](manifest.json) records input hashes, exact execution source hashes, environment, options, source revisions and the missing execution commit identity explicitly.',
        'Full selected-variable trajectories remain in each unchanged archive, with their per-job event counts and SHA256 links in jobs.csv.',
        '[tests.log](tests.log) records the solver-free tests, [preservation.json](preservation.json) records protected-file hashes, and [artifact_checksums.json](artifact_checksums.json) seals the new code, archives and outputs.',
        'The report is a follow-up on review/cstr15-dantzig-results, the branch associated with already-merged PR 49; pushing it does not automatically update main.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    logging.getLogger('pyomo').setLevel(logging.ERROR)
    summary = analyze(parser.parse_args().output)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('by_method', 'bound_conflicts')}, indent=2))
