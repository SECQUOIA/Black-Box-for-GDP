"""CSTR-only finite-penalty experiment; archived primary paths and starts."""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from functools import lru_cache
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

import ipopt_dfo_cstr as core

ROOT = Path(__file__).resolve().parent
THREADS = {k: '1' for k in ('OMP_NUM_THREADS', 'OMP_THREAD_LIMIT', 'OPENBLAS_NUM_THREADS',
    'MKL_NUM_THREADS', 'BLIS_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')}
THREADS.update(OMP_DYNAMIC='FALSE', MKL_DYNAMIC='FALSE')


def rows(path):
    import csv
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(stream))


def check(root):
    core.verify_inventory(root)
    plan = core.read(root / 'plan.json')
    expected = {(f'cstr_{n}', b, s, m) for n, b in core.BUDGETS.items()
                for s in range(10) for m in ('dsda', 'rbfopt')}
    actual = {(j['spec']['case'], j['spec']['budget'], j['spec']['seed'], j['spec']['method']) for j in plan}
    if actual != expected or len(plan) != 120:
        raise ValueError('Expected exactly the authorized 120 slots')
    report = []
    for case in core.CASES:
        table, _ = core.load_table(root, case)
        vals = [float(r['objective']) for r in table.values() if r['accepted'] == 'True']
        if max(vals) >= 1e6:
            raise ValueError(f'Penalty conflicts with accepted objective: {case}')
        costs = cost_table(root, case)
        report.append({'case': case, 'accepted_maximum': max(vals), 'target': min(vals),
                       'lookup_rows': len(table), 'cost_rows': len(costs)})
    for job in plan:
        spec = job['spec']
        if spec['unaccepted_response'] != 1e6:
            raise ValueError('Frozen experiment must use 1e6')
        events = core.jsonl(root / 'baseline' / spec['job_id'] / 'callbacks.jsonl')
        if spec['starts'] != [e['point'] for e in events[:3]]:
            raise ValueError('Archived initial sequence changed')
    return {'planned_runs': 120, 'methods': ['dsda', 'rbfopt'], 'input_report': report,
            'server_runtime_checked': False, 'optimization_performed': False}


@lru_cache(maxsize=24)
def lookup_table(root, case):
    return core.load_table(root, case)


@lru_cache(maxsize=24)
def cost_table(root, case):
    data = rows(root / 'data' / f'cost_table_{case}.csv')
    out = {}
    for r in data:
        n = int(case.split('_')[1])
        if r.get('case') not in ('cstr', case) or int(r['cstr_size']) != n:
            raise ValueError('Point cost model/size mismatch')
        key = ('cstr', n, tuple(json.loads(r['point'])))
        if key in out:
            raise ValueError('Duplicate point cost key')
        out[key] = r
    return out


def metrics(root, spec, events, result):
    charged = [e for e in events if e['index'] <= spec['budget'] and not e.get('budget_overrun')]
    accepted = [e for e in charged if e['accepted']]
    best = min(accepted, key=lambda e: e['raw_objective']) if accepted else None
    table, _ = lookup_table(root, spec['case'])
    target = min(float(r['objective']) for r in table.values() if r['accepted'] == 'True')
    hits = [e for e in accepted if abs(e['raw_objective'] - target) <= 1e-5 * max(1, abs(target))]
    status = result.get('status', 'not_run')
    failure = status not in ('completed', 'budget_completed', 'not_run') or (status != 'not_run' and not best)
    failure = failure or len(events) > spec['budget'] or any(e.get('budget_overrun') for e in events)
    failure = failure or [e['point'] for e in events[:3]] != spec['starts'][:min(3, len(events))]
    category = 'not_run' if status == 'not_run' else 'execution_failed' if failure else 'target_reached' if hits else 'target_not_reached'
    costs, ledger, missing = cost_table(root, spec['case']), [], []
    for e in charged:
        key = ('cstr', spec['cstr_size'], tuple(e['point']))
        row = costs.get(key)
        cost = float(row['total_wall_s']) if row and row.get('total_wall_s') else None
        if cost is not None and (not math.isfinite(cost) or cost < 0):
            raise ValueError('Invalid historical point cost')
        if row and e['accepted'] and (row['accepted'] != 'True' or float(row['objective']) != e['raw_objective']):
            raise ValueError('Cost/accepted objective mismatch')
        if cost is None:
            missing.append(list(key[:2]) + [list(key[2])])
        ledger.append({**e, 'cost_key': list(key[:2]) + [list(key[2])],
                       'historical_point_cost_s': cost, 'point_cost_source': row,
                       'repeated_point': any(p['point'] == e['point'] for p in ledger)})
    wall = result.get('recorded_search_wall_s', result.get('dfo_wall_s'))
    lookup = sum(e['lookup_wall_s'] for e in events)
    retained = wall - lookup if wall is not None else None
    total = sum(e['historical_point_cost_s'] for e in ledger) if ledger and not missing else None
    return {'status': status, 'category': category, 'execution_failure': category == 'execution_failed',
            'error': result.get('error'), 'best_accepted_objective': best['raw_objective'] if best else None,
            'best_point': best['point'] if best else None, 'target': target,
            'target_hit': category == 'target_reached', 'target_observed_even_if_failed': bool(hits),
            'first_target_evaluation': hits[0]['index'] if hits else None,
            'charged_evaluations': len(charged), 'callback_attempts': len(events),
            'accepted_evaluations': len(accepted), 'unaccepted_evaluations': len(charged) - len(accepted),
            'measured_search_s': wall, 'lookup_s': lookup, 'retained_search_s': retained,
            'point_cost_sum_s': total, 'missing_cost_keys': missing,
            'estimated_completion_s': retained + total if retained is not None and total is not None else None}, ledger


@contextmanager
def settings_audit(job, output):
    if job['spec']['method'] != 'rbfopt':
        expected = {**job['spec']['settings'], 'max_points_explored': job['spec']['budget'] - 3}
        if expected != job['reference_settings']:
            raise ValueError('DSDA settings differ from archived primary')
        yield
        return
    import rbfopt
    original = rbfopt.RbfoptSettings
    def create(**kwargs):
        settings = original(**kwargs)
        actual = vars(settings)
        if actual != job['reference_settings']:
            raise ValueError('RBFOpt settings differ from archived genetic primary')
        core.write(output / 'settings_comparison.json', {'identical_to_primary': True, 'actual': actual})
        return settings
    rbfopt.RbfoptSettings = create
    try:
        yield
    finally:
        rbfopt.RbfoptSettings = original


def runtime(job, config):
    expected = job['reference_runtime']
    current = core.preflight(job['spec']['method'], config)
    if (current['versions'] != expected['versions'] or current['python'] != expected['python']
            or current['host'] != expected['host']):
        raise ValueError(f'Historical environment mismatch: actual={current}; expected={expected}')
    if any(os.environ.get(k) != v for k, v in THREADS.items()):
        raise ValueError('Single-thread configuration missing')
    if job['spec']['method'] == 'rbfopt':
        for name, setting in [('bonmin', 'minlp_solver_path'), ('ipopt', 'nlp_solver_path')]:
            if config[name] != job['reference_settings'][setting] or current[name + '_sha256'] != expected['binary_sha256'][name]:
                raise ValueError('Historical auxiliary solver path/hash mismatch')
        import rbfopt.rbfopt_utils as ru
        import rbfopt.rbfopt_algorithm as ra
        current['rbfopt_sources_sha256'] = {m.__name__: core.sha(m.__file__) for m in (ru, ra)}
    current.update(threads=THREADS, effective_cpus=sorted(os.sched_getaffinity(0)),
                   platform_matches_historical=current['platform'] == expected['platform'])
    return current


def worker(root, directory, preflight=False):
    job = core.read(directory / 'job.json')
    config = core.read(directory.parent.parent / 'run.json')['config']
    core.write(directory / 'runtime.json', runtime(job, config))
    if preflight:
        return
    sys.meta_path.insert(0, core.ProcessModelImportBlocker())
    spec = job['spec']
    table, _ = core.load_table(root, spec['case'])
    oracle = core.Oracle(spec, table, directory)
    status, error, returned = 'completed', None, None
    with settings_audit(job, directory):
        started = time.perf_counter()
        core.write(directory / 'started.json', {'pid': os.getpid(), 'utc': datetime.now(timezone.utc).isoformat()})
        try:
            returned = core.optimize(spec, oracle, config, directory)
        except core.BudgetStop:
            status = 'budget_completed'
        except Exception as exc:
            if oracle.events and oracle.events[-1]['callback_exit'] == 'budget_stop':
                status = 'budget_completed'
                returned = {'terminal_budget_exception': str(exc)}
            else:
                status, error = 'execution_failed', f'{type(exc).__name__}: {exc}'
                traceback.print_exc()
        wall = time.perf_counter() - started
    if any(e.get('budget_overrun') for e in oracle.events):
        status, error = 'execution_failed', 'Attempt beyond budget (blocked before lookup)'
    core.write(directory / 'result.json', {'status': status, 'error': error,
               'algorithm_result': returned, 'recorded_search_wall_s': wall})


def summarize(root, directory):
    paired, all_events, groups = [], [], defaultdict(list)
    for job in core.read(root / 'plan.json'):
        spec = job['spec']
        dest = directory / 'jobs' / spec['job_id']
        result = core.read(dest / 'result.json') if (dest / 'result.json').exists() else {'status': 'not_run'}
        new, ledger = metrics(root, spec, core.jsonl(dest / 'callbacks.jsonl'), result)
        base = root / 'baseline' / spec['job_id']
        old, _ = metrics(root, spec, core.jsonl(base / 'callbacks.jsonl'), core.read(base / 'result.json'))
        row = {k: spec[k] for k in ('job_id', 'case', 'cstr_size', 'method', 'seed', 'budget')}
        row.update(new)
        row.update({'baseline_' + k: v for k, v in old.items()})
        row['target_hit_change'] = int(new['target_hit']) - int(old['target_hit']) if new['category'] != 'not_run' else None
        a, b = new['best_accepted_objective'], old['best_accepted_objective']
        row['best_objective_change'] = a - b if a is not None and b is not None else None
        paired.append(row)
        groups[spec['case'], spec['method']].append(row)
        all_events.extend({'job_id': spec['job_id'], 'case': spec['case'],
                           'method': spec['method'], 'seed': spec['seed'], **e} for e in ledger)
    core.write_csv(directory / 'paired_comparison.csv', paired)
    core.write_csv(directory / 'runs.csv', [{k: v for k, v in r.items() if not k.startswith('baseline_')} for r in paired])
    core.write_csv(directory / 'callbacks.csv', all_events)
    core.write_csv(directory / 'rbfopt_coordinates.csv', [
        {k: e.get(k) for k in ('job_id', 'case', 'seed', 'index', 'phase', 'point',
            'callback_coordinates', 'repeated_point', 'raw_objective', 'raw_candidate_objective',
            'accepted', 'evaluation_state', 'method_value', 'method_value_kind',
            'penalty_applied', 'value_returned_to_optimizer', 'callback_exit')}
        for e in all_events if e['method'] == 'rbfopt'])
    summary = []
    for (case, method), rr in groups.items():
        counts = Counter(r['category'] for r in rr)
        summary.append({'case': case, 'method': method, 'target_hits': counts['target_reached'],
                        'denominator': 10, 'baseline_target_hits': sum(r['baseline_target_hit'] for r in rr),
                        'execution_failed': counts['execution_failed'], 'not_run': counts['not_run'],
                        'target_not_reached': counts['target_not_reached'],
                        'success_rate': counts['target_reached'] / 10 if not counts['not_run'] else None})
    counts = dict(Counter(r['category'] for r in paired))
    core.write_csv(directory / 'summary.csv', summary)
    core.write(directory / 'summary.json', {'planned': 120, 'counts': counts, 'groups': summary})
    (directory / 'README.txt').write_text('CSTR penalty experiment\n' + json.dumps(counts, indent=2) +
        '\nSee runs.csv, paired_comparison.csv, summary.csv and callbacks.csv.\n'
        'Target hits exclude execution failures; all 10 seeds remain in each denominator.\n'
        'No new NLP solves. Estimated completion = measured search - lookup + repeated same-key point costs.\n'
        'Missing cost keys stay null. Timing differences include host load/instrumentation and are not attributable solely to penalty.\n'
        'Runtime, exact commands, input/source hashes and original attempts are retained.\n')
    return counts


def launch(command, directory, seconds, fd):
    from watchdog import _stop_process_group
    started = time.perf_counter()
    with (directory / 'optimizer.log').open('a') as log:
        p = subprocess.Popen(command, cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True, pass_fds=(fd,))
        core.write(directory / 'process.json', {'command': command, 'pid': p.pid, 'hard_seconds': seconds})
        try:
            p.wait(timeout=seconds)
        except BaseException:
            _stop_process_group(p)
            raise
    return p.returncode, time.perf_counter() - started


def pack(directory):
    archive = Path(str(directory) + '.zip')
    with zipfile.ZipFile(str(archive) + '.tmp', 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith(('.tmp', '.lock')):
                z.write(p, directory.name + '/' + str(p.relative_to(directory)))
    Path(str(archive) + '.tmp').replace(archive)
    Path(str(archive) + '.sha256').write_text(f'{core.sha(archive)}  {archive.name}\n')
    print('RESULT_ZIP=' + str(archive), flush=True)


def controller(args):
    report = check(ROOT)
    if args.mode in ('dry-run', 'plan'):
        print(json.dumps(report, indent=2))
        return
    if args.mode in ('run', 'check'):
        args.output_root.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix='cstr_penalty_1e6_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_', dir=args.output_root)).resolve()
        # Copy the exact frozen inventory, including validation logs. Exclude
        # incidental launch logs/caches and avoid recursing into an output root.
        for name in ['SHA256SUMS'] + [line.split('  ', 1)[1]
                for line in (ROOT / 'SHA256SUMS').read_text().splitlines()]:
            target = directory / 'reproduction' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        config = {'dfo_python': args.python, 'conda': args.conda, 'bonmin': args.bonmin, 'ipopt': args.ipopt}
        core.write(directory / 'run.json', {'config': config, 'inventory_sha256': core.sha(ROOT / 'SHA256SUMS'),
            'command': sys.argv, 'created_utc': datetime.now(timezone.utc).isoformat(), 'mode': args.mode})
    else:
        if args.run_dir is None:
            raise ValueError('--run-dir required')
        directory = args.run_dir.resolve()
        saved = core.read(directory / 'run.json')
        config = saved['config']
        if core.sha(ROOT / 'SHA256SUMS') != saved['inventory_sha256']:
            raise ValueError('Resume requires the original bundle')
    root = directory / 'reproduction'
    core.verify_inventory(root)
    print('RESULT_DIR=' + str(directory), flush=True)
    with (directory / '.controller.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.mode in ('pack', 'status'):
            print(summarize(root, directory))
            if args.mode == 'pack':
                pack(directory)
            return
        if platform.system() != 'Linux':
            raise RuntimeError('Actual execution requires Dantzig/Linux; use dry-run locally')
        cpu = core.select_cpu(args.cpu)
        core.write(directory / 'cpu_selection.json', cpu)
        command = core.python_command(config['dfo_python'], config)
        plan = core.read(root / 'plan.json')
        # Fail before any search if either method has a mismatched environment.
        for method in ('dsda', 'rbfopt'):
            dest = directory / 'checks' / method
            dest.mkdir(parents=True, exist_ok=True)
            core.write(dest / 'job.json', next(j for j in plan if j['spec']['method'] == method))
            code, _ = launch(command + [str(root / 'runner.py'), '_preflight', '--run-dir', str(dest)], dest, 90, lock.fileno())
            if code:
                summarize(root, directory)
                raise RuntimeError(f'Environment check failed; see {dest}/optimizer.log')
        tests = directory / 'checks/tests'
        tests.mkdir(parents=True, exist_ok=True)
        code, _ = launch(command + ['-m', 'unittest', 'discover', '-s', str(root), '-p', 'test_runner.py', '-v'], tests, 120, lock.fileno())
        if code:
            raise RuntimeError('Protocol tests failed; no searches launched')
        if args.mode == 'check':
            summarize(root, directory)
            print('CHECK_PASSED (no optimizer runs)')
            return
        try:
            for job in plan:
                spec = job['spec']
                dest = directory / 'jobs' / spec['job_id']
                if (dest / 'result.json').exists():
                    continue
                if dest.exists():
                    core.write(dest / 'result.json', {'status': 'execution_failed', 'error': 'interrupted_previous_attempt; not retried'})
                    continue
                dest.mkdir(parents=True)
                core.write(dest / 'job.json', job)
                print('START ' + spec['job_id'], flush=True)
                try:
                    code, wall = launch(command + [str(root / 'runner.py'), '_worker', '--run-dir', str(dest)], dest, job['hard_seconds'], lock.fileno())
                    result = core.read(dest / 'result.json') if (dest / 'result.json').exists() else {'status': 'execution_failed', 'error': 'worker produced no result'}
                    if code:
                        result.update(status='execution_failed', error=f'worker exit={code}')
                    result.update(worker_wall_s=wall, returncode=code)
                    core.write(dest / 'result.json', result)
                except (Exception, KeyboardInterrupt) as exc:
                    core.write(dest / 'result.json', {'status': 'execution_failed', 'error': f'{type(exc).__name__}: {exc}'})
                    if isinstance(exc, KeyboardInterrupt):
                        raise
                summarize(root, directory)
                print('END ' + spec['job_id'], flush=True)
        finally:
            core.verify_inventory(root)
            summarize(root, directory)
            pack(directory)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('dry-run', 'plan', 'check', 'run', 'resume', 'status', 'pack', '_worker', '_preflight'))
    p.add_argument('--run-dir', type=Path)
    p.add_argument('--output-root', type=Path, default=ROOT.parent / 'results')
    p.add_argument('--python', default='/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig/bin/python')
    p.add_argument('--conda', default='')
    p.add_argument('--bonmin', default='/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig/bin/bonmin')
    p.add_argument('--ipopt', default='/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig/bin/ipopt')
    p.add_argument('--cpu', type=int)
    args = p.parse_args()
    if args.mode in ('_worker', '_preflight'):
        worker(ROOT, args.run_dir.resolve(), args.mode == '_preflight')
    else:
        controller(args)


if __name__ == '__main__':
    main()
