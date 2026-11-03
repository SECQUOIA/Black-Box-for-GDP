"""Verify delivered bytes, frozen error-only plans and diagnostic packaging."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'results/runners/grid_gdpopt_scip_recovery_20261025'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate():
    records = json.loads((OUTPUT / 'BUILD_MANIFEST.json').read_text())
    jobs = json.loads((ROOT / 'results/grid_gdpopt_scip_20261025/jobs.json').read_text())
    expected = {(j['grid_name'], j['method']) for j in jobs if j['status'] == 'error'}
    seen, reports = set(), []
    environment = {**os.environ, 'MPLCONFIGDIR': '/private/tmp/grid-recovery-validation', 'PYTHONNOUSERSITE': '1'}
    environment.pop('PYTHONPATH', None)
    for record in records:
        archive = OUTPUT / record['archive']
        assert sha(archive.read_bytes()) == record['sha256']
        with tempfile.TemporaryDirectory(prefix='grid-recovery-validate-') as temporary:
            with zipfile.ZipFile(archive) as z:
                assert z.testzip() is None and len(z.namelist()) == len(set(z.namelist()))
                assert all(n.startswith(archive.stem + '/') and '..' not in Path(n).parts for n in z.namelist())
                z.extractall(temporary)
            package = Path(temporary) / archive.stem
            manifest = json.loads((package / 'PACKAGE_MANIFEST.json').read_text())
            for row in manifest['files']:
                assert sha((package / row['path']).read_bytes()) == row['sha256'], row['path']
            checks = (package / 'SHA256SUMS').read_text().splitlines()
            for line in checks:
                checksum, name = line.split('  ', 1)
                assert sha((package / name).read_bytes()) == checksum
            result = subprocess.run([sys.executable, 'run_method.py', 'plan'], cwd=package,
                                    env=environment, text=True, capture_output=True, check=True)
            plan = json.loads(result.stdout)
            method = record['method']
            assert plan['planned_jobs'] == record['jobs'] and plan['config']['methods'] == [method]
            assert plan['config']['cpu'] == record['cpu'] and plan['config']['time_limit'] == 1800
            assert plan['config']['relative_gap'] == 1e-5 and plan['config']['threads'] == 1
            assert plan['config']['mip_solver'] == plan['config']['nlp_solver'] == 'scip'
            selection = json.loads((package / 'RECOVERY_SELECTION.json').read_text())
            assert [r['grid_name'] for r in plan['instances']] == [r['grid_name'] for r in selection['jobs']]
            for row in plan['instances']:
                key = row['grid_name'], method
                assert key not in seen and key in expected
                seen.add(key)
            (OUTPUT / f'PLAN_{method.upper()}.json').write_text(result.stdout)
            # Scope and limits cannot accidentally be overridden by the wrapper.
            for arguments in (['plan', '--grids', 'alpine1'], ['plan', '--time-limit', '3600'], ['resume']):
                rejected = subprocess.run([sys.executable, 'run_method.py', *arguments], cwd=package,
                                          env=environment, capture_output=True)
                assert rejected.returncode != 0
            # Verify the amended packer retains unfinished GAMS files and seals.
            probe = '''
from pathlib import Path
import tempfile, zipfile
import gdp_scip_experiments as e
import grid_gdp_benchmark as b
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp) / 'probe'
    scratch = root / 'benchmark/grid/method/gams-leftover'
    scratch.mkdir(parents=True)
    (scratch / 'model.gms').write_text('diagnostic model')
    b.ensure_stopped = lambda directory: None
    e.summarize = lambda directory: {'all_jobs_finished': True}
    e.pack(root)
    with zipfile.ZipFile(root.with_suffix('.zip')) as z:
        assert z.read('probe/benchmark/grid/method/gams-leftover/model.gms') == b'diagnostic model'
        assert 'benchmark/grid/method/gams-leftover/model.gms' in z.read('probe/SHA256SUMS').decode()
'''
            subprocess.run([sys.executable, '-c', probe], cwd=package, env=environment, capture_output=True, check=True)
            # A modified recovery policy must fail inventory verification before execution.
            policy = package / 'grid_recovery.py'
            policy.write_text(policy.read_text() + '\n# tamper probe\n')
            rejected = subprocess.run([sys.executable, 'run_method.py', 'plan'], cwd=package,
                                      env=environment, text=True, capture_output=True)
            assert rejected.returncode != 0 and 'Package file changed: grid_recovery.py' in rejected.stderr
            reports.append({**record, 'checksum_entries_verified': len(checks), 'plan_verified': True,
                            'scope_override_rejected': True, 'scratch_preservation_verified': True,
                            'tamper_rejected': True, 'solver_calls': 0})
    assert seen == expected and len(seen) == 46
    result = {'packages': reports, 'unique_error_jobs': len(seen), 'timeouts_selected': 0,
              'solver_calls': 0, 'remote_execution_performed': False}
    (OUTPUT / 'VALIDATION.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    validate()
