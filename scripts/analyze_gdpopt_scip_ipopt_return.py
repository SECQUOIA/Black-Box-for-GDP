"""Audit six SCIP/IPOPT returns and pair historical results; never optimize.

Import originals with --archives DIR once. The checked-in evidence ZIPs retain
all non-call members byte-for-byte; large per-call scratch stays in originals.
Default reproduction uses only those compact evidence ZIPs and repository data.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
from datetime import datetime
import hashlib
import io
import json
import logging
from pathlib import Path, PurePosixPath
import re
import statistics
import sys
import zipfile
import csv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import analyze_process_scip_return as audit  # noqa: E402

DEFAULT = ROOT / 'results/gdpopt_scip_ipopt_analysis_20261030'
METHODS = ('loa', 'ric', 'gloa')
ERRORS = {'error', 'worker_error', 'subproblem_incomplete', 'interrupted'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def read(z, name):
    return json.loads(z.read(name))


def journal(z, name):
    rows = []
    lines = z.read(name).decode().splitlines() if name in z.namelist() else []
    for index, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except ValueError:
            require(index == len(lines)-1, 'Corrupt interior journal record')
            rows.append({'event': 'truncated_last_record', 'raw': line})
    return rows


def inventory(z):
    names = z.namelist()
    require(len(names) == len(set(names)), 'Duplicate ZIP members')
    require(all(n.startswith('run/') and '..' not in PurePosixPath(n).parts for n in names), 'Unsafe ZIP members')
    expected = {}
    for line in z.read('run/SHA256SUMS').decode().splitlines():
        digest, name = line.split('  ', 1)
        require(name not in expected, 'Duplicate inventory entry')
        expected[name] = digest
    return expected


def import_archives(directory, evidence):
    """Verify every original member before making explicitly partial evidence."""
    evidence.mkdir(parents=True, exist_ok=False)
    entries = []
    for path in sorted(directory.glob('gdpopt_scip_ipopt_part??_result_*.zip')):
        digest = sha(path.read_bytes())
        require(digest == path.with_suffix('.zip.sha256').read_text().split()[0], 'Outer checksum mismatch')
        with zipfile.ZipFile(path) as z:
            expected = inventory(z)
            require(set(expected) == {n[4:] for n in z.namelist()} - {'SHA256SUMS'}, 'Incomplete inventory')
            for name, checksum in expected.items():
                require(sha(z.read('run/' + name)) == checksum, 'Original member checksum mismatch: ' + name)
            package = read(z, 'run/run.json')['package_id']
            destination = evidence / (package + '.zip')
            kept = {}
            with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
                for name in sorted(z.namelist()):
                    if '/calls/' in name:
                        continue
                    data = z.read(name)
                    info = zipfile.ZipInfo(name, (2026, 10, 30, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    out.writestr(info, data, compresslevel=9)
                    kept[name] = sha(data)
            entries.append({'package_id': package, 'original_archive': path.name,
                'original_sha256': digest, 'original_bytes': path.stat().st_size,
                'original_members_verified': len(expected), 'compact_archive': destination.name,
                'compact_sha256': sha(destination.read_bytes()), 'retained_members_sha256': kept,
                'omitted_members': len(expected)+1-len(kept),
                'omission_policy': 'Only /calls/ scratch and nested call archives omitted. All logs, journals, vectors, source ZIP and original full inventory retained byte-for-byte.'})
        print('Imported ' + package, flush=True)
    require(len(entries) == len({e['package_id'] for e in entries}) == 6, 'Expected one return for each of six packages')
    save(evidence / 'IMPORT.json', entries)


def comparison(old, new, cohort, clock_key):
    value = old['objective']
    old_hit = old['target_hit']
    new_hit = new['target_hit']
    return {'job_id': new['job_id'], 'scope': new['scope'], 'method': new['method'], 'cohort': cohort,
        'reference': new['reference'], 'old_objective': value, 'new_objective': new['objective'],
        'new_minus_old_objective': new['objective']-value if value is not None and new['objective'] is not None else None,
        'old_target_hit': old_hit, 'new_target_hit': new_hit,
        'pair_class': ('both' if old_hit else 'new_only') if new_hit else ('old_only' if old_hit else 'neither'),
        'old_target_attained': audit.attained(value, new['reference']), 'new_target_attained': new['target_attained'],
        'old_seconds': old['seconds'], 'new_seconds': new[clock_key],
        'new_over_old_time_ratio': new[clock_key]/old['seconds'] if old['seconds'] else None,
        'clock': clock_key, 'old_termination': old['termination'], 'new_termination': new['termination'],
        'old_archive': old.get('archive'), 'old_result_sha256': old.get('result_sha256'),
        'causal_solver_speed_comparison': False}


def aggregate(rows):
    return {'jobs': len(rows), 'target_hits': sum(r['target_hit'] for r in rows),
        'target_attained': sum(r['target_attained'] for r in rows),
        'feasible_vectors': sum(r['original_gdp_feasible'] for r in rows),
        'execution_errors': sum(r['status'] in ERRORS for r in rows),
        'time_limits': sum(r['termination'] == 'maxTimeLimit' for r in rows),
        'hard_watchdogs': sum(r['status'] == 'hard_time_limit' for r in rows),
        'optimal_but_target_miss': sum(r['termination'] == 'optimal' and not r['target_hit'] for r in rows),
        'worker_seconds': sum(r['worker_seconds'] for r in rows),
        'completion_with_preparation_seconds': sum(r['completion_with_preparation_seconds'] for r in rows),
        'actual_scip_calls': sum(r['actual_scip_calls'] for r in rows),
        'actual_ipopt_calls': sum(r['actual_ipopt_calls'] for r in rows)}


def summarize_pairs(rows):
    return {'pairs': len(rows), 'old_hits': sum(r['old_target_hit'] for r in rows),
        'new_hits': sum(r['new_target_hit'] for r in rows),
        'classes': dict(Counter(r['pair_class'] for r in rows)),
        'old_seconds_sum': sum(r['old_seconds'] for r in rows),
        'new_seconds_sum': sum(r['new_seconds'] for r in rows),
        'ratio_of_summed_seconds': sum(r['new_seconds'] for r in rows)/sum(r['old_seconds'] for r in rows),
        'median_paired_ratio': statistics.median(r['new_over_old_time_ratio'] for r in rows),
        'new_only_jobs': [r['job_id'] for r in rows if r['pair_class'] == 'new_only'],
        'old_only_jobs': [r['job_id'] for r in rows if r['pair_class'] == 'old_only']}


def analyze(evidence, output):
    logging.getLogger('pyomo').setLevel(logging.ERROR)
    output.mkdir(parents=True, exist_ok=True)
    entries = json.loads((evidence / 'IMPORT.json').read_text())
    require(len(entries) == 6, 'Expected six evidence ZIPs')
    rows, checks, packages, pairs, issues = [], [], [], [], []
    inputs = {str(Path(__file__).relative_to(ROOT)): sha(Path(__file__).read_bytes()),
              'scripts/analyze_process_scip_return.py': sha((ROOT / 'scripts/analyze_process_scip_return.py').read_bytes())}
    history_paths = {key: ROOT / 'results/process_scip_four_analysis_20261026' / name for key, name in
                     [('scip', 'jobs.csv'), ('baron', 'paired_baron_scip.csv'), ('highs_scip', 'paired_highs_scip.csv')]}
    history = {}
    for key, path in history_paths.items():
        history[key] = {(r['instance_id'], r['method']): r for r in csv.DictReader(path.open())}
        inputs[str(path.relative_to(ROOT))] = sha(path.read_bytes())
    with ExitStack() as stack:
        archives = {}
        source = None
        for entry in entries:
            path = evidence / entry['compact_archive']
            require(sha(path.read_bytes()) == entry['compact_sha256'], 'Compact evidence changed')
            z = stack.enter_context(zipfile.ZipFile(path))
            require(set(z.namelist()) == set(entry['retained_members_sha256']), 'Compact inventory changed')
            for name, digest in entry['retained_members_sha256'].items():
                require(sha(z.read(name)) == digest, 'Retained member changed')
            inv = inventory(z)
            require(all(inv[n[4:]] == d for n, d in entry['retained_members_sha256'].items() if n != 'run/SHA256SUMS'), 'Original link mismatch')
            run, config = read(z, 'run/run.json'), read(z, 'run/config.json')
            manifest, specs = read(z, 'run/MANIFEST.json'), read(z, 'run/jobs.json')
            require(run['status'] == 'completed' and len(specs) == 15, 'Incomplete package')
            require(config['mip_solver'] == 'scip' and config['nlp_solver'] == 'ipopt', 'Wrong solver design')
            require(config['time_limit'] == 1800 and config['threads'] == 1, 'Budget/thread design changed')
            require(read(z, 'run/environment.json')['differences'] == {}, 'Environment gate failed')
            require(all(v == '1' for v in run['runtime']['thread_environment'].values()), 'Thread environment differs')
            preflights = [read(z, n) for n in z.namelist() if n.endswith('/preflight/checks.json')]
            require(len(preflights) == 1 and preflights[0]['status'] == 'passed', 'Preflight not passed')
            preflight_starts = Counter(s for n in z.namelist() if '/preflight/' in n and n.endswith('/solver_calls.jsonl')
                for c in journal(z, n) for s in c.get('observed', {}).get('solver_starts', []))
            require(preflight_starts == {'SCIP': 1, 'IPOPT': 1}, 'Unexpected preflight solves')
            src = stack.enter_context(zipfile.ZipFile(io.BytesIO(z.read('run/package_source.zip'))))
            for name, digest in manifest['files_sha256'].items():
                require(sha(src.read(name)) == digest, 'Executed source hash mismatch')
            model_hashes = {n: d for n, d in manifest['files_sha256'].items() if n.startswith('source/')}
            if source is None:
                source, frozen_hashes = src, model_hashes
            require(model_hashes == frozen_hashes, 'Models differ across packages')
            ledger = journal(z, 'run/ledger.jsonl')
            starts = [r['job_id'] for r in ledger if r.get('event') == 'START']
            terminals = [r['job_id'] for r in ledger if r.get('event') in {'DONE', 'FAILED'}]
            require(starts == [s['job_id'] for s in specs] and terminals == starts, 'Missing/duplicate terminal jobs')
            packages.append({'package_id': entry['package_id'], 'started_utc': run['started_utc'],
                'ended_utc': run['ended_utc'], 'elapsed_seconds': (datetime.fromisoformat(run['ended_utc'])-datetime.fromisoformat(run['started_utc'])).total_seconds(),
                'status': run['status'], 'jobs': len(specs), 'runtime': run['runtime'],
                'original_archive_sha256': entry['original_sha256'], 'preflight': preflights[0],
                'preflight_solver_starts': dict(preflight_starts)})
            archives[entry['package_id']] = (z, specs, read(z, 'run/summary.json')['results'])
        # Builds and evaluates frozen original models only. SolverFactory is blocked.
        with audit.frozen_models(source, '') as build_process:
            from gdp_models.grid import build_grid_gdp
            for package, (z, specs, results) in archives.items():
                require(len(results) == len({r['job_id'] for r in results}) == 15, 'Bad result denominator')
                result_map = {r['job_id']: r for r in results}
                for spec in specs:
                    job = 'run/jobs/' + spec['job_id'] + '/'
                    result = read(z, job + 'result.json')
                    require(result == result_map[spec['job_id']], 'Summary/result mismatch')
                    check = {'original_gdp_feasible': False, 'availability': 'no_saved_vector'}
                    if job + 'solution.json' in z.namelist():
                        model = build_grid_gdp(spec['instance_id'], verify_csv=False) if spec['scope'] == 'grid' else build_process(spec)
                        check = audit.verify_solution(model, read(z, job + 'solution.json'), result)
                    checks.append({'job_id': spec['job_id'], **check,
                                   'server_validation': result.get('original_validation')})
                    feasible = check['original_gdp_feasible']
                    value = check.get('objective_recomputed') if feasible else None
                    target = feasible and audit.hit(value, spec['reference'])
                    require(target == result['target_hit'], 'Independent target outcome differs')
                    if feasible and not result.get('original_validation', {}).get('original_gdp_feasible'):
                        issues.append({'job_id': spec['job_id'], 'kind': 'server_validation_missing_after_watchdog',
                            'resolution': 'Saved vector independently verified locally; original returned record unchanged.',
                            'target_hit': target})
                    log = z.read(job + 'run.log').decode(errors='replace')
                    banners = Counter(re.findall(r'^--- Executing (\w+) \(', log, re.M))
                    require(dict(banners) == result['actual_solver_starts'], 'Journal/banner mismatch')
                    require(set(banners) <= {'SCIP', 'IPOPT'}, 'Unexpected solver execution')
                    calls = journal(z, job + 'solver_calls.jsonl')
                    complete = [c for c in calls if 'index' in c]
                    require([c['index'] for c in complete] == list(range(1, len(complete)+1)), 'Call sequence differs')
                    for c in complete:
                        require((c['solver'], c['mtype']) in {('scip', 'mip'), ('ipopt', 'nlp')}, 'Wrong routing')
                        require(c['threads'] == 1 and c['affinity'] == [int(packages[[p['package_id'] for p in packages].index(package)]['runtime']['affinity']['cpu'])], 'Call affinity differs')
                        observed = c.get('observed', {})
                        if observed.get('solver_starts'):
                            require(observed['solver_starts'] == [c['solver'].upper()], 'Wrong actual start')
                            require(observed[c['solver']] == [{'scip': '9.2.4', 'ipopt': '3.14.19'}[c['solver']]], 'Wrong version')
                    require(banners['IPOPT'] == result['actual_nlp_calls'], 'NLP call count differs')
                    if spec['scope'] == 'grid':
                        require(banners['IPOPT'] == 0, 'Unexpected Grid NLP call')
                    prep = result.get('preparation_wall_s', 0)
                    measured = result.get('method_wall_s')
                    completion = measured + prep if measured is not None else result['worker_wall_s']
                    first = result.get('first_target', {})
                    row = {k: spec[k] for k in ('job_id', 'scope', 'instance_id', 'method', 'reference', 'historical_cohort')}
                    row.update(package_id=package, status=result['status'], termination=result['termination'],
                        original_gdp_feasible=feasible, objective=value, target_hit=target,
                        target_attained=feasible and audit.attained(value, spec['reference']),
                        worker_seconds=result['worker_wall_s'], completion_with_preparation_seconds=completion,
                        first_target_job_seconds=first.get('job_elapsed_s') if target else None,
                        actual_scip_calls=banners['SCIP'], actual_ipopt_calls=banners['IPOPT'],
                        interface_attempts=result['interface_attempts'], call_errors=sum(c.get('status') == 'error' for c in complete),
                        retries=len(journal(z, job + 'network_recovery.jsonl')),
                        presolve_rejections=result.get('presolve_rejections', 0),
                        max_original_violation=check.get('max_original_violation'),
                        reported_lower_bound=result.get('reported_lower_bound'), global_optimality_certified=False,
                        solver_versions_from_raw_log={
                            'SCIP': sorted(set(re.findall(r'SCIP version (\d+\.\d+\.\d+)\b', log))),
                            'IPOPT': sorted(set(re.findall(r'(?:Ipopt Library |Ipopt version )(\d+\.\d+\.\d+)\b', log)))},
                        result_sha256=sha(z.read(job + 'result.json')), solution_sha256=sha(z.read(job + 'solution.json')) if feasible else None)
                    rows.append(row)
                    for solver, count, expected_version in [('SCIP', banners['SCIP'], '9.2.4'), ('IPOPT', banners['IPOPT'], '3.14.19')]:
                        require(not count or row['solver_versions_from_raw_log'][solver] == [expected_version], 'Raw log version mismatch')
                    if row['termination'] == 'optimal' and not target:
                        issues.append({'job_id': row['job_id'], 'kind': 'optimal_termination_but_target_miss', 'objective': value, 'reference': spec['reference']})
                    # Bind the primary comparison to exactly the baseline chosen before execution.
                    old_path = ROOT / spec['historical_archive']
                    inputs[spec['historical_archive']] = None
                    with zipfile.ZipFile(old_path) as old_zip:
                        raw = old_zip.read(spec['historical_result_member'])
                    require(sha(raw) == spec['historical_result_sha256'], 'Historical result differs')
                    old_result = json.loads(raw)
                    if spec['scope'] == 'process':
                        old_row = history['scip'][spec['instance_id'], spec['method']]
                        old_value = float(old_row['objective']) if old_row['objective'] else None
                        old_hit = old_row['target_hit'] == 'True'
                        old_seconds = float(old_row['total_with_preparation_s'])
                        clock = 'completion_with_preparation_seconds'
                    else:
                        old_value = old_result.get('objective')
                        old_hit = audit.hit(old_value, spec['reference'])
                        old_seconds = old_result['worker_wall_s']
                        clock = 'worker_seconds'
                    pairs.append(comparison({'objective': old_value, 'target_hit': old_hit, 'seconds': old_seconds,
                        'termination': old_result['termination'], 'archive': spec['historical_archive'],
                        'result_sha256': spec['historical_result_sha256']}, row, 'previous_scip_scip', clock))
                    if spec['scope'] == 'process':
                        for cohort in ('baron', 'highs_scip'):
                            old = history[cohort][spec['instance_id'], spec['method']]
                            pairs.append(comparison({'objective': float(old['old_objective']) if old['old_objective'] else None,
                                'target_hit': old['old_target_hit'] == 'True', 'seconds': float(old['old_completion_s']),
                                'termination': old['old_termination']}, row, 'previous_' + cohort, clock))
                print('Audited ' + package, flush=True)
    for name, digest in inputs.items():
        if digest is None:
            inputs[name] = sha((ROOT / name).read_bytes())
    require(len(rows) == len({r['job_id'] for r in rows}) == 90, 'Missing/duplicate jobs')
    rows.sort(key=lambda r: r['job_id'])
    summary = {'overall': aggregate(rows), 'by_scope_method': [], 'comparisons': [],
        'new_optimization_calls': 0, 'independent_audit': 'Frozen original GDP vectors evaluated under blocked SolverFactory.',
        'parallel_elapsed_seconds_before_final_packaging': (max(datetime.fromisoformat(p['ended_utc']) for p in packages)-min(datetime.fromisoformat(p['started_utc']) for p in packages)).total_seconds(),
        'server_validation_gaps': sum(i['kind'] == 'server_validation_missing_after_watchdog' for i in issues)}
    summary['audit_max_original_violation'] = max(r['max_original_violation'] for r in rows if r['original_gdp_feasible'])
    summary['actual_solver_calls_exclude_preflight'] = True
    summary['preflight_solver_calls'] = sum(sum(p['preflight_solver_starts'].values()) for p in packages)
    for scope in ('grid', 'process'):
        for method in METHODS:
            subset = [r for r in rows if r['scope'] == scope and r['method'] == method]
            summary['by_scope_method'].append({'scope': scope, 'method': method, **aggregate(subset)})
        for cohort in sorted({r['cohort'] for r in pairs if r['scope'] == scope}):
            for method in (None, *METHODS):
                subset = [r for r in pairs if r['scope'] == scope and r['cohort'] == cohort and (method is None or r['method'] == method)]
                summary['comparisons'].append({'scope': scope, 'cohort': cohort, 'method': method or 'all', **summarize_pairs(subset)})
    for name, obj in [('jobs.json', rows), ('paired_comparisons.json', pairs), ('solution_checks.json', checks),
                      ('issues.json', issues), ('packages.json', packages), ('summary.json', summary),
                      ('provenance.json', {'input_sha256': inputs, 'original_archives': entries, 'analysis_scope': 'No benchmark reruns; historical and returned records unchanged.'})]:
        save(output / name, obj)
    report(output, rows, summary)
    return summary


def report(output, rows, summary):
    lines = ['# GDPopt SCIP–IPOPT returns, 30 October 2026', '',
        'All 90 jobs have terminal records. The new campaign uses SCIP 9.2.4 for MIP and IPOPT 3.14.19 for NLP; the primary historical Process cohort uses SCIP for both. These are separate solver configurations, not a correction that invalidates every previous SCIP result.', '',
        '| Scope | Method | Feasible | Target hits | Time limits | Optimal but misses | Worker seconds | SCIP / IPOPT calls |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in summary['by_scope_method']:
        lines.append(f"| {r['scope']} | {r['method'].upper()} | {r['feasible_vectors']}/{r['jobs']} | {r['target_hits']}/{r['jobs']} | {r['time_limits']} | {r['optimal_but_target_miss']} | {r['worker_seconds']:.3f} | {r['actual_scip_calls']} / {r['actual_ipopt_calls']} |")
    lines += ['', '## Historical comparison', '',
        'Every primary pair uses the exact historical result hash selected before launching the new experiment. Grid history is the unchanged descriptive mixture of retained first attempts and recoveries, not a fresh equal-budget cohort. Process history is the October 26 SCIP/SCIP cohort. Supplementary Process pairs retain the selected HiGHS/BARON and earlier HiGHS/SCIP cohorts.', '',
        '| Scope | Previous configuration | Method | Previous hits | New hits | Previous seconds | New seconds | New / old |',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for r in summary['comparisons']:
        lines.append(f"| {r['scope']} | {r['cohort']} | {r['method']} | {r['old_hits']}/{r['pairs']} | {r['new_hits']}/{r['pairs']} | {r['old_seconds_sum']:.3f} | {r['new_seconds_sum']:.3f} | {r['ratio_of_summed_seconds']:.3f} |")
    lines += ['', 'Grid timing compares worker wall seconds. Process timing compares method completion plus preparation, using worker wall time for hard watchdog cases to avoid double-counting preparation. These are completion costs, not time to first target. Sums across concurrent packages are not elapsed duration. One run per problem, changed tracing/adapter overhead and nonexclusive cores do not establish causal solver speed or statistical superiority.', '',
        '## Interpretation', '',
        '- Process LOA/RIC gain the Dynamic target and lose the CSTR10 and CSTR25 targets relative to SCIP/SCIP. Column objectives improve but still miss the unchanged reference. The IPOPT change is not uniformly better.',
        '- All 63 Grid jobs make zero actual IPOPT calls. Their fixed subproblems take the linear SCIP path. Grid timing/target differences cannot be attributed to changing the NLP solver to IPOPT.',
        '- holder_table, michalewicz and shubert remain target misses for all three methods. The previously diagnosed preprocessing issue is not repaired by this experiment. Optimal termination strings are not independently valid global certificates.',
        '- IPOPT is a local NLP solver. A feasible returned vector, target hit and global certificate are distinct claims. This report grants no new global certificate, including for GLOA or RIC.',
        '- Targets and acceptance tolerance remain abs(objective-reference) <= 1e-5*max(1,abs(reference)). Separate minimization attainment is retained. No objective, reference, initialization, bound or returned result is replaced.',
        '- CSTR30 retains constructor initialization; CSTR5–25 retain the algebraic saved initialization. The separate DFO mass_balance_zero_recycle protocol is not substituted. Direct Big-M/Hull methods were not rerun.', '',
        '## Audit and limitations', '',
        f"All {summary['overall']['feasible_vectors']} saved vectors pass an independent original-GDP check without an optimizer. {summary['server_validation_gaps']} hard-watchdog Grid returns had a saved vector but only an unavailable server validation marker; local verification fills that analytical gap without rewriting the source record or changing any hit outcome.", '',
        f"The measured parallel campaign span was {summary['parallel_elapsed_seconds_before_final_packaging']/3600:.4f} hours, from launch through the last run end timestamp, excluding final ZIP packaging. Reported execution errors: {summary['overall']['execution_errors']}. Time-limited runs: {summary['overall']['time_limits']}. Completed does not mean globally solved.", '',
        'Each original ZIP outer SHA256 and every internally listed member was verified at import. Compact evidence retains all non-call files byte-for-byte, including complete run logs, solver journals, trajectories, solution vectors, preflights, exact executed source ZIP and the original full member inventory. Only the large /calls/ scratch and nested per-call ZIPs are omitted from Git; unchanged originals remain with the user. IMPORT.json records original hashes and the explicit retained-file inventory. Solver execution banners in complete logs independently match the journal counts. All 90 jobs keep their denominator, including watchdogs and target misses.', '',
        '## Per-job primary comparisons', '',
        '| Job | Previous target | New target | Previous objective | New objective | Termination |',
        '|---|---|---|---:|---:|---|']
    pairs = json.loads((output / 'paired_comparisons.json').read_text())
    for r in sorted((p for p in pairs if p['cohort'] == 'previous_scip_scip'), key=lambda p:p['job_id']):
        lines.append(f"| {r['job_id']} | {r['old_target_hit']} | {r['new_target_hit']} | {r['old_objective']} | {r['new_objective']} | {r['new_termination']} |")
    lines += ['', '## Reproduce without a solver', '', '```bash',
        'python scripts/analyze_gdpopt_scip_ipopt_return.py --output /tmp/gdpopt-scip-ipopt-analysis',
        'python -m pytest tests/test_gdpopt_scip_ipopt_return.py -q', '```', '',
        'To verify the original downloaded archives again, add --archives /path/to/original-zips and use a fresh output directory. Pyomo 6.10.0 is required for saved-vector evaluation. Analysis never launches a benchmark. Existing reports and manuscript files are unchanged.']
    (output / 'README.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path)
    parser.add_argument('--evidence', type=Path, default=DEFAULT / 'evidence')
    parser.add_argument('--output', type=Path, default=DEFAULT)
    args = parser.parse_args()
    if args.archives:
        args.evidence = args.output / 'evidence'
        import_archives(args.archives, args.evidence)
    result = analyze(args.evidence, args.output)
    print(json.dumps(result['overall'], indent=2))
