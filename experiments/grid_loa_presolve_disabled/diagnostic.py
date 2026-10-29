"""One-use LOA diagnostic with six gated actual SCIP subproblem calls."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.metadata
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys
from types import SimpleNamespace
import zipfile

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
TAG = 'grid_loa_presolve_disabled_20261025_v2'
GRIDS = ('holder_table', 'michalewicz', 'shubert')
POINTS = (('holder_table', (3, 1)), ('holder_table', (3, 29)),
          ('holder_table', (27, 1)), ('holder_table', (27, 29)),
          ('michalewicz', (21, 15)), ('shubert', (17, 22)))
TOLERANCE = 1e-5
MODULES = ('pyomo.contrib.fbbt.fbbt', 'pyomo.contrib.fbbt.interval',
           'pyomo.contrib.gdpopt.solve_subproblem')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, data):
    from gdp_models.comparison import save_json
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    save_json(Path(path), data)


def verify_package():
    inventory = read(PACKAGE / 'DIAGNOSTIC_MANIFEST.json')
    for name, digest in inventory['files_sha256'].items():
        path = (PACKAGE / name).resolve()
        require(path.is_relative_to(PACKAGE) and sha(path.read_bytes()) == digest,
                'Package bytes changed: ' + name)
    return inventory


def baseline():
    return read(PACKAGE / 'BASELINE.json')


def config():
    c = baseline()['run']['config'].copy()
    c.update(grids=list(GRIDS), recovery_grids=list(GRIDS), methods=['loa'], planned_jobs=3,
             diagnostic_presolve_disabled=True)
    require(c['time_limit'] == 1800 and c['threads'] == 1 and c['cpu'] == 14,
            'Historical time/thread/CPU policy changed')
    require(c['nlp_solver'] == c['mip_solver'] == 'scip', 'Historical solver route changed')
    return c


def module_hashes():
    return {n: sha(Path(importlib.import_module(n).__file__).read_bytes()) for n in MODULES}


def structure(model):
    """Exclude values; retain original algebra, activity, domains and bounds."""
    import pyomo.environ as pyo
    from pyomo.gdp import Disjunct, Disjunction
    descend = (pyo.Block, Disjunct)
    data = {
        'variables': [(v.name, str(v.domain), str(v.lb), str(v.ub), v.fixed)
                      for v in model.component_data_objects(pyo.Var, descend_into=descend)],
        'constraints': [(c.name, str(c.expr), c.active)
                        for c in model.component_data_objects(pyo.Constraint, active=None, descend_into=descend)],
        'objectives': [(c.name, str(c.expr), str(c.sense), c.active)
                       for c in model.component_data_objects(pyo.Objective, active=None, descend_into=descend)],
        'logic': [(c.name, str(c.expr), c.active)
                  for c in model.component_data_objects(pyo.LogicalConstraint, active=None, descend_into=descend)],
        'disjunctions': [(c.name, c.xor, [d.name for d in c.disjuncts], c.active)
                         for c in model.component_data_objects(Disjunction, active=None, descend_into=descend)],
    }
    return {'sha256': sha(json.dumps(data, sort_keys=True).encode()), 'components': data}


def setup(grid, point):
    """Same model/FBBT/subproblem construction as the historical local probe."""
    from gdp_models.grid import build_grid_gdp
    from pyomo.contrib.fbbt.fbbt import fbbt
    from pyomo.contrib.gdpopt import create_oa_subproblems as create
    from pyomo.contrib.gdpopt.util import move_nonlinear_objective_to_constraints
    model = build_grid_gdp(grid)
    fbbt(model)
    util = create.add_util_block(model)
    create.add_disjunct_list(util)
    create.add_boolean_variable_lists(util)
    create.add_algebraic_variable_list(util)
    move_nonlinear_objective_to_constraints(util, logging.getLogger('presolve_diagnostic'))
    model, util = create.get_subproblem(model, util)
    for choices, selected in zip((model.Xchoice, model.Ychoice), point):
        for index, disjunct in choices.items():
            disjunct.indicator_var.fix(index == selected)
            if index != selected:
                disjunct.deactivate()
    return model, util


def original_check(grid, variables):
    """Evaluate returned variables on a fresh, unmodified original GDP."""
    import pyomo.environ as pyo
    from gdp_models.grid import build_grid_gdp, _read_reference, GRID_DIR
    from gdp_models.comparison import validate_original, grid_coordinates, DESCEND
    model = build_grid_gdp(grid)
    expected = {v.name for v in model.component_data_objects(pyo.Var, descend_into=DESCEND)}
    missing = sorted(expected - variables.keys())
    for name in expected & variables.keys():
        model.find_component(name).set_value(variables[name], skip_validation=True)
    checked = validate_original(model, tolerance=TOLERANCE)
    coordinates = grid_coordinates(model)
    reference, _ = _read_reference(GRID_DIR / (grid + '.csv'))
    value = checked['candidate_objective']
    checked.update(grid_point=coordinates['grid_point'], missing_variables=missing,
                   reference_minimum=min(reference.values()), original_structure_sha256=structure(model)['sha256'])
    checked['has_feasible_solution'] = checked['has_feasible_solution'] and not missing
    checked['normalized_gap'] = None if value is None else value - min(reference.values())
    checked['target_hit'] = bool(checked['has_feasible_solution'] and value - min(reference.values()) <= TOLERANCE)
    return checked


def values(model):
    import pyomo.environ as pyo
    from gdp_models.comparison import DESCEND
    return {v.name: v.value for v in model.component_data_objects(pyo.Var, descend_into=DESCEND)}


def fixed_config(presolve):
    import pyomo.environ as pyo
    from gdp_models.comparison import SOLVER_NAME
    c = pyo.SolverFactory('gdpopt.loa').config()
    c.set_value(dict(subproblem_presolve=presolve, time_limit=60, mip_solver=SOLVER_NAME,
                     nlp_solver=SOLVER_NAME, mip_solver_args={'solver': 'scip', 'mtype': 'mip'},
                     nlp_solver_args={'solver': 'scip', 'mtype': 'nlp'},
                     force_subproblem_nlp=True, init_algorithm='set_covering', bound_tolerance=TOLERANCE))
    return c


def inspect_point(grid, point):
    import pyomo.environ as pyo
    from gdp_models.grid import build_grid_gdp
    from pyomo.contrib.gdpopt.solve_subproblem import preprocess_subproblem
    require((grid, tuple(point)) in POINTS, 'Unapproved fixed configuration')
    witness = build_grid_gdp(grid)
    initial = structure(witness)
    witness.x.set_value(pyo.value(witness.gx[point[0]]))
    witness.y.set_value(pyo.value(witness.gy[point[1]]))
    for choices, selected in zip((witness.Xchoice, witness.Ychoice), point):
        for i, disjunct in choices.items():
            disjunct.indicator_var.set_value(i == selected)
    checked = original_check(grid, values(witness))
    require(initial == structure(witness), 'Witness assignment changed model algebra or bounds')
    model, util = setup(grid, point)
    before = structure(model)
    off, _ = setup(grid, point)
    require(before == structure(off), 'On/off subproblem construction changed')
    c = fixed_config(True)
    out = io.StringIO()
    handler = logging.StreamHandler(out)
    old_level = c.logger.level
    c.logger.addHandler(handler)
    c.logger.setLevel(logging.DEBUG)
    try:
        with preprocess_subproblem(util, c) as allowed:
            default_allowed = bool(allowed)
    finally:
        c.logger.removeHandler(handler)
        c.logger.setLevel(old_level)
    return dict(grid_name=grid, point=list(point), original_witness=checked,
                default_presolve_allows_solver=default_allowed, default_presolve_log=out.getvalue(),
                presolve_disabled_path='solve_subproblem -> call_appropriate_subproblem_solver',
                subproblem_before_option_sha256=before['sha256'],
                subproblem_after_option_sha256=structure(off)['sha256'],
                original_model_structure_sha256=initial['sha256'],
                optimization_calls=0, witness_not_a_returned_solution=True)


def local_inspect(output):
    require(not output.exists(), 'Use a fresh inspect output')
    require(importlib.metadata.version('pyomo') == '6.10.0', 'Diagnostic requires Pyomo 6.10.0')
    verify_package()
    before = module_hashes()
    rows = [inspect_point(g, p) for g, p in POINTS]
    require(all(r['original_witness']['target_hit'] for r in rows), 'Original witness failed')
    require(all(not r['default_presolve_allows_solver'] for r in rows), 'Baseline rejection not reproduced')
    require(before == module_hashes(), 'Pyomo installation changed')
    save(output, dict(status='local_solver_free_only', python=sys.version, platform=sys.platform,
                      pyomo=importlib.metadata.version('pyomo'), pyomo_module_sha256=before,
                      results=rows, actual_fixed_solver_calls=0, actual_full_loa_runs=0,
                      remote_validation='not_run', note='No SCIP or GAMS execution; not a Dantzig result.'))


class ActualConfigCapture(logging.Handler):
    """Read GDPopt's own effective-config log before it starts any solver call."""
    def __init__(self, directory):
        super().__init__()
        self.directory, self.observed = Path(directory), False

    def emit(self, record):
        message = record.getMessage()
        if 'subproblem_presolve:' not in message:
            return
        settings = dict(re.findall(r'^([A-Za-z_]+):\s*(.*?)\s*$', message, re.M))
        (self.directory / 'effective_gdpopt_config.txt').write_text(message + '\n')
        save(self.directory / 'effective_gdpopt_config.json', settings)
        require(settings.get('subproblem_presolve') == 'false', 'Official GDPopt config did not disable subproblem presolve')
        require(settings.get('mip_presolve') == 'true', 'mip_presolve changed')
        self.observed = True


@contextmanager
def actual_config_capture(directory):
    handler = ActualConfigCapture(directory)
    logger = logging.getLogger('pyomo.contrib.gdpopt')
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


def fixed_gate(record):
    check = record.get('original_validation', {})
    return bool(record.get('actual_solver_calls') == 1 and record.get('returned_solution_count', 0) > 0
                and record.get('scip_version_verified') and record.get('subproblem_presolve') is False
                and check.get('has_feasible_solution') and check.get('target_hit'))


def claim_fixed_call(report, directory):
    require(report['actual_solver_calls'] == 0, 'Fixed configuration solver-call cap exceeded')
    report['actual_solver_calls'] += 1
    save(Path(directory) / 'result.json', report)


def guarded_fixed_solve(original, solver, model, kwargs, context, report, directory):
    from grid_recovery import retry_solve
    def attempt(instance, candidate, **options):
        claim_fixed_call(report, directory)
        return original(instance, candidate, **options)
    return retry_solve(attempt, solver, model, kwargs, context)


def fixed_worker(template, method, directory, config, deadline):
    """Invoke official solve_subproblem once; no full GDPopt solve or retry."""
    os.setsid()
    directory = Path(directory)
    from gdp_models import comparison as impl
    from grid_gdp_benchmark import process_identity
    from grid_recovery import POLICY
    from pyomo.contrib.gdpopt.solve_subproblem import solve_subproblem
    from pyomo.common.collections import Bunch
    from pyomo.contrib.gdpopt.util import time_code
    save(directory / 'process.json', process_identity(os.getpid()))
    g, point = template.metadata['grid_name'], template.metadata['diagnostic_point']
    report = dict(grid_name=g, point=point, status='running', subproblem_presolve=False,
                  actual_solver_calls=0, returned_solution_count=0, global_optimality_certified=False,
                  time_limit_s=60, original_network_policy=POLICY,
                  fixed_call_cap=1, retry_note='The preserved network policy has insufficient budget to retry within 60 seconds; a hard one-call guard also applies.')
    save(directory / 'result.json', report)
    with (directory / 'run.log').open('w', buffering=1) as log:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        original_solve = impl.TimedGAMS.solve
        impl.CONTEXT = impl.SolveContext(config['executable'], directory, deadline, TOLERANCE)
        def once(self, model, **kwargs):
            result = guarded_fixed_solve(original_solve, self, model, kwargs, impl.CONTEXT, report, directory)
            report['returned_solution_count'] = len(result.solution)
            save(directory / 'solver_return.json', {'solution_count': len(result.solution),
                 'termination': str(result.solver.termination_condition), 'status': str(result.solver.status),
                 'variables': values(model)})
            return result
        try:
            require((g, tuple(point)) in POINTS, 'Invalid fixed target')
            diagnostic = inspect_point(g, point)
            save(directory / 'baseline_probe.json', diagnostic)
            require(diagnostic['original_witness']['target_hit'] and not diagnostic['default_presolve_allows_solver'],
                    'Original witness/default rejection differs')
            model, util = setup(g, point)
            signature = structure(model)
            save(directory / 'subproblem_structure.json', signature)
            c = fixed_config(False)
            config_text = io.StringIO()
            c.display(ostream=config_text)
            (directory / 'effective_gdpopt_config.txt').write_text(config_text.getvalue())
            save(directory / 'effective_gdpopt_config.json', {'subproblem_presolve': c.subproblem_presolve,
                 'mip_presolve': c.mip_presolve, 'time_limit': c.time_limit, 'force_subproblem_nlp': c.force_subproblem_nlp,
                 'mip_solver_args': c.mip_solver_args.value(), 'nlp_solver_args': c.nlp_solver_args.value()})
            def event(label):
                def callback(solver, subproblem, block):
                    impl.append_event(directory / 'fixed_path.jsonl', {'event': label, 'point': point,
                        'subproblem_presolve': c.subproblem_presolve, 'presolve': 'bypassed_by_official_option',
                        'calls': len(impl.CONTEXT.calls)})
                return callback
            c.call_before_subproblem_solve = event('before_subproblem')
            c.call_after_subproblem_solve = event('after_subproblem')
            c.call_after_subproblem_feasible = event('feasible_subproblem')
            impl.TimedGAMS.solve = once
            solver = SimpleNamespace(timing=Bunch())
            with time_code(solver.timing, 'total', is_main_timer=True):
                termination = solve_subproblem(util, solver, c)
            require(signature == structure(model), 'Solver path changed algebra/bounds')
            returned = read(directory / 'solver_return.json')
            checked = original_check(g, returned['variables'])
            save(directory / 'solution.json', returned)
            log.flush()
            versions = re.findall(r'^SCIP version (.+)$', (directory / 'run.log').read_text(), re.M)
            report.update(status='finished', termination=str(termination), original_validation=checked,
                          objective=checked['candidate_objective'], scip_versions=versions,
                          scip_version_verified=versions == ['9.2.4 (a94f778ac8)'],
                          unchanged_subproblem_structure=True, calls=impl.CONTEXT.calls)
            report['gate_passed'] = fixed_gate(report)
        except Exception as error:
            import traceback
            traceback.print_exc()
            report.update(status='error', message=f'{type(error).__name__}: {error}', gate_passed=False,
                          calls=impl.CONTEXT.calls)
        finally:
            impl.TimedGAMS.solve = original_solve
            save(directory / 'result.json', report)


def full_worker(template, method, directory, config, deadline):
    import gdp_scip_experiments as experiment
    from grid_recovery import install_worker
    require(method == 'loa' and template.metadata['grid_name'] in GRIDS, 'Unapproved full job')
    require(config['diagnostic_presolve_disabled'] is True, 'Diagnostic option not enabled')
    install_worker(experiment)
    with actual_config_capture(directory):
        experiment.worker(template, method, directory, config, deadline)


def fixed_results_pass(rows):
    return len(rows) == 6 and [(r['grid_name'], tuple(r['point'])) for r in rows] == list(POINTS) and all(fixed_gate(r) for r in rows)


def run_sequence(run_dir, c, launch):
    """One fixed attempt per point, then at most three full attempts; never resume."""
    fixed, full = [], []
    for g, point in POINTS:
        print(f'FIXED_START {g} {point}', flush=True)
        row = launch('fixed', g, point, 60)
        fixed.append(row)
        save(run_dir / 'progress.json', {'fixed': fixed, 'full': full})
        print(f'FIXED_DONE {g} {point}; gate={fixed_gate(row)}', flush=True)
        if not fixed_gate(row):
            return {'status': 'stopped_fixed_gate', 'fixed': fixed, 'full': full}
    require(fixed_results_pass(fixed), 'Six fixed configurations did not all pass')
    for g in GRIDS:
        print(f'LOA_START {g}; subproblem_presolve=False', flush=True)
        row = launch('full', g, None, 1800)
        full.append(row)
        save(run_dir / 'progress.json', {'fixed': fixed, 'full': full})
        print(f"LOA_DONE {g}; status={row.get('status')}; objective={row.get('objective')}", flush=True)
    return {'status': 'completed', 'fixed': fixed, 'full': full}


def claim(output_root):
    output_root.mkdir(parents=True, exist_ok=True)
    claim_path = output_root / 'execution_claim.json'
    with claim_path.open('x') as stream:
        json.dump({'created_utc': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid(),
                   'policy': 'One invocation only; no automatic resume or rerun.'}, stream)
    return claim_path


def zero_call_predecessor(repository):
    """Allow this logging correction only after the exact pre-solver failure."""
    policy = read(PACKAGE / 'DIAGNOSTIC_MANIFEST.json')['logging_fix_predecessor']
    archive = Path(repository) / policy['result_relative_path']
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) and z.testzip() is None, 'Invalid predecessor ZIP')
        require(all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in names), 'Unsafe predecessor paths')
        roots = [n[:-len('run.json')] for n in names if n.endswith('/run.json') and n.count('/') == 1]
        require(len(roots) == 1, 'Expected one predecessor run')
        root = roots[0]
        require(all(n.startswith(root) for n in names), 'Multiple predecessor roots')
        for line in z.read(root + 'SHA256SUMS').decode().splitlines():
            digest, name = line.split('  ', 1)
            require(sha(z.read(root + name)) == digest, 'Predecessor checksum mismatch: ' + name)
        require(sha(z.read(root + 'package/DIAGNOSTIC_MANIFEST.json')) == policy['diagnostic_manifest_sha256'],
                'Predecessor was not the original diagnostic package')
        record = json.loads(z.read(root + 'run.json'))
        require(record.get('status') == 'stopped_fixed_gate'
                and record.get('actual_fixed_solver_calls') == 0
                and record.get('actual_full_loa_runs') == 0
                and record.get('full_loa_worker_launches') == 0,
                'Predecessor is not a zero-call stopped diagnostic; no restart permitted')
        require(len(record.get('fixed', [])) == 1 and record.get('full') == [], 'Unexpected predecessor job scope')
        jobs = [n for n in names if n.startswith(root + 'fixed/') and n.endswith('/result.json')]
        require(jobs == [root + 'fixed/holder_table_3_1/result.json'], 'Unexpected predecessor fixed jobs')
        for row in (record['fixed'][0], json.loads(z.read(jobs[0]))):
            require(row.get('grid_name') == 'holder_table' and row.get('point') == [3, 1]
                    and row.get('actual_solver_calls') == 0 and row.get('returned_solution_count') == 0
                    and row.get('gate_passed') is False and row.get('message') == policy['allowed_error'],
                    'Predecessor differs from the reported serialization failure')
        ledger = [json.loads(line) for line in z.read(root + 'launch_ledger.jsonl').decode().splitlines()]
        require(len(ledger) == 1 and ledger[0]['kind'] == 'fixed'
                and ledger[0]['grid_name'] == 'holder_table' and ledger[0]['point'] == [3, 1],
                'Predecessor launch ledger exceeds the zero-call scope')
        for name in names:
            if not name.startswith((root + 'fixed/', root + 'full/')):
                continue
            leaf = Path(name).name
            require(not name.startswith(root + 'full/'), 'Predecessor has full-LOA artifacts')
            require(leaf not in ('solver_return.json', 'solution.json', 'active_solver_call.json'),
                    'Predecessor has solver execution evidence')
            if leaf == 'solver_calls.jsonl':
                require(not z.read(name).strip(), 'Predecessor has solver call records')
            if leaf == 'run.log':
                require(not re.search(rb'^(?:--- Executing |SCIP version )', z.read(name), re.M),
                        'Predecessor log contains an optimizer invocation')
    return {'archive': str(archive), 'sha256': sha(archive.read_bytes()),
            'status': 'verified_serialization_failure_before_any_solver_call',
            'actual_fixed_solver_calls': 0, 'actual_full_loa_runs': 0}


def environment(c, output):
    from grid_gdp_benchmark import runtime
    expected = baseline()['run']['runtime']
    save(output / 'environment_precheck.json', {'python': sys.version, 'platform': sys.platform,
        'host': os.uname().nodename, 'versions': {n: importlib.metadata.version(n) for n in expected['versions']},
        'thread_environment': {n: os.environ.get(n) for n in expected['thread_environment']},
        'gams_executable': c['executable'], 'gams_executable_exists': Path(c['executable']).is_file(),
        'pyomo_modules_sha256': module_hashes()})
    actual = runtime(c, exercise=False)
    save(output / 'environment.json', {'expected': expected, 'actual': actual,
        'pyomo_modules_sha256': module_hashes(), 'pyomo_module_hash_scope': baseline()['pyomo_module_hash_scope'],
        'scip_version_check': 'First actual fixed call; no extra smoke solves.'})
    for key in ('gams_version', 'gams_sha256', 'python', 'versions', 'thread_environment'):
        require(actual[key] == expected[key], 'Environment differs: ' + key)
    require(actual['affinity']['effective_cpus'] == [14], 'CPU differs')
    require(actual['host'].split('.')[0] == 'dantzig', 'Expected Dantzig host')
    require(module_hashes() == baseline()['pyomo_module_sha256'], 'Pyomo module bytes differ from the recorded local 6.10.0 diagnostic reference')
    return actual


def package_result(run_dir, output_root):
    files = sorted(p for p in run_dir.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
    (run_dir / 'SHA256SUMS').write_text(''.join(f'{sha(p.read_bytes())}  {p.relative_to(run_dir)}\n' for p in files))
    path = output_root / (TAG + '_result.zip')
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(run_dir.rglob('*')):
            if p.is_file():
                z.write(p, str(Path(run_dir.name) / p.relative_to(run_dir)))
    Path(str(path) + '.sha256').write_text(f'{sha(path.read_bytes())}  {path.name}\n')
    print('RESULT_ZIP=' + str(path), flush=True)
    return path


def run():
    require(sys.platform == 'linux', 'Actual solves are Dantzig-only; use inspect locally')
    verify_package()
    repository = Path(os.environ.get('GDP_SCIP_REPOSITORY', '/local/scratch/a/lee4382/repository/RBFopt_Test'))
    predecessor = zero_call_predecessor(repository)
    output_root = repository / 'results' / TAG
    claim(output_root)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    run_dir = output_root / ('run_' + stamp)
    run_dir.mkdir()
    print('RUN_DIR=' + str(run_dir), flush=True)
    c = config()
    record = dict(status='starting', config=c, requested_option={'subproblem_presolve': False},
                  review_revision=baseline()['review_revision'], actual_fixed_solver_calls=0, actual_full_loa_runs=0)
    save(run_dir / 'run.json', record)
    save(run_dir / 'predecessor_verification.json', predecessor)
    shutil.copyfile(predecessor['archive'], run_dir / 'predecessor_result.zip')
    shutil.copytree(PACKAGE, run_dir / 'package', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    before = module_hashes()
    try:
        environment(c, run_dir)
        from gdp_compare import run_job
        from gdp_models.grid_benchmark import grid_template
        from gdp_models.comparison import Template
        def launch(kind, grid, point, seconds):
            # Claim each attempt durably before creating its worker; no replay path exists.
            ledger = run_dir / 'launch_ledger.jsonl'
            from gdp_models.comparison import append_event
            append_event(ledger, {'kind': kind, 'grid_name': grid, 'point': point, 'time_limit_s': seconds})
            if kind == 'fixed':
                template = Template(None, {'case': 'grid', 'grid_name': grid, 'instance_id': grid,
                                          'cstr_size': None, 'diagnostic_point': list(point)})
                path = run_dir / 'fixed' / f'{grid}_{point[0]}_{point[1]}'
                worker = fixed_worker
            else:
                template = grid_template(grid)  # New midpoint model; diagnostic solutions are never transferred.
                path = run_dir / 'full' / grid / 'loa'
                worker = full_worker
                save(run_dir / 'initial_templates' / (grid + '.json'),
                     {'values': values(template.model), 'structure': structure(template.model),
                      'metadata': template.metadata})
            row = run_job(template, 'loa', path, {**c, 'time_limit': seconds}, target=worker)
            if kind == 'fixed':
                row['grid_name'], row['point'] = grid, list(point)
                row['gate_passed'] = fixed_gate(row)
            else:
                if (path / 'solution.json').exists():
                    check = original_check(grid, read(path / 'solution.json')['variables'])
                    row['original_validation'] = check
                    row['target_hit'] = check['target_hit']
                    bound = row.get('reported_lower_bound')
                    row['lower_bound_exceeds_known_feasible_reference'] = bound is not None and bound > check['reference_minimum'] + TOLERANCE
                row['global_optimality_certified'] = False
                settings = read(path / 'effective_gdpopt_config.json') if (path / 'effective_gdpopt_config.json').exists() else {}
                row['actual_option_verified'] = settings.get('subproblem_presolve') == 'false' and settings.get('mip_presolve') == 'true'
            save(path / 'result.json', row)
            return row
        outcome = run_sequence(run_dir, c, launch)
        record.update(outcome)
    except Exception as error:
        import traceback
        traceback.print_exc()
        record.update(status='stopped_error', message=f'{type(error).__name__}: {error}')
    finally:
        rows = [read(p) for p in sorted((run_dir / 'fixed').glob('*/result.json'))]
        record['actual_fixed_solver_calls'] = sum(r.get('actual_solver_calls', 0) for r in rows)
        ledger = [json.loads(line) for line in (run_dir / 'launch_ledger.jsonl').read_text().splitlines()] if (run_dir / 'launch_ledger.jsonl').exists() else []
        record['full_loa_worker_launches'] = sum(r['kind'] == 'full' for r in ledger)
        record['actual_full_loa_runs'] = sum((run_dir / 'full' / g / 'loa/effective_gdpopt_config.txt').exists() for g in GRIDS)
        record['pyomo_modules_unchanged'] = module_hashes() == before
        save(run_dir / 'run.json', record)
        from analyze_diagnostic import analyze
        try:
            analyze(run_dir, run_dir / 'analysis')
        except Exception as error:
            save(run_dir / 'analysis_error.json', {'message': f'{type(error).__name__}: {error}'})
        package_result(run_dir, output_root)
    return int(record['status'] != 'completed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['inspect', 'run'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.mode == 'inspect':
        require(args.output is not None, 'inspect requires --output')
        local_inspect(args.output)
        return 0
    require(args.output is None, 'Run output is fixed to the separate diagnostic directory')
    return run()


if __name__ == '__main__':
    raise SystemExit(main())
