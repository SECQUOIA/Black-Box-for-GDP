#!/usr/bin/env python3
"""Offline launch of the unmodified a1c3bf33 MINLP reproduction script."""
import fcntl
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

import support as S
import verify as V
import audit

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'state'
PIN='a1c3bf336493dc496bb2571e160b1054f237e0be'
SCRIPT='experiments/catalytic_distillation_minlp/run_dantzig.sh'


def state(**values):
    old=V.read(STATE/'run.json') if (STATE/'run.json').exists() else {}
    old.update(values,updated_utc=S.now());V.write(STATE/'run.json',old)


def active_processes():
    rows=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
        try:
            if proc.stat().st_uid != os.getuid():continue
            cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
            if 'catalytic_distillation_minlp/' in cmd and any(s in cmd for s in ('run_dantzig.sh','run_solvers.sh','validate.sh','check_point.gms')):
                rows.append({'pid':int(proc.name),'command':cmd})
        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
    return rows


def existing_results():
    # Match Dantzig output names, not the professor's checked-in workstation reference.
    paths=list((S.REPO/'results').glob('catalytic_distillation_minlp_dantzig_*'))
    paths+=list(S.REPO.parent.glob('catdist_minlp_dantzig_*'))
    for line in S.git('worktree','list','--porcelain').splitlines():
        if line.startswith('worktree '):
            paths+=list((Path(line[9:])/'results').glob('catalytic_distillation_minlp_dantzig_*'))
    for parent in S.REPO.parent.glob('m54_*'):
        paths+=list((parent/'src/results').glob('catalytic_distillation_minlp_dantzig_*'))
        if (parent/'raw/environment.txt').exists(): paths.append(parent/'raw')
    # New runs use the user's scratch home to keep GAMS scratch paths short.
    for parent in Path('/local/scratch/a/lee4382').glob('m54_*'):
        if (parent/'raw/environment.txt').exists():paths.append(parent/'raw')
    return sorted(set(str(p) for p in paths))


def setup_environment(work,session):
    real=Path('/package/gams/54.3/gams')
    V.require(real.is_file() and os.access(real,os.X_OK),'GAMS 54.3 executable is unavailable')
    python=Path(os.environ.get('SCALES_PYTHON',str(S.REPO/'.venv-dantzig/bin/python')))
    V.require(python.is_absolute() and python.is_file(),'An existing absolute SCALES_PYTHON is required')
    env={**S.ENV,'GAMS_EXE':str(real),'SCALES_PYTHON':str(python),
         'MINLP_RESLIM':'3600','FIXED_RESLIM':'1200','MINLP_OUTPUT':str(session/'raw'),
         'MINLP_DEST':str(work/'results'/('catalytic_distillation_minlp_dantzig_'+S.now()[:10].replace('-',''))),
         'BASH_ENV':str(ROOT/'guard.sh'),'MINLP_GUARD_SCRIPT':str(ROOT/'guard.py'),
         'MINLP_GUARD_PYTHON':sys.executable,'MINLP_GUARD_DIR':str(session/'raw/guard'),
         'MINLP_SOURCE':str(work),'MINLP_REAL_TIMEOUT':shutil.which('timeout') or ''}
    V.require(env['MINLP_REAL_TIMEOUT'],'GNU timeout is required')
    for tool in ('git','bash','taskset','flock','zip','gzip','sha256sum'):
        V.require(shutil.which(tool) is not None,'Required existing executable missing: '+tool)
    package=S.environment(python,['pyomo'],env=S.ENV)
    S.capture([str(python),'-c','from pyomo.contrib.fbbt.fbbt import fbbt, compute_bounds_on_expr; from pyomo.repn import generate_standard_repn'],env=S.ENV)
    # Inspect registered helpers without publishing license text or editing the installation.
    registry=real.parent/'gmscmpun.txt'
    V.require(registry.is_file(),'Cannot inspect the GAMS solver registry')
    text=registry.read_text(errors='replace').lower()
    required=('conopt','cplex','dicopt','sbb','baron','scip','jams','convert','examiner','examiner2')
    V.require(all(re.search(r'(?m)^\s*'+name+r'\b',text) for name in required),'Required solver/helper absent from the GAMS registry')
    env['PATH']=str(ROOT/'bin')+os.pathsep+env['PATH']
    metadata=dict(real_gams=str(real),real_gams_resolved=str(real.resolve()),gams_sha256=V.sha(real),
                  expected_gams='54.3.1',scales_python=package,registered_helpers=list(required),
                  gams_registry_sha256=V.sha(registry),threads=S.THREADS,
                  source_revision=PIN,utc_started=S.now(),host=platform.node(),
                  source_sha256={str(p.relative_to(work)):V.sha(p) for folder in
                    ('experiments/catalytic_distillation_minlp','gdp_models/catalytic_distillation')
                    for p in sorted((work/folder).rglob('*')) if p.is_file()},
                  instrumentation='BASH_ENV gates scale/version checks and pins validation children; timeout shim records the unchanged watchdog exit')
    return env,metadata


def package(session,dest,report):
    # Preserve the original evidence archive, including its existing exclusion rules.
    provenance=dest/'execution_provenance';provenance.mkdir(exist_ok=False)
    for name in ('execution.json','environment_wrapper.json','inventory.json','audit.json'):
        if (session/name).exists():shutil.copy2(session/name,provenance/name)
    shutil.copy2(session/'controller.log',provenance/'controller.log')
    for name in ('guard.sh','guard.py','supervisor.py','audit.py','FILES_SHA256.json'):
        shutil.copy2(ROOT/name,provenance/name)
    audit.readme(dest,report,V.read(session/'environment_wrapper.json'),V.read(session/'execution.json'))
    V.write(dest/'FILE_SHA256.json',{str(p.relative_to(dest)):V.sha(p) for p in sorted(dest.rglob('*')) if p.is_file()})
    S.no_secret_files([p for p in dest.rglob('*') if p.is_file()])
    archive=ROOT/'RETURN_MINLP54.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(dest.rglob('*')):
            if p.is_file():z.write(p,str(Path('results')/dest.name/p.relative_to(dest)))
    info=V.zip_check(archive)
    archive.with_name(archive.name+'.sha256').write_text(info['sha256']+'  '+archive.name+'\n')
    state(return_archive=str(archive),return_sha256=info['sha256'],return_bytes=info['bytes'])


def run():
    V.require(platform.system()=='Linux' and platform.node().split('.')[0].lower()=='dantzig','Run experiments only on Dantzig')
    STATE.mkdir(exist_ok=True)
    with (STATE/'launch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=V.read(STATE/'run.json') if (STATE/'run.json').exists() else None
        if before:
            V.require(not S.alive(before.get('supervisor',{})),'Supervisor already active')
            V.require(before['state']=='waiting_for_16_cores','Existing attempt preserved; automatic rerun refused')
            V.write(STATE/('capacity_attempt_'+S.stamp()+'.json'),before)
        state(state='checking',revision=PIN,supervisor=dict(pid=os.getpid(),start_ticks=S.identity(os.getpid())),error=None)
        session=None;cores=[]
        try:
            for name,h in V.read(ROOT/'FILES_SHA256.json').items():V.require(V.sha(ROOT/name)==h,'Package hash mismatch: '+name)
            inventory=S.inventory()
            V.require(not active_processes(),'A catalytic MINLP run is already active; inspect it before starting another')
            prior=existing_results();V.require(not prior,'Existing Dantzig MINLP output requires provenance review: '+', '.join(prior))
            for key in ('SLURM_CPUS_ON_NODE','SLURM_CPUS_PER_TASK'):
                if key in os.environ:V.require(int(os.environ[key])>=16,'Scheduler allocation is below sixteen CPUs')
            try:cores=S.acquire_cpus('MINLP54',16)
            except RuntimeError as error:
                if str(error)=='No idle physical core observed; retry later':cores=[]
                else:raise
            if len(cores)!=16:
                state(state='waiting_for_16_cores',available_cores=len(cores),message='No experiment started; START.sh may be run later')
                return 2
            state(cores=cores,available_cores=16)
            session=Path(tempfile.mkdtemp(prefix='m54_',dir='/local/scratch/a/lee4382'))
            work=session/'src';raw=session/'raw';(raw/'guard').mkdir(parents=True)
            state(state='preparing',session=str(session),worktree=str(work),output=str(raw),log=str(session/'controller.log'))
            V.write(session/'inventory.json',inventory)
            S.capture(['git','--git-dir',str(ROOT/'source.git'),'worktree','add','--detach',str(work),PIN])
            V.require(S.capture(['git','rev-parse','HEAD'],cwd=work).strip()==PIN,'Execution revision mismatch')
            env,metadata=setup_environment(work,session)
            env['CPUS']=' '.join(str(c['cpu']) for c in cores)
            metadata['cores']=cores;V.write(session/'environment_wrapper.json',metadata)
            dest=Path(env['MINLP_DEST']);V.require(not dest.exists(),'Result destination already exists')
            command=['bash',str(work/SCRIPT)]
            with (session/'controller.log').open('x') as stream:
                process=subprocess.Popen(command,cwd=work,env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                S.hold_process('MINLP54',process.pid)
                record=dict(command=command,pid=process.pid,start_ticks=S.identity(process.pid),started_utc=S.now(),
                            revision=PIN,host=platform.node(),cores=cores,output=str(raw),destination=str(dest),timezone='UTC')
                V.write(session/'execution.json',record)
                state(state='running',controller=dict(pid=process.pid,start_ticks=record['start_ticks']),destination=str(dest),started_utc=record['started_utc'])
                with (session/'process_samples.jsonl').open('x') as samples:
                    while process.poll() is None:
                        rows=[]
                        for p in Path('/proc').iterdir():
                            if not p.name.isdigit():continue
                            try:
                                cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
                                if str(session) in cmd and p.stat().st_uid==os.getuid():
                                    rows.append(dict(pid=int(p.name),affinity=sorted(os.sched_getaffinity(int(p.name))),command=cmd))
                            except (FileNotFoundError,ProcessLookupError,PermissionError):pass
                        samples.write(json.dumps(dict(at=S.now(),processes=rows))+'\n');samples.flush()
                        state(controller_log_bytes=(session/'controller.log').stat().st_size,
                              main_results=len(list(raw.glob('*/*/result.txt'))))
                        time.sleep(10)
            record.update(exit_code=process.returncode,finished_utc=S.now());V.write(session/'execution.json',record)
            V.require(not S.capture(['git','status','--porcelain','--untracked-files=no'],cwd=work).strip(),'Tracked source changed during execution')
            if process.returncode!=0:
                state(state='blocked_or_failed',exit_code=process.returncode,error='Original script or guard failed; inspect controller.log; no automatic retry')
                diagnostic_zip(session)
                return 1
            report=audit.audit(raw,dest,work/'results/catalytic_distillation_minlp_20261101')
            V.write(session/'audit.json',report)
            package(session,dest,report)
            state(state='finished_pending_review',exit_code=0,audit=report,finished_utc=S.now())
            return 0
        except Exception:
            error=traceback.format_exc();state(state='blocked_or_failed',error=error[-6000:]);print(error,flush=True)
            if session:
                (session/'failure.txt').write_text(error)
                diagnostic_zip(session)
            return 1
        finally:
            S.release_cpus('MINLP54')


def diagnostic_zip(session):
    archive=ROOT/('DIAGNOSTICS_'+S.stamp()+'.zip')
    # Original raw files stay on the server; diagnostic text excludes licenses and binary points.
    candidates=[p for p in session.rglob('*') if p.is_file() and 'src' not in p.relative_to(session).parts
                and p.suffix in ('.json','.jsonl','.log','.lst','.txt','.csv')]
    candidates=[p for p in candidates if not re.search(r'(gamslice|bamlice|license)',p.name,re.I)]
    try:
        S.no_secret_files(candidates)
        with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in candidates:z.write(p,str(p.relative_to(session)))
        info=V.zip_check(archive);archive.with_name(archive.name+'.sha256').write_text(info['sha256']+'  '+archive.name+'\n')
        state(diagnostics=str(archive))
    except Exception as e:state(diagnostics_error=str(e))


def status():
    if not (STATE/'run.json').exists():print('STATE=not_started');return
    d=V.read(STATE/'run.json')
    print('STATE='+d['state']+'; supervisor_alive='+str(S.alive(d.get('supervisor',{}))))
    for k in ('revision','cores','available_cores','controller','worktree','output','log','started_utc','exit_code','error','return_archive','return_sha256','diagnostics'):
        if k in d:print(k.upper()+'='+json.dumps(d[k]))
    if 'output' in d:
        raw=Path(d['output']);main=sum((raw/f/s/'result.txt').exists() for f in audit.FORMS for s in audit.SOLVERS)
        fixed=sum((raw/'fixed_best'/f/s/'result.txt').exists() for f in ('bigm','chull') for s in ('baron','scip'))
        validation=sum((raw/'validation'/f/c/'result.txt').exists() for f in ('gdp',*audit.FORMS) for c in audit.CONFIGS)
        print(f'MINLP result files={main}/12; fixed-best result files={fixed}/4; fixed-form result files={validation}/36')
    if d.get('audit'):print('REVIEW_REASONS='+json.dumps(d['audit']['review_reasons']))


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='status':status()
    else:sys.exit(run())
