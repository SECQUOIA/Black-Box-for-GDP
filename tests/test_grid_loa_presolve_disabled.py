"""Exercise the delivered diagnostic without any real optimization calls."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import textwrap
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('presolve_builder', ROOT/'experiments/grid_loa_presolve_disabled/build_package.py')
builder=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


@pytest.fixture(scope='module')
def package(tmp_path_factory):
    root=tmp_path_factory.mktemp('presolve_package')
    archive=builder.build(root/'delivery')
    with zipfile.ZipFile(archive) as z:
        z.extractall(root/'extracted')
    return root/'extracted'/builder.NAME/'execution'


def execute(package, source):
    result=subprocess.run([sys.executable,'-c',textwrap.dedent(source)],cwd=package,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr


def test_original_source_and_single_explicit_option_delta(package):
    execute(package,'''
        import diagnostic as d
        from pathlib import Path
        m=d.verify_package()
        old=Path('../original_source')
        changed=[]
        for path in old.rglob('*'):
            if path.is_file() and path.read_bytes()!=Path(path.relative_to(old)).read_bytes():
                changed.append(str(path.relative_to(old)))
        assert changed==['gdp_models/comparison.py']
        assert m['algorithm_option_delta']=={'subproblem_presolve':{'old':'default True','new':False}}
    ''')


def test_option_reaches_actual_solve_call_and_default_path_is_unchanged(package):
    execute(package,'''
        import tempfile
        from pathlib import Path
        from time import monotonic
        from unittest.mock import patch
        import diagnostic as d
        from gdp_models import comparison as impl
        from gdp_models.grid_benchmark import grid_template
        captured=[]
        class Capture:
            def solve(self,model,**kwargs):
                captured.append(kwargs)
                raise RuntimeError('test-only stop before optimizer')
        for enabled in [True,False]:
            c=d.config();c['diagnostic_presolve_disabled']=enabled
            path=Path(tempfile.mkdtemp())
            with patch.object(impl.pyo,'SolverFactory',return_value=Capture()):
                impl.solve_method(grid_template('michalewicz'),'loa',path,c,monotonic()+1800)
        assert captured[0]['subproblem_presolve'] is False
        assert 'subproblem_presolve' not in captured[1]
        assert 'mip_presolve' not in captured[0] and 'mip_presolve' not in captured[1]
        for k in ['mip_solver','nlp_solver','mip_solver_args','nlp_solver_args','force_subproblem_nlp','init_algorithm','bound_tolerance']:
            assert captured[0][k]==captured[1][k]
        assert not impl.CONTEXT.calls
    ''')


def test_actual_official_config_capture_detects_missing_forwarding(package):
    execute(package,'''
        import tempfile
        from pathlib import Path
        import diagnostic as d
        import pyomo.environ as pyo
        algorithm=pyo.SolverFactory('gdpopt.loa')
        for enabled in [False,True]:
            path=Path(tempfile.mkdtemp())
            c=d.fixed_config(enabled)
            old=c.logger.level;c.logger.setLevel(20)
            try:
                with d.actual_config_capture(path) as capture:
                    try:algorithm._log_solver_intro_message(c)
                    except ValueError:
                        assert enabled is True
                    else:
                        assert enabled is False and capture.observed
            finally:c.logger.setLevel(old)
    ''')


def test_six_models_preserved_and_default_rejections_reproduced(package):
    execute(package,'''
        import diagnostic as d
        before=d.module_hashes()
        for grid,point in d.POINTS:
            r=d.inspect_point(grid,point)
            assert r['original_witness']['has_feasible_solution'] and r['original_witness']['target_hit']
            assert not r['default_presolve_allows_solver']
            assert r['subproblem_before_option_sha256']==r['subproblem_after_option_sha256']
        assert before==d.module_hashes()
    ''')


def test_official_disabled_subproblem_path_reaches_solver_without_presolve(package):
    execute(package,'''
        from pathlib import Path
        from tempfile import mkdtemp
        from types import SimpleNamespace
        from unittest.mock import patch
        import diagnostic as d
        from pyomo.common.collections import Bunch
        from pyomo.contrib.gdpopt.util import time_code
        from pyomo.contrib.gdpopt import solve_subproblem as s
        from pyomo.opt import SolverResults,TerminationCondition as tc
        from gdp_models import comparison as impl
        observed=[]
        def fake(self,model,**kwargs):
            observed.append(kwargs)
            r=SolverResults();r.solver.termination_condition=tc.optimal
            return r
        impl.CONTEXT=impl.SolveContext('/usr/bin/true',Path(mkdtemp()),1e30)
        with patch.object(impl.TimedGAMS,'solve',fake):
            for grid,point in d.POINTS:
                m,u=d.setup(grid,point)
                c=d.fixed_config(False)
                solver=SimpleNamespace(timing=Bunch())
                signature=d.structure(m)
                with time_code(solver.timing,'total',is_main_timer=True):
                    s.solve_subproblem(u,solver,c)
                assert d.structure(m)==signature
        assert len(observed)==6
        assert all(r['solver']=='scip' and r['mtype']=='nlp' for r in observed)
    ''')


def test_fixed_call_cap_and_one_time_launch_claim(package):
    execute(package,'''
        import diagnostic as d
        from tempfile import mkdtemp
        from pathlib import Path
        p=Path(mkdtemp());r={'actual_solver_calls':0}
        d.claim_fixed_call(r,p)
        try:d.claim_fixed_call(r,p)
        except ValueError:pass
        else:raise AssertionError('Second call accepted')
        assert r['actual_solver_calls']==1
        from unittest.mock import patch
        attempts=[]
        def fake_original(*args,**kwargs):attempts.append(1)
        def forced_retry(original,solver,model,kwargs,context):
            original(solver,model,**kwargs)
            original(solver,model,**kwargs)
        counter={'actual_solver_calls':0}
        with patch('grid_recovery.retry_solve',forced_retry):
            try:d.guarded_fixed_solve(fake_original,None,None,{},None,counter,p/'internal')
            except ValueError:pass
            else:raise AssertionError('Internal retry bypassed the one-call cap')
        assert len(attempts)==1 and counter['actual_solver_calls']==1
        d.claim(p/'once')
        try:d.claim(p/'once')
        except FileExistsError:pass
        else:raise AssertionError('Duplicate run accepted')
    ''')


def test_gate_stops_at_first_failure_and_exact_success_scope(package):
    execute(package,'''
        from tempfile import mkdtemp
        from pathlib import Path
        import diagnostic as d
        for failure in [0,3,5,None]:
            calls=[]
            def launch(kind,g,point,seconds):
                calls.append((kind,g,point,seconds))
                if kind=='full':return {'status':'finished','grid_name':g}
                return dict(grid_name=g,point=list(point),actual_solver_calls=1,returned_solution_count=1,
                    scip_version_verified=True,subproblem_presolve=False,
                    original_validation={'has_feasible_solution':len(calls)-1!=failure,'target_hit':True})
            out=d.run_sequence(Path(mkdtemp()),d.config(),launch)
            if failure is not None:
                assert len(calls)==failure+1 and not out['full']
            else:
                assert len(calls)==9 and len(out['fixed'])==6 and len(out['full'])==3
                assert [r[1] for r in calls[6:]]==list(d.GRIDS)
                assert [r[3] for r in calls]==[60]*6+[1800]*3
    ''')


def test_gate_requires_returned_solution_and_original_feasibility(package):
    execute(package,'''
        import copy
        import diagnostic as d
        row=dict(actual_solver_calls=1,returned_solution_count=1,scip_version_verified=True,
                 subproblem_presolve=False,original_validation={'has_feasible_solution':True,'target_hit':True})
        assert d.fixed_gate(row)
        for key,value in [('returned_solution_count',0),('actual_solver_calls',2),('subproblem_presolve',True)]:
            bad=copy.deepcopy(row);bad[key]=value;assert not d.fixed_gate(bad)
        for key in ['has_feasible_solution','target_hit']:
            bad=copy.deepcopy(row);bad['original_validation'][key]=False;assert not d.fixed_gate(bad)
        for g,p in d.POINTS:
            model,_=d.setup(g,p)
            v=d.values(model)
            v['x']=1000
            assert not d.original_check(g,v)['has_feasible_solution']
    ''')


def test_stopped_result_analysis_is_solver_free_and_reproducible(package):
    execute(package,'''
        import shutil
        from tempfile import mkdtemp
        from pathlib import Path
        from unittest.mock import patch
        import diagnostic as d
        import pyomo.environ as pyo
        from analyze_diagnostic import analyze
        root=Path(mkdtemp());run=root/'run';run.mkdir()
        shutil.copytree(d.PACKAGE,run/'package')
        d.save(run/'run.json',{'status':'stopped_error','config':d.config()})
        with patch.object(type(pyo.SolverFactory),'__call__',side_effect=AssertionError('No optimization permitted')):
            first=analyze(run,run/'analysis')
            second=analyze(run,root/'replayed')
        assert first==second and first['fixed_call_attempts']==first['full_loa_solve_entries']==0
        assert all(r['new_status']=='not_run' and r['new_objective'] is None for r in d.read(run/'analysis/comparison.json'))
        for path in (run/'analysis').iterdir():
            assert path.read_bytes()==(root/'replayed'/path.name).read_bytes(),path.name
    ''')


def test_actual_fixed_worker_serializes_config_before_mock_solver_boundary(package):
    execute(package,'''
        import inspect
        from pathlib import Path
        from tempfile import mkdtemp
        from unittest.mock import patch
        import diagnostic as d
        from gdp_compare import run_job
        from gdp_models import comparison as impl
        root=Path(mkdtemp())
        c=d.config();c['time_limit']=60;c['executable']='/usr/bin/true'
        def boundary(self,model,**kwargs):
            directory=impl.CONTEXT.directory
            recorded=d.read(directory/'effective_gdpopt_config.json')
            assert recorded==dict(subproblem_presolve=False,mip_presolve=True,time_limit=60,
                force_subproblem_nlp=True,mip_solver_args={'solver':'scip','mtype':'mip'},
                nlp_solver_args={'solver':'scip','mtype':'nlp'})
            assert kwargs['solver']=='scip' and kwargs['mtype']=='nlp'
            d.save(directory/'mock_solver_boundary.json',{'actual_external_calls':0})
            raise RuntimeError('test-only mock solver boundary reached')
        # Restore the faulty two expressions to prove this exercises the reported failure.
        scope=d.__dict__.copy()
        old=inspect.getsource(d.fixed_worker).replace('c.mip_solver_args.value()', 'c.mip_solver_args').replace('c.nlp_solver_args.value()', 'c.nlp_solver_args')
        exec(compile(old,'<pre-fix logging worker>','exec'),scope)
        def template(g,p):
            return impl.Template(None,{'case':'grid','grid_name':g,'instance_id':g,'diagnostic_point':list(p)})
        with patch.object(impl.TimedGAMS,'solve',boundary):
            legacy=run_job(template(*d.POINTS[0]),'loa',root/'legacy',c,target=scope['fixed_worker'])
            assert legacy['actual_solver_calls']==0 and legacy['message']=='TypeError: Object of type ConfigDict is not JSON serializable'
            assert not (root/'legacy/mock_solver_boundary.json').exists()
            for i,(g,p) in enumerate(d.POINTS):
                directory=root/str(i)
                row=run_job(template(g,p),'loa',directory,c,target=d.fixed_worker)
                assert row['actual_solver_calls']==1 and row['message']=='RuntimeError: test-only mock solver boundary reached',row
                assert d.read(directory/'mock_solver_boundary.json')['actual_external_calls']==0
                assert not row['gate_passed']
                assert not (directory/'solver_return.json').exists()
    ''')


def test_logging_fix_only_allows_exact_zero_call_predecessor(package):
    previous=ROOT/'results/grid_loa_presolve_disabled_20261025/grid_loa_presolve_disabled_dantzig_20261025.zip'
    with zipfile.ZipFile(previous) as z:
        original_manifest=z.read(previous.stem+'/DIAGNOSTIC_MANIFEST.json')
    execute(package, rf'''
        import copy,json,zipfile
        from pathlib import Path
        from tempfile import mkdtemp
        from unittest.mock import patch
        import diagnostic as d
        policy=d.read(d.PACKAGE/'DIAGNOSTIC_MANIFEST.json')['logging_fix_predecessor']
        row=dict(grid_name='holder_table',point=[3,1],actual_solver_calls=0,returned_solution_count=0,
                 gate_passed=False,message=policy['allowed_error'])
        base=dict(status='stopped_fixed_gate',actual_fixed_solver_calls=0,actual_full_loa_runs=0,
                  full_loa_worker_launches=0,fixed=[row],full=[])
        ledger=[dict(kind='fixed',grid_name='holder_table',point=[3,1],time_limit_s=60)]
        def fixture(case):
            r=copy.deepcopy(base);extra={{}};manifest={original_manifest!r}
            if case=='call':r['actual_fixed_solver_calls']=1
            if case=='row_call':r['fixed'][0]['actual_solver_calls']=1
            if case=='full':r['actual_full_loa_runs']=1
            if case=='error':r['fixed'][0]['message']='different failure'
            if case=='journal':extra['fixed/holder_table_3_1/solver_calls.jsonl']=b'{{"index":1}}\n'
            if case=='log':extra['fixed/holder_table_3_1/run.log']=b'--- Executing SCIP (Solvelink=2)\n'
            if case=='return':extra['fixed/holder_table_3_1/solver_return.json']=b'{{}}'
            if case=='source':manifest=b'{{}}'
            payload={{'run.json':json.dumps(r).encode(),'fixed/holder_table_3_1/result.json':json.dumps(r['fixed'][0]).encode(),
                'launch_ledger.jsonl':('\n'.join(json.dumps(e) for e in ledger)+'\n').encode(),
                'package/DIAGNOSTIC_MANIFEST.json':manifest,**extra}}
            payload['SHA256SUMS']=''.join(d.sha(b)+'  '+n+'\n' for n,b in payload.items()).encode()
            repo=Path(mkdtemp());archive=repo/policy['result_relative_path'];archive.parent.mkdir(parents=True)
            with zipfile.ZipFile(archive,'x') as z:
                for n,b in payload.items():z.writestr('run_fixture/'+n,b)
            return repo
        for case in ['valid','call','row_call','full','error','journal','log','return','source']:
            repo=fixture(case)
            with patch('subprocess.Popen',side_effect=AssertionError('No external commands permitted')):
                try:r=d.zero_call_predecessor(repo)
                except ValueError:assert case!='valid',case
                else:assert case=='valid' and r['actual_fixed_solver_calls']==r['actual_full_loa_runs']==0,case
    ''')
