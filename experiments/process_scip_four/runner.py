"""One-use Process SCIP experiments, independent of the preserved old runners."""
import argparse
from collections import Counter
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'source'))
os.environ['RBFOPT_GDP_SOURCES'] = str(HERE / 'source/external')
GROUPS = {'minlp': ['bigm', 'hull'], 'ric': ['ric'], 'loa': ['loa'], 'gloa': ['gloa']}
CPU_IDS = [18, 20, 22, 24]
INSTANCES = [f'cstr_{n}' for n in (5, 10, 15, 20, 25, 30)] + ['column', 'small_batch', 'dynamic']


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    from gdp_models.comparison import save_json
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    save_json(path, value)


def verify():
    manifest = read(HERE / 'MANIFEST.json')
    for name, digest in manifest['files_sha256'].items():
        path = (HERE / name).resolve()
        require(path.is_relative_to(HERE) and sha(path.read_bytes()) == digest, 'Package file changed: ' + name)
    config = read(HERE / 'config.json')
    require(config['methods'] == GROUPS[config['group']], 'Incorrect method selection')
    require(config['mip_solver'] == config['nlp_solver'] == config['minlp_solver'] == 'scip', 'Solver changed')
    require(config['threads'] == 1 and config['time_limit'] == 1800 and config['relative_gap'] == 1e-5, 'Budget changed')
    require(config['cpu'] == CPU_IDS[list(GROUPS).index(config['group'])], 'CPU plan changed')
    return config, manifest


def plans(config):
    from gdp_compare import planned_instances
    specs = planned_instances(config)
    require([s['instance_id'] for s in specs] == INSTANCES, 'Process instance set/order differs')
    return specs, [{'instance_id': s['instance_id'], 'method': m} for s in specs for m in config['methods']]


def topology(config):
    from cpu_affinity import cpu_topology
    require(sys.platform == 'linux', 'Actual execution requires the existing Dantzig Linux environment')
    require(set(CPU_IDS) <= os.sched_getaffinity(0), 'The four planned CPUs are not all available in this allocation')
    rows = [cpu_topology(cpu) for cpu in CPU_IDS]
    identities = [(r['physical_package_id'], r['core_id']) for r in rows]
    require(all(a not in (None, '', '-1') and b not in (None, '', '-1') for a, b in identities), 'Missing CPU topology')
    require(len(set(identities)) == 4, 'Package CPUs share a physical core/SMT sibling')
    return {'cpus': rows, 'distinct_physical_cores': True, 'selected_cpu': config['cpu'],
            'policy': 'Separate cores for these four packages; not an exclusive server reservation'}


@contextmanager
def core_lock(record):
    selected = next(r for r in record['cpus'] if r['cpu'] == record['selected_cpu'])
    path = Path(tempfile.gettempdir()) / f"process-scip-{os.getuid()}-socket{selected['physical_package_id']}-core{selected['core_id']}.lock"
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another package using this physical core is active: ' + str(path)) from error
        yield


def environment(config, directory):
    from grid_gdp_benchmark import runtime
    observed = runtime(config, exercise=False)
    expected = read(HERE / 'BASELINE.json')['runtime']
    differences = {k: {'expected': expected[k], 'actual': observed[k]} for k in
                   ('host', 'python', 'gams_version', 'gams_sha256', 'versions', 'thread_environment')
                   if observed[k] != expected[k]}
    if 'gloa' in config['methods'] and observed['mcpp_sha256'] != expected['mcpp_sha256']:
        differences['mcpp_sha256'] = {'expected': expected['mcpp_sha256'], 'actual': observed['mcpp_sha256']}
    save(directory / 'environment.json', {'actual': observed, 'differences': differences,
          'intentional_difference': 'CPU core changes to support four separate packages'})
    require(not differences, 'Dantzig environment differs; see environment.json; no automatic installation')
    return observed


def parse_options(message):
    options, section = {}, None
    for line in message.splitlines():
        match = re.fullmatch(r'([A-Za-z_]+):\s*(.*)', line)
        if match:
            key, value = match.groups()
            options[key] = value or {}
            section = key if not value else None
        elif section and (match := re.fullmatch(r'\s+(\w+):\s*(\S+)', line)):
            options[section][match[1]] = match[2]
    require(options.get('mip_solver_args') == {'mtype': 'mip', 'solver': 'scip'}, 'Actual MIP solver is not SCIP')
    require(options.get('nlp_solver_args') == {'mtype': 'nlp', 'solver': 'scip'}, 'Actual NLP solver is not SCIP/NLP')
    require(options.get('subproblem_presolve') == options.get('mip_presolve') == 'true', 'Original process presolve changed')
    return options


class ConfigFilter(logging.Filter):
    """Filters survive Pyomo's tee handler replacement; no installed code is patched."""
    def __init__(self, directory):
        super().__init__()
        self.directory = directory

    def filter(self, record):
        message = record.getMessage()
        if 'subproblem_presolve:' in message:
            options = parse_options(message)
            (self.directory / 'effective_gdpopt_config.txt').write_text(message.rstrip() + '\n')
            save(self.directory / 'effective_gdpopt_config.json', options)
        return True


@contextmanager
def capture_options(directory):
    logger = logging.getLogger('pyomo.contrib.gdpopt')
    handler = ConfigFilter(directory)
    logger.addFilter(handler)
    try:
        yield
    finally:
        logger.removeFilter(handler)


def worker(template, method, directory, config, deadline):
    from gdp_models import comparison as impl
    from grid_gdp_benchmark import process_identity
    from grid_recovery import retry_solve
    os.setsid()
    save(directory / 'process.json', process_identity(os.getpid()))
    original = impl.TimedGAMS.solve

    def transport(self, model, **kwargs):
        require(kwargs.get('solver') == 'scip', 'Unexpected benchmark solver request')
        return retry_solve(original, self, model, kwargs, impl.CONTEXT)

    with (directory / 'run.log').open('w', buffering=1) as log:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        try:
            impl.TimedGAMS.solve = transport
            save(directory / 'transport_policy.json', {'function': 'grid_recovery.retry_solve',
                 'max_attempts_per_transport_call': 3, 'backoff_s': [5, 15], 'original_deadline': deadline,
                 'whole_job_retries': 0, 'grid_or_fbbt_patches_installed': False})
            with capture_options(directory):
                result = impl.solve_method(template, method, directory, config, deadline)
            result['scip_options'] = list(impl.SCIP_OPTIONS)
            save(directory / 'result.json', result)
        except BaseException as error:
            traceback.print_exc()
            result = read(directory / 'result.json') if (directory / 'result.json').exists() else dict(template.metadata)
            result.update(status='worker_error', message=f'{type(error).__name__}: {error}', global_optimality_certified=False)
            save(directory / 'result.json', result)
            raise
        finally:
            impl.TimedGAMS.solve = original


def compile_model(template, method, output, executable):
    """Compile the actual direct reformulation; action=c never starts an optimizer."""
    from gdp_models.comparison import reformulate
    output.mkdir(parents=True, exist_ok=False)
    model = template.model.clone()
    reformulate(model, method)
    model.write(str(output / 'model.gms'), format='gams', io_options={'solver': 'scip', 'mtype': 'minlp'})
    text = (output / 'model.gms').read_text()
    require('USING minlp' in text and 'option minlp=scip;' in text, 'Incorrect MINLP export')
    command = [executable, 'model.gms', 'action=c', 'lo=3', 'threads=1']
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=output, capture_output=True, text=True, timeout=60)
        log, code = result.stdout + result.stderr, result.returncode
    except subprocess.TimeoutExpired as error:
        log = (error.stdout or b'').decode(errors='replace') + (error.stderr or b'').decode(errors='replace')
        code = None
    (output / 'compile.log').write_text(log)
    row = {'method': method, 'instance_id': template.metadata['instance_id'], 'returncode': code,
           'model_sha256': sha((output / 'model.gms').read_bytes()), 'command': command,
           'wall_s': time.monotonic() - started, 'confirmed_optimizer_starts': len(re.findall(r'^--- Executing ', log, re.M)),
           'gams_banners': re.findall(r'^--- Job model.gms Start (.+)$', log, re.M)}
    row['passed'] = code == 0 and row['confirmed_optimizer_starts'] == 0
    save(output / 'result.json', row)
    require(row['passed'], 'Actual GAMS compilation failed: ' + str(output))
    return row


def preflight(config, directory):
    from gdp_models import comparison as impl
    from gdp_scip_experiments import template_for
    (directory / 'preflight').mkdir()
    checks = ['scip'] if config['group'] == 'minlp' else ['scip_mip', 'scip_nlp']
    print('PREFLIGHT_SOLVERS=' + ','.join(checks), flush=True)
    with (directory / 'preflight/solver.log').open('w') as stream, redirect_stdout(stream), redirect_stderr(stream):
        smoke = impl.smoke_solvers(config['executable'], directory / 'preflight', checks)
    text = (directory / 'preflight/solver.log').read_text()
    versions = sorted(set(re.findall(r'^SCIP version (.+)$', text, re.M)))
    save(directory / 'preflight/solver_checks.json', {'checks': smoke, 'scip_versions': versions,
         'confirmed_scip_invocations': len(re.findall(r'^--- Executing SCIP \(', text, re.M))})
    require(versions == ['9.2.4 (a94f778ac8)'], 'SCIP version differs from the original Dantzig run')
    templates, compilation = {}, []
    for spec in plans(config)[0]:
        name = spec['instance_id']
        print('PREFLIGHT_TEMPLATE=' + name, flush=True)
        template = template_for(spec)
        templates[name] = template
        save(directory / 'preflight/templates' / (name + '.json'), template.metadata)
        if config['group'] == 'minlp':
            for method in config['methods']:
                print(f'COMPILE_ONLY={name}/{method}', flush=True)
                compilation.append(compile_model(template, method, directory / 'preflight/compile' / name / method, config['executable']))
    save(directory / 'preflight/compilation.json', compilation)
    return templates


def verify_solution(directory, spec, row):
    """Independent original GDP check, with no solver or FBBT invocation."""
    if not (directory / 'solution.json').exists():
        return {'original_gdp_feasible': False, 'reason': 'No saved returned variable vector'}
    from gdp_models.models import build_gdp, _discretize_dynamic, _initialize
    from solution_audit import verify_solution as audit
    model = build_gdp(spec['case'], cstr_size=spec['cstr_size'] or 30)
    if spec['case'] == 'dynamic':
        _discretize_dynamic(model)
    _initialize(model, spec['case'], spec['cstr_size'] or 30, 'auto')
    try:
        return audit(model, read(directory / 'solution.json'), row)
    except Exception as error:
        return {'original_gdp_feasible': False, 'reason': f'{type(error).__name__}: {error}'}


def evidence(job, row, reference):
    calls = [json.loads(line) for line in (job / 'solver_calls.jsonl').read_text().splitlines()] if (job / 'solver_calls.jsonl').exists() else []
    active = read(job / 'active_solver_call.json') if (job / 'active_solver_call.json').exists() else None
    log = (job / 'run.log').read_text(errors='replace') if (job / 'run.log').exists() else ''
    counts = Counter(f"{c['solver']}/{c['mtype']}" for c in calls)
    value = row.get('original_validation', {}).get('objective_recomputed')
    feasible = row.get('original_validation', {}).get('original_gdp_feasible', False)
    lower = row.get('reported_lower_bound')
    target_tolerance = 1e-5 * max(1, abs(reference))
    result = {'journaled_calls': dict(counts), 'started_interface_attempts': len(calls) + bool(active),
              'confirmed_scip_invocations': len(re.findall(r'^--- Executing SCIP \(', log, re.M)),
              'active_unjournaled_call': active, 'reference': reference,
              'target_hit': bool(feasible and value is not None and abs(value - reference) <= target_tolerance),
              'target_attained': bool(feasible and value is not None and value <= reference + target_tolerance),
              'lower_bound_exceeds_known_reference': lower is not None and lower > reference + target_tolerance,
              'target_rule': 'abs(objective-reference) <= 1e-5*max(1,abs(reference))',
              'actual_gdpopt_entry': bool(re.search(r'^Starting GDPopt version .+ using ', log, re.M)),
              'actual_gdpopt_options_saved': (job / 'effective_gdpopt_config.json').exists()}
    return result


@contextmanager
def heartbeat(label, job):
    started = time.monotonic()

    def report(signum, frame):
        active = ''
        try:
            call = read(job / 'active_solver_call.json')
            active = f"; call={call['index']}; type={call['mtype']}"
        except (OSError, ValueError):
            pass
        print(f'RUNNING {label}; elapsed={time.monotonic()-started:.0f}s{active}', flush=True)

    # No background thread exists when the original watchdog forks its worker.
    # POSIX interval timers are not inherited by the forked solver worker.
    previous_handler = signal.signal(signal.SIGALRM, report)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, 60, 60)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


def execute(config, directory, templates, run):
    from gdp_compare import run_job
    from gdp_models.comparison import append_event
    from grid_gdp_benchmark import seal_benchmark
    references = read(HERE / 'BASELINE.json')['references']
    planned = plans(config)[1]
    specs = {s['instance_id']: s for s in plans(config)[0]}
    rows = []
    for item in planned:
        name, method = item['instance_id'], item['method']
        job = directory / 'benchmark' / name / method
        require(not job.exists(), 'Never replace/retry an existing benchmark job')
        append_event(directory / 'launch_ledger.jsonl', {**item, 'time_limit_s': 1800})
        (directory.parent / 'current_job.txt').write_text(str(job) + '\n')
        print(f'START {name}/{method}; cpu={config["cpu"]}; solver=SCIP', flush=True)
        with heartbeat(name + '/' + method, job):
            row = run_job(templates[name], method, job, config, target=worker)
        # Keep the original worker result before adding independently checked fields.
        shutil.copyfile(job / 'result.json', job / 'worker_result.json')
        row['original_validation'] = verify_solution(job, specs[name], row)
        row['execution_evidence'] = evidence(job, row, references[name])
        row['global_optimality_certified'] = False
        row['certificate_note'] = 'Returned feasibility/target and reported solver termination are separate; global certification requires post-run review.'
        save(job / 'result.json', row)
        seal_benchmark(job)
        rows.append(row)
        summary = {'planned_jobs': len(planned), 'completed_jobs': len(rows), 'results': rows,
                   'target_hits': sum(r['execution_evidence']['target_hit'] for r in rows),
                   'verified_solutions': sum(r['original_validation']['original_gdp_feasible'] for r in rows),
                   'actual_gdpopt_runs': sum(r['execution_evidence']['actual_gdpopt_entry'] for r in rows)}
        save(directory / 'summary.json', summary)
        run['completed_jobs'] = len(rows)
        save(directory / 'run.json', run)
        print(f"DONE {name}/{method}; status={row['status']}; termination={row.get('termination')}; objective={row.get('objective')}; {len(rows)}/{len(planned)}", flush=True)
    return rows


def pack(directory, tag):
    """Keep all result/scratch evidence used by terminal seals; never omit gams-* wholesale."""
    files = sorted(p for p in directory.rglob('*') if p.is_file() and not p.is_symlink()
                   and p.name not in {'.lock', 'SHA256SUMS'} and not p.name.endswith(('.tmp', '.pyc'))
                   and '__pycache__' not in p.parts)
    inventory = ''.join(f'{sha(p.read_bytes())}  {p.relative_to(directory)}\n' for p in files)
    archive = directory.parent / (tag + '_result.zip')
    require(not archive.exists(), 'Result archive already exists; refusing to overwrite')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for path in files:
            z.write(path, directory.name + '/' + str(path.relative_to(directory)))
        z.writestr(directory.name + '/SHA256SUMS', inventory)
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None, 'Result ZIP CRC failure')
    archive.with_suffix('.zip.sha256').write_text(sha(archive.read_bytes()) + '  ' + archive.name + '\n')
    (directory.parent / 'result_zip.txt').write_text(str(archive) + '\n')
    print('RESULT_ZIP=' + str(archive), flush=True)


def run(config, manifest):
    from gdp_compare import environment as thread_environment
    thread_environment()
    repository = Path(os.environ.get('GDP_SCIP_REPOSITORY', '/local/scratch/a/lee4382/repository/RBFopt_Test'))
    output = repository / 'results' / config['output_tag']
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'execution_claim.json').open('x') as stream:
        json.dump({'created_utc': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid()}, stream)
    directory = Path(tempfile.mkdtemp(prefix='run_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_', dir=output))
    (output / 'run_dir.txt').write_text(str(directory) + '\n')
    print('RUN_DIR=' + str(directory), flush=True)
    run_record = {'status': 'starting', 'config': config, 'created_utc': datetime.now(timezone.utc).isoformat(),
                  'baseline_revision': manifest['baseline_revision'], 'completed_jobs': 0,
                  'time_policy': '1800 seconds per complete job; transport retries share the same deadline; preflight separate'}
    save(directory / 'run.json', run_record)
    shutil.copytree(HERE, directory / 'package', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'launch.log'))
    try:
        cpu = topology(config)
        save(directory / 'cpu_plan.json', cpu)
        with core_lock(cpu):
            run_record['runtime'] = environment(config, directory)
            save(directory / 'run.json', run_record)
            print('ENVIRONMENT=verified; CPU=' + str(config['cpu']), flush=True)
            templates = preflight(config, directory)
            run_record['preflight_status'] = 'passed'
            save(directory / 'run.json', run_record)
            print('PREFLIGHT=passed', flush=True)
            rows = execute(config, directory, templates, run_record)
            run_record['status'] = 'completed'
            run_record['jobs_with_error'] = sum(r['status'] in {'error', 'worker_error', 'subproblem_incomplete'} for r in rows)
    except BaseException as error:
        traceback.print_exc()
        run_record.update(status='stopped_error', message=f'{type(error).__name__}: {error}')
    finally:
        save(directory / 'run.json', run_record)
        pack(directory, config['output_tag'])
    return int(run_record['status'] != 'completed' or run_record.get('jobs_with_error', 0) > 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['plan', 'run'])
    args = parser.parse_args()
    config, manifest = verify()
    if args.mode == 'plan':
        print(json.dumps({'config': config, 'jobs': plans(config)[1], 'optimization_calls': 0}, indent=2))
        return 0
    return run(config, manifest)


if __name__ == '__main__':
    raise SystemExit(main())
