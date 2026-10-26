"""Validate the separate DNLP route and compiler gate without optimizer execution."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import textwrap
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('dnlp_builder', ROOT / 'experiments/grid_loa_dnlp/build_package.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


@pytest.fixture(scope='module')
def package(tmp_path_factory):
    root = tmp_path_factory.mktemp('dnlp_package')
    archive = builder.build(root / 'delivery')
    with zipfile.ZipFile(archive) as z:
        z.extractall(root)
    return root / builder.NAME / 'execution'


def execute(package, source):
    p = subprocess.run([sys.executable, '-c', textwrap.dedent(source)], cwd=package,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr


def test_explicit_dnlp_forwarding_and_original_default_route(package):
    execute(package, '''
        from pathlib import Path
        from tempfile import mkdtemp
        from time import monotonic
        from unittest.mock import patch
        import diagnostic as d
        from gdp_models import comparison as impl
        from gdp_models.grid_benchmark import grid_template
        manifest=d.verify_package()
        assert manifest['algorithm_option_delta']['nlp_solver_args.mtype']['new']=='dnlp'
        old=Path('../original_source')
        assert [str(p.relative_to(old)) for p in old.rglob('*') if p.is_file() and p.read_bytes()!=Path(p.relative_to(old)).read_bytes()]==['gdp_models/comparison.py']
        observed=[]
        class Capture:
            def solve(self,model,**kwargs):
                observed.append(kwargs);raise RuntimeError('Test boundary only')
        for enabled in [True,False]:
            c=d.config();c['diagnostic_dnlp']=c['diagnostic_presolve_disabled']=enabled
            with patch.object(impl.pyo,'SolverFactory',return_value=Capture()):
                impl.solve_method(grid_template('holder_table'),'loa',Path(mkdtemp()),c,monotonic()+1800)
        assert observed[0]['nlp_solver_args']=={'solver':'scip','mtype':'dnlp'}
        assert observed[0]['subproblem_presolve'] is False
        assert observed[1]['nlp_solver_args']=={'solver':'scip','mtype':'nlp'} and 'subproblem_presolve' not in observed[1]
        assert observed[0]['mip_solver_args']==observed[1]['mip_solver_args']=={'solver':'scip','mtype':'mip'}
        assert 'mip_presolve' not in observed[0]
    ''')


def test_effective_config_rejects_nlp_instead_of_dnlp(package):
    execute(package, '''
        from pathlib import Path
        from tempfile import mkdtemp
        import diagnostic as d
        import pyomo.environ as pyo
        for mtype in ['dnlp','nlp']:
            c=d.fixed_config(False);c.nlp_solver_args['mtype']=mtype;c.logger.setLevel(20)
            path=Path(mkdtemp())
            with d.actual_config_capture(path) as handler:
                try:pyo.SolverFactory('gdpopt.loa')._log_solver_intro_message(c)
                except ValueError:assert mtype=='nlp'
                else:
                    assert mtype=='dnlp' and handler.observed
                    assert d.read(path/'effective_gdpopt_config.json')['nlp_solver_args_verified']=={'mtype':'dnlp','solver':'scip'}
    ''')


def test_actual_workers_record_synthetic_returns_without_changing_models(package):
    execute(package, '''
        from pathlib import Path
        from tempfile import mkdtemp
        from unittest.mock import patch
        import pyomo.environ as pyo
        from pyomo.opt import SolverResults,TerminationCondition,SolverStatus
        import diagnostic as d
        from gdp_compare import run_job
        from gdp_models import comparison as impl
        c=d.config();c.update(time_limit=60,executable='/usr/bin/true')
        root=Path(mkdtemp())
        for i,(g,point) in enumerate(d.POINTS):
            def fake(self,model,**kwargs):
                assert kwargs['solver']=='scip' and kwargs['mtype']=='dnlp'
                settings=d.read(impl.CONTEXT.directory/'effective_gdpopt_config.json')
                assert settings['nlp_solver_args']=={'solver':'scip','mtype':'dnlp'}
                model.x.set_value(pyo.value(model.gx[point[0]]));model.y.set_value(pyo.value(model.gy[point[1]]))
                r=SolverResults();r.solver.status=SolverStatus.ok;r.solver.termination_condition=TerminationCondition.optimal;r.solution.add()
                print('SCIP version 9.2.4 (a94f778ac8)',flush=True)
                return r
            template=impl.Template(None,{'case':'grid','grid_name':g,'instance_id':g,'diagnostic_point':list(point)})
            with patch.object(impl.TimedGAMS,'solve',fake):
                row=run_job(template,'loa',root/str(i),c,target=d.fixed_worker)
            assert row['status']=='finished' and row['gate_passed'],row
            assert row['unchanged_subproblem_structure'] and row['returned_solution_count']==1
            assert row['original_validation']['has_feasible_solution'] and row['original_validation']['target_hit']
    ''')


def test_compile_only_gate_covers_six_and_stops_before_any_solve_on_failure(package):
    execute(package, '''
        from pathlib import Path
        from tempfile import mkdtemp
        from types import SimpleNamespace
        from unittest.mock import patch
        import dnlp_support as s
        import diagnostic as d
        for fail in [False,True]:
            calls=[]
            def compiler(command,**kwargs):
                calls.append(command)
                assert command==['/usr/bin/true','model.gms','action=c','lo=3','threads=1']
                text=(kwargs['cwd']/'model.gms').read_text()
                assert 'USING dnlp' in text and 'option dnlp=scip;' in text
                return SimpleNamespace(returncode=2 if fail else 0,stdout='Compilation error' if fail else 'Normal completion',stderr='')
            with patch.object(s.subprocess,'run',compiler):
                try:s.compile_preflight({'executable':'/usr/bin/true'},Path(mkdtemp()))
                except ValueError:assert fail and len(calls)==1
                else:assert not fail and len(calls)==6
    ''')


def test_previous_failure_is_kept_separate_and_exactly_identified(package):
    archive = ROOT / 'results/archives/grid_loa_presolve_disabled_20261025_v2_result.zip'
    execute(package, f'''
        from pathlib import Path
        from tempfile import mkdtemp
        import shutil
        import dnlp_support as s
        r=Path(mkdtemp());p=r/'results/grid_loa_presolve_disabled_20261025_v2'/s.PRIOR_RESULT;p.parent.mkdir(parents=True)
        shutil.copyfile({str(archive)!r},p)
        record=s.predecessor(r)
        assert record['prior_fixed_interface_calls']==1 and record['prior_confirmed_scip_calls']==0
        assert record['followup_limits']=={{'fixed_calls':6,'full_loa_runs':3}}
        p.write_bytes(b'wrong archive')
        try:s.predecessor(r)
        except ValueError:pass
        else:raise AssertionError('Wrong predecessor accepted')
    ''')


def test_real_launcher_stops_on_compile_gate_before_creating_solver_workers(package):
    archive = ROOT / 'results/archives/grid_loa_presolve_disabled_20261025_v2_result.zip'
    execute(package, f'''
        from pathlib import Path
        from tempfile import mkdtemp
        from unittest.mock import patch
        import diagnostic as d
        import dnlp_support as s
        import grid_gdp_benchmark
        import gdp_compare
        repository=Path(mkdtemp());order=[]
        def runtime(*args,**kwargs):
            assert kwargs=={{'exercise':False}};order.append('environment')
            return d.baseline()['run']['runtime']
        def compile_failure(*args):
            order.append('compile');raise ValueError('test compile failure before optimizers')
        with patch.object(d.sys,'platform','linux'), patch.dict(d.os.environ,{{'GDP_SCIP_REPOSITORY':str(repository)}}), \
             patch.object(d,'verified_predecessor',return_value={{'archive':{str(archive)!r}}}), \
             patch.object(grid_gdp_benchmark,'runtime',runtime), patch.object(s,'compile_preflight',compile_failure), \
             patch.object(gdp_compare,'run_job',side_effect=AssertionError('No worker permitted')):
            assert d.run()==1
        r=d.read(next((repository/'results'/d.TAG).glob('run_*/run.json')))
        assert order==['environment','compile']
        assert r['status']=='stopped_error' and r['message']=='ValueError: test compile failure before optimizers'
        assert r['actual_fixed_solver_calls']==r['actual_full_loa_runs']==0
    ''')
