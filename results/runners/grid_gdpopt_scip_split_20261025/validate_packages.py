"""Verify sealed split packages and launcher isolation without calling a solver."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent

ROUTING = r'''
from itertools import combinations
import json
import os
from pathlib import Path
import run_method as wrapper
import cpu_affinity

package = wrapper.experiment.read(wrapper.experiment.ROOT / 'gdp_scip_package.json')
calls, pairs = [], []
def fake_main(argv):
    calls.append(argv)
    return 0
def fake_pair(a, b):
    pairs.append((a,b))
    return {'distinct_physical_cores': True}
wrapper.experiment.main = fake_main
wrapper.sys.platform = 'linux'
cpu_affinity.check_cpu_pair = fake_pair
wrapper.main(['run'])
assert pairs == list(combinations([6,8,10,12,14,16],2))
assert len(calls) == 1
args = calls[0]
assert args[args.index('--methods')+1] == package['split_method']
assert args[args.index('--cpu')+1] == str(package['cpu'])
assert args[args.index('--time-limit')+1] == '1800'
output = Path(os.environ['GDP_SCIP_REPOSITORY']) / 'results' / ('grid_gdpopt_scip_'+package['split_method'])
assert args[args.index('--output-root')+1] == str(output)
with wrapper.launcher_lock(output):
    try:
        wrapper.main(['run'])
    except RuntimeError as error:
        assert 'active launcher' in str(error)
    else:
        raise AssertionError('Duplicate launch accepted')
assert len(calls) == 1
def overlap(a,b):
    raise ValueError('Synthetic physical-core conflict')
cpu_affinity.check_cpu_pair = overlap
try:
    wrapper.main(['run'])
except ValueError as error:
    assert 'physical-core conflict' in str(error)
else:
    raise AssertionError('CPU conflict accepted')
assert len(calls) == 1
print('VALIDATION_JSON='+json.dumps({'method':package['split_method'],'cpu':package['cpu'],
    'isolated_output_root':str(output),'routing_verified':True,'duplicate_launch_blocked':True,
    'physical_core_conflict_blocked':True,'real_solver_calls':0}))
'''


def run(command, **kwargs):
    result = subprocess.run(command, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main():
    build = json.loads((ROOT / 'BUILD_MANIFEST.json').read_text())
    report = {'packages': [], 'server_execution': False, 'real_solver_calls': 0,
              'server_cpu_topology_checked_locally': False,
              'cpu_note': 'Actual allowed-CPU and physical-core checks run on Dantzig before any solver invocation.'}
    with tempfile.TemporaryDirectory(prefix='grid-method-split-validation-') as temporary:
        temporary = Path(temporary)
        for row in build['packages']:
            path = ROOT / row['archive']
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == row['sha256'] == path.with_suffix('.zip.sha256').read_text().split()[0]
            with zipfile.ZipFile(path) as archive:
                assert archive.testzip() is None
                prefix = path.stem + '/'
                names = archive.namelist()
                assert len(names) == len(set(names))
                assert all(n.startswith(prefix) and '..' not in Path(n).parts for n in names)
                checksums = archive.read(prefix+'SHA256SUMS').decode().splitlines()
                for line in checksums:
                    checksum, name = line.split('  ',1)
                    assert hashlib.sha256(archive.read(prefix+name)).hexdigest() == checksum
                assert len(checksums) == len(names)-1
                archive.extractall(temporary)
            directory = temporary / path.stem
            plan = json.loads(run([sys.executable, str(directory/'run_method.py'),'plan'], cwd=temporary))
            assert plan['planned_jobs'] == 21 and len(plan['instances']) == 21
            assert plan['config']['methods'] == [row['method']]
            assert plan['config']['cpu'] == row['cpu']
            assert plan['config']['time_limit'] == 1800
            assert plan['config']['mip_solver'] == plan['config']['nlp_solver'] == 'scip'
            assert plan['config']['record_grid_path'] and plan['config']['record_gdp_path']
            run(['bash','-n',str(directory/'run_method.sh')])
            run([sys.executable,'-m','ruff','check',str(directory/'run_method.py')])
            env = {**os.environ,'GDP_SCIP_REPOSITORY':str(temporary/'server-repository')}
            mock = run([sys.executable,'-c',ROUTING],cwd=directory,env=env)
            routing = json.loads(next(line.removeprefix('VALIDATION_JSON=') for line in mock.splitlines() if line.startswith('VALIDATION_JSON=')))
            routing['isolated_output_root'] = 'results/grid_gdpopt_scip_' + row['method']
            (ROOT / ('PLAN_'+row['method']+'.json')).write_text(json.dumps(plan,indent=2)+'\n')
            report['packages'].append({**row,'crc_passed':True,'internal_checksums_verified':len(checksums),
                'standalone_plan_verified':True,'bash_syntax_passed':True,'ruff_passed':True,**routing})
    (ROOT/'VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
