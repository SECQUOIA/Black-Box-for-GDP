"""Compile-only preflight and immutable predecessor verification for the DNLP follow-up."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from time import monotonic
import zipfile

PRIOR_RESULT = 'grid_loa_presolve_disabled_20261025_v2_result.zip'
PRIOR_HASH = '303012e48a2480ddcabb5388fe2a7d1c6f83082795484bd13b7f0130671a1b1a'


def predecessor(repository):
    import diagnostic as d
    p = Path(repository) / 'results/grid_loa_presolve_disabled_20261025_v2' / PRIOR_RESULT
    d.require(hashlib.sha256(p.read_bytes()).hexdigest() == PRIOR_HASH, 'Expected the preserved v2 stopped result')
    with zipfile.ZipFile(p) as z:
        root = next(n[:-len('run.json')] for n in z.namelist() if n.endswith('/run.json') and n.count('/') == 1)
        r = json.loads(z.read(root + 'run.json'))
        d.require(r['actual_fixed_solver_calls'] == 1 and r['actual_full_loa_runs'] == 0,
                  'Unexpected predecessor counts')
    return dict(archive=str(p), sha256=PRIOR_HASH, prior_fixed_interface_calls=1,
                prior_confirmed_scip_calls=0, prior_full_loa_runs=0,
                status='verified_v2_compile_failure_separate_followup_authorized',
                followup_limits={'fixed_calls': 6, 'full_loa_runs': 3})


def nlp_options(message):
    """Read the NLP arguments from GDPopt's actual effective-config text."""
    import diagnostic as d
    section = re.search(r'^nlp_solver_args:\s*\n((?:[ \t]+[^\n]*\n)*)', message + '\n', re.M)
    args = dict(re.findall(r'^\s+(\w+):\s*(\S+)\s*$', section[1], re.M)) if section else {}
    d.require(args == {'mtype': 'dnlp', 'solver': 'scip'}, 'Actual GDPopt NLP arguments are not SCIP/DNLP')
    return args


def compile_one(executable, directory, grid, point, mtype='dnlp'):
    """GAMS action=c compiles the exported original subproblem without solving."""
    import diagnostic as d
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    model, _ = d.setup(grid, point)
    signature = d.structure(model)
    model.write(str(directory / 'model.gms'), format='gams',
                io_options={'solver': 'scip', 'mtype': mtype})
    d.require(signature == d.structure(model), 'GAMS export changed the mathematical model')
    text = (directory / 'model.gms').read_text()
    d.require(f'USING {mtype} ' in text and f'option {mtype}=scip;' in text,
              'Exported solver/model type differs')
    command = [str(executable), 'model.gms', 'action=c', 'lo=3', 'threads=1']
    started = monotonic()
    row = dict(grid_name=grid, point=list(point), model_type=mtype, command=command,
               utc=datetime.now(timezone.utc).isoformat(), optimizer_calls=0,
               structure_sha256=signature['sha256'], model_sha256=d.sha(text.encode()))
    try:
        run = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=30)
        log = run.stdout + run.stderr
        row.update(returncode=run.returncode, passed=run.returncode == 0)
    except subprocess.TimeoutExpired as error:
        log = (error.stdout or b'').decode(errors='replace') + (error.stderr or b'').decode(errors='replace')
        row.update(returncode=None, passed=False, message='Compile-only check exceeded 30 seconds')
    (directory / 'compile.log').write_text(log)
    row.update(wall_s=monotonic() - started,
               gams_banners=re.findall(r'^--- Job model\.gms Start (.+)$', log, re.M),
               confirmed_optimizer_starts=len(re.findall(r'^--- Executing ', log, re.M)))
    d.require(row['confirmed_optimizer_starts'] == 0, 'Compile-only preflight unexpectedly executed a solver')
    d.save(directory / 'result.json', row)
    return row


def compile_preflight(config, output):
    import diagnostic as d
    root = Path(output) / 'compile_preflight'
    d.require(not root.exists(), 'Compile preflight already exists')
    root.mkdir(parents=True)
    rows = []
    for grid, point in d.POINTS:
        print(f'COMPILE_START {grid} {point}; GAMS action=c; mtype=dnlp', flush=True)
        row = compile_one(config['executable'], root / f'{grid}_{point[0]}_{point[1]}', grid, point)
        rows.append(row)
        d.save(root / 'summary.json', dict(results=rows, optimizer_calls=0,
               gams_executable_sha256=d.sha(Path(config['executable']).read_bytes()),
               platform=sys.platform, compiler_environment_scope=config.get('compiler_environment_scope', 'verified_Dantzig_52.2')))
        print(f"COMPILE_DONE {grid} {point}; passed={row['passed']}", flush=True)
        d.require(row['passed'], 'GAMS compile-only preflight failed; no optimization launched')
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gams', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    compile_preflight({'executable': str(args.gams), 'compiler_environment_scope': 'local_compile_only_not_Dantzig_solver_validation'}, args.output)
