"""One explicitly allocated GAMS/IPOPT W03 check; prepare/verify never solve."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import zipfile

from review_comparison.common import csvrows, writecsv
from . import feasibility as f
from . import feasibility_followup as prior
from . import feasibility_tautology as identities
from .common import ROOT, environment, read, save, sha
from .replay import sources_match

INPUT = ROOT / "results/review_feasibility_followup_20261020"
LOCAL = ROOT / "results/review_feasibility_tautology_20261020"
HISTORY = "results/archives/dantzig_gdp_gams_20260922_050038_p4q8hy54.zip"
HISTORY_SHA = "e406b8fae2a90191835eb7332d483c719ebb1675d14d3b0e6d3bf5f7789a197b"
ALLOCATION = "cstr15-w03-gams52-20261021-one-call"
OPTIONS = {
    "tol": "1e-10", "constr_viol_tol": "1e-10", "acceptable_iter": "0",
    "bound_relax_factor": "0", "honor_original_bounds": "yes",
    "nlp_scaling_method": "none", "max_iter": "3000",
    "warm_start_init_point": "no", "linear_solver": "mumps",
}
THREADS = dict.fromkeys(("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS",
                        "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "GOTO_NUM_THREADS",
                        "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "NUMEXPR_MAX_THREADS"), "1")
THREADS.update(OMP_DYNAMIC="FALSE", MKL_DYNAMIC="FALSE")
SOURCES = tuple(dict.fromkeys((*identities.SOURCES, "review_diagnostics/cstr15_gams.py",
                               "gdp_models/solvers.py", "gdp_models/preflight.py")))
DOC_URL = "https://www.gams.com/52/docs/S_IPOPT.html#IPOPT_SPECIFICATION_OF_OPTIONS"


def now():
    return datetime.now(timezone.utc).isoformat()


def historical_environment():
    path = ROOT / HISTORY
    if sha(path) != HISTORY_SHA:
        raise ValueError("Historical GAMS archive hash mismatch")
    with zipfile.ZipFile(path) as z:
        member = next(n for n in z.namelist() if n.endswith('/run.json'))
        runtime = json.loads(z.read(member))["runtime"]["gams_ipopt/cstr_15"]
        log_member = member.removesuffix('run.json') + 'gams_ipopt/cstr_15/run.log'
        log = z.read(log_member).decode()
        versions = set(re.findall(r"This is Ipopt version (\d+(?:\.\d+)+), running with linear solver MUMPS (\d+(?:\.\d+)+)", log))
        if len(versions) != 1:
            raise ValueError("Historical IPOPT/MUMPS versions are ambiguous")
        ipopt, mumps = next(iter(versions))
        return {"archive": HISTORY, "archive_sha256": HISTORY_SHA, "runtime_member": member,
                "runtime_member_sha256": hashlib.sha256(z.read(member)).hexdigest(),
                "log_member": log_member, "log_member_sha256": hashlib.sha256(z.read(log_member)).hexdigest(),
                "runtime": runtime, "ipopt_version": ipopt, "mumps_version": mumps}


def check_sealed(directory):
    manifest = read(directory / 'manifest.json')
    for name, digest in manifest['outputs_sha256'].items():
        if sha(directory / name) != digest:
            raise ValueError(f"Historical output changed: {directory / name}")
    return sha(directory / 'manifest.json')


def inputs(directory):
    # This does not call the AMPL-specific verifier or inspect its local solver.
    prior_manifest = check_sealed(directory)
    local_manifest = check_sealed(LOCAL)
    reference, before, provenance = f.verify_input(directory)
    if provenance['model']['commit'] != '3e469dbeea8931670b8cd6752014ab7a767d3af5':
        raise ValueError('Unexpected CSTR model revision')
    checks = prior.fixed_model_check(reference, before)
    nlp, proof = identities.preprocess(reference)
    from gdp_models.comparison import pyo
    expected = read(LOCAL / 'nl_comparison.json')
    counts = {}
    for label, model in [('before', f.prepare_fixed_nlp(reference)), ('after', nlp)]:
        constraints = list(model.component_data_objects(pyo.Constraint, active=True, descend_into=True))
        variables = list(model.component_data_objects(pyo.Var, descend_into=True))
        counts[label] = {'variables': sum(not v.fixed for v in variables),
                         'constraints': len(constraints), 'equalities': sum(c.equality for c in constraints)}
        if counts[label] != {k: expected[label][k] for k in counts[label]}:
            raise ValueError('Model counts differ from the retained identity preprocessing')
    audit = ROOT / 'reproduction/data/algebraic_audit/table8_bound_audit.csv'
    rows = [r for r in csvrows(audit) if r['instance_id'] == 'cstr_15' and r['method'] in {'gloa', 'hull'}]
    if len(rows) != 2 or {r['method'] for r in rows} != {'gloa', 'hull'}:
        raise ValueError('Missing/ambiguous CSTR15 GLOA/Hull audit records')
    bounds = {r['method']: {'audit_id': r['audit_id'], 'lower_bound': float(r['reported_lower_bound']),
                            'source_result': r['result_local_path'], 'source_result_sha256': r['result_sha256']} for r in rows}
    for row in bounds.values():
        if sha(audit.parent / row['source_result']) != row['source_result_sha256']:
            raise ValueError('Bound source record hash mismatch')
    evidence = {'prior_manifest_sha256': prior_manifest, 'local_manifest_sha256': local_manifest,
                'model': provenance, 'fixed_model_check': checks, 'counts': counts, 'bounds': bounds,
                'audit_sha256': sha(audit), 'local_summary': read(LOCAL / 'summary.json'),
                'original_execution_provider_revision': read(directory / 'selection.json')['original_execution_provider_revision']}
    return reference, nlp, before, proof, evidence


def write_gams(model, output):
    """Pure writer, with explicit maps for every active row and free variable."""
    from pyomo.repn.plugins.gams_writer import ProblemWriter_gams
    from gdp_models.comparison import pyo, DESCEND
    output.mkdir(parents=True, exist_ok=False)
    file = output / 'model.gms'
    original = identities.inventory(model)
    _, smap = ProblemWriter_gams()(model, str(file), lambda _: True, {
        'solver': 'ipopt', 'mtype': 'nlp', 'warmstart': True, 'solvelink': 5,
        'skip_trivial_constraints': False, 'output_fixed_variables': False,
        'put_results': 'results', 'put_results_format': 'dat',
        'add_options': ['option reslim=290;', 'option iterlim=3000;', 'option threads=1;', 'GAMS_MODEL.optfile=1;'],
    })
    text = file.read_text()
    # More decimal places in exported primal levels; no model expression changes.
    text = text.replace('results.nd=15;', 'results.nd=17;').replace('results.nw=21;', 'results.nw=26;')
    file.write_text(text)
    if identities.inventory(model) != original:
        raise ValueError('GAMS writer mutated the model')
    variables = {label: {'name': v.name, 'start': v.value, 'fixed': v.fixed,
                         'lower': v.lb, 'upper': v.ub, 'domain': str(v.domain)}
                 for label, v in smap.bySymbol.items() if v.is_variable_type()}
    all_vars = list(model.component_data_objects(pyo.Var, descend_into=DESCEND))
    exported = {v['name'] for v in variables.values()}
    fixed = {v.name: v.value for v in all_vars if v.fixed and v.name not in exported}
    missing = [v.name for v in all_vars if not v.fixed and v.name not in exported]
    if missing or any(v['fixed'] for v in variables.values()):
        raise ValueError('Unexplained GAMS free-variable omission or fixed-variable export: ' + str(missing))
    starts = dict(re.findall(r'^(\w+)\.l = ([^;]+);$', text, re.M))
    for label, row in variables.items():
        if label not in starts or not math.isclose(float(starts[label]), row['start'], rel_tol=1e-15, abs_tol=0):
            raise ValueError('W03 start missing or changed in GAMS input: ' + label)
    constraints = {label: c for label, c in smap.bySymbol.items() if c.ctype is pyo.Constraint}
    expected = {c.name for c in model.component_data_objects(pyo.Constraint, active=True, descend_into=True)}
    if {c.name for c in constraints.values()} != expected:
        raise ValueError('GAMS writer changed the active algebraic constraint set')
    equations = re.findall(r'^(\w+)\.\.', text, re.M)
    rows = {}
    for label, c in constraints.items():
        symbols = [label] if c.equality else ([label + '_lo'] if c.lower is not None else []) + ([label + '_hi'] if c.upper is not None else [])
        if not set(symbols).issubset(equations):
            raise ValueError('Constraint absent from GAMS output: ' + c.name)
        rows[c.name] = symbols
    objectives = [label for label, c in smap.bySymbol.items() if c.ctype is pyo.Objective]
    if set(equations) != {e for row in rows.values() for e in row} | set(objectives):
        raise ValueError('Unexpected GAMS equation')
    if len(re.findall(r'^SOLVE ', text, re.M)) != 1 or 'option nlp=ipopt;' not in text:
        raise ValueError('Expected exactly one explicit NLP=IPOPT solve')
    (output / 'ipopt.opt').write_text(''.join(f'{key} {value}\n' for key, value in OPTIONS.items()))
    return {'variables': variables, 'fixed_values_substituted': fixed, 'constraints': rows,
            'objective_equations': objectives, 'exported_free_variables': len(variables),
            'gams_equations_including_objective': len(equations),
            'note': 'Fixed variables are substituted by the Pyomo writer; GAMS adds an objective variable/equality; internal solver presolve counts are recorded separately.'}


def inspect_environment(executable, history):
    """Read files only; never available(), license probes, -v, or smoke solves."""
    runtime = history['runtime']
    binary = Path(executable).resolve(strict=True)
    if platform.system() != 'Linux' or not os.access(binary, os.X_OK):
        raise ValueError('Execution requires the existing Dantzig Linux GAMS installation')
    if sha(binary) != runtime['solver_executable_sha256']:
        raise ValueError('GAMS binary differs from the historical 52.2.0 binary; no replacement is permitted')
    versions = {name: importlib.metadata.version(name) for name in runtime['dependency_versions']}
    if versions != runtime['dependency_versions'] or platform.python_version() != runtime['python_version']:
        raise ValueError(f'Historical Python/dependency mismatch: {platform.python_version()}, {versions}')
    for key, value in THREADS.items():
        if os.environ.get(key) != value:
            raise ValueError('Missing single-thread environment: ' + key)
    if len(os.sched_getaffinity(0)) != 1:
        raise ValueError('Select one idle CPU with taskset before preparing or running')
    support = [p for p in binary.parent.glob('*') if p.is_file() and any(s in p.name.lower() for s in ('ipopt', 'icp', 'mumps', 'gmscmp'))]
    definitions = [p for p in support if p.name.lower() == 'optipopt.def']
    if not definitions:
        raise ValueError('Missing installed optipopt.def; option support cannot be checked without a solve')
    definition = definitions[0].read_text(errors='replace')
    if any(not re.search(r'\b' + re.escape(key) + r'\b', definition) for key in OPTIONS):
        raise ValueError('Installed IPOPT option definition does not contain every requested option')
    return {'environment': environment(), 'verified_historical_dependency_versions': versions,
            'host': platform.node(), 'gams_executable': str(binary),
            'gams_sha256': sha(binary), 'gams_version_from_matching_historical_binary': runtime['solver_version'],
            'support_files_sha256': {str(p): sha(p) for p in support},
            'option_definition': str(definitions[0]), 'option_documentation': DOC_URL,
            'threads': {k: os.environ[k] for k in THREADS}, 'affinity': sorted(os.sched_getaffinity(0)),
            'ipopt_mumps_version_confirmation': 'Pending the sole actual solve log; no version/license trial was run'}


def source_hashes():
    return {name: sha(ROOT / name) for name in SOURCES}


def _prepare(directory, output, executable, ledger):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if Path(ledger).exists():
        raise FileExistsError('This one-call allocation is already consumed: ' + str(ledger))
    history = historical_environment()
    reference, nlp, before, proof, evidence = inputs(Path(directory))
    mapping = write_gams(nlp, output / 'solver_input')
    save(output / 'before_solution.json', f.vector(reference))
    save(output / 'before_residuals.json', before)
    save(output / 'identity_proof.json', proof)
    save(output / 'gams_mapping.json', mapping)
    save(output / 'input_evidence.json', evidence)
    save(output / 'historical_environment.json', history)
    runtime = inspect_environment(executable, history)
    save(output / 'environment.json', runtime)
    if (ROOT / 'PACKAGE_MANIFEST.json').is_file():
        shutil.copyfile(ROOT / 'PACKAGE_MANIFEST.json', output / 'package_manifest.json')
    for name in SOURCES:
        path = output / 'execution_sources' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    revision = read(ROOT / 'PACKAGE_MANIFEST.json').get('code_revision') if (ROOT / 'PACKAGE_MANIFEST.json').exists() else subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    save(output / 'selection.json', {'allocation': ALLOCATION, 'created_utc': now(), 'code_revision': revision,
         'input_relative_to_repository': str(Path(directory).resolve().relative_to(ROOT)),
         'output_directory': str(output), 'allocation_ledger': str(Path(ledger).resolve()),
         'target': {'instance': 'cstr_15', 'witness': 'W03', 'original_GDP_residual': 1e-8},
         'call_limit': 1, 'external_wall_limit_s': 300, 'gams_reslim_s': 290, 'ipopt_options': OPTIONS,
         'source_sha256': source_hashes(), 'historical_execution_provider_revision': evidence['original_execution_provider_revision']})
    files = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
    save(output / 'preflight.json', {'passed': True, 'solver_calls': 0, 'files_sha256': files})
    seal(output, 'prepared')
    return output


def prepare(directory, output, executable, ledger):
    output = Path(output).resolve()
    existed = output.exists()
    try:
        return _prepare(directory, output, executable, ledger)
    except Exception as error:
        # Preserve only this new preparation attempt, never a previous result.
        if not existed and output.is_dir():
            save(output / 'preparation_failure.json', {
                'status': 'blocked_before_solver', 'actual_new_NLP_calls': 0,
                'error': f'{type(error).__name__}: {error}', 'created_utc': now(),
                'environment': environment(), 'source_sha256': source_hashes(),
            })
            (output / 'README.md').write_text(
                '# Preparation stopped before any solver call\n\n'
                'See `preparation_failure.json` for the specific blocker.\n'
                'No installation, replacement environment or automatic retry was attempted.\n')
            seal(output, 'blocked_before_solver')
        raise


def verify_preflight(directory, check_runtime=False):
    preflight = read(directory / 'preflight.json')
    if preflight.get('passed') is not True:
        raise ValueError('Preflight not completed')
    for name, digest in preflight['files_sha256'].items():
        if sha(directory / name) != digest:
            raise ValueError('Prepared input changed: ' + name)
    selection = read(directory / 'selection.json')
    current_sources = source_hashes()
    if selection['source_sha256'] != current_sources:
        # Replay may use pinned verifier fixes; execution still requires the
        # exact sources recorded when this solver input was prepared.
        if check_runtime or not sources_match(current_sources, selection['source_sha256']):
            raise ValueError('Diagnostic source differs from prepared source')
    if check_runtime:
        expected = read(directory / 'environment.json')
        actual = inspect_environment(expected['gams_executable'], read(directory / 'historical_environment.json'))
        if actual != expected:
            raise ValueError('Server environment changed after preparation')
    return selection


def claim_call(directory, ledger):
    # Global ledger is outside the output, preventing reruns with a new output name.
    record = {'allocation': ALLOCATION, 'started_utc': now(), 'output_directory': str(directory),
              'charged_NLP_calls': 1, 'automatic_retries': 0}
    with Path(ledger).open('x') as stream:
        json.dump(record, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    with (directory / 'solver_call.json').open('x') as stream:
        json.dump(record, stream, indent=2)
    return record


def worker(directory):
    selection = verify_preflight(directory, check_runtime=True)
    if (directory / 'solver_call.json').exists():
        raise FileExistsError('Solver already called')
    runtime = read(directory / 'environment.json')
    claim_call(directory, selection['allocation_ledger'])
    command = [runtime['gams_executable'], 'model.gms', 'lo=3', 'o=model.lst', 'reslim=290', 'threads=1']
    started = time.perf_counter()
    result = {'command': command, 'returncode': None, 'error': None}
    try:
        with (directory / 'solver_input/gams.log').open('x') as log:
            # Inherit the worker process group; the controller kills all descendants.
            child = subprocess.run(command, cwd=directory / 'solver_input', stdout=log, stderr=subprocess.STDOUT)
        result['returncode'] = child.returncode
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    result['wall_s'] = time.perf_counter() - started
    save(directory / 'worker_result.json', result)


def bounded_worker(command, directory, seconds=300):
    started = time.perf_counter()
    with (directory / 'worker.log').open('x') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, cwd=ROOT)
        timeout = False
        try:
            code = child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(child.pid, signal.SIGKILL)
            code = child.wait()
        except BaseException:
            # Interruptions must not leave an orphaned solver running.
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise
    return {'command': command, 'returncode': code, 'timed_out': timeout,
            'wall_s': time.perf_counter() - started, 'external_wall_limit_s': seconds}


def read_dat(path, expected=None):
    rows = {}
    for line in path.read_text().splitlines()[1:]:
        parts = line.split()
        if not parts or (expected is not None and parts[0] not in expected):
            continue
        if len(parts) < 2 or parts[0] in rows:
            raise ValueError('Missing or duplicate DAT value: ' + line)
        try:
            number = float(parts[1])
        except ValueError as exc:
            raise ValueError('Non-numeric DAT value: ' + line) from exc
        if not math.isfinite(number):
            raise ValueError('Nonfinite DAT value: ' + line)
        rows[parts[0]] = number
    if expected is not None and set(rows) != set(expected):
        raise ValueError('Incomplete returned vector; no starting values may fill missing free variables')
    return rows


def read_statistics(path):
    from gdp_models.solvers import read_gams_statistics
    # Auxiliary statistics such as OBJEST can legitimately be NA for local NLPs.
    # Candidate acceptance still requires known MODELSTAT/SOLVESTAT below.
    return read_gams_statistics(path)


def log_evidence(text, history):
    banners = re.findall(r'This is Ipopt version (\d+(?:\.\d+)+), running with linear solver (\w+) (\d+(?:\.\d+)+)', text)
    starts = re.findall(r'--- Executing IPOPT \(', text)
    iterations = re.findall(r'Number of Iterations\.+:\s*(\d+)', text)
    echoed = {key: {'value': value, 'used': used} for key, value, used in re.findall(r'^\s*(\w+)\s*=\s*(\S+)\s+(yes|no)\s*$', text, re.M)}
    option_errors = [line for line in text.splitlines() if re.search(r'(?i)(invalid option|unknown option|not a valid option|error.*option|option.*(ignored|unrecognized))', line)]
    matches = True
    for name, requested in OPTIONS.items():
        value = echoed.get(name, {}).get('value')
        try:
            equal = float(value) == float(requested)
        except (ValueError, TypeError):
            equal = value == requested
        matches &= equal
    expected = (history['ipopt_version'], 'MUMPS', history['mumps_version'])
    return {'solver_entry_count': len(starts), 'banners': banners, 'iterations': iterations,
            'option_echo': echoed, 'option_errors': option_errors,
            'environment_and_options_confirmed': len(starts) == 1 and banners == [expected] and matches and not option_errors,
            'exit_messages': re.findall(r'^EXIT:.*$', text, re.M),
            'too_few_dof': 'TOO_FEW_DOF' in text or 'Too few degrees of freedom' in text}


def returned_vector(directory, mapping, stats, log):
    if stats.get('MODELSTAT') not in {1, 2, 5, 6, 7, 8} or stats.get('SOLVESTAT') not in {1, 2, 3, 4}:
        raise ValueError('Raw GAMS status does not identify a returned candidate')
    if not log['iterations'] or not log['exit_messages'] or log['too_few_dof']:
        raise ValueError('No completed IPOPT iterate evidence; initial levels are not a returned solution')
    values = read_dat(directory / 'solver_input/results.dat', mapping['variables'])
    by_name = {row['name']: values[label] for label, row in mapping['variables'].items()}
    by_name.update(mapping['fixed_values_substituted'])
    return {'variables': by_name}


def bound_comparisons(check, bounds, eligible):
    objective = check['objective'] if check else None
    result = {}
    for method, record in bounds.items():
        lower = record['lower_bound']
        delta = lower - objective if objective is not None else None
        tau = 1e-5 * max(1, abs(objective)) if objective is not None else None
        rho = delta / tau if delta is not None else None
        result[method] = {**record, 'objective': objective, 'delta': delta, 'tau': tau, 'rho': rho,
                          'rho_gt_1': rho > 1 if rho is not None else None,
                          'tightened_bound_discrepancy_persists': rho > 1 if eligible else None}
    return result


def assess(directory):
    history = read(directory / 'historical_environment.json')
    mapping = read(directory / 'gams_mapping.json')
    before = read(directory / 'before_residuals.json')
    evidence = read(directory / 'input_evidence.json')
    execution = read(directory / 'execution.json')
    text = (directory / 'solver_input/gams.log').read_text(errors='replace') if (directory / 'solver_input/gams.log').exists() else ''
    logged = log_evidence(text, history)
    stats, solution, checked, error = {}, None, None, None
    try:
        stats = read_statistics(directory / 'solver_input/resultsstat.dat')
        if execution['timed_out']:
            raise ValueError('External 300-second timeout; no retry permitted')
        result = read(directory / 'worker_result.json')
        if result['returncode'] != 0 or result['error']:
            raise ValueError('GAMS worker failed: ' + str(result))
        solution = returned_vector(directory, mapping, stats, logged)
        reference, _ = f.restore(solution)
        if set(solution['variables']) != set(f.vector(reference)['variables']):
            raise ValueError('Returned/fixed variable mapping does not cover original GDP')
        _, checked = identities.original_check(reference, before['discrete_configuration'])
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        solution, checked = None, None
    passed = bool(checked and checked['numerically_feasible_under_stated_residual_test'])
    protocol = bool(logged['environment_and_options_confirmed'] and not execution['timed_out'])
    summary = {'actual_new_NLP_calls': int((directory / 'solver_call.json').exists()),
               'returned_solution': solution is not None, 'raw_gams_statistics': stats,
               'tightened_feasibility_passed': passed, 'execution_protocol_confirmed': protocol,
               'objective': checked['objective'] if checked else None,
               'maximum_unscaled_original_GDP_violation': checked['maximum_unscaled_primal_violation'] if checked else None,
               'bounds': bound_comparisons(checked, evidence['bounds'], passed and protocol),
               'log_evidence': logged, 'error': error,
               'status': 'passed' if passed and protocol else 'failed_or_unconfirmed',
               'new_benchmark_runs': 0, 'new_fit_or_annealing_calls': 0,
               'interpretation': 'Fixed-configuration numerical evidence only; not exact feasibility, global optimality, solver-defect proof, or reproduction of LOA/BARON.'}
    return summary, solution, checked


def seal(directory, status):
    files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file() and p.name != 'manifest.json'}
    save(directory / 'manifest.json', {'status': status, 'files_sha256': files, 'created_utc': now()})


def report(directory, summary):
    before = read(directory / 'before_residuals.json')
    local = read(directory / 'input_evidence.json')['local_summary']['assessment']
    rows = [{'record': 'original_W03', 'objective': before['objective'], 'maximum_unscaled_violation': before['maximum_unscaled_primal_violation'], 'passes_1e_8': before['maximum_unscaled_primal_violation'] <= 1e-8},
            {'record': 'retained_local_AMPL_IPOPT', 'objective': local['objective'], 'maximum_unscaled_violation': local['maximum_unscaled_primal_violation'], 'passes_1e_8': local['tightened_feasibility_passed']},
            {'record': 'new_Dantzig_GAMS_IPOPT', 'objective': summary['objective'], 'maximum_unscaled_violation': summary['maximum_unscaled_original_GDP_violation'], 'passes_1e_8': summary['tightened_feasibility_passed']}]
    writecsv(directory / 'comparison.csv', rows)
    writecsv(directory / 'bound_comparison.csv', [{'method': key, **row} for key, row in summary['bounds'].items()])
    lines = ['# CSTR15 W03 GAMS/IPOPT single-call check', '',
             f"The actual charged NLP call count is {summary['actual_new_NLP_calls']} and the assessment status is `{summary['status']}`.",
             f"Returned objective: `{summary['objective']}`; maximum unscaled original-GDP violation: `{summary['maximum_unscaled_original_GDP_violation']}`.",
             f"The `1e-8` numerical check passed: `{summary['tightened_feasibility_passed']}`; requested environment/options confirmed: `{summary['execution_protocol_confirmed']}`.",
             'The original W03 vector was the start; the retained local polished vector was used only in the comparison table.',
             'Historical benchmark records, point costs and execution-provider revisions are unchanged, and this diagnostic time is not added to performance comparisons.',
             'See `environment.json`, `historical_environment.json`, `solver_input/gams.log`, the listing, raw DAT files and `summary.json` for environment differences and raw statuses.',
             'The old local experiment used AMPL/IPOPT 3.12.13 on macOS; this allocation requests the recorded Dantzig GAMS/IPOPT/MUMPS installation and does not require matching objectives or iterations.',
             'Model-level and writer-level row/variable counts are recorded separately in `input_evidence.json` and `gams_mapping.json`.',
             'Fixed values substituted in GAMS are explicitly mapped; missing free values are never filled from the starting vector.',
             '', '## Draft reviewer/manuscript wording', '']
    if summary['tightened_feasibility_passed'] and summary['execution_protocol_confirmed']:
        lines.append(f"A single additional fixed-configuration GAMS/IPOPT check from the retained CSTR15 W03 start returned objective {summary['objective']} with maximum unscaled original-GDP violation {summary['maximum_unscaled_original_GDP_violation']}, below the numerical threshold of 1e-8.")
        for method, row in summary['bounds'].items():
            lines.append(f"For the retained {method.upper()} lower bound, delta={row['delta']}, tau={row['tau']} and rho={row['rho']}; rho>1 is {row['rho_gt_1']}.")
    else:
        lines.append('The single allocated Dantzig check did not establish a point satisfying both the requested execution protocol and the 1e-8 independent original-GDP residual test; the tightened bound comparison remains unestablished.')
    lines += ['This is numerical evidence for one fixed configuration, not a proof of exact feasibility, global optimality or a solver defect.',
              'These are draft sentences only; no manuscript or Overleaf file was edited.', '', '## Solver-free recheck', '', '```bash',
              'python -m review_diagnostics.cstr15_gams verify --directory /path/to/returned/result --output /path/to/new/verification.json', '```', '']
    (directory / 'README.md').write_text('\n'.join(lines))


def run(directory):
    directory = Path(directory).resolve()
    selection = verify_preflight(directory, check_runtime=True)
    if Path(selection['allocation_ledger']).exists() or (directory / 'solver_call.json').exists():
        raise FileExistsError('One-call allocation already consumed')
    with (directory / 'run_started.json').open('x') as stream:
        json.dump({'created_utc': now(), 'automatic_retries': 0}, stream)
    execution = bounded_worker([sys.executable, '-m', 'review_diagnostics.cstr15_gams', '_worker', '--directory', str(directory)], directory)
    save(directory / 'execution.json', execution)
    summary, solution, residuals = assess(directory)
    save(directory / 'summary.json', summary)
    if solution is not None:
        save(directory / 'solution.json', solution)
        save(directory / 'residuals.json', residuals)
    report(directory, summary)
    seal(directory, summary['status'])
    return summary


def equivalent(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equivalent(a[k], b[k]) for k in a)
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    if type(a) is bool or type(b) is bool:
        return a is b
    if isinstance(a, (float, int)) and isinstance(b, (float, int)):
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
    return a == b


def verify(directory):
    directory = Path(directory).resolve()
    manifest = read(directory / 'manifest.json')
    for name, digest in manifest['files_sha256'].items():
        if sha(directory / name) != digest:
            raise ValueError('Result hash mismatch: ' + name)
    if manifest['status'] == 'blocked_before_solver':
        return {'blocked_before_solver': True, 'new_solver_calls': 0,
                'failure': read(directory / 'preparation_failure.json')}
    selection = verify_preflight(directory)
    reference, nlp, before, proof, evidence = inputs(ROOT / selection['input_relative_to_repository'])
    if not equivalent(before, read(directory / 'before_residuals.json')) or proof != read(directory / 'identity_proof.json'):
        raise ValueError('Original W03 or exact identity proof differs')
    if not equivalent(evidence, read(directory / 'input_evidence.json')):
        raise ValueError('Input model/audit/provenance differs')
    if manifest['status'] == 'prepared':
        return {'prepared_input_verified': True, 'new_solver_calls': 0, 'executed': False}
    summary, solution, residuals = assess(directory)
    if not equivalent(summary, read(directory / 'summary.json')):
        raise ValueError('Saved summary disagrees with independent replay')
    if solution is not None:
        if solution != read(directory / 'solution.json') or not equivalent(residuals, read(directory / 'residuals.json')):
            raise ValueError('Saved returned vector or residuals disagree')
    elif (directory / 'solution.json').exists():
        raise ValueError('No returned solution but a solution file exists')
    return {'verified': True, 'new_solver_calls': 0, 'summary': summary}


def pack(directory):
    directory = Path(directory).resolve()
    target = directory.with_name(directory.name + '_return_' + str(time.time_ns()) + '.zip')
    archive_hashes = {}
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                relative = str(path.relative_to(directory))
                archive_hashes[relative] = sha(path)
                z.write(path, directory.name + '/' + relative)
        z.writestr(directory.name + '/RETURN_MANIFEST.json', json.dumps({
            'created_utc': now(), 'files_sha256': archive_hashes,
            'note': 'Includes post-run verification reports; original result manifest is unchanged.'}, indent=2) + '\n')
    target.with_suffix('.zip.sha256').write_text(sha(target) + '  ' + target.name + '\n')
    print('RESULT_DIR=' + str(directory))
    print('RESULT_ZIP=' + str(target))
    return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['prepare', 'run', 'verify', 'pack', '_worker'])
    p.add_argument('--input', type=Path, default=INPUT)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--gams', type=Path)
    p.add_argument('--allocation-ledger', type=Path)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    if args.mode == 'prepare':
        if args.gams is None or args.allocation_ledger is None:
            p.error('prepare requires --gams and --allocation-ledger')
        prepare(args.input, args.directory, args.gams, args.allocation_ledger)
        print('PREPARED; no solver invoked: ' + str(args.directory))
    elif args.mode == 'run':
        print(json.dumps(run(args.directory), indent=2))
    elif args.mode == '_worker':
        worker(args.directory.resolve())
    elif args.mode == 'verify':
        if args.output is None or args.output.exists():
            p.error('verify requires a new --output file')
        save(args.output, verify(args.directory))
        print('VERIFIED without a solver: ' + str(args.output))
    else:
        pack(args.directory)


if __name__ == '__main__':
    main()
