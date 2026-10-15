"""Audit and preserve the returned non-CSTR DFO archive, without running solvers."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import stat
import statistics
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ipopt_dfo_non_cstr as runner

RETURN_NAME = 'ipopt_dfo_non_cstr_20261015_172428_o671edu_'
RETURN_SHA256 = 'ed7eaa2c20031b58f5a9c02c0bc89699cf170c7e256a65c92664ac4b1875cc6e'
PACKAGE = ROOT / 'results/runners/ipopt_dfo_non_cstr_20261015.zip'
PACKAGE_SHA256 = 'b2e61d0e58e1b6e1f76daf91ceaf1631846cbb3048e4ba07066144d85cdc1e3f'
TABLES = ('runs.csv', 'callbacks.csv', 'summary.csv', 'summary.json')
CATEGORIES = ('target_reached', 'target_not_reached', 'execution_failed', 'not_run')
OVERRUN_MESSAGE = 'RuntimeError: Optimizer swallowed the hard budget stop'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rows(path):
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(stream))


def strict_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def number(row, field):
    return float(row[field]) if row and row.get(field) not in (None, '') else None


def extract_verified(archive, temporary):
    require(runner.sha(archive) == RETURN_SHA256, 'Unexpected return archive hash')
    require(runner.sha(PACKAGE) == PACKAGE_SHA256, 'Submitted package hash changed')
    hashes = {}
    with zipfile.ZipFile(archive) as source:
        require(source.testzip() is None, 'Return ZIP CRC failure')
        for member in source.infolist():
            path = PurePosixPath(member.filename)
            require(not path.is_absolute() and '..' not in path.parts and path.parts[0] == RETURN_NAME,
                    'Unsafe archive member')
            require(not stat.S_ISLNK(member.external_attr >> 16), 'Archive symlink not allowed')
            if member.is_dir():
                continue
            name = '/'.join(path.parts[1:])
            require(name and name not in hashes, 'Duplicate/empty member')
            data = source.read(member)
            hashes[name] = hashlib.sha256(data).hexdigest()
            target = temporary / RETURN_NAME / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    directory = temporary / RETURN_NAME
    reproduction = directory / 'reproduction'
    names = set()
    with zipfile.ZipFile(PACKAGE) as package:
        for name in package.namelist():
            if name.endswith('/'):
                continue
            require(name.startswith('ipopt_dfo_non_cstr_runner/'), 'Unexpected package root')
            relative = name.removeprefix('ipopt_dfo_non_cstr_runner/')
            names.add(relative)
            require((reproduction / relative).read_bytes() == package.read(name), 'Changed reproduction file: ' + relative)
    require(names == {p.relative_to(reproduction).as_posix() for p in reproduction.rglob('*') if p.is_file()},
            'Missing/extra reproduction files')
    runner.verify_inventory(reproduction)
    require(runner.sha(runner.__file__) == runner.sha(reproduction / 'ipopt_dfo_non_cstr.py'), 'Local runner differs')
    require(runner.read(directory / 'run.json')['bundle_inventory_sha256'] == runner.sha(reproduction / 'SHA256SUMS'),
            'Run inventory mismatch')
    return directory, hashes, len(names)


def validate_callback(event, spec, table, index):
    point = tuple(event['point'])
    require(event['index'] == index and index <= spec['budget'], 'Invalid recorded callback index')
    require(len(point) == len(spec['lower']) and all(type(x) is int and lo <= x <= hi
            for x, lo, hi in zip(point, spec['lower'], spec['upper'])), 'Out-of-domain coordinate')
    require(tuple(int(round(x)) for x in event['callback_coordinates']) == point, 'Coordinate mapping mismatch')
    require(event['phase'] == ('initial' if index <= 3 else 'adaptive'), 'Callback phase mismatch')
    if index <= 3:
        require(list(point) == spec['starts'][index - 1], 'Shared initial order changed')
    source = table.get(point)
    require(event['source_row'] == source, 'Source differs from exact case/coordinate CSV row')
    require(source is not None or not runner.logical_allowed(spec['case'], point), 'Unevaluated candidate used')
    accepted = bool(source and source['accepted'] == 'True')
    raw = number(source, 'objective') if accepted else None
    value = raw if accepted else 1e6 if spec['method'] in ('rbfopt', 'dsda') else None
    kind = 'finite' if value is not None else 'nan' if spec['method'] == 'bam' else '+inf'
    require(event['accepted'] is accepted and event['raw_objective'] == raw, 'Acceptance/objective mismatch')
    require(event['method_value'] == value and event['method_value_kind'] == kind, 'Method penalty mismatch')
    state = 'accepted' if accepted else 'evaluated_unaccepted' if source else 'logical_exclusion_unmeasured'
    require(event['evaluation_state'] == state, 'Evaluation state mismatch')
    reason = None if accepted else source['message'] if source else state
    require(event['failure_reason'] == reason, 'Original failure reason changed')
    require(event['callback_exit'] == ('budget_stop' if index == spec['budget'] else 'return'), 'Callback exit mismatch')
    require(event['value_returned_to_optimizer'] is (index < spec['budget']), 'Delivered-value flag mismatch')
    require(event['selected_attempt'] == (1 if source else None) and event['available_attempts'] == (1 if source else 0),
            'Unexpected attempt selection')
    for field in ('selected_attempt_nlp_s', 'all_attempts_nlp_s'):
        require(event[field] == number(source, 'total_wall_s'), 'NLP cost is not from selected row')
    require(event['nlp_times'] == {k: number(source, k) for k in runner.TIMES}, 'NLP timing breakdown mismatch')
    require(event['fmqa_reporting_penalty'] == (1e6 if spec['method'] == 'fmqa_sa' and not accepted else None),
            'FMQA reporting penalty changed')
    require(all(math.isfinite(event[k]) and event[k] >= 0 for k in ('lookup_wall_s', 'elapsed_s')), 'Invalid callback clock')


def budget_issue(spec, result, events):
    """A guard exception proves an extra request; its coordinates were not logged."""
    message = (result.get('algorithm_result') or {}).get('terminal_budget_exception')
    if message is None:
        return None
    require(message == OVERRUN_MESSAGE and spec['method'] == 'bam', 'Unknown terminal exception')
    require(len(events) == spec['budget'] and events[-1]['callback_exit'] == 'budget_stop', 'Invalid overrun evidence')
    return {'job_id': spec['job_id'], 'case': spec['case'], 'budget': spec['budget'], 'seed': spec['seed'],
            'recorded_callbacks': len(events), 'actual_callbacks_lower_bound': len(events) + 1,
            'actual_callbacks_exact': None, 'unlogged_callback_coordinates': None,
            'overrun_csv_read': False, 'overrun_value_delivered': False,
            'evidence': message, 'original_execution_status': result['status'],
            'audit_category': 'execution_failed', 'cause_scope': 'DFO runner/backend budget-stop handling, not IPOPT rejection'}


def validate_settings(spec, settings, events):
    method, budget = spec['method'], spec['budget']
    if method == 'rbfopt':
        expected = {**spec['settings'], 'max_evaluations': budget, 'rand_seed': spec['seed'], 'target_objval': -1e10}
        require(all(settings[k] == v for k, v in expected.items()), 'RBFOpt options/target changed')
    elif method == 'bam':
        options = settings['options']
        require(options['max_evals'] == budget - 3 and options['x_evaluated'] == spec['starts'], 'BAM design/budget changed')
        require(options['f_evaluated'] == [e['raw_objective'] for e in events[:3]], 'BAM initial objectives changed')
        require(settings['x0'] is None and settings['integrality'] == [1] * len(spec['lower'])
                and settings['python_numpy_seed'] == spec['seed'], 'BAM settings changed')
    elif method == 'dsda':
        require(settings == {**spec['settings'], 'max_points_explored': budget - 3}, 'DSDA settings changed')
    else:
        require(all(settings[k] == v for k, v in spec['settings'].items()), 'FMQA settings changed')
        require(settings['torch'] == {'device': 'cpu', 'dtype': 'float32', 'threads': 1,
                'interop_threads': 1, 'deterministic_algorithms': True}, 'FMQA CPU settings changed')


def inspect_inputs(root, tables):
    reports = []
    for case, table in tables.items():
        path = root / 'inputs' / case
        info = runner.read(path / 'provenance.json')
        # Cross-check normalized CSVs against independent per-attempt records.
        for point, row in table.items():
            record = runner.read(path / 'records' / f'point_{int(row["point_index"]):06d}.json')
            require(record['point'] == list(point) and record['case'] == case and record['solver'] == 'gams_ipopt',
                    'Raw record identity mismatch')
            require(record['accepted'] is (row['accepted'] == 'True') and record['status'] == row['status'], 'Raw record status mismatch')
            for field in ('objective', 'candidate_objective', *runner.TIMES):
                require(number(row, field) == record.get(field), 'Raw record value/time mismatch')
        config = runner.CASES[case]
        box = set(itertools.product(*(range(lo, hi + 1) for lo, hi in zip(config['lower'], config['upper']))))
        require(set(table) <= box and all(not runner.logical_allowed(case, p) for p in box - set(table)),
                'Input missing a logical candidate')
        accepted = [r for r in table.values() if r['accepted'] == 'True']
        best = min(float(r['objective']) for r in accepted)
        reports.append({'case': case, 'model': info['model'], 'lower': config['lower'], 'upper': config['upper'],
            'input_csv': f'inputs/{case}/evaluations.csv', 'csv_sha256': runner.sha(path / 'evaluations.csv'),
            'source_directory': info['source_directory'], 'initialization': info['initialization'],
            'upstream': info['upstream'], 'acceptance': info['acceptance'], 'attempt_selection': info['attempt_selection'],
            'search_box_points': len(box), 'processed_rows': len(table), 'status_counts': dict(Counter(r['status'] for r in table.values())),
            'accepted_rows': len(accepted), 'logical_exclusions_unmeasured': len(box - set(table)), 'missing_logical_candidates': 0,
            'best_accepted_objective': best, 'best_points': [list(p) for p, r in table.items() if number(r, 'objective') == best],
            'missing_timing_fields': {k: sum(number(r, k) is None for r in table.values()) for k in runner.TIMES}})
    return reports


def verify(directory):
    root = directory / 'reproduction'
    from build_ipopt_dfo_non_cstr import plan as original_design
    plan = runner.read(root / 'plan.json')
    require(plan == original_design() and len(plan) == 320, 'Plan differs from original settings/LHC procedure')
    require({p.name for p in (directory / 'jobs').iterdir()} == {s['job_id'] for s in plan}, 'Missing/extra job directory')
    require(runner.read(directory / 'availability.json') == {'data_errors': {}, 'environment_errors': {}}, 'Preflight errors')
    tables = {case: runner.load_table(root, case)[0] for case in runner.CASES}
    inputs = inspect_inputs(root, tables)
    targets = {r['case']: r['best_accepted_objective'] for r in inputs}
    original_rows = rows(directory / 'runs.csv')
    reported = {r['job_id']: r for r in original_rows}
    require(len(original_rows) == len(reported) == 320, 'Run report incomplete/duplicate')
    cpu = runner.read(directory / 'cpu_selection.json')
    selected = cpu['selected']['cpu']
    require(selected not in cpu['excluded_cpus'] and cpu['selected']['effective_cpus'] == [selected], 'CPU mismatch')
    callbacks, issues, metadata, audited, shared = [], [], [], [], {}
    auxiliary = Counter()
    for spec in plan:
        job = directory / 'jobs' / spec['job_id']
        require(runner.read(job / 'spec.json') == spec, 'Job spec changed')
        key = (spec['case'], spec['seed'])
        require(key not in shared or shared[key] == spec['starts'], 'Methods/budgets use different initial points')
        shared[key] = spec['starts']
        result, runtime = runner.read(job / 'result.json'), runner.read(job / 'runtime.json')
        settings, started = runner.read(job / 'actual_settings.json'), runner.read(job / 'started.json')
        require(runtime['host'] == 'dantzig.ecn.purdue.edu' and started['effective_cpu'] == [selected], 'Wrong host/CPU')
        require(all(runtime['versions'][k].split('+')[0] == v for k, v in runner.VERSIONS[spec['method']].items()), 'Version mismatch')
        events = strict_jsonl(job / 'callbacks.jsonl')
        require(3 <= len(events) <= spec['budget'] and result['callback_count'] == len(events), 'Recorded callback count mismatch')
        for index, event in enumerate(events, 1):
            validate_callback(event, spec, tables[spec['case']], index)
        validate_settings(spec, settings, events)
        require(all(a['elapsed_s'] <= b['elapsed_s'] for a, b in zip(events, events[1:])), 'Nonmonotonic callbacks')
        require(result['worker_returncode'] == 0 and result['watchdog_timeout'] is False, 'Worker interruption')
        require(0 <= sum(e['lookup_wall_s'] for e in events) <= result['dfo_wall_s'] <= result['worker_process_wall_s'], 'Invalid DFO clock')
        accepted = [e for e in events if e['accepted']]
        best = min(accepted, key=lambda e: e['raw_objective']) if accepted else None
        target = targets[spec['case']]
        hit = bool(best and abs(best['raw_objective'] - target) <= 1e-5 * max(1, abs(target)))
        if result['status'] == 'execution_failed':
            require(spec['job_id'] == 'column_B16_seed0_dsda' and not accepted and len(events) == 3
                    and result['error'] == 'RuntimeError: No accepted initial point; no reseeding', 'Unexpected execution failure')
        else:
            require(result['status'] in ('completed', 'budget_completed'), 'Unrecognized execution status')
        if result['status'] == 'budget_completed':
            require(len(events) == spec['budget'], 'Premature budget completion')
        category = 'execution_failed' if not best or result['status'] == 'execution_failed' else 'target_reached' if hit else 'target_not_reached'
        report = reported[spec['job_id']]
        require(report['category'] == category and int(report['callback_count']) == len(events), 'Reported category/count mismatch')
        require(number(report, 'best_accepted_objective') == (best['raw_objective'] if best else None)
                and number(report, 'table_accepted_minimum') == target, 'Reported objective mismatch')
        require(report['target_observed_even_if_execution_failed'] == str(hit), 'Reported target observation changed')
        missing = sum(e['selected_attempt_nlp_s'] is None for e in events)
        require(int(report['missing_nlp_times']) == missing and report['nlp_time_available'] == str(not missing), 'Missing cost masked')
        issue = budget_issue(spec, result, events)
        if issue:
            issues.append({**issue, 'original_category': category, 'target_observed_within_recorded_budget': hit})
        audited.append({**report, 'audit_category': 'execution_failed' if issue else category,
            'budget_audit': 'violation_evidenced' if issue else 'no_violation_observed',
            'actual_callbacks_lower_bound': len(events) + bool(issue),
            'unlogged_overrun_coordinates': None,
            'target_first_observed_callback': next((e['index'] for e in accepted if abs(e['raw_objective'] - target) <= 1e-5 * max(1, abs(target))), None)})
        callbacks.extend({'job_id': spec['job_id'], **e} for e in events)
        item = {'job_id': spec['job_id'], 'spec': spec, 'settings': settings, 'runtime': runtime, 'started': started, 'result': result}
        if (job / 'effective_rbfopt_settings.json').exists():
            item['effective_rbfopt_settings'] = runner.read(job / 'effective_rbfopt_settings.json')
        metadata.append(item)
        if (job / 'auxiliary_solver_calls.jsonl').exists():
            require(spec['method'] == 'rbfopt', 'Unexpected auxiliary audit')
            for event in strict_jsonl(job / 'auxiliary_solver_calls.jsonl'):
                require(event['solver'] in ('bonmin', 'ipopt'), 'Unexpected auxiliary solver')
                if event['event'] == 'start':
                    require(event['scope'] == 'RBFOpt surrogate only', 'Unexpected solver scope')
                auxiliary[(event['solver'], event['event'])] += 1
    require(len(shared) == 30, 'Incomplete shared design matrix')
    originals = {name: (directory / name).read_bytes() for name in TABLES}
    runner.summarize(directory)  # Reporting only, on the disposable extraction.
    for name, original in originals.items():
        require((directory / name).read_bytes() == original, 'Reconstructed server report differs: ' + name)
    grouped = defaultdict(list)
    for row in audited:
        grouped[(row['case'], int(row['budget']), row['method'])].append(row)
    groups = []
    for (case, budget, method), group in grouped.items():
        require(len(group) == 10 and {int(r['seed']) for r in group} == set(range(10)), 'Seed omitted/replaced')
        raw, reviewed = Counter(r['category'] for r in group), Counter(r['audit_category'] for r in group)
        values = [number(r, 'best_accepted_objective') for r in group if number(r, 'best_accepted_objective') is not None]
        groups.append({'case': case, 'budget': budget, 'method': method, 'denominator': 10,
            **{'original_' + k: raw[k] for k in CATEGORIES}, **{'audit_' + k: reviewed[k] for k in CATEGORIES},
            'budget_violation_runs': sum(r['budget_audit'] == 'violation_evidenced' for r in group),
            'best_objective_min': min(values) if values else None, 'best_objective_median': statistics.median(values) if values else None,
            'objective_available_runs': len(values), 'recorded_callbacks_min': min(int(r['callback_count']) for r in group),
            'recorded_callbacks_max': max(int(r['callback_count']) for r in group),
            'recorded_callbacks_mean': statistics.mean(int(r['callback_count']) for r in group),
            'dfo_wall_s_median': statistics.median(float(r['dfo_wall_s']) for r in group),
            'dfo_wall_s_sum': sum(float(r['dfo_wall_s']) for r in group),
            'nlp_time_complete_recorded_runs': sum(r['nlp_time_available'] == 'True' for r in group)})
    audit = {'slots': len(plan), 'original_categories': dict(Counter(r['category'] for r in audited)),
        'audit_categories': dict(Counter(r['audit_category'] for r in audited)),
        'recorded_callbacks': len(callbacks), 'actual_callbacks_lower_bound': len(callbacks) + len(issues), 'actual_callbacks_exact': None,
        'budget_protocol_pass': False if issues else None, 'budget_violation_runs': len(issues),
        'callback_states': dict(Counter(e['evaluation_state'] for e in callbacks)),
        'source_status_counts': dict(Counter(e['source_row']['status'] if e['source_row'] else 'no_measured_row' for e in callbacks)),
        'terminal_values_logged_not_returned': sum(e['callback_exit'] == 'budget_stop' for e in callbacks),
        'same_row_objectives_statuses_and_times_verified': True, 'original_LHC_shared_initial_designs_verified': True,
        'server_reports_exactly_reproduced': list(TABLES), 'cpu': cpu,
        'auxiliary_solver_events': {f'{s}:{e}': n for (s, e), n in auxiliary.items()},
        'nlp_time_complete_recorded_runs': sum(r['nlp_time_available'] == 'True' for r in audited),
        'local_optimizer_or_solver_calls': 0, 'local_timings_used': False,
        'audit_policy': 'Original tables remain unchanged. Eight proven overrun runs are execution_failed only in separate audited outputs; no seed exclusion/replacement.',
        'callback_limitations': 'Guard executes before logging. At least one extra invocation is proven for each flagged run. Exact extra counts/coordinates cannot be recovered. No evidence of extra CSV reads or values.',
        'metric_scope': 'Group objective statistics include every recorded accepted best, including protocol-failed runs. Never substitute those observations for audited success counts.',
        'timing_scope': 'DFO wall time includes surrogate work. Same-row historical NLP totals are separate; unmeasured logical exclusions stay unknown. Dynamic preparation is separate.',
        'comparison_scope': 'This audit does not establish a causal BARON-versus-IPOPT success-rate comparison or certify every callback was logged.'}
    return audit, issues, metadata, inputs, audited, groups


def readme(audit, inputs, groups):
    lines = ['Non-CSTR IPOPT DFO return audit, 2026-10-15', '',
        'Original report: 320 slots; 190 target_reached, 129 target_not_reached, 1 execution_failed, 0 not_run.',
        'Separate protocol audit: 184 target_reached, 127 target_not_reached, 9 execution_failed, 0 not_run.',
        'Column B16 seed0 DSDA failed after three unaccepted starts: [8,3], [15,9], [10,4].',
        'It was retained; seed0 was not replaced with seed10.', '',
        'IMPORTANT: Eight Dynamic BAM runs requested a callback after B:',
        'B30 seeds1,4,7,9; B37 seed7; B50 seeds4,6,8.',
        'The older non-CSTR guard raised before recording these calls. The worker',
        'then labeled them budget_completed. Six had already observed the table',
        'minimum within B. Their original records remain unchanged, while separate',
        'audit categories flag protocol failure. No new objective was read/returned',
        'for the blocked calls. Their coordinates and exact count are unknown.',
        '7058 callbacks are logged; at least 7066 were requested. This is not a',
        'fully documented, budget-compliant 320-run benchmark. IPOPT rejection',
        'and the BAM runner/backend exception interaction are distinct issues.', '',
        'Counts per ten seeds (original hits/misses/failures -> audit hits/misses/failures):']
    for g in groups:
        raw = '/'.join(str(g['original_' + k]) for k in CATEGORIES[:3])
        checked = '/'.join(str(g['audit_' + k]) for k in CATEGORIES[:3])
        lines.append(f"  {g['case']} B={g['budget']} {g['method']}: {raw} -> {checked}")
    lines += ['', 'Input IPOPT table minima (reporting targets, not GDP global optima):']
    for r in inputs:
        lines.append(f"  {r['case']}: {r['best_accepted_objective']:.12g} at {r['best_points']}; "
                     f"{r['accepted_rows']}/{r['processed_rows']} accepted; statuses {r['status_counts']}; "
                     f"{r['logical_exclusions_unmeasured']} unmeasured logical exclusions in the search box.")
    lines += ['',
        'RBFOpt reaches the Dynamic target in 9/10 runs at B12 and 10/10 at B15+',
        'and DSDA in 10/10 at B30+. Small Batch favors DSDA (8/10) in this return.',
        'Column has lower hit rates (RBFOpt4, BAM0, DSDA5, FMQA4 out of10).',
        'These observations alone do not isolate the effect of changing BARON to IPOPT.', '',
        'Input provenance: Column and Small Batch use SECQUOIA/dsda-gdp at',
        '3e469dbeea8931670b8cd6752014ab7a767d3af5 and the upstream saved initializations.',
        'Dynamic uses SECQUOIA/LD-SDA-Dynamic at 482e14ebf9caabbd35d959986942cb028778a1d7',
        'with constructor defaults, 9 stages, nfe30/ncp3 LAGRANGE-RADAU.',
        'All logical candidates are processed; no missing candidate became infeasible.',
        'Column retains 7 rejected rows, 28 preprocessing_infeasible rows and 29 accepted rows.',
        'Raw candidate objectives, termination, solver statuses and reasons remain in source_row.',
        'Penalties: RBFOpt/DSDA 1e6; BAM NaN; FMQA callback +inf (reporting penalty1e6).',
        'Rejected is an unaccepted evaluation, not a proof of global infeasibility.', '',
        'Recorded NLP cost is complete for 9/40 Column runs, 2/240 Dynamic runs,',
        'and all40 Small Batch runs. The missing costs are unmeasured logical',
        'exclusions, not zero-duration NLP solves. Total cost for affected runs is',
        'unavailable. Preprocessing-only records may lack setup/preprocess split',
        'despite having measured total time. Dynamic one-time preparation cost',
        '(0.1090063113s) is preserved separately. No missing times are zero-filled.',
        'DFO wall time includes surrogate/candidate work and is separate from NLP',
        'historical cost and CSV lookup time. Every input has one selected attempt.',
        'Callback B is recorded but raises BudgetStop without delivering its value.',
        'Reported best is the best accepted ledger observation, including callback B.',
        'Target rule: abs(best-table_min) <= 1e-5*max(1,abs(table_min)); reporting only.', '',
        'Verification: ZIP CRC; exact submitted/reproduced package and input hashes;',
        'CSV versus raw attempt records; every logged callback and same-attempt',
        'cost; original LHC design; seeds0..9; actual settings and environment;',
        'four server reports reproduced byte-for-byte. CPU0/sibling48 was used.',
        'RBFOpt auxiliary exceptions are retained and are not process NLP failures.',
        'No optimizer/process solver/enumeration was run locally during this import.', '',
        'Original files: runs.csv, summary.csv/json, callbacks.csv.gz (lossless).',
        'Audit: audited_runs.csv, analysis_groups.csv/json, budget_control_issues.csv/json,',
        'inputs_report.csv/json, audit.json. Job specs/settings/runtime/results are',
        'in job_metadata.json; frozen inputs and per-attempt records are in inputs/.',
        'All original per-job paths, logs, proposals, evidence and executable',
        'snapshots remain in the full return archive:',
        f"  {audit['archive']}", f"  SHA256 {RETURN_SHA256}",
        'Archive and compact-export SHA256 inventories are included.', '',
        'Reproduce into a new directory (no optimizer calls):',
        f"  .venv/bin/python scripts/import_ipopt_dfo_non_cstr.py {audit['archive']} --output /tmp/non_cstr_dfo_verified_import", '',
        'Before a clean BAM comparison, review the callback stop/exception handling',
        'and rerun affected slots under the same input/settings/seeds if authorized.',
        'The submitted runner remains exactly as executed; no repair/rerun is applied.',
        'Existing CSTR and publication results are unchanged.']
    return '\n'.join(lines) + '\n'


def build(archive, output):
    archive, output = Path(archive).resolve(), Path(output).resolve()
    require(not output.exists(), 'Refusing to overwrite existing results')
    with tempfile.TemporaryDirectory(prefix='non-cstr-dfo-import-') as temporary:
        directory, hashes, count = extract_verified(archive, Path(temporary))
        audit, issues, metadata, inputs, audited, groups = verify(directory)
        audit.update(archive=f'results/archives/{archive.name}', archive_sha256=RETURN_SHA256,
                     original_download=str(archive), archive_crc_pass=True, archive_members=len(hashes),
                     submitted_package=str(PACKAGE.relative_to(ROOT)), submitted_package_sha256=PACKAGE_SHA256,
                     byte_identical_reproduction_files=count, importer_sha256=runner.sha(__file__))
        stage = Path(temporary) / 'import'
        stage.mkdir()
        for name in (*TABLES, 'run.json', 'availability.json', 'cpu_selection.json'):
            if name == 'callbacks.csv':
                (stage / 'callbacks.csv.gz').write_bytes(gzip.compress((directory / name).read_bytes(), mtime=0))
            else:
                shutil.copyfile(directory / name, stage / name)
        for path in directory.glob('preflight_*.json'):
            shutil.copyfile(path, stage / path.name)
        shutil.copytree(directory / 'reproduction/inputs', stage / 'inputs')
        for name, value in [('audit', audit), ('archive_members_sha256', hashes), ('job_metadata', metadata),
                            ('budget_control_issues', issues), ('inputs_report', inputs), ('analysis_groups', groups)]:
            runner.write(stage / f'{name}.json', value)
        for name, value in [('budget_control_issues', issues), ('inputs_report', inputs),
                            ('analysis_groups', groups), ('audited_runs', audited)]:
            runner.write_csv(stage / f'{name}.csv', value)
        (stage / 'README.txt').write_text(readme(audit, inputs, groups))
        runner.write(stage / 'import_files_sha256.json', {
            p.relative_to(stage).as_posix(): runner.sha(p) for p in sorted(stage.rglob('*')) if p.is_file()})
        dest = ROOT / 'results/archives' / archive.name
        require(not dest.exists() or runner.sha(dest) == RETURN_SHA256, 'Existing archive differs')
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copyfile(archive, dest)
        dest.with_suffix('.zip.sha256').write_text(f'{RETURN_SHA256}  {archive.name}\n')
        shutil.copytree(stage, output)
    print(json.dumps({k: audit[k] for k in ('slots', 'original_categories', 'audit_categories', 'recorded_callbacks',
                                         'actual_callbacks_lower_bound', 'budget_violation_runs')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'results' / RETURN_NAME)
    args = parser.parse_args()
    build(args.archive, args.output)
