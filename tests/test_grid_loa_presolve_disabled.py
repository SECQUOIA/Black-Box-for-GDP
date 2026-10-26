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
