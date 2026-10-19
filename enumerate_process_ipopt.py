"""Full DFO-box process evaluations; shared implementation for two entry points.

The historical evaluator still owns model preparation, solving and acceptance.
Instrumentation measures failed preparation stages without bypassing them.
No GDPopt enumeration, objective lookup, cross-coordinate warm start or retry.
"""
import argparse
import csv
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import shutil
from time import perf_counter
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / 'results/ipopt_dfo_non_cstr_20261015_172428_o671edu_/inputs'
CASES = {'column': ([7, 1], [15, 9], 64, 29), 'dynamic': ([1, 2], [9, 9], 37, 37)}
REFERENCE_HASHES = {
    'column': {'evaluations.csv': '5e04eb22463a91fb8165b8f76af357d1cea8ea3913c1efbe7249eee6686e0ab8',
               'manifest.json': '433b5fe194358bf847f6e3a5263e7612ef871ea37be247792f2c0d1e5f07be4c'},
    'dynamic': {'evaluations.csv': '1e6a615a2170fc2bd68d8d3e05f7c3ad4eb9c7c9c6cdbcfaab61f19ade24b3e2',
                'manifest.json': '3f5c3d6a1307fcdb022ae51b5e15fd8c0699ff3064f856135f422951deba9747'},
}
APPROVED_CHANGED_ADAPTERS = {
    'evaluation.py': '98eda90acea6fc70d26192020972d9b9917b5802a06239aa4a92ad42a9aa19f5',
    'solvers.py': 'bdc1a4c52c65128cda618c9b64be28a53abea557f3f5a4e4e975a77e57085d1d',
    'preflight.py': 'fca788f4312c463fc169754470a1859cd1558fe36b87610e79739e183b870e56',
}
# PR #23/main commit 5a9e704 carries the reviewed GAMS executable routing fix.
# Keep the original frozen-run profile above and admit only these exact newer
# bytes. Models, initialization, options and acceptance checks are unchanged.
MAIN_ROUTING_ADAPTERS = {
    'evaluation.py': '1ee3dda18a4031a3c9c039c3270d8225da7bbd4eb8f8d31d844d8111667ffa84',
    'solvers.py': 'cd1c88cb8ec66dceac2bb4f17dcd38e40fb5b3cf0891ad93298002f879040f06',
}
# PR #30 only distinguishes logical rejection metadata from preprocessing;
# original models, initialization, options and acceptance remain unchanged.
REJECTION_PHASE_ADAPTERS = {
    'models.py': '1dddc02ee1463c03c1b041dfaf83444171765514e570ab8da7bf26d3ec2e9c23',
    'evaluation.py': 'cb9d5cb77e8bf48b72665ffeafcfb0e0c00d3ac0656def725a294a21a1a4c18e',
}
EXTRA_FIELDS = ['logical_allowed', 'reflux_tray', 'boilup_tray', 'legacy_status',
    'failure_stage', 'logic_wall_s', 'original_total_wall_s', 'instrumented_call_wall_s',
    'solver_called', 'validation_performed', 'primal_feasible', 'acceptance_failure',
    'mathematical_infeasibility_claim', 'exception_type']
CONFIG = {'solver': 'gams_ipopt', 'initialization': 'auto', 'time_limit_s': 60.0,
          'feasibility_tolerance': 1e-5}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def allowed(case, point):
    return point[0] >= 8 and point[1] <= 8 if case == 'column' else point[0] < point[1] or tuple(point) == (9, 9)


def plan(case, **unused):
    lower, upper, logical, _ = CASES[case]
    points = [list(p) for p in itertools.product(*(range(lo, hi + 1) for lo, hi in zip(lower, upper)))]
    return {'case': case, 'cstr_size': None, 'domain': 'dfo_box', 'bounds': list(map(list, zip(lower, upper))),
            'points': points, 'box_count': len(points), 'candidate_count': len(points),
            'logical_candidate_count': logical, 'excluded_by_logic': len(points) - logical,
            'logical_rule': 'x1>=8 and x2<=8' if case == 'column' else 'x1<x2 or (x1,x2)==(9,9)'}


def reference_root():
    return ROOT / 'reference' if (ROOT / 'reference').is_dir() else REFERENCE


def verify_sources(case):
    """Read-only provenance check; no model construction or solver invocation."""
    from gdp_models._sources import provenance
    folder = reference_root() / case
    for name, digest in REFERENCE_HASHES[case].items():
        require(sha(folder / name) == digest, f'Historical reference changed: {case}/{name}')
    baseline = read(folder / 'manifest.json')
    prior = baseline['runtime']
    upstream = 'dsda-gdp' if case == 'column' else 'ld-sda-dynamic'
    require(provenance(upstream, prior['source']['files_sha256']) == prior['source'], 'Upstream model/initialization changed')
    differences = {}
    for name in ('__init__.py', '_sources.py', 'models.py', 'domains.py', 'evaluation.py', 'solvers.py', 'preflight.py'):
        digest = sha(ROOT / 'gdp_models' / name)
        old = prior['adapter_sha256'][name]
        if digest != old:
            require(digest in {APPROVED_CHANGED_ADAPTERS.get(name), MAIN_ROUTING_ADAPTERS.get(name), REJECTION_PHASE_ADAPTERS.get(name)},
                    f'Unreviewed adapter change: {name}')
            differences[name] = {'historical_sha256': old, 'current_sha256': digest}
            if MAIN_ROUTING_ADAPTERS.get(name) == digest:
                differences[name]['reviewed_change'] = '5a9e704: effective GAMS executable routing and reporting'
            if REJECTION_PHASE_ADAPTERS.get(name) == digest:
                differences[name]['reviewed_change'] = 'PR #30: logical rejection exception subtype and rejection_phase metadata'
    return baseline, differences


def runtime_identity(case, cstr_size, initialization, solver, executable):
    from gdp_models import models
    from gdp_models.preflight import dependency_versions
    from gdp_models.solvers import optimizer_for, solve_options, option_file_lines
    import platform
    import shutil
    baseline, differences = verify_sources(case)
    prior = baseline['runtime']
    require(dependency_versions() == prior['dependency_versions'], 'Use the original GDP environment; dependency versions differ')
    require(platform.python_version() == prior['python_version'], 'Original Python 3.11.16 is required')
    binary = shutil.which(executable or '/package/gams/52.2/gams')
    require(binary is not None, 'GAMS executable missing')
    binary = str(Path(binary).resolve())
    require(sha(binary) == prior['solver_executable_sha256'], 'GAMS binary differs from the historical run')
    optimizer = optimizer_for('gams_ipopt', binary)
    require(optimizer.available(exception_flag=False), 'GAMS unavailable')
    version = list(optimizer.version())
    require(version == prior['solver_version'], 'GAMS version differs')
    initialized, _ = models.initialization_info(case, 5, 'auto')
    require(initialized == prior['initialization'], 'Initialization differs')
    code_files = [ROOT / name for name in ('enumerate_process_ipopt.py', 'enumerate_column_ipopt.py',
                                         'enumerate_dynamic_ipopt.py')]
    code_files += sorted((ROOT / 'gdp_models').glob('*.py'))
    bundled = read(ROOT / 'bundle_provenance.json') if (ROOT / 'bundle_provenance.json').exists() else None
    commit = bundled['git_commit'] if bundled else subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    return {'solver_executable': binary, 'solver_executable_sha256': sha(binary), 'solver_version': version,
            'expected_ipopt_version': '3.14.19', 'expected_mumps_version': '5.8.1',
            'solver_interface': 'gams_shell', 'gams_solver': 'ipopt', 'source': prior['source'],
            'initialization': initialized, 'dependency_versions': dependency_versions(),
            'python_version': platform.python_version(), 'host': platform.node(),
            'effective_cpu': sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
            'git_commit': commit, 'code_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in code_files},
            'reference_sha256': REFERENCE_HASHES[case], 'adapter_differences': differences,
            'solver_options': solve_options('gams_ipopt', 60.0), 'solver_option_file': option_file_lines('gams_ipopt'),
            'thread_environment': {k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')},
            'preflight_solver_calls': 0}


def classify(report, logical):
    legacy = report['status']
    term = report.get('termination', '')
    if legacy == 'accepted':
        return 'accepted'
    if legacy == 'preprocessing_infeasible':
        return 'preprocessing_infeasible' if logical else 'logical_infeasible'
    if report.get('gams_solve_status') == 3 or term in ('maxTimeLimit', 'maxTime', 'resourceInterrupt'):
        return 'time_limit'
    if legacy == 'exception':
        return 'exception'
    return 'ipopt_failed'


def evaluate(case, point, **kwargs):
    from gdp_models import evaluation, models
    # Match the historical procedure: common Dynamic construction is outside
    # each coordinate clock. Clone + fixed-mode logic remain inside it.
    if case == 'dynamic':
        models.dynamic_template()
    started = perf_counter()
    stage = {'failure_stage': None, 'logic_wall_s': None, 'preprocess_wall_s': None,
             'solver_called': False, 'solve_wall_s': 0.0}
    original_prepare, original_fbbt = evaluation.prepare_nlp, models.fbbt
    original_solve = evaluation.solve_gams
    fix_name = '_fix_static' if case == 'column' else '_fix_dynamic'
    original_fix = getattr(models, fix_name)

    def measured_fix(*args, **options):
        clock = perf_counter()
        try:
            return original_fix(*args, **options)
        except Exception:
            stage['failure_stage'] = 'logic'
            raise
        finally:
            stage['logic_wall_s'] = perf_counter() - clock

    def measured_fbbt(*args, **options):
        clock = perf_counter()
        try:
            return original_fbbt(*args, **options)
        except Exception:
            stage['failure_stage'] = 'preprocessing'
            raise
        finally:
            stage['preprocess_wall_s'] = perf_counter() - clock

    def measured_prepare(*args, **options):
        clock = perf_counter()
        try:
            return original_prepare(*args, **options)
        except Exception:
            stage['failure_stage'] = stage['failure_stage'] or 'setup'
            # Measured elapsed preparation minus its measured FBBT component.
            stage['setup_wall_s'] = perf_counter() - clock - (stage['preprocess_wall_s'] or 0)
            raise

    def measured_solve(*args, **options):
        stage['solver_called'] = True
        clock = perf_counter()
        try:
            return original_solve(*args, **options)
        except Exception as error:
            stage['failure_stage'] = 'solver'
            stage['exception_type'] = type(error).__name__
            raise
        finally:
            stage['solve_wall_s'] = perf_counter() - clock

    try:
        with patch.object(evaluation, 'prepare_nlp', measured_prepare), patch.object(models, fix_name, measured_fix), \
                patch.object(models, 'fbbt', measured_fbbt), patch.object(evaluation, 'solve_gams', measured_solve):
            report = evaluation.evaluate_point(case, point, **kwargs)
    except Exception as error:
        import traceback
        traceback.print_exc()
        report = {'case': case, 'point': list(point), 'cstr_size': None, 'solver': 'gams_ipopt',
                  'status': 'exception', 'accepted': False, 'objective': None, 'candidate_objective': None,
                  'termination': 'error', 'exception_type': type(error).__name__, 'message': str(error)}
    elapsed = perf_counter() - started
    logical = allowed(case, point)
    raw_status = report['status']
    report.update(legacy_status=raw_status, status=classify(report, logical), logical_allowed=logical,
                  original_total_wall_s=report.get('total_wall_s'), total_wall_s=elapsed,
                  instrumented_call_wall_s=elapsed, logic_wall_s=stage['logic_wall_s'],
                  failure_stage=stage['failure_stage'], mathematical_infeasibility_claim=False)
    if stage.get('exception_type'):
        report.update(status='exception', exception_type=stage['exception_type'])
    for key in ('setup_wall_s', 'preprocess_wall_s'):
        if report.get(key) is None:
            report[key] = stage.get(key)
    report['solver_called'] = stage['solver_called']
    if report.get('solve_wall_s') is None:
        report['solve_wall_s'] = stage['solve_wall_s']
    report['validation_performed'] = raw_status in ('accepted', 'rejected')
    violation = report.get('max_primal_violation')
    report['primal_feasible'] = (violation is not None and violation <= 1e-5) if report['validation_performed'] else None
    report['acceptance_failure'] = None if report['accepted'] else (
        'status/objective/primal checks not all satisfied' if report['validation_performed'] else 'no validated solver solution')
    if not report.get('initialization'):
        report['initialization'] = models.initialization_info(case, 5, 'auto')[0]
    if case == 'column':
        report.update(reflux_tray=point[0] + 1, boilup_tray=point[1] + 1)
    if not logical and report['accepted']:
        report.update(status='exception', accepted=False, objective=None,
                      exception_type='LogicalConsistencyError',
                      message='Original model unexpectedly accepted a logically excluded coordinate')
    report['total_wall_s'] = report['instrumented_call_wall_s'] = perf_counter() - started
    return report


def compare_and_validate(case, directory):
    from gdp_models.batch import _load_records, _write_json
    directory = Path(directory)
    protocol = plan(case)
    records = _load_records(directory, protocol, 'gams_ipopt')
    require(sha(reference_root() / case / 'evaluations.csv') == REFERENCE_HASHES[case]['evaluations.csv'],
            'Historical comparison CSV changed during the run')
    with (reference_root() / case / 'evaluations.csv').open(newline='') as stream:
        old = {tuple(json.loads(r['point'])): r for r in csv.DictReader(stream)}
    comparisons = []
    for record in records.values():
        prior = old.get(tuple(record['point']))
        value = float(prior['objective']) if prior and prior['objective'] else None
        current = record.get('objective')
        comparisons.append({'point': json.dumps(record['point']), 'old_record_exists': prior is not None,
            'old_status': prior['status'] if prior else None, 'new_status': record['status'],
            'new_legacy_status': record['legacy_status'], 'old_accepted': prior['accepted'] if prior else None,
            'new_accepted': record['accepted'], 'acceptance_changed': prior is not None and (prior['accepted'] == 'True') != record['accepted'],
            'old_objective': value, 'new_objective': current,
            'objective_difference': current - value if current is not None and value is not None else None,
            'old_termination': prior['termination'] if prior else None, 'new_termination': record.get('termination'),
            'old_solver_status': prior['solver_status'] if prior else None, 'new_solver_status': record.get('solver_status'),
            'old_total_wall_s': prior['total_wall_s'] if prior else None, 'new_total_wall_s': record['total_wall_s']})
    if comparisons:
        temp = directory / 'comparison.csv.tmp'
        with temp.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(comparisons[0]))
            writer.writeheader()
            writer.writerows(comparisons)
        temp.replace(directory / 'comparison.csv')
    with (directory / 'evaluations.csv').open(newline='') as stream:
        exported = list(csv.DictReader(stream))
    require(len(exported) == len(records) and len({r['point'] for r in exported}) == len(records), 'CSV missing/duplicate rows')
    require(all(math.isfinite(r['total_wall_s']) and r['total_wall_s'] > 0 for r in records.values()), 'Missing/invalid total time')
    versions = sorted(set(re.findall(r'Ipopt version ([\d.]+), running with linear solver MUMPS ([\d.]+)',
                                     (directory / 'run.log').read_text())))
    versions = [[v[0], v[1].rstrip('.')] for v in versions]
    summary = read(directory / 'summary.json')
    summary.update(expected_rows=protocol['candidate_count'], missing_rows=protocol['candidate_count'] - len(records),
        duplicate_rows=0, missing_total_times=0, expected_historical_accepted=CASES[case][3],
        accepted_count_matches_history=summary['accepted_points'] == CASES[case][3],
        acceptance_changes=sum(r['acceptance_changed'] for r in comparisons), observed_ipopt_mumps_versions=versions,
        solver_release_matches_history=(versions == [['3.14.19', '5.8.1']]) if versions else None,
        accepted_count_is_not_an_acceptance_target=True)
    _write_json(directory / 'summary.json', summary)
    return summary


def run_case(case, directory, *, resume=False, max_points=None, executable=None):
    from gdp_models import batch
    directory = Path(directory)
    # Reuse the existing atomic checkpoints, exclusive lock and explicit loop.
    with patch.object(batch, 'enumeration_plan', plan), patch.object(batch, 'evaluate_point', evaluate), \
            patch.object(batch, '_runtime_identity', runtime_identity), \
            patch.object(batch, 'CSV_FIELDS', batch.CSV_FIELDS + EXTRA_FIELDS), \
            patch.object(batch, 'ERROR_STATUSES', {'ipopt_failed', 'time_limit', 'exception'}):
        try:
            batch.run_batch(case, directory, solver='gams_ipopt', initialization='auto', time_limit=60.0,
                feasibility_tolerance=1e-5, executable=executable, resume=resume, max_points=max_points, tee=True,
                progress=lambda r, s: print(f"[{s['completed_points']}/{s['candidate_count']}] {r['point']} "
                                           f"{r['status']} objective={r.get('objective')} total={r['total_wall_s']:.6f}s", flush=True))
        except KeyboardInterrupt:
            if (directory / 'evaluations.csv').exists() and (directory / 'summary.json').exists():
                compare_and_validate(case, directory)
            raise
        compare_and_validate(case, directory)
    return read(directory / 'summary.json')


def snapshot_bundle(directory):
    """Preserve the exact executable bundle; refuse a changed bundle on resume."""
    require((ROOT / 'RUNNER_SHA256SUMS').exists(), 'Use the supplied standalone ZIP launcher')
    for line in (ROOT / 'RUNNER_SHA256SUMS').read_text().splitlines():
        digest, relative = line.split('  ', 1)
        require(sha(ROOT / relative) == digest, 'Bundle checksum mismatch: ' + relative)
        target = Path(directory) / 'reproduction' / relative
        if target.exists():
            require(sha(target) == digest, 'Resume bundle differs: ' + relative)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
    shutil.copyfile(ROOT / 'RUNNER_SHA256SUMS', Path(directory) / 'reproduction/RUNNER_SHA256SUMS')


def pack_run(directory):
    directory = Path(directory).resolve()
    require((directory / 'reproduction/bundle_provenance.json').exists(), 'Not a result directory from this bundle')
    archive = directory.with_suffix('.zip')
    temporary = archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(directory.rglob('*')):
            if path.is_file() and not path.name.endswith(('.tmp', '.lock')):
                z.write(path, directory.name + '/' + path.relative_to(directory).as_posix())
    temporary.replace(archive)
    archive.with_suffix('.zip.sha256').write_text(f'{sha(archive)}  {archive.name}\n')
    print(f'RESULT_DIR={directory}\nRESULT_ZIP={archive}', flush=True)


def main(case):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--executable', default=os.environ.get('GAMS_BIN', '/package/gams/52.2/gams'))
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--max-points', type=int)
    parser.add_argument('--dry-run', action='store_true', help='List coordinates only; no solver call or file writes')
    parser.add_argument('--check', action='store_true', help='Validate sources/environment; no NLP solver invocation')
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(plan(case), indent=2))
        return 0
    if args.check:
        print(json.dumps(runtime_identity(case, 5, 'auto', 'gams_ipopt', args.executable), indent=2))
        return 0
    if args.output_dir is None:
        parser.error('--output-dir is required')
    try:
        summary = run_case(case, args.output_dir, resume=args.resume, max_points=args.max_points, executable=args.executable)
    except KeyboardInterrupt:
        print('Interrupted; reuse --output-dir with --resume. Completed records will not be solved again.', file=sys.stderr)
        return 130
    print(json.dumps(summary, indent=2))
    return 0
