"""Frozen IPOPT lookup-only searches. Never constructs a process GDP/NLP."""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import importlib.abc
import importlib.metadata
import itertools
import json
import math
import os
from pathlib import Path
import platform
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parent
BUDGETS = {5: 8, 10: 15, 15: 22, 20: 29, 25: 36, 30: 43}
CASES = {f'cstr_{n}': {'size': n, 'lower': [1, 1], 'upper': [n, n],
          'budgets': [budget], 'rows': n * n if n < 30 else n * (n + 1) // 2,
          'initialization': 'mass_balance_zero_recycle' if n < 30 else
              'constructor_defaults (no upstream saved initialization)'}
         for n, budget in BUDGETS.items()}
METHODS = ('rbfopt', 'bam', 'dsda', 'fmqa_sa')
TIMES = ('setup_wall_s', 'preprocess_wall_s', 'feasible_initialization_wall_s',
         'solve_wall_s', 'total_wall_s', 'worker_process_wall_s')
SETTINGS = {
    'rbfopt': {'algorithm': 'MSRSM', 'global_search_method': 'solver', 'rbf': 'auto', 'num_cpus': 1},
    'bam': {'integrality': 'all_integer', 'x0': None, 'print_to_screen': 1,
            'budget_stop_policy': 'native_max_evals_return_terminal_v2'},
    'dsda': {'diagonal': True, 'tie_break': 'first', 'tol': 1e-12},
    'fmqa_sa': {'epochs': 1000, 'learning_rate': 0.01, 'num_reads': 100,
                'num_sweeps': 1000, 'time_limit': 1800},
}
VERSIONS = {
    'rbfopt': {'numpy': '2.4.6', 'scipy': '1.17.1', 'rbfopt': '4.3.0', 'pyomo': '6.10.0'},
    'bam': {'numpy': '2.4.6', 'scipy': '1.17.1', 'bam-solver': '5.0.0'},
    'dsda': {'numpy': '2.4.6', 'scipy': '1.17.1', 'pandas': '2.3.3'},
    'fmqa_sa': {'numpy': '2.2.6', 'scipy': '1.15.3', 'dimod': '0.12.21',
                'dwave-samplers': '1.6.0', 'torch': '2.8.0'},
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, 'tolist'):
        return clean(value.tolist())
    if isinstance(value, Path):
        return str(value)
    return value


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(clean(value), indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def append(path, value):
    with Path(path).open('a') as stream:
        stream.write(json.dumps(clean(value), allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def jsonl(path):
    if not Path(path).exists():
        return []
    lines = Path(path).read_text().splitlines()
    events = []
    for i, line in enumerate(lines):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines) - 1:
                raise
    return events


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    tmp = Path(path).with_suffix('.csv.tmp')
    with tmp.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in r.items()})
    tmp.replace(path)


def logical_allowed(case, point):
    return point[1] <= point[0]


def verify_inventory(root):
    for line in (root / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        if sha(root / name) != digest:
            raise ValueError(f'Bundle checksum mismatch: {name}')


def load_table(root, case):
    """Validate exact size, completed domain, source hashes and original acceptance."""
    directory = root / 'inputs' / case
    info = read(directory / 'provenance.json')
    if info.get('availability') != 'ready':
        raise ValueError(info.get('unavailable_reason', 'Input not ready'))
    n = CASES[case]['size']
    if (info['cstr_size'] != n or info['initialization'] != CASES[case]['initialization']
            or info['attempt_selection'] != 'Single original attempt per coordinate; no retries or merging'):
        raise ValueError(f'Wrong model size, initialization or attempt selection: {case}')
    for name, digest in info['files_sha256'].items():
        if sha(directory / name) != digest:
            raise ValueError(f'Input checksum mismatch: {case}/{name}')
    summary = read(directory / 'summary.json')
    if not summary['complete']:
        raise ValueError(f'Incomplete input summary: {case}')
    box = set(itertools.product(range(1, n + 1), repeat=2))
    logical = {p for p in box if logical_allowed(case, p)}
    expected = box if n < 30 else logical
    if n < 30:
        manifest = read(directory / 'run.json')
        configuration = manifest['config']
        runtime = manifest['runtime'][str(n)]
        declared = [tuple(r['point']) for r in manifest['coordinates'] if r['cstr_size'] == n]
        summary_case = next(r for r in summary['cases'] if r['cstr_size'] == n)
        valid_manifest = (
            manifest['initialization'] == 'mass_balance_zero_recycle'
            and runtime['post_preprocessing_initialization'] == 'mass_balance_zero_recycle'
            and configuration['time_limit'] == 60 and configuration['feasibility_tolerance'] == 1e-5
            and summary['pending_points'] == 0
            and summary_case['completed_points'] == len(expected))
    else:
        manifest = read(directory / 'manifest.json')
        runtime = manifest['runtime']
        declared = [tuple(p) for p in manifest['plan']['points']]
        valid_manifest = (
            manifest['plan']['case'] == 'cstr' and manifest['plan']['cstr_size'] == n
            and manifest['plan']['bounds'] == [[1, n], [1, n]]
            and manifest['config'] == {'solver': 'gams_ipopt', 'initialization': 'auto',
                                      'time_limit_s': 60, 'feasibility_tolerance': 1e-5}
            and runtime['initialization'] == CASES[case]['initialization']
            and summary['completed_points'] == len(expected) and summary['remaining_points'] == 0)
    if (not valid_manifest or runtime['source'] != info['upstream']
            or runtime['source']['repository'] != 'https://github.com/SECQUOIA/dsda-gdp'
            or runtime['source']['commit'] != '3e469dbeea8931670b8cd6752014ab7a767d3af5'
            or set(declared) != expected or len(declared) != len(expected)):
        raise ValueError(f'Wrong model/solver/initialization or incomplete domain: {case}')
    with (directory / 'evaluations.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(expected):
        raise ValueError(f'Incomplete or duplicate IPOPT domain: {case}')
    table = {}
    for line, row in enumerate(rows, 2):
        point = tuple(json.loads(row['point']))
        if (point in table or point not in expected or row['case'] != 'cstr' or int(row['cstr_size']) != n
                or row['solver'] != 'gams_ipopt' or row['accepted'] not in ('True', 'False')
                or row['status'] in ('pending', '')
                or point != (int(row['x1']), int(row['x2']))):
            raise ValueError(f'Invalid/duplicate/unprocessed row: {case}:{line}')
        if n < 30 and (row['initialization_requested'] != CASES[case]['initialization']
                       or (row['logical_allowed'] == 'True') != (point in logical)):
            raise ValueError(f'Wrong evaluation procedure or logical classification: {case}:{line}')
        if point not in logical and (row['accepted'] != 'False' or row['status'] != 'preprocessing_infeasible'):
            raise ValueError(f'Inconsistent model-logical exclusion: {case}:{line}')
        if point in logical and row['initialization'] != CASES[case]['initialization']:
            raise ValueError(f'Wrong initialization: {case}:{line}')
        accepted = row['accepted'] == 'True'
        if accepted:
            value = float(row['objective'])
            if (not math.isfinite(value) or value >= 1e6 or row['status'] != 'accepted'
                    or row['termination'] not in ('optimal', 'locallyOptimal', 'globallyOptimal')
                    or row['solver_status'] in ('error', 'aborted')
                    or float(row['gams_solve_status']) != 1 or float(row['gams_model_status']) not in (1, 2)
                    or not math.isfinite(float(row['max_primal_violation']))
                    or float(row['max_primal_violation']) > 1e-5):
                raise ValueError(f'Invalid accepted result: {case}:{line}')
        elif row['objective']:
            raise ValueError(f'Nonaccepted row has objective: {case}:{line}')
        for field in TIMES:
            if row.get(field) and (not math.isfinite(float(row[field])) or float(row[field]) < 0):
                raise ValueError(f'Invalid measured time: {case}:{line}:{field}')
        table[point] = {**row, 'csv_line': line,
                        'record_file': f'records/cstr_{n}_{point[0]:02d}_{point[1]:02d}.json' if n < 30
                            else f'records/point_{int(row["point_index"]):06d}.json'}
    if set(table) != expected:
        raise ValueError(f'Unmeasured logical candidates: {case}')
    return table, info


def failure_reason(row):
    return '; '.join(f'{key}={row[key]}' for key in (
        'status', 'termination', 'solver_status', 'gams_solve_status', 'gams_model_status', 'message')
        if row.get(key) and row[key] != 'None')


def write_input_report(root, output):
    """Report minima separately; this report is never passed to an optimizer."""
    rows = []
    for case, settings in CASES.items():
        n = settings['size']
        try:
            table, info = load_table(root, case)
            accepted = [(p, float(r['objective'])) for p, r in table.items() if r['accepted'] == 'True']
            best = min(v for p, v in accepted) if accepted else None
            rows.append({'case': case, 'cstr_size': n, 'availability': 'ready',
                'required_logical_points': n * (n + 1) // 2, 'processed_rows': len(table),
                'accepted': len(accepted), 'processed_unaccepted': len(table) - len(accepted),
                'logical_processed_unaccepted': sum(r['accepted'] != 'True' and logical_allowed(case, p) for p, r in table.items()),
                'unmeasured_logical_exclusions': n * n - len(table),
                'status_counts': dict(Counter(r['status'] for r in table.values())),
                'table_accepted_minimum': best, 'best_points': [p for p, v in accepted if v == best],
                'unaccepted_logical_points': [p for p, r in table.items() if logical_allowed(case, p) and r['accepted'] != 'True'],
                'initialization': info['initialization'], 'source_csv': info['source_csv'],
                'csv_sha256': sha(root / 'inputs' / case / 'evaluations.csv'),
                'measured_time_rows': {k: sum(bool(r.get(k)) for r in table.values()) for k in TIMES}})
        except Exception as error:
            rows.append({'case': case, 'cstr_size': n, 'availability': 'not_run', 'reason': str(error)})
    write_csv(output / 'inputs_report.csv', rows)
    write(output / 'inputs_report.json', rows)
    return rows


class ProcessModelImportBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname.split('.')[0] in {'gdp_models', 'gdp', 'cstr30_retry', 'cstr_box_ipopt'}
                or fullname.startswith('case_studies.') and fullname.endswith('_case')):
            raise ImportError(f'Process model/legacy objective import prohibited: {fullname}')


def bam_native_budget(spec):
    """Old frozen specs retain their original terminal-exception protocol."""
    return (spec['method'] == 'bam' and
            spec['settings'].get('budget_stop_policy') == 'native_max_evals_return_terminal_v2')


class BudgetStop(Exception):
    """Stop non-BAM or legacy runs after recording evaluation B."""


class MissingEvaluation(Exception):
    pass


class Oracle:
    def __init__(self, spec, table, directory):
        self.spec, self.table, self.directory = spec, table, directory
        self.events, self.wall_times = [], []
        self.started = time.perf_counter()

    @property
    def call_count(self):
        return len(self.events)

    def __call__(self, coordinates):
        started = time.perf_counter()
        spec = self.spec
        budget_overrun = self.call_count >= spec['budget']
        point, protocol_error = (), None
        raw_coordinates = list(coordinates)
        try:
            raw_coordinates = [float(x) for x in coordinates]
            point = tuple(int(round(x)) for x in raw_coordinates)
            if len(point) != len(spec['lower']) or any(not lo <= x <= hi for x, lo, hi in zip(point, spec['lower'], spec['upper'])):
                raise ValueError(f'Optimizer requested out-of-domain point: {point}')
            if self.call_count < 3 and list(point) != spec['starts'][self.call_count]:
                raise ValueError('Optimizer changed the shared initial order')
        except (ValueError, TypeError, OverflowError) as error:
            protocol_error = str(error)
        if budget_overrun:
            protocol_error = 'Optimizer swallowed the hard budget stop; callback beyond B'
        row = None if protocol_error else self.table.get(point)
        accepted = row is not None and row['accepted'] == 'True'
        state = 'invalid_callback' if protocol_error else 'accepted' if accepted else 'evaluated_unaccepted' if row else (
            'logical_exclusion_unmeasured' if not logical_allowed(spec['case'], point) else 'not_evaluated')
        value = float(row['objective']) if accepted else (
            math.nan if spec['method'] == 'bam' else math.inf)
        terminal = self.call_count + 1 == spec['budget']
        # BAM must receive evaluation B. Its native max_evals already counts
        # the remaining B-3 calls, including NaNs and repeated points. Raising
        # here discards the last value and can trigger another native request.
        stop_at_terminal = terminal and not bam_native_budget(spec)
        event = {'index': self.call_count + 1, 'phase': 'initial' if self.call_count < 3 else 'adaptive',
                 'point': list(point), 'cstr_size': CASES[spec['case']]['size'], 'callback_coordinates': raw_coordinates,
                 'budget_overrun': budget_overrun,
                 'raw_candidate_objective': float(row['candidate_objective']) if row and row.get('candidate_objective') else None,
                 'raw_objective': float(row['objective']) if accepted else None,
                 'method_value': value if math.isfinite(value) else None,
                 'method_value_kind': 'finite' if math.isfinite(value) else 'nan' if math.isnan(value) else '+inf',
                 'value_returned_to_optimizer': not stop_at_terminal and not protocol_error and state != 'not_evaluated',
                 'callback_exit': 'protocol_error' if protocol_error else 'missing_data' if state == 'not_evaluated' else 'budget_stop' if stop_at_terminal else 'return',
                 'fmqa_reporting_penalty': 1e6 if spec['method'] == 'fmqa_sa' and not accepted else None,
                 'accepted': accepted, 'evaluation_state': state,
                 'failure_reason': protocol_error or (None if accepted else failure_reason(row) if row else state),
                 'source_row': row, 'selected_attempt': 1 if row else None,
                 'available_attempts': 1 if row else 0,
                 'selected_attempt_nlp_s': float(row['total_wall_s']) if row and row['total_wall_s'] else None,
                 'all_attempts_nlp_s': float(row['total_wall_s']) if row and row['total_wall_s'] else None,
                 'nlp_times': {k: float(row[k]) if row and row.get(k) else None for k in TIMES},
                 'lookup_wall_s': time.perf_counter() - started,
                 'elapsed_s': time.perf_counter() - self.started}
        self.events.append(event)
        self.wall_times.append(event['lookup_wall_s'])
        append(self.directory / 'callbacks.jsonl', event)
        if protocol_error:
            raise ValueError(protocol_error)
        if state == 'not_evaluated':
            raise MissingEvaluation(f'Unmeasured coordinate {point}; not declared infeasible')
        if stop_at_terminal:
            raise BudgetStop()
        return value


@contextmanager
def audit_surrogate_solvers(directory):
    import pyomo.environ
    import pyomo.opt
    original = pyomo.opt.SolverFactory
    def factory(name, *args, **kwargs):
        if name not in ('bonmin', 'ipopt'):
            raise RuntimeError(f'Only RBFOpt surrogate Bonmin/IPOPT allowed: {name}')
        solver = original(name, *args, **kwargs)
        solve = solver.solve
        def audited(model, *a, **kw):
            import pyomo.core.base.var
            from pyomo.gdp import Disjunct
            if (any(model.component_data_objects(Disjunct)) or not hasattr(model, 'OBJ')
                    or not (hasattr(model, 'x') or hasattr(model, 'rbf_lambda'))):
                raise RuntimeError('Unexpected surrogate model; process solve blocked')
            append(directory / 'auxiliary_solver_calls.jsonl', {
                'event': 'start', 'scope': 'RBFOpt surrogate only', 'solver': name,
                'executable': solver.executable(), 'options': dict(solver.options)})
            started = time.perf_counter()
            try:
                result = solve(model, *a, **kw)
                append(directory / 'auxiliary_solver_calls.jsonl', {
                    'event': 'end', 'solver': name, 'wall_s': time.perf_counter() - started,
                    'termination': str(result.solver.termination_condition), 'status': str(result.solver.status)})
                return result
            except Exception as error:
                append(directory / 'auxiliary_solver_calls.jsonl', {
                    'event': 'error', 'solver': name, 'wall_s': time.perf_counter() - started, 'error': str(error)})
                raise
        solver.solve = audited
        return solver
    pyomo.opt.SolverFactory = factory
    try:
        yield
    finally:
        pyomo.opt.SolverFactory = original


def optimize(spec, oracle, config, directory):
    import numpy as np
    random.seed(spec['seed'])
    np.random.seed(spec['seed'])
    method = spec['method']
    if method == 'fmqa_sa':
        from fmqa_benchmark.optimizer import optimize as fmqa
        from fmqa_benchmark.qhd_surrogate import cpu_settings
        settings = {**spec['settings'], 'torch': cpu_settings(), 'factorization_size': 8,
                    'training_optimizer': 'Adam', 'loss': 'MSELoss',
                    'sa_beta_schedule_type': 'geometric',
                    'bit_widths': [max(1, int(hi).bit_length()) for hi in spec['upper']],
                    'training_response': 'observed finite min-max -> [0,1]; observed failures -> 2',
                    'rng': 'SeedSequence(seed).spawn(3): model, annealing, unseen fallback'}
        write(directory / 'actual_settings.json', settings)
        return fmqa(oracle, spec['lower'], spec['upper'], spec['starts'], spec['budget'], spec['seed'],
                    spec['settings'], on_proposal=lambda e: append(directory / 'proposals.jsonl', e))
    if method == 'rbfopt':
        import rbfopt
        settings = rbfopt.RbfoptSettings(max_evaluations=spec['budget'], rand_seed=spec['seed'],
            minlp_solver_path=config['bonmin'], nlp_solver_path=config['ipopt'], **spec['settings'])
        write(directory / 'actual_settings.json', vars(settings))
        bb = rbfopt.RbfoptUserBlackBox(len(spec['lower']), np.array(spec['lower']), np.array(spec['upper']),
                                     np.array(['I'] * len(spec['lower'])), oracle)
        with audit_surrogate_solvers(directory):
            alg = rbfopt.RbfoptAlgorithm(settings, bb, init_node_pos=np.array(spec['starts'], dtype=float),
                                        init_node_val=None, do_init_strategy=False)
            write(directory / 'effective_rbfopt_settings.json', vars(alg.l_settings))
            return {'returned': clean(alg.optimize())}
    if method == 'bam':
        import bam
        bam.set_license_file(config['bam_license'])
        values = np.array([oracle(p) for p in spec['starts']], dtype=float)
        options = {'print_to_screen': 1, 'x_evaluated': np.array(spec['starts'], dtype=float),
                   'f_evaluated': values, 'max_evals': spec['budget'] - 3}
        write(directory / 'actual_settings.json', {'options': options, 'integrality': [1] * len(spec['lower']),
              'x0': None, 'python_numpy_seed': spec['seed'], 'bam_seed_option': 'not exposed in original runner',
              'budget_stop_policy': spec['settings'].get('budget_stop_policy', 'terminal_exception_v1')})
        if oracle.call_count == spec['budget']:
            # Do not enter BAM when the shared initial design has already
            # consumed the entire process-evaluation budget.
            ranking = np.where(np.isfinite(values), values, np.inf)
            best = int(np.argmin(ranking))
            return {'x': spec['starts'][best], 'fun': clean(values[best]),
                    'status': None, 'success': True, 'message': 'Budget exhausted by shared initialization',
                    'nit': 0, 'nfev': 0}
        result = bam.minimize(oracle, x0=None, bounds=list(zip(spec['lower'], spec['upper'])),
                              integrality=[1] * len(spec['lower']), options=options)
        return {k: clean(getattr(result, k, None)) for k in ('x', 'fun', 'status', 'success', 'message', 'nit', 'nfev')}
    from grid_dsda import dsda_from_csv
    write(directory / 'actual_settings.json', {**spec['settings'], 'max_points_explored': spec['budget'] - 3})
    for p in spec['starts']:
        oracle(p)
    accepted = [e for e in oracle.events if e['accepted']]
    if not accepted:
        raise RuntimeError('No accepted initial point; no reseeding')
    best = min(accepted, key=lambda e: e['raw_objective'])
    domain = dict.fromkeys(itertools.product(*(range(lo, hi + 1) for lo, hi in zip(spec['lower'], spec['upper']))))
    return dsda_from_csv(csv_path='IPOPT_lookup', start_point=best['point'], start_value=best['raw_objective'],
                         grid=domain, tracked_objective=oracle, max_points_explored=spec['budget'] - 3,
                         verbose=True, **spec['settings'])


def preflight(method, config):
    versions = {name: importlib.metadata.version(name) for name in VERSIONS[method]}
    if any(versions[n].split('+')[0] != v for n, v in VERSIONS[method].items()):
        raise RuntimeError(f'Existing experiment environment version mismatch: {versions}; expected {VERSIONS[method]}')
    extras = {}
    if method == 'rbfopt':
        import rbfopt
        for name in ('bonmin', 'ipopt'):
            p = Path(config[name])
            if not p.is_file() or not os.access(p, os.X_OK):
                raise RuntimeError(f'Missing surrogate solver: {p}')
            extras[name + '_sha256'] = sha(p)
    elif method == 'bam':
        import bam
        if not Path(config['bam_license']).is_file():
            raise RuntimeError('BAM license file not available')
        bam.set_license_file(config['bam_license'])
    elif method == 'fmqa_sa':
        import torch
        from dwave.samplers import SimulatedAnnealingSampler
        from fmqa_benchmark.qhd_surrogate import verify_sources
        extras['qhd_source'] = verify_sources()
    else:
        import grid_dsda
    return {'versions': versions, 'python': platform.python_version(), 'executable': sys.executable,
            'host': platform.node(), 'platform': platform.platform(), **extras}


def worker(directory):
    spec, config = read(directory / 'spec.json'), read(directory.parent.parent / 'run.json')['config']
    root = directory.parent.parent / 'reproduction'
    sys.meta_path.insert(0, ProcessModelImportBlocker())
    table, _ = load_table(root, spec['case'])
    runtime = preflight(spec['method'], config)
    write(directory / 'runtime.json', runtime)
    oracle = Oracle(spec, table, directory)
    started = time.perf_counter()
    write(directory / 'started.json', {'pid': os.getpid(), 'monotonic': started,
          'utc': datetime.now(timezone.utc).isoformat(), 'effective_cpu': sorted(os.sched_getaffinity(0))})
    status, error, result = 'completed', None, None
    try:
        result = optimize(spec, oracle, config, directory)
        if isinstance(result, dict) and result.get('status') == 'time_limit':
            status, error = 'execution_failed', 'FMQA soft time limit'
        if spec['method'] == 'bam' and result.get('success') is False:
            status, error = 'execution_failed', f'BAM status={result.get("status")}: {result.get("message")}'
        elif bam_native_budget(spec) and oracle.call_count == spec['budget']:
            status = 'budget_completed'
    except BudgetStop as exc:
        status = 'budget_completed'
        result = {'backend_result_at_budget': clean(getattr(exc, 'result', None))}
    except Exception as exc:
        if oracle.events and oracle.events[-1]['callback_exit'] == 'budget_stop':
            # A native backend may wrap Python callback exceptions.
            status = 'budget_completed'
            result = {'terminal_budget_exception': f'{type(exc).__name__}: {exc}'}
        else:
            status, error = 'execution_failed', f'{type(exc).__name__}: {exc}'
            traceback.print_exc()
    if any(e['budget_overrun'] for e in oracle.events):
        status, error = 'execution_failed', 'Backend continued after hard budget stop; all callback attempts preserved'
    write(directory / 'result.json', {'status': status, 'error': error, 'algorithm_result': result,
          'dfo_wall_s': time.perf_counter() - started, 'callback_count': oracle.call_count})


def summarize(directory):
    run = read(directory / 'run.json')
    root = directory / 'reproduction'
    tables, targets, input_errors = {}, {}, {}
    for case in CASES:
        try:
            table, _ = load_table(root, case)
            tables[case] = table
            targets[case] = min(float(r['objective']) for r in table.values() if r['accepted'] == 'True')
        except Exception as error:
            targets[case] = None
            input_errors[case] = str(error)
    write_input_report(root, directory)
    rows, all_events = [], []
    for spec in read(root / 'plan.json'):
        job = directory / 'jobs' / spec['job_id']
        result = read(job / 'result.json') if (job / 'result.json').exists() else {'status': 'not_run', 'error': 'not_started'}
        events = jsonl(job / 'callbacks.jsonl')
        accepted = [e for e in events if e['accepted']]
        best = min(accepted, key=lambda e: e['raw_objective']) if accepted else None
        target = targets[spec['case']]
        hit = bool(best and target is not None and abs(best['raw_objective'] - target) <= 1e-5 * max(1, abs(target)))
        failed = result['status'] not in ('completed', 'budget_completed', 'not_run') or (result['status'] != 'not_run' and (not best or target is None))
        category = 'not_run' if result['status'] == 'not_run' else 'execution_failed' if failed else 'target_reached' if hit else 'target_not_reached'
        missing = sum(e['selected_attempt_nlp_s'] is None for e in events)
        known = sum(e['selected_attempt_nlp_s'] for e in events if e['selected_attempt_nlp_s'] is not None)
        unique = {tuple(e['point']): e for e in events}
        row = {'job_id': spec['job_id'], 'case': spec['case'], 'cstr_size': CASES[spec['case']]['size'], 'budget': spec['budget'], 'method': spec['method'],
               'seed': spec['seed'], 'category': category, 'execution_status': result['status'],
               'error': result.get('error') or input_errors.get(spec['case']) or ('no_accepted_observation' if failed and not best else None),
               'best_accepted_objective': best['raw_objective'] if best else None,
               'best_point': best['point'] if best else None, 'table_accepted_minimum': target,
               'target_observed_even_if_execution_failed': hit, 'callback_count': len(events),
               'initial_callbacks': sum(e['phase'] == 'initial' for e in events),
               'adaptive_callbacks': sum(e['phase'] == 'adaptive' for e in events),
               'accepted_callbacks': len(accepted),
               'unique_points': len(unique), 'initial_points': spec['starts'],
               'dfo_wall_s': result.get('dfo_wall_s'), 'worker_process_wall_s': result.get('worker_process_wall_s'),
               'lookup_wall_s': sum(e['lookup_wall_s'] for e in events) if events else None,
               'nlp_time_available': bool(events) and missing == 0, 'missing_nlp_times': missing,
               'historical_nlp_per_callback_sum_s': known if events and not missing else None,
               'known_historical_nlp_sum_s': known if events else None,
               'historical_all_attempts_per_callback_sum_s': sum(e['all_attempts_nlp_s'] for e in events) if events and all(e['all_attempts_nlp_s'] is not None for e in events) else None,
               'historical_unique_attempts_sum_s': sum(e['selected_attempt_nlp_s'] for e in unique.values())
                   if events and all(e['selected_attempt_nlp_s'] is not None for e in unique.values()) else None,
               'input_csv': f'reproduction/inputs/{spec["case"]}/evaluations.csv',
               'input_csv_sha256': sha(root / 'inputs' / spec['case'] / 'evaluations.csv') if (root / 'inputs' / spec['case'] / 'evaluations.csv').exists() else None}
        rows.append(row)
        all_events.extend({'job_id': spec['job_id'], **e} for e in events)
    write_csv(directory / 'runs.csv', rows)
    write_csv(directory / 'callbacks.csv', all_events)
    groups = defaultdict(list)
    for row in rows:
        groups[(row['case'], row['budget'], row['method'])].append(row)
    grouped = []
    for (case, budget, method), group in groups.items():
        counts = Counter(r['category'] for r in group)
        grouped.append({'case': case, 'budget': budget, 'method': method, 'planned_seeds': 10,
                        **{k: counts[k] for k in ('target_reached', 'target_not_reached', 'execution_failed', 'not_run')},
                        'success_rate_denominator': 10,
                        'success_rate': counts['target_reached'] / 10 if not counts['not_run'] else None,
                        'nlp_time_complete_runs': sum(r['nlp_time_available'] for r in group)})
    write_csv(directory / 'summary.csv', grouped)
    write(directory / 'summary.json', {'slots': len(rows), 'counts': dict(Counter(r['category'] for r in rows)),
          'target_rule': 'abs(best_accepted - table_accepted_minimum) <= 1e-5 * max(1, abs(table_accepted_minimum))',
          'target_used_only_after_search': True, 'groups': grouped, 'input_errors': input_errors,
          'nlp_cost_scope': 'Historical same-row costs, not NLP solves in this run; no borrowed/zero-filled missing times',
          'input_initialization_note': 'N5..25 mass_balance_zero_recycle; N30 original constructor defaults; no retry merging'})
    return rows


def pack(directory):
    summarize(directory)
    archive = directory.with_suffix('.zip')
    tmp = archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith('.tmp') and p.name != '.run.lock':
                z.write(p, directory.name + '/' + p.relative_to(directory).as_posix())
    tmp.replace(archive)
    archive.with_suffix('.zip.sha256').write_text(f'{sha(archive)}  {archive.name}\n')
    print(f'RESULT_DIR={directory}\nRESULT_ZIP={archive}', flush=True)


def python_command(executable, config):
    executable = Path(executable)
    if (executable.parent.parent / 'conda-meta').is_dir():
        if not config['conda']:
            raise ValueError('Set IPOPT_DFO_CONDA for the existing conda environment')
        return [config['conda'], 'run', '--no-capture-output', '--prefix', str(executable.parent.parent), 'python']
    return [str(executable)]


def _stop_process_group(process, grace_seconds=5):
    """Stop the session we created, including children outliving its leader."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            process.poll()  # Reap the leader without assuming its children exited.
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    finally:
        # A cooperative leader can exit before a solver that ignores SIGTERM.
        # Always finish cleanup of our group, even if the grace wait is interrupted.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def launch(command, logfile, seconds):
    started = time.perf_counter()
    with logfile.open('w') as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=seconds)
            return code, time.perf_counter() - started, False
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            _stop_process_group(process)
            if isinstance(error, KeyboardInterrupt):
                raise
            return process.returncode, time.perf_counter() - started, True


def select_cpu(requested):
    """Read other experiment affinities; never change their processes/files."""
    from cpu_affinity import cpu_topology, pin_cpu, affinity_record
    allowed, excluded, observed = set(os.sched_getaffinity(0)), set(), []
    ancestors = own_ancestors()
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            if p.stat().st_uid != os.getuid():
                continue
            argv = (p / 'cmdline').read_bytes().decode(errors='replace').split('\0')
            if int(p.name) in ancestors or not any(is_other_experiment_script(arg) for arg in argv):
                continue
            cpus = set()
            for task in (p / 'task').iterdir():
                cpus.update(os.sched_getaffinity(int(task.name)))
            excluded.update(cpus)
            observed.append({'pid': int(p.name), 'argv': argv, 'cpus': sorted(cpus)})
        except (FileNotFoundError, ProcessLookupError):
            continue
    for cpu in list(excluded):
        siblings = cpu_topology(cpu)['thread_siblings_list']
        if siblings is None:
            raise RuntimeError('Cannot verify other experiment physical-core separation')
        for part in siblings.split(','):
            lo, _, hi = part.partition('-')
            excluded.update(range(int(lo), int(hi or lo) + 1))
    candidates = allowed - excluded
    if not candidates or requested is not None and requested not in candidates:
        raise RuntimeError(f'No safe requested CPU; Other experiment exclusions={sorted(excluded)}')
    cpu = pin_cpu(requested if requested is not None else min(candidates))
    return {'selected': affinity_record(cpu), 'observed_other_experiment_processes': observed,
            'excluded_cpus': sorted(excluded), 'note': 'Read-only affinity check; not an exclusive allocation'}


def is_other_experiment_script(argument):
    name = Path(argument).name.lower()
    return name.endswith(('.py', '.sh')) and any(token in name for token in (
        'ipopt_dfo_', 'process_ipopt', 'cstr_box_ipopt', 'cstr30_retry',
        'nlp_overnight', 'process_dsda_fairness'))


def own_ancestors():
    ancestors, pid = {os.getpid()}, os.getppid()
    while pid > 1 and pid not in ancestors:
        ancestors.add(pid)
        try:
            status = Path(f'/proc/{pid}/status').read_text().splitlines()
            pid = int(next(line for line in status if line.startswith('PPid:')).split()[1])
        except (OSError, StopIteration):
            break
    return ancestors


def controller(args):
    import fcntl
    verify_inventory(ROOT)
    config = {'dfo_python': args.dfo_python, 'fmqa_python': args.fmqa_python, 'conda': args.conda,
              'bonmin': args.bonmin, 'ipopt': args.ipopt, 'bam_license': args.bam_license,
              'hard_seconds': 2100}
    if args.mode in ('pack', 'status'):
        if not args.run_dir:
            raise ValueError('--run-dir required')
        directory = args.run_dir.resolve()
    elif args.mode == 'resume':
        if not args.run_dir:
            raise ValueError('--run-dir required')
        directory = args.run_dir.resolve()
        saved = read(directory / 'run.json')
        config = saved['config']
        verify_inventory(directory / 'reproduction')
        if sha(ROOT / 'SHA256SUMS') != saved['bundle_inventory_sha256']:
            raise ValueError('Resume requires the original bundle')
    else:
        args.output_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        directory = Path(tempfile.mkdtemp(prefix=f'ipopt_dfo_cstr_{stamp}_', dir=args.output_root)).resolve()
        shutil.copytree(ROOT, directory / 'reproduction', ignore=shutil.ignore_patterns('__pycache__', '*.log'))
        # This CLI is run from a standalone bundle, never from the repository root.
        for p in (directory / 'reproduction' / 'inputs').rglob('*'):
            if p.is_file():
                p.chmod(0o444)
        write(directory / 'run.json', {'config': config, 'bundle_inventory_sha256': sha(ROOT / 'SHA256SUMS'),
              'created_utc': datetime.now(timezone.utc).isoformat(), 'mode': args.mode,
              'user_authorized_surrogate_solvers': True})
    print(f'RESULT_DIR={directory}', flush=True)
    with (directory / '.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.mode == 'pack':
            pack(directory)
            return
        if args.mode == 'status':
            summarize(directory)
            print(json.dumps(read(directory / 'summary.json'), indent=2))
            return
        try:
            cpu = select_cpu(args.cpu)
        except (OSError, ValueError, RuntimeError) as error:
            write(directory / 'availability.json', {'cpu_error': str(error)})
            for spec in read(directory / 'reproduction/plan.json'):
                job = directory / 'jobs' / spec['job_id']
                if not (job / 'result.json').exists():
                    write(job / 'spec.json', spec)
                    started = (job / 'started.json').exists() or (job / 'callbacks.jsonl').exists()
                    write(job / 'result.json', {'status': 'execution_failed' if started else 'not_run',
                          'error': 'interrupted_previous_attempt' if started else f'CPU separation unavailable: {error}'})
            pack(directory)
            raise
        write(directory / 'cpu_selection.json', cpu)
        root = directory / 'reproduction'
        data_errors, env_errors = {}, {}
        for case in CASES:
            try:
                load_table(root, case)
            except Exception as error:
                data_errors[case] = str(error)
        selected_methods = {spec['method'] for spec in read(root / 'plan.json')}
        for method in METHODS:
            if method not in selected_methods:
                continue
            path = directory / f'preflight_{method}.json'
            executable = config['fmqa_python'] if method == 'fmqa_sa' else config['dfo_python']
            command = python_command(executable, config) + [str(root / 'ipopt_dfo_cstr.py'), '_preflight',
                        '--method', method, '--run-dir', str(directory)]
            try:
                code, _, timeout = launch(command, directory / f'preflight_{method}.log', 90)
                if code or timeout or not path.exists():
                    env_errors[method] = f'Preflight failed; see preflight_{method}.log'
            except (OSError, ValueError) as error:
                env_errors[method] = str(error)
        write(directory / 'availability.json', {'data_errors': data_errors, 'environment_errors': env_errors})
        plan = read(root / 'plan.json')
        try:
            for spec in plan:
                job = directory / 'jobs' / spec['job_id']
                job.mkdir(parents=True, exist_ok=True)
                if (job / 'result.json').exists():
                    continue  # Never replace failed seeds or retry completed attempts.
                write(job / 'spec.json', spec)
                if (job / 'started.json').exists() or (job / 'callbacks.jsonl').exists():
                    write(job / 'result.json', {'status': 'execution_failed', 'error': 'interrupted_previous_attempt'})
                    continue
                reason = data_errors.get(spec['case']) or env_errors.get(spec['method'])
                if reason:
                    write(job / 'result.json', {'status': 'not_run', 'error': reason})
                    continue
                if args.mode == 'check':
                    continue
                print(f'START {spec["job_id"]}', flush=True)
                executable = config['fmqa_python'] if spec['method'] == 'fmqa_sa' else config['dfo_python']
                command = python_command(executable, config) + [str(root / 'ipopt_dfo_cstr.py'), '_worker', '--run-dir', str(job)]
                try:
                    code, elapsed, timeout = launch(command, job / 'optimizer.log', config['hard_seconds'])
                    result = read(job / 'result.json') if (job / 'result.json').exists() else {
                        'status': 'execution_failed' if (job / 'started.json').exists() else 'not_run',
                        'error': f'Worker exit={code}, watchdog_timeout={timeout}'}
                    if code or timeout:
                        result.update(status='execution_failed' if (job / 'started.json').exists() else 'not_run',
                                      error=f'Worker exit={code}, watchdog_timeout={timeout}')
                    result.update(worker_process_wall_s=elapsed, worker_returncode=code, watchdog_timeout=timeout)
                    write(job / 'result.json', result)
                except KeyboardInterrupt:
                    write(job / 'result.json', {'status': 'execution_failed', 'error': 'interrupted'})
                    raise
                verify_inventory(root)
                summarize(directory)
                print(f'END {spec["job_id"]}: {result["status"]}', flush=True)
        finally:
            pack(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('run', 'check', 'resume', 'pack', 'status', '_worker', '_preflight'))
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--output-root', type=Path, default=ROOT.parent / 'results')
    parser.add_argument('--method', choices=METHODS)
    parser.add_argument('--cpu', type=int)
    parser.add_argument('--dfo-python', default=sys.executable)
    parser.add_argument('--fmqa-python', default=sys.executable)
    parser.add_argument('--conda', default='')
    parser.add_argument('--bonmin', default='bonmin')
    parser.add_argument('--ipopt', default='ipopt')
    parser.add_argument('--bam-license', default='')
    args = parser.parse_args()
    if args.mode == '_worker':
        worker(args.run_dir.resolve())
    elif args.mode == '_preflight':
        sys.meta_path.insert(0, ProcessModelImportBlocker())
        write(args.run_dir / f'preflight_{args.method}.json', preflight(args.method, read(args.run_dir / 'run.json')['config']))
    else:
        controller(args)


if __name__ == '__main__':
    main()
