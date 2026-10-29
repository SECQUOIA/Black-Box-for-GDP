"""Validate the delivered frozen source without launching any optimizer."""
import hashlib
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import zipfile

import pytest

HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture(scope='module')
def delivery(tmp_path_factory):
    builder = module('process_scip_builder', HERE / 'build_packages.py')
    root = tmp_path_factory.mktemp('process-scip')
    entries = builder.build(root / 'delivery')
    paths = {}
    for entry in entries:
        with zipfile.ZipFile(root / 'delivery' / entry['zip']) as z:
            z.extractall(root / 'extracted')
        paths[entry['group']] = root / 'extracted' / entry['zip'][:-4]
    runner = module('process_scip_delivered_runner', paths['loa'] / 'runner.py')
    sys.path.insert(0, str(paths['loa']))
    yield SimpleNamespace(builder=builder, root=root, entries=entries, paths=paths, runner=runner)


def test_scopes_hashes_frozen_source_and_reproducible_zips(delivery):
    original, _, _ = delivery.builder.original()
    entries = delivery.builder.build(delivery.root / 'repeat')
    assert entries == delivery.entries
    all_jobs, cpus = [], []
    r = delivery.runner
    for entry in entries:
        path = delivery.paths[entry['group']]
        old = r.HERE
        r.HERE = path
        try:
            config, manifest = r.verify()
            specs, jobs = r.plans(config)
        finally:
            r.HERE = old
        assert len(specs) == 9 and len(jobs) == entry['jobs']
        assert config['mip_solver'] == config['nlp_solver'] == config['minlp_solver'] == 'scip'
        assert config['time_limit'] == 1800 and config['threads'] == 1
        assert config['record_gdp_path'] is True
        assert manifest['preflight_optimizer_calls'] == (1 if entry['group'] == 'minlp' else 2)
        for name, data in original.items():
            assert (path / 'source' / name).read_bytes() == data
        for line in (path / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            assert hashlib.sha256((path / name).read_bytes()).hexdigest() == digest
        all_jobs += [(j['instance_id'], j['method']) for j in jobs]
        cpus.append(config['cpu'])
    assert len(all_jobs) == len(set(all_jobs)) == 45
    assert len(set(cpus)) == 4
    with pytest.raises(AssertionError, match='fresh delivery'):
        delivery.builder.build(delivery.root / 'delivery')


@pytest.mark.parametrize('method', ['bigm', 'hull', 'ric', 'loa', 'gloa'])
def test_original_solve_boundary_receives_scip_and_clones_model(delivery, tmp_path, monkeypatch, method):
    import pyomo.environ as pyo
    from pyomo.gdp import Disjunct, Disjunction
    from gdp_models import comparison as impl
    from pyomo.opt import SolverResults, SolverStatus, TerminationCondition
    m = pyo.ConcreteModel()
    m.x = pyo.Var(bounds=(0, 4), initialize=1)
    m.a = Disjunct()
    m.a.c = pyo.Constraint(expr=m.x >= 1)
    m.b = Disjunct()
    m.b.c = pyo.Constraint(expr=m.x >= 3)
    m.choice = Disjunction(expr=[m.a, m.b])
    m.obj = pyo.Objective(expr=m.x)
    m.a.indicator_var.set_value(True)
    m.b.indicator_var.set_value(False)
    before = StringIO()
    m.pprint(ostream=before)
    calls = []
    result = SolverResults()
    result.solver.status = SolverStatus.ok
    result.solver.termination_condition = TerminationCondition.optimal
    result.problem.lower_bound = result.problem.upper_bound = 1

    def solve(model, **kwargs):
        assert model is not m
        model.x.set_value(2)
        calls.append(kwargs)
        return result

    if method in {'bigm', 'hull'}:
        monkeypatch.setattr(impl.TimedGAMS, 'solve', lambda self, model, **kw: solve(model, **kw))
    else:
        monkeypatch.setattr(pyo, 'SolverFactory', lambda name: SimpleNamespace(iteration=0, solve=solve))
    config = json.loads((delivery.paths['loa'] / 'config.json').read_text())
    template = SimpleNamespace(model=m, metadata={'instance_id': 'toy', 'case': 'cstr', 'cstr_size': 5})
    report = impl.solve_method(template, method, tmp_path, config, time.monotonic() + 1800)
    assert report['status'] == 'finished', report
    assert len(calls) == 1 and m.x.value == 1
    after = StringIO()
    m.pprint(ostream=after)
    assert m.a.c.active and m.choice.active and after.getvalue() == before.getvalue()
    if method in {'bigm', 'hull'}:
        assert calls[0] == {'solver': 'scip', 'mtype': 'minlp'}
    else:
        assert calls[0]['mip_solver_args'] == {'solver': 'scip', 'mtype': 'mip'}
        assert calls[0]['nlp_solver_args'] == {'solver': 'scip', 'mtype': 'nlp'}
        assert calls[0]['force_subproblem_nlp'] and calls[0]['init_algorithm'] == 'set_covering'
        assert 'subproblem_presolve' not in calls[0] and 'mip_presolve' not in calls[0]


@pytest.mark.parametrize('method', ['ric', 'loa', 'gloa'])
def test_real_config_logging_survives_tee_and_is_json_serializable(delivery, tmp_path, method):
    import pyomo.environ as pyo
    from pyomo.contrib.gdpopt.util import lower_logger_level_to
    algorithm = pyo.SolverFactory('gdpopt.' + method)
    config = algorithm.CONFIG()
    config.mip_solver_args = {'solver': 'scip', 'mtype': 'mip'}
    config.nlp_solver_args = {'solver': 'scip', 'mtype': 'nlp'}
    with delivery.runner.capture_options(tmp_path):
        with lower_logger_level_to(config.logger, tee=True):
            algorithm._log_solver_intro_message(config)
    options = json.loads((tmp_path / 'effective_gdpopt_config.json').read_text())
    assert options['mip_solver_args']['solver'] == options['nlp_solver_args']['solver'] == 'scip'
    assert options['subproblem_presolve'] == options['mip_presolve'] == 'true'
    text = (tmp_path / 'effective_gdpopt_config.txt').read_text()
    with pytest.raises(ValueError, match='not SCIP'):
        delivery.runner.parse_options(text.replace('solver: scip', 'solver: highs', 1))
    with pytest.raises(ValueError, match='presolve changed'):
        delivery.runner.parse_options(text.replace('subproblem_presolve: true', 'subproblem_presolve: false'))


def test_cpu_plan_rejects_shared_smt_core(delivery, monkeypatch):
    import cpu_affinity
    r = delivery.runner
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(os, 'sched_getaffinity', lambda _: set(range(96)), raising=False)
    monkeypatch.setattr(cpu_affinity, 'cpu_topology', lambda cpu: {'cpu': cpu, 'core_id': cpu // 2, 'physical_package_id': 0})
    assert r.topology({'cpu': 18})['distinct_physical_cores']
    monkeypatch.setattr(cpu_affinity, 'cpu_topology', lambda cpu: {'cpu': cpu, 'core_id': 1, 'physical_package_id': 0})
    with pytest.raises(ValueError, match='share a physical core'):
        r.topology({'cpu': 18})


def test_preflight_failure_blocks_all_benchmarks_and_second_launch(delivery, tmp_path, monkeypatch):
    from contextlib import nullcontext
    r = delivery.runner
    config, manifest = r.verify()
    monkeypatch.setenv('GDP_SCIP_REPOSITORY', str(tmp_path))
    monkeypatch.setattr(r, 'topology', lambda c: {})
    monkeypatch.setattr(r, 'core_lock', lambda c: nullcontext())
    monkeypatch.setattr(r, 'environment', lambda c, d: {})
    def fail(*args):
        raise RuntimeError('simulated preflight error')
    monkeypatch.setattr(r, 'preflight', fail)
    monkeypatch.setattr(r, 'execute', lambda *args: pytest.fail('Benchmark must not start'))
    assert r.run(config, manifest) == 1
    output = tmp_path / 'results' / config['output_tag']
    directory = Path((output / 'run_dir.txt').read_text().strip())
    record = json.loads((directory / 'run.json').read_text())
    assert record['status'] == 'stopped_error' and record['completed_jobs'] == 0
    assert (output / (config['output_tag'] + '_result.zip')).exists()
    with pytest.raises(FileExistsError):
        r.run(config, manifest)


def test_all_nine_jobs_retained_once_even_on_error_and_scratch_is_sealed(delivery, tmp_path, monkeypatch):
    import gdp_compare
    from gdp_models.comparison import save_json
    r = delivery.runner
    config, _ = r.verify()
    specs, planned = r.plans(config)
    directory = tmp_path / 'run_test'
    directory.mkdir()
    calls = []
    def fake_job(template, method, job, config, target):
        job.mkdir(parents=True)
        row = {'instance_id': template['instance_id'], 'method': method,
               'status': 'error' if not calls else 'finished', 'objective': None}
        save_json(job / 'result.json', row)
        (job / 'gams-stopped').mkdir()
        (job / 'gams-stopped/model.lst').write_text('retained interrupted solver evidence')
        calls.append((row['instance_id'], method))
        return row
    monkeypatch.setattr(gdp_compare, 'run_job', fake_job)
    monkeypatch.setattr(r, 'verify_solution', lambda *args: {'original_gdp_feasible': False})
    rows = r.execute(config, directory, {s['instance_id']: s for s in specs}, {})
    assert calls == [(p['instance_id'], p['method']) for p in planned]
    assert len(rows) == 9 and rows[0]['status'] == 'error'
    assert json.loads((directory / 'summary.json').read_text())['completed_jobs'] == 9
    r.pack(directory, 'test')
    with zipfile.ZipFile(tmp_path / 'test_result.zip') as z:
        for p in planned:
            base = 'run_test/benchmark/' + p['instance_id'] + '/' + p['method'] + '/'
            terminal = json.loads(z.read(base + 'terminal.json'))
            for name, digest in terminal['files_sha256'].items():
                assert hashlib.sha256(z.read(base + name)).hexdigest() == digest
            assert base + 'worker_result.json' in z.namelist()
            assert base + 'gams-stopped/model.lst' in z.namelist()
    with pytest.raises(ValueError, match='refusing to overwrite'):
        r.pack(directory, 'test')
