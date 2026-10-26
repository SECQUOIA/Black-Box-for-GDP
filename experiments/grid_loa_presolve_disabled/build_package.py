"""Build from the actually returned LOA source; retain its original bytes."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[2]
REVIEW='24df0376881409a533b98d9a8490c902eef38b5b'
ARCHIVE='grid_gdpopt_scip_20261025_180441_051rkijg.zip'
EXPECTED='69ec44f83c20817a33f51a94ec2e1a3e01ad37031cb3f8c37aae4993eafe1f50'
NAME='grid_loa_presolve_disabled_dantzig_20261025'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(data):
    return (json.dumps(data,indent=2,allow_nan=False)+'\n').encode()


def change_source(data):
    before='                force_subproblem_nlp=True, init_algorithm="set_covering",\n'
    after='                **({"subproblem_presolve": False} if config.get("diagnostic_presolve_disabled") is True else {}),\n'+before
    text=data.decode()
    if text.count(before)!=1:
        raise ValueError('Expected exact archived GDPopt invocation')
    return text.replace(before,after).encode()


def build(output):
    output.mkdir(parents=True,exist_ok=True)
    path=ROOT/'results/archives'/ARCHIVE
    if sha(path.read_bytes())!=EXPECTED:
        raise ValueError('Wrong baseline return')
    with zipfile.ZipFile(path) as z:
        prefix=path.stem+'/'
        if z.testzip() is not None:
            raise ValueError('Baseline ZIP CRC error')
        source={n[len(prefix+'source/'):]:z.read(n) for n in z.namelist() if n.startswith(prefix+'source/')}
        run=json.loads(z.read(prefix+'run.json'))
        original_configs={g:z.read(prefix+f'benchmark/{g}/loa/run.log').decode().split('\nIf you use this software',1)[0]
                          for g in ['holder_table','michalewicz','shubert']}
        if {n:sha(d) for n,d in source.items()}!=run['source_sha256']:
            raise ValueError('Original executed source differs')
    payload={'original_source/'+n:d for n,d in source.items()}
    payload.update({'execution/'+n:d for n,d in source.items()})
    changed=change_source(source['gdp_models/comparison.py'])
    payload['execution/gdp_models/comparison.py']=changed
    for name in ['diagnostic.py','analyze_diagnostic.py','run_diagnostic.sh']:
        payload['execution/'+name]=(Path(__file__).parent/name).read_bytes()
    payload['README.md']=(Path(__file__).parent/'README.md').read_bytes()
    audit=ROOT/'results/grid_gdpopt_scip_recovery_loa_20261025'
    baseline={'review_revision':REVIEW,'original_archive':ARCHIVE,'original_archive_sha256':EXPECTED,
        'run':run,'original_effective_gdpopt_config_logs':original_configs,
        'jobs':[r for r in json.loads((audit/'jobs.json').read_text()) if r['grid_name'] in ['holder_table','michalewicz','shubert']],
        'pyomo_module_sha256':json.loads((audit/'manifest.json').read_text())['local_diagnostic_modules_sha256'],
        'pyomo_module_hash_scope':'Local Pyomo 6.10.0 diagnostic source hashes; historical Dantzig module-byte hashes were not recorded.',
        'diagnostics':json.loads((audit/'target_mismatch_diagnostics.json').read_text())}
    payload['BASELINE.json']=encode(baseline)
    payload['comparison_option.diff']=''.join(difflib.unified_diff(source['gdp_models/comparison.py'].decode().splitlines(keepends=True),changed.decode().splitlines(keepends=True),fromfile='original_source/gdp_models/comparison.py',tofile='execution/gdp_models/comparison.py')).encode()
    manifest={'review_revision':REVIEW,'original_archive_sha256':EXPECTED,'original_source_sha256':run['source_sha256'],
        'changed_existing_source':['execution/gdp_models/comparison.py'],
        'algorithm_option_delta':{'subproblem_presolve':{'old':'default True','new':False}},
        'targets':{'holder_table':[[3,1],[3,29],[27,1],[27,29]],'michalewicz':[[21,15]],'shubert':[[17,22]]},
        'max_fixed_calls':6,'fixed_time_limit_s':60,'max_full_loa_runs':3,'full_time_limit_s':1800,
        'pyomo_installation_modified':False,'mip_presolve':'unchanged default True',
        'historical_corrections':'All preserved; none of the model-specific corrections applies to these three grids.',
        'network_policy':'Original retry_solve retained; full-call internal retries share 1800s; fixed-call guard permits one invocation only.',
        'files_sha256':{n:sha(d) for n,d in sorted(payload.items())}}
    payload['DIAGNOSTIC_MANIFEST.json']=encode(manifest)
    payload['SHA256SUMS']=''.join(f'{sha(d)}  {n}\n' for n,d in sorted(payload.items())).encode()
    dest=output/(NAME+'.zip')
    with zipfile.ZipFile(dest,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for n,d in sorted(payload.items()):
            info=zipfile.ZipInfo(NAME+'/'+n,date_time=(2026,10,25,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            z.writestr(info,d)
    Path(str(dest)+'.sha256').write_text(f'{sha(dest.read_bytes())}  {dest.name}\n')
    (output/'BUILD_MANIFEST.json').write_bytes(encode({**manifest,'package_sha256':sha(dest.read_bytes()),'package':dest.name}))
    print(dest)
    return dest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    build(parser.parse_args().output)
