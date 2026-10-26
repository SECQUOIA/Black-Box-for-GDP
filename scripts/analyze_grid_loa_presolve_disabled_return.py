"""Audit the stopped presolve-disabled return using recorded bytes only."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = 'grid_loa_presolve_disabled_20261025_v2_result.zip'
EXPECTED_SHA256 = '303012e48a2480ddcabb5388fe2a7d1c6f83082795484bd13b7f0130671a1b1a'
DELIVERY = 'grid_loa_presolve_disabled_dantzig_20261025_v2'
BASE = '9bedaca03fd74e8c9962876982140cd943875570'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def verified_members(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        require(z.testzip() is None and len(names) == len(set(names)), 'Corrupt or duplicate ZIP members')
        require(all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in names), 'Unsafe ZIP paths')
        roots = [n[:-len('run.json')] for n in names if n.endswith('/run.json') and n.count('/') == 1]
        require(len(roots) == 1 and all(n.startswith(roots[0]) for n in names), 'Unexpected archive roots')
        prefix = roots[0]
        files = {n[len(prefix):]: z.read(n) for n in names}
    inventory = dict((n, digest) for digest, n in
                     (line.split('  ', 1) for line in files['SHA256SUMS'].decode().splitlines()))
    require(set(inventory) == {n for n in files if Path(n).name != 'SHA256SUMS'}, 'Incomplete result inventory')
    require(all(sha(files[n]) == digest for n, digest in inventory.items()), 'Result hash mismatch')
    return files, len(inventory)


def call_evidence(result, calls, log, listing):
    """An interface attempt is not a confirmed execution of the SCIP optimizer."""
    return {
        'interface_call_attempts': result['actual_solver_calls'],
        'journaled_interface_calls': len(calls),
        'gams_job_starts': len(re.findall(r'^--- Job model\.gms Start ', log, re.M)),
        'confirmed_scip_invocations': len(re.findall(r'^--- Executing SCIP \(', log, re.M)),
        'returned_solution_count': result['returned_solution_count'],
        'gams_compilation_error_61_abs_in_nlp': 'the function ABS is not smooth, use DNLP' in listing
            and 'SOLVE GAMS_MODEL USING nlp' in listing and '$61,256' in listing,
        'failure_stage': 'gams_compilation' if '*** Status: Compilation error(s)' in log else 'unclassified',
        'gams_interface_wall_s': sum(c['wall_s'] for c in calls),
        'worker_wall_s': result['worker_wall_s'],
    }


def analyze(output):
    require(not output.exists(), 'Use a fresh analysis directory')
    data = (ROOT / 'results/archives' / ARCHIVE).read_bytes()
    require(sha(data) == EXPECTED_SHA256, 'Unexpected returned archive')
    files, count = verified_members(data)
    previous, previous_count = verified_members(files['predecessor_result.zip'])
    def read(name):
        return json.loads(files[name])
    run = read('run.json')
    previous_run = json.loads(previous['run.json'])
    source = ROOT / 'results/grid_loa_presolve_disabled_20261025_v2' / (DELIVERY + '.zip')
    source_hash = json.loads((source.parent / 'BUILD_MANIFEST.json').read_text())['package_sha256']
    require(sha(source.read_bytes()) == source_hash, 'Original v2 delivery changed')
    with zipfile.ZipFile(source) as z:
        for name in z.namelist():
            relative = name[len(DELIVERY) + 1:]
            require(files['package/' + relative] == z.read(name), 'Executed source changed: ' + relative)
    require(sha(files['predecessor_result.zip']) == read('predecessor_verification.json')['sha256'],
            'Predecessor archive mismatch')
    require(previous_run['actual_fixed_solver_calls'] == previous_run['actual_full_loa_runs'] == 0,
            'Unexpected predecessor solver calls')
    prefix = 'fixed/holder_table_3_1/'
    result = read(prefix + 'result.json')
    calls = [json.loads(line) for line in files[prefix + 'solver_calls.jsonl'].decode().splitlines()]
    events = [json.loads(line) for line in files[prefix + 'fixed_path.jsonl'].decode().splitlines()]
    log, listing = (files[prefix + n].decode() for n in ('run.log', 'call_00001_error.lst'))
    evidence = call_evidence(result, calls, log, listing)
    settings = read(prefix + 'effective_gdpopt_config.json')
    require(settings['subproblem_presolve'] is False and settings['mip_presolve'] is True,
            'Unexpected actual options')
    require(settings['nlp_solver_args'] == {'solver': 'scip', 'mtype': 'nlp'}, 'Changed solver route')
    require(evidence['interface_call_attempts'] == evidence['journaled_interface_calls'] == evidence['gams_job_starts'] == 1,
            'Unexpected call accounting')
    require(evidence['confirmed_scip_invocations'] == evidence['returned_solution_count'] == 0
            and evidence['gams_compilation_error_61_abs_in_nlp'], 'Unexpected failure stage')
    require(run['fixed'] == [result] and run['full'] == [] and run['status'] == 'stopped_fixed_gate'
            and run['actual_full_loa_runs'] == run['full_loa_worker_launches'] == 0, 'Stopping rule differs')
    require(not any(n.startswith('full/') for n in files)
            and not any(n.endswith('/solver_return.json') or n.endswith('/solution.json') for n in files),
            'Unexpected solution or full-run evidence')
    env = read('environment.json')
    for key in ('host', 'python', 'gams_version', 'gams_sha256', 'affinity', 'versions', 'thread_environment'):
        require(env['actual'][key] == env['expected'][key], 'Environment differs: ' + key)
    require(run['pyomo_modules_unchanged'], 'Pyomo modules changed')
    require(len(events) == 1 and events[0]['event'] == 'before_subproblem'
            and events[0]['subproblem_presolve'] is False, 'Disabled path did not enter evaluation')
    baseline = read('package/BASELINE.json')
    compared = []
    for row in baseline['jobs']:
        compared.append(dict(grid_name=row['grid_name'], prior_objective=row['objective_recomputed'],
            prior_termination=row['termination'], prior_max_violation=row['max_original_violation'],
            prior_worker_s=row['worker_wall_s'], prior_target_hit=row['target_hit_verified'],
            new_full_loa_status='not_run', new_objective=None, new_max_violation=None,
            new_target_hit=None, new_full_loa_worker_s=None))
    summary = dict(status=run['status'], **evidence, actual_full_loa_runs=0,
        fixed_configurations_attempted=1, fixed_configurations_not_run=5,
        fixed_gates_passed=0, subproblem_presolve=False, mip_presolve=True,
        presolve_bypass_entered_evaluation=True, original_gdp_returned_solution=None,
        effect_on_full_loa='not_evaluated', scip_runtime_version_verified=False,
        scip_version_note='Historical 9.2.4; no current SCIP banner because GAMS compilation stopped first.',
        additional_solver_calls_during_analysis=0, new_runner_prepared=False,
        retry_performed=False, original_21_results_replaced=False)
    output.mkdir(parents=True)
    save(output / 'summary.json', summary)
    save(output / 'comparison.json', compared)
    save(output / 'environment.json', env)
    save(output / 'fixed_configurations.json', read('analysis/fixed_configurations.json'))
    # Preserve the exact returned evidence, separately from the interpretation.
    raw = output / 'evidence'
    raw.mkdir()
    for name in ('run.json', 'launch_ledger.jsonl', 'predecessor_verification.json'):
        (raw / name).write_bytes(files[name])
    for name, content in files.items():
        if name.startswith(prefix):
            (raw / Path(name).name).write_bytes(content)
    (raw / 'predecessor_run.json').write_bytes(previous['run.json'])
    table = '\n'.join(f"| {r['grid_name']} | {r['prior_objective']:.12g} | {r['prior_termination']} | {r['prior_max_violation']} | {r['prior_worker_s']:.3f} | Not run |" for r in compared)
    (output / 'README.md').write_text('''# Presolve-disabled LOA diagnostic: stopped before SCIP execution

The v2 return stopped on holder_table [3,1] during GAMS compilation.
The official subproblem_presolve=False option was applied and the before_subproblem event was recorded.
The retained GAMS mtype=nlp route rejected the ABS function in equation c3_hi with errors 61 and 256 before SCIP started.
The initial preprocessing rejection in run.log belongs to the separate default-presolve probe, not to the disabled-presolve call.
This result confirms entry past the known preprocessing rejection but does not establish successful solution of the subproblem or any full LOA improvement.

There was one solver-interface attempt and one GAMS job, zero confirmed SCIP invocations, zero returned solutions and zero full LOA runs.
The remaining five fixed configurations were not attempted after the first gate failed.
The runner field actual_fixed_solver_calls counts interface attempts, so its value of one must not be described as one completed SCIP solve.
The first delivery's serialization failure is also preserved inside the returned ZIP and made zero interface calls.
''' + f"The v2 GAMS interface call took {evidence['gams_interface_wall_s']:.6f} seconds and its fixed worker took {evidence['worker_wall_s']:.6f} seconds.\n" + '''
| Problem | Prior objective | Prior termination | Prior maximum violation | Prior worker seconds | New full LOA |
| --- | ---: | --- | ---: | ---: | --- |
''' + table + '''

New objectives, residuals, target outcomes and full-run timings are unavailable and are not replaced by reference-witness values or zeros.
The baseline optimal strings do not certify original-GDP global optimality, and their known target misses remain preserved.
This is a stopped selective diagnostic, not a three-problem performance result or a replacement of the 21-problem benchmark.

The server host, Python, Pyomo 6.10.0, GAMS 52.2.0 executable hash, CPU 14 affinity and single-thread settings match the recorded baseline.
The installed Pyomo module hashes remained unchanged.
SCIP 9.2.4 is the historical version, but this failed call produced no fresh SCIP banner and cannot verify its runtime version.
The actual effective options and original GDP witness are retained under evidence without treating the witness as a returned solver solution.

The earlier 42-test validation covered mocked solver boundaries and did not test whether GAMS could compile this ABS-containing model as NLP.
That validation gap was missed during package preparation and is the reason the corrected package still failed immediately on the server.
The earlier ConfigDict serialization error and the current compilation error are distinct failures.
The GAMS diagnostic suggests DNLP, but changing mtype would be a second solver-option change beyond the requested single-option experiment and is not validated here.
No DNLP change, additional patch, retry, new execution package or optimization run is performed in this audit.
The requested stop-on-first-fixed-failure rule remains in force.

The original ZIPs, historical results, source packages and publication material remain unchanged.
The analysis uses archive bytes only and can be reproduced without any optimization solver.

```bash
python scripts/analyze_grid_loa_presolve_disabled_return.py --output /tmp/grid_loa_return_fresh
```
''')
    save(output / 'manifest.json', dict(review_revision=baseline['review_revision'], execution_source_revision=BASE,
        input_archive=ARCHIVE, input_archive_sha256=sha(data), input_archive_bytes=len(data),
        verified_outer_file_hashes=count, verified_predecessor_file_hashes=previous_count,
        predecessor_archive_sha256=sha(files['predecessor_result.zip']), delivered_package_sha256=source_hash,
        execution_source_matches_delivery=True, actual_settings=settings,
        analysis_source_sha256=sha(Path(__file__).read_bytes()),
        outputs_sha256={str(p.relative_to(output)): sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()},
        optimization_calls_during_analysis=0))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(analyze(parser.parse_args().output), indent=2))
