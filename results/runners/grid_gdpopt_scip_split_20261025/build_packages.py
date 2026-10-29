"""Split the byte-verified October 24 Grid SCIP package without changing solvers."""
import hashlib
import json
from pathlib import Path
import zipfile

OUTPUT = Path(__file__).resolve().parent
REPOSITORY = OUTPUT.parents[2]
BASE = REPOSITORY / 'results/runners/gdp_scip_20261024/grid_gdpopt_scip_dantzig_20261024.zip'
BASE_SHA = '8b79a53bc1a6001c003db171753391be24b0690c58a39089164877b49608ddf4'
CPUS = {'ric': 12, 'loa': 14, 'gloa': 16}
TAG = '20261025'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


WRAPPER = '''"""One Grid GDPopt method, separate result pointers, and distinct CPU cores."""
import argparse
from contextlib import contextmanager
import fcntl
from itertools import combinations
import json
import os
from pathlib import Path
import sys

import gdp_scip_experiments as experiment


@contextmanager
def launcher_lock(output):
    output.mkdir(parents=True, exist_ok=True)
    with (output / '.method_launcher.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('This method already has an active launcher; inspect its run.log.') from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['plan', 'run', 'check', 'resume', 'status', 'pack'])
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--grids', help='Optional subset; defaults to all 21 original Grid problems.')
    parser.add_argument('--time-limit', type=float, default=1800)
    args = parser.parse_args(argv)
    if args.mode in {'resume', 'status', 'pack'} and args.run_dir is None:
        parser.error('--run-dir is required for this mode')
    if args.mode in {'resume', 'status', 'pack'} and (args.grids or args.time_limit != 1800):
        parser.error('Existing runs retain their recorded grids and time limit')
    return args


def main(argv=None):
    args = arguments(argv)
    experiment.package_inventory()
    package = experiment.read(experiment.ROOT / 'gdp_scip_package.json')
    method = package['split_method']
    if package['methods'] != [method] or package['planned_jobs'] != 21:
        raise ValueError('Invalid single-method package')
    repository = Path(os.environ.get('GDP_SCIP_REPOSITORY', '/local/scratch/a/lee4382/repository/RBFopt_Test'))
    output = repository / 'results' / ('grid_gdpopt_scip_' + method)
    command = [args.mode, '--methods', method, '--cpu', str(package['cpu']),
               '--time-limit', str(args.time_limit), '--output-root', str(output)]
    if args.grids:
        command.extend(['--grids', args.grids])
    if args.run_dir:
        command.extend(['--run-dir', str(args.run_dir)])
    if args.mode in {'plan', 'status'}:
        return experiment.main(command)
    if sys.platform != 'linux':
        raise RuntimeError('Execute this benchmark on Dantzig; use plan for solver-free local validation.')
    from cpu_affinity import check_cpu_pair
    checks = [check_cpu_pair(a, b) for a, b in combinations(package['separate_cpu_ids'], 2)]
    print('CPU_SEPARATION=' + json.dumps({'requested_cpu': package['cpu'], 'checks': checks}), flush=True)
    print('METHOD=' + method + '; OUTPUT_ROOT=' + str(output), flush=True)
    with launcher_lock(output):
        return experiment.main(command)


if __name__ == '__main__':
    raise SystemExit(main())
'''

SHELL = '''#!/usr/bin/env bash
set -Eeuo pipefail
GRID_METHOD_RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export GDP_SCIP_REPOSITORY=${GDP_SCIP_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
GRID_METHOD_PYTHON=${GDP_SCIP_PYTHON:-$GDP_SCIP_REPOSITORY/.venv-dantzig-gdp/bin/python}
export GAMS_BIN=${GAMS_BIN:-/package/gams/52.2/gams}
export GDP_GAMS_VERSION=${GDP_GAMS_VERSION:-52.2}
export PYOMO_CONFIG_DIR=${PYOMO_CONFIG_DIR:-$GDP_SCIP_REPOSITORY/.pyomo-gdp-comparison}
export PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
[[ -x "$GRID_METHOD_PYTHON" ]] || { echo "Missing GDP Python: $GRID_METHOD_PYTHON" >&2; exit 2; }
cd "$GRID_METHOD_RUNNER"
[[ $# -gt 0 ]] || set -- run
exec "$GRID_METHOD_PYTHON" run_method.py "$@"
'''


def build():
    assert digest(BASE.read_bytes()) == BASE_SHA, 'Base ZIP identity changed'
    with zipfile.ZipFile(BASE) as archive:
        assert archive.testzip() is None
        prefix = 'grid_gdpopt_scip_dantzig_20261024/'
        original = {n[len(prefix):]: archive.read(n) for n in archive.namelist() if not n.endswith('/')}
    for line in original['SHA256SUMS'].decode().splitlines():
        checksum, name = line.split('  ', 1)
        assert digest(original[name]) == checksum, name
    base_manifest = json.loads(original['PACKAGE_MANIFEST.json'])
    for row in base_manifest['files']:
        assert digest(original[row['path']]) == row['sha256']
    outputs = [OUTPUT / f'grid_gdpopt_scip_{m}_dantzig_{TAG}.zip' for m in CPUS]
    if any(p.exists() or p.with_suffix('.zip.sha256').exists() for p in outputs):
        raise FileExistsError('Do not overwrite delivered ZIPs; choose another output/tag.')
    evidence = []
    for method, cpu in CPUS.items():
        stem = f'grid_gdpopt_scip_{method}_dantzig_{TAG}'
        payload = {k: v for k, v in original.items() if k not in {'SHA256SUMS', 'PACKAGE_MANIFEST.json'}}
        package = json.loads(payload['gdp_scip_package.json'])
        package.update(tag=TAG, methods=[method], planned_jobs=21, cpu=cpu, peer_cpu=6,
                       split_method=method, separate_cpu_ids=[6, 8, 10, 12, 14, 16])
        payload['gdp_scip_package.json'] = encoded(package)
        payload['run_method.py'] = WRAPPER.encode()
        payload['run_method.sh'] = SHELL.encode()
        payload['README.md'] = f'''Grid GDPopt SCIP {method.upper()} package, 2026-10-25

This package starts all 21 Grid problems from the beginning with {method.upper()} only.
It uses actual GAMS/SCIP for both MIP and NLP routing, retaining the original 1,800-second budget per problem, relative gap 1e-5, one thread, model definitions, corrections and trajectory recording.
It does not import results or resume attempts from the earlier combined 63-job run.
The cumulative worker budget is at most 10.5 hours, plus preflight, verification and packaging.
The packaged optimization source files are byte-identical to the verified October 24 Grid package.
Only the package selection metadata, this README, manifests and the added launch wrapper differ.
The retained docs/gdp_scip_experiments.md describes the original two-package experiment; this README governs the single-method launch.

Use CPU {cpu} for {method.upper()}.
The launcher verifies that CPUs 12, 14 and 16 are distinct allowed physical cores and also distinct from earlier experiment CPUs 6, 8 and 10.
This prevents overlap among the selected experiment cores but does not reserve CPUs against other users.
Results are written under /local/scratch/a/lee4382/repository/RBFopt_Test/results/grid_gdpopt_scip_{method}/.
The method has its own result_zip.txt and latest_result.json, so parallel methods cannot overwrite one another's result pointers.
A per-method launcher lock rejects duplicate launches through this wrapper.

Run on Dantzig from this extracted directory:

```bash
sha256sum -c SHA256SUMS > verify.log
bash run_method.sh plan > plan.json
nohup bash run_method.sh run > run.log 2>&1 < /dev/null &
echo $! > launcher.pid
tail -f run.log
```

The launcher prints CPU_SEPARATION and METHOD before preflight, RUN_DIR when the result directory is created, START/DONE for each of the 21 jobs, and RESULT_ZIP when packaging completes.
The run.log file is unbuffered at the Python level.
Each job's detailed solver log is RUN_DIR/benchmark/GRID/{method}/run.log.
Solver calls, full returned solutions when available, GDP and Grid coordinate paths, and immutable source hashes remain in the result ZIP.
Preflight checks the existing Dantzig GAMS 52.2, Pyomo 6.10.0 and solver availability; there is no alternative-solver fallback.
Preflight is outside the benchmark budget and may take time before the first START line.
Inspect all_jobs_finished and the completed-job count before interpreting a packaged failure as a complete benchmark.

After completion, display the result path:

```bash
cat /local/scratch/a/lee4382/repository/RBFopt_Test/results/grid_gdpopt_scip_{method}/result_zip.txt
```

To resume this package's own interrupted run after the old controller has stopped:

```bash
bash run_method.sh resume --run-dir /absolute/RUN_DIR
```

The existing runner preserves incomplete attempts under previous_attempts and skips sealed completed jobs.
Every attempt must remain identifiable in later analysis.
The three split runs are independent new experiments; they do not select better outcomes from the earlier combined run.
No server execution was performed while creating these ZIPs.
'''.encode()
        changed = sorted(k for k in original if k in payload and original[k] != payload[k])
        assert changed == ['README.md', 'gdp_scip_package.json']
        unchanged = sorted(k for k in original if k in payload and original[k] == payload[k])
        provenance = {'base_zip': BASE.name, 'base_zip_sha256': BASE_SHA,
                      'method': method, 'cpu': cpu, 'planned_jobs': 21,
                      'unchanged_base_files': {k: digest(payload[k]) for k in unchanged},
                      'changed_base_files': changed,
                      'added_launcher_files': ['run_method.py', 'run_method.sh'],
                      'builder_sha256': digest(Path(__file__).read_bytes()),
                      'optimizer_model_and_input_bytes_unchanged': True}
        payload['SPLIT_PROVENANCE.json'] = encoded(provenance)
        manifest = {**base_manifest, 'split_method': method,
                    'files': [{'path': n, 'sha256': digest(d)} for n, d in sorted(payload.items())]}
        payload['PACKAGE_MANIFEST.json'] = encoded(manifest)
        payload['SHA256SUMS'] = ''.join(f'{digest(d)}  {n}\n' for n, d in sorted(payload.items())).encode()
        path = OUTPUT / (stem + '.zip')
        with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(payload.items()):
                info = zipfile.ZipInfo(f'{stem}/{name}', date_time=(2026, 10, 25, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
                archive.writestr(info, data)
        checksum = digest(path.read_bytes())
        path.with_suffix('.zip.sha256').write_text(f'{checksum}  {path.name}\n')
        evidence.append({'archive': path.name, 'sha256': checksum, 'bytes': path.stat().st_size,
                         'method': method, 'cpu': cpu, 'planned_jobs': 21,
                         'unchanged_base_files': len(unchanged)})
    (OUTPUT / 'BUILD_MANIFEST.json').write_bytes(encoded({'base_sha256': BASE_SHA, 'packages': evidence}))
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    build()
