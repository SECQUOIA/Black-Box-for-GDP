"""Verify and archive the CSTR DFO return without running any optimizer/solver."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ipopt_dfo_cstr as runner  # Standard-library validation/reporting only.

RETURN_SHA256 = 'b91afb707229766adcdcfb1ee67406377d1d2ef44839b062ec9e0539893bfefa'
PACKAGE = ROOT / 'results/runners/ipopt_dfo_cstr_20261015.zip'
PACKAGE_SHA256 = '79a093ca026f4fe96650b21e73f49763db9a48d9514ec7dd9b654f515cc066d4'
RETURN_NAME = 'ipopt_dfo_cstr_20261015_174637_r1dzn5tk'
TABLES = ('runs.csv', 'callbacks.csv', 'summary.csv', 'summary.json', 'inputs_report.csv', 'inputs_report.json')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def rows(path):
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(stream))


def strict_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def number(row, field):
    return float(row[field]) if row and row.get(field) else None


def validate_callback(event, spec, table, index):
    """Check raw values, failures and same-attempt costs independently of the report."""
    point = tuple(event['point'])
    require(event['index'] == index and event['cstr_size'] == spec['cstr_size'], 'Callback order/size mismatch')
    require(len(point) == 2 and all(type(x) is int and 1 <= x <= spec['cstr_size'] for x in point), 'Invalid coordinate')
    require(tuple(int(round(x)) for x in event['callback_coordinates']) == point, 'Coordinate mapping mismatch')
    require(event['phase'] == ('initial' if index <= 3 else 'adaptive'), 'Callback phase mismatch')
    if index <= 3:
        require(list(point) == spec['starts'][index - 1], 'Shared initial order changed')
    overrun = index > spec['budget']
    require(event['budget_overrun'] is overrun, 'Budget overrun flag mismatch')
    source = None if overrun else table.get(point)
    require(event['source_row'] == source, 'Callback source differs from exact size/coordinate CSV row')
    if not overrun and source is None:
        require(point[1] > point[0], 'Missing logical candidate was used')
    accepted = bool(source and source['accepted'] == 'True')
    require(event['accepted'] is accepted, 'Acceptance mismatch')
    value = number(source, 'objective') if accepted else None
    require(event['raw_objective'] == value and event['method_value'] == value, 'Objective or penalty mismatch')
    require(event['raw_candidate_objective'] == number(source, 'candidate_objective'), 'Candidate value mismatch')
    kind = 'finite' if accepted else 'nan' if spec['method'] == 'bam' else '+inf'
    require(event['method_value_kind'] == kind, 'Method failure representation changed')
    expected_state = ('invalid_callback' if overrun else 'accepted' if accepted else
                      'evaluated_unaccepted' if source else 'logical_exclusion_unmeasured')
    require(event['evaluation_state'] == expected_state, 'Evaluation state mismatch')
    terminal_stop = index == spec['budget'] and not runner.bam_native_budget(spec)
    expected_exit = 'protocol_error' if overrun else 'budget_stop' if terminal_stop else 'return'
    require(event['callback_exit'] == expected_exit, 'Callback exit mismatch')
    require(event['value_returned_to_optimizer'] is (index <= spec['budget'] and not terminal_stop), 'Delivered-value flag mismatch')
    require(event['selected_attempt'] == (1 if source else None)
            and event['available_attempts'] == (1 if source else 0), 'Unexpected retry selection')
    for field in ('selected_attempt_nlp_s', 'all_attempts_nlp_s'):
        require(event[field] == number(source, 'total_wall_s'), 'NLP cost is not from the selected row')
    require(event['nlp_times'] == {field: number(source, field) for field in runner.TIMES}, 'NLP timing breakdown mismatch')
    if overrun:
        require('callback beyond B' in event['failure_reason'], 'Missing overrun reason')
    elif accepted:
        require(event['failure_reason'] is None, 'Accepted callback has failure reason')
    else:
        expected = runner.failure_reason(source) if source else 'logical_exclusion_unmeasured'
        require(event['failure_reason'] == expected, 'Original failure reason changed')
    require(event['fmqa_reporting_penalty'] == (1e6 if spec['method'] == 'fmqa_sa' and not accepted else None),
            'FMQA reporting penalty mismatch')
    for field in ('lookup_wall_s', 'elapsed_s'):
        require(math.isfinite(event[field]) and event[field] >= 0, 'Invalid callback clock')


def validate_settings(spec, settings, events):
    method, budget = spec['method'], spec['budget']
    if method == 'rbfopt':
        expected = {**spec['settings'], 'max_evaluations': budget, 'rand_seed': spec['seed'], 'target_objval': -1e10}
        require(all(settings[k] == v for k, v in expected.items()), 'RBFOpt options/target changed')
    elif method == 'bam':
        if runner.bam_native_budget(spec):
            require(settings.get('budget_stop_policy') == spec['settings']['budget_stop_policy'],
                    'BAM budget-stop policy mismatch')
        options = settings['options']
        require(options['max_evals'] == budget - 3 and options['x_evaluated'] == spec['starts'], 'BAM design/budget changed')
        require(options['f_evaluated'] == [e['raw_objective'] for e in events[:3]], 'BAM initial objectives changed')
        require(settings['x0'] is None and settings['integrality'] == [1, 1]
                and settings['python_numpy_seed'] == spec['seed'], 'BAM configuration changed')
    elif method == 'dsda':
        require(settings == {**spec['settings'], 'max_points_explored': budget - 3}, 'DSDA configuration changed')
    else:
        require(all(settings[k] == v for k, v in spec['settings'].items()), 'FMQA options changed')
        require(settings['torch'] == {'device': 'cpu', 'dtype': 'float32', 'threads': 1,
                'interop_threads': 1, 'deterministic_algorithms': True}, 'FMQA CPU settings changed')


def extract_verified(archive, temporary):
    require(runner.sha(archive) == RETURN_SHA256, 'Unexpected return archive hash')
    require(runner.sha(PACKAGE) == PACKAGE_SHA256, 'Original submitted package changed')
    checks = {}
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None, 'Archive CRC failure')
        for member in z.infolist():
            path = PurePosixPath(member.filename)
            require(not path.is_absolute() and '..' not in path.parts and path.parts[0] == RETURN_NAME,
                    'Unsafe/unexpected archive path')
            require(not stat.S_ISLNK(member.external_attr >> 16), 'Archive symlink not allowed')
            if member.is_dir():
                continue
            name = '/'.join(path.parts[1:])
            require(name not in checks, 'Duplicate archive member')
            data = z.read(member)
            checks[name] = hashlib.sha256(data).hexdigest()
            target = temporary / RETURN_NAME / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    directory = temporary / RETURN_NAME
    reproduction = directory / 'reproduction'
    with zipfile.ZipFile(PACKAGE) as package:
        names = set()
        for name in package.namelist():
            if name.endswith('/'):
                continue
            relative = name.removeprefix('ipopt_dfo_cstr_runner/')
            names.add(relative)
            require((reproduction / relative).read_bytes() == package.read(name), 'Executed package/input changed: ' + relative)
        require(names == {p.relative_to(reproduction).as_posix() for p in reproduction.rglob('*') if p.is_file()},
                'Extra/missing reproduction files')
    runner.verify_inventory(reproduction)
    # The pinned package above authenticates historical source bytes; current
    # validation helpers need not be byte-identical to that frozen runner.
    run = runner.read(directory / 'run.json')
    require(run['bundle_inventory_sha256'] == runner.sha(reproduction / 'SHA256SUMS'), 'Run inventory mismatch')
    return directory, checks, len(names)


def verify(directory):
    root = directory / 'reproduction'
    plan = runner.read(root / 'plan.json')
    require(len(plan) == 240 and len({s['job_id'] for s in plan}) == 240, 'Incorrect plan size')
    require({(s['cstr_size'], s['budget']) for s in plan} == set(runner.BUDGETS.items()), 'Incorrect sizes/budgets')
    require({p.name for p in (directory / 'jobs').iterdir()} == {s['job_id'] for s in plan}, 'Missing/extra job directories')
    require(runner.read(directory / 'availability.json') == {'data_errors': {}, 'environment_errors': {}}, 'Preflight errors')
    tables = {case: runner.load_table(root, case)[0] for case in runner.CASES}
    targets = {case: min(float(r['objective']) for r in table.values() if r['accepted'] == 'True') for case, table in tables.items()}
    reported = {r['job_id']: r for r in rows(directory / 'runs.csv')}
    require(len(reported) == 240, 'Run summary incomplete')
    cpu = runner.read(directory / 'cpu_selection.json')
    selected = cpu['selected']['cpu']
    require(selected not in cpu['excluded_cpus'] and cpu['selected']['effective_cpus'] == [selected], 'CPU overlap')
    require(not set(map(int, cpu['selected']['thread_siblings_list'].split(','))) & set(cpu['excluded_cpus']), 'Physical-core overlap')
    shared = {}
    callbacks, issues, metadata = [], [], []
    categories, auxiliary, statuses = Counter(), Counter(), Counter()
    for spec in plan:
        job = directory / 'jobs' / spec['job_id']
        require(runner.read(job / 'spec.json') == spec, 'Job spec changed')
        require(spec['lower'] == [1, 1] and spec['upper'] == [spec['cstr_size']] * 2, 'Wrong bounds')
        key = (spec['cstr_size'], spec['seed'])
        if key in shared:
            require(shared[key] == spec['starts'], 'Methods used different initial points')
        shared[key] = spec['starts']
        require(0 <= spec['seed'] <= 9 and len(spec['starts']) == 3 and 'target' not in spec, 'Invalid seed/design')
        result, runtime = runner.read(job / 'result.json'), runner.read(job / 'runtime.json')
        started, settings = runner.read(job / 'started.json'), runner.read(job / 'actual_settings.json')
        require(runtime['host'] == 'dantzig.ecn.purdue.edu' and started['effective_cpu'] == [selected], 'Wrong host/CPU')
        require(all(runtime['versions'][k].split('+')[0] == v for k, v in runner.VERSIONS[spec['method']].items()), 'Environment mismatch')
        events = strict_jsonl(job / 'callbacks.jsonl')
        require(len(events) >= 3 and result['callback_count'] == len(events), 'Callback count mismatch')
        for index, event in enumerate(events, 1):
            validate_callback(event, spec, tables[spec['case']], index)
        require(all(a['elapsed_s'] <= b['elapsed_s'] for a, b in zip(events, events[1:])), 'Nonmonotonic callbacks')
        validate_settings(spec, settings, events)
        require(result['worker_returncode'] == 0 and result['watchdog_timeout'] is False, 'Worker interruption')
        require(0 <= sum(e['lookup_wall_s'] for e in events) <= result['dfo_wall_s'] <= result['worker_process_wall_s'], 'Invalid DFO clock')
        over = [e for e in events if e['budget_overrun']]
        if over:
            require(spec['method'] == 'bam' and len(over) == 1 and len(events) == spec['budget'] + 1,
                    'Unrecognized budget violation')
            require(result['status'] == 'execution_failed' and result['error'] ==
                    'Backend continued after hard budget stop; all callback attempts preserved', 'Overrun hidden as success')
            issues.append({'job_id': spec['job_id'], 'cstr_size': spec['cstr_size'], 'seed': spec['seed'],
                'budget': spec['budget'], 'recorded_callbacks': len(events), 'overrun_index': over[0]['index'],
                'overrun_point': over[0]['point'], 'overrun_csv_read': False, 'overrun_value_delivered': False,
                'classification': 'execution_failed', 'cause_scope': 'DFO runner/backend budget-stop handling, not IPOPT rejection'})
        else:
            require(result['status'] in ('completed', 'budget_completed') and len(events) <= spec['budget'], 'Unexpected execution status')
            if result['status'] == 'budget_completed':
                require(len(events) == spec['budget'], 'Premature budget completion')
        accepted = [e for e in events if e['accepted']]
        best = min(accepted, key=lambda e: e['raw_objective']) if accepted else None
        target = targets[spec['case']]
        hit = bool(best and abs(best['raw_objective'] - target) <= 1e-5 * max(1, abs(target)))
        category = 'execution_failed' if over or not best else 'target_reached' if hit else 'target_not_reached'
        report = reported[spec['job_id']]
        require(report['category'] == category and int(report['callback_count']) == len(events), 'Reported category/count differs')
        require(number(report, 'best_accepted_objective') == (best['raw_objective'] if best else None)
                and number(report, 'table_accepted_minimum') == target, 'Reported objective differs')
        require(report['target_observed_even_if_execution_failed'] == str(hit), 'Target observation hidden/changed')
        missing = sum(e['selected_attempt_nlp_s'] is None for e in events)
        require(int(report['missing_nlp_times']) == missing and report['nlp_time_available'] == str(not missing), 'Missing cost masked')
        categories[category] += 1
        statuses[result['status']] += 1
        callbacks.extend({'job_id': spec['job_id'], **e} for e in events)
        metadata.append({'job_id': spec['job_id'], 'spec': spec, 'settings': settings, 'runtime': runtime,
                         'started': started, 'result': result})
        audit_path = job / 'auxiliary_solver_calls.jsonl'
        if audit_path.exists():
            require(spec['method'] == 'rbfopt', 'Unexpected auxiliary audit')
            for event in strict_jsonl(audit_path):
                require(event['solver'] in ('bonmin', 'ipopt'), 'Unexpected auxiliary solver')
                if event['event'] == 'start':
                    require(event['scope'] == 'RBFOpt surrogate only', 'Unexpected solver scope')
                auxiliary[(event['solver'], event['event'])] += 1
    require(len(shared) == 60, 'Incomplete size/seed matrix')
    # Independently checked ledger above; regenerate six server tables in the
    # disposable extraction only, then require exact byte agreement.
    originals = {name: (directory / name).read_bytes() for name in TABLES}
    runner.summarize(directory)
    for name, original in originals.items():
        require((directory / name).read_bytes() == original, 'Reconstructed server table differs: ' + name)
    audit = {'slots': len(plan), 'all_slots_processed': True, 'categories': dict(categories), 'execution_statuses': dict(statuses),
        'callbacks': len(callbacks), 'callbacks_within_budget': sum(not e['budget_overrun'] for e in callbacks),
        'budget_protocol_pass': not issues, 'budget_overrun_runs': len(issues), 'budget_overrun_callbacks': sum(e['budget_overrun'] for e in callbacks),
        'callback_states': dict(Counter(e['evaluation_state'] for e in callbacks)),
        'terminal_values_logged_not_returned': sum(e['callback_exit'] == 'budget_stop' for e in callbacks),
        'same_row_objectives_statuses_and_times_verified': True, 'ordered_shared_initial_designs_verified': True,
        'server_tables_exactly_reproduced': list(TABLES), 'cpu': cpu,
        'auxiliary_solver_events': {f'{solver}:{event}': count for (solver, event), count in auxiliary.items()},
        'local_optimizer_or_solver_calls': 0, 'local_timings_used': False,
        'issue_policy': 'Keep all 19 failed BAM attempts and B+1 callback records. Do not relabel, truncate, exclude or replace seeds.',
        'interpretation': '240 returned slots; 221 within the callback budget, 19 BAM budget-control failures. Not a clean 240-run budget-compliant benchmark.',
        'time_limitations': 'N30 y>x costs were never measured; overrun callbacks did not read CSV or deliver values. Missing cost stays null.',
        'process_solver_calls': 'No process solver entry point in the exact submitted DFO package; auxiliary surrogate solves retained.'}
    return audit, issues, metadata


def build(archive, output):
    archive, output = Path(archive).resolve(), Path(output).resolve()
    require(not output.exists(), 'Refusing to overwrite an existing import directory')
    with tempfile.TemporaryDirectory(prefix='cstr-dfo-import-') as temporary:
        directory, hashes, source_count = extract_verified(archive, Path(temporary))
        audit, issues, metadata = verify(directory)
        audit.update(archive=f'results/archives/{archive.name}', archive_sha256=RETURN_SHA256,
                     original_download=str(archive), archive_crc_pass=True, archive_members=len(hashes),
                     submitted_package=str(PACKAGE.relative_to(ROOT)), submitted_package_sha256=PACKAGE_SHA256,
                     byte_identical_reproduction_files=source_count, importer_sha256=runner.sha(__file__))
        stage = Path(temporary) / 'import'
        stage.mkdir()
        for name in (*TABLES, 'run.json', 'availability.json', 'cpu_selection.json'):
            if name == 'callbacks.csv':
                (stage / 'callbacks.csv.gz').write_bytes(gzip.compress((directory / name).read_bytes(), mtime=0))
            else:
                shutil.copyfile(directory / name, stage / name)
        for p in directory.glob('preflight_*.json'):
            shutil.copyfile(p, stage / p.name)
        for case in runner.CASES:
            original = directory / 'reproduction/inputs' / case
            for p in original.iterdir():
                if p.is_file():
                    dest = stage / 'inputs' / case / p.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(p, dest)
        runner.write(stage / 'audit.json', audit)
        runner.write(stage / 'archive_members_sha256.json', hashes)
        runner.write(stage / 'job_metadata.json', metadata)
        runner.write_csv(stage / 'budget_control_failures.csv', issues)
        runner.write(stage / 'budget_control_failures.json', issues)
        (stage / 'README.txt').write_text(readme(audit, runner.read(directory / 'summary.json')['groups']))
        export_hashes = {p.relative_to(stage).as_posix(): runner.sha(p) for p in sorted(stage.rglob('*')) if p.is_file()}
        runner.write(stage / 'import_files_sha256.json', export_hashes)
        dest_archive = ROOT / 'results/archives' / archive.name
        require(not dest_archive.exists() or runner.sha(dest_archive) == RETURN_SHA256, 'Existing archive differs')
        if not dest_archive.exists():
            shutil.copyfile(archive, dest_archive)
        dest_archive.with_suffix('.zip.sha256').write_text(f'{RETURN_SHA256}  {archive.name}\n')
        shutil.copytree(stage, output)
    print(json.dumps({k: audit[k] for k in ('archive_sha256', 'slots', 'categories', 'callbacks', 'budget_protocol_pass', 'budget_overrun_runs')}, indent=2))


def readme(audit, groups):
    lines = [
        'Verified CSTR-only IPOPT DFO return, 2026-10-15', '',
        '240 slots returned: 97 target_reached, 124 target_not_reached, 19 execution_failed, 0 not_run.',
        'IMPORTANT: All 19 execution failures are BAM budget-control failures.',
        'N20: seeds2,6; N25: all ten seeds; N30: seeds0,2,3,4,5,7,9.',
        'Each has one recorded B+1 callback after callback B raised BudgetStop.',
        'The B+1 request is retained as a protocol error; its CSV row was not read',
        'and no value was delivered. These failures are separate from IPOPT rejections.',
        'Do not use them as evidence that IPOPT objectives degraded BAM performance.',
        'The original returned classification and ten-seed denominators are unchanged.',
        'This return is not a fully budget-compliant 240-run benchmark. Further BAM',
        'experiments require reviewing the runner/backend stop interaction first.', '',
        'Counts per ten seeds (hit / miss / execution failure / not run):']
    for g in groups:
        lines.append(f"  {g['case']} B={g['budget']} {g['method']}: " + ' / '.join(str(g[k]) for k in ('target_reached', 'target_not_reached', 'execution_failed', 'not_run')))
    lines += ['',
        'Input/source integrity: return ZIP CRC passed; all reproduction files exactly',
        'match the submitted package (including all frozen IPOPT records and sources).',
        'All callbacks were checked against the exact size/coordinate/attempt row.',
        'Six returned aggregate/report files were reproduced byte for byte.',
        '5783 callback attempts are preserved: 5764 within budget and 19 overruns.',
        'N5..25 use mass_balance_zero_recycle; N30 uses constructor defaults.',
        'N10 [10,1] and seven original N30 solver rejections remain unchanged.',
        'CSTR ran on CPU1 (physical sibling49), excluding non-CSTR CPUs0/48.', '',
        'Timing: DFO clocks are measured server method time, including learning and',
        'candidate/auxiliary solves. Historical NLP time comes from the same CSV row.',
        'N30 unmeasured logical exclusions and protocol-error callbacks have unknown',
        'NLP cost. No missing cost was zero-filled or borrowed from another model.',
        'Callback B is in the ledger but raises BudgetStop without returning a value.',
        'Final best/target observation uses the ledger, as in the supplied protocol.',
        'RBFOpt auxiliary exceptions remain in raw logs; they are not process NLP failures.', '',
        'Files: runs.csv (240 slots), summary.csv/json (24 groups), inputs_report.csv/json,',
        'callbacks.csv.gz (lossless original aggregate), job_metadata.json (all specs,',
        'actual settings, runtimes, start clocks and results), inputs/ (original CSVs',
        'and provenance), budget_control_failures.csv/json, audit.json and hash inventories.',
        'All original per-job callback paths, solver logs, FMQA proposals, per-point',
        'IPOPT JSON records and executable snapshots remain in the full archive:',
        f"  {audit['archive']}", f"  SHA256 {audit['archive_sha256']}",
        'The inputs/ provenance inventories include raw records retained in that archive.',
        'Existing publication results and non-CSTR files were not replaced.',
        'No local optimizer, process NLP solve or enumeration was executed during import.', '',
        'Reproduce the verification/import into a new directory:',
        f"  python3 scripts/import_ipopt_dfo_cstr.py {audit['archive']} --output /tmp/cstr_dfo_verified_import", '',
        'The submitted CSTR runner/package is preserved exactly as executed, including',
        'the known BAM stop-handling issue. No post-hoc solver/code repair is applied.',
    ]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'results' / RETURN_NAME)
    args = parser.parse_args()
    build(args.archive, args.output)
