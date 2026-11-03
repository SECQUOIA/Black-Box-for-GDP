"""Maintained protocol integration with CSV consumers and standalone runners."""

import csv
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd
import pytest

import case_study_benchmark as cases
from instrumentation import (
    RESULT_FIELDS, make_result_record, result_schema, save_results_csv,
)

ROOT = Path(__file__).resolve().parents[1]
THREAD_VARIABLES = (
    'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
    'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS',
)


def record(method='DSDA', **report):
    return {**make_result_record(
        csv_name='compl_enum_cstr_5_baron_hull.csv', method=method, seed=0,
        n_starts=1, max_evals=1, best_value=2., best_point=[1, 1], total_evals=1,
        wall_time_s=.1, found_optimum=False, incumbent_trajectory=[2.],
        initial_evals=1, adaptive_evals=0, unique_evals=1,
    ), **report}


def test_mixed_csv_restores_optional_types_and_absent_fields(tmp_path):
    from case_study_analysis import load_case_study_results

    records = [record(observed_best_value=2., target_reached=False), record('RBFOpt')]
    output = tmp_path / 'mixed.csv'
    save_results_csv(records, output)
    with output.open() as handle:
        reader = csv.DictReader(handle)
        restored = [cases._deserialize_result_record(row) for row in reader]
        assert reader.fieldnames == list(RESULT_FIELDS) + ['observed_best_value', 'target_reached']
    assert restored == records
    frame = load_case_study_results(output)
    assert frame.loc[0, 'observed_best_value'] == 2.
    assert not frame.loc[0, 'target_reached']
    assert pd.isna(frame.loc[1, 'target_reached'])
    assert pd.isna(frame.loc[1, 'observed_best_value'])
    # No accepted observation is distinct from another method's absent report.
    save_results_csv([record(observed_best_value=None, target_reached=False)], output)
    with output.open() as handle:
        restored = cases._deserialize_result_record(next(csv.DictReader(handle)))
    assert restored['observed_best_value'] is None
    assert restored['target_reached'] is False


def test_checkpoint_requires_csv_header_to_match_manifest(tmp_path):
    output = tmp_path / 'checkpoint.csv'
    row = record(observed_best_value=2., target_reached=False)
    save_results_csv([row], output)
    key = dict(csv_name=row['csv_name'], method='dsda', seed=0, n_starts=1, max_evaluations=1)
    with pytest.raises(ValueError, match='schema does not match its manifest'):
        cases._read_checkpoint_csv(output, [key], expected_schema=result_schema())


@pytest.mark.parametrize('fields', [
    RESULT_FIELDS[:-1], RESULT_FIELDS + ('unknown',),
    RESULT_FIELDS + ('target_reached', 'observed_best_value'),
])
def test_optional_schema_does_not_relax_required_header_validation(fields):
    with pytest.raises(ValueError, match='schema'):
        result_schema(fields)


@pytest.mark.parametrize('builder,inventory', [
    ('build_ipopt_dfo_cstr', 'FILES'), ('build_ipopt_dfo_non_cstr', 'FILES'),
    ('process_dsda_fairness', 'sources'), ('process_followup_runner', 'source_files'),
    ('grid_trace_runner', 'source_files'), ('overnight_benchmark.common', 'source_files'),
    ('fmqa_benchmark_runner', 'source_files'),
])
def test_declared_bundle_imports_dsda_without_checkout_fallback(tmp_path, builder, inventory):
    module = importlib.import_module(builder)
    declared = getattr(module, inventory)
    paths = declared() if callable(declared) else declared
    paths = [Path(p) if Path(p).is_absolute() else ROOT / p for p in paths]
    assert ROOT / 'dsda_protocol.py' in paths
    for source in paths:
        if source.suffix != '.py':
            continue
        destination = tmp_path / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    # -I removes PYTHONPATH/cwd; only the extracted sources and installed
    # dependencies can satisfy imports, never the original checkout.
    script = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import grid_dsda, dsda_protocol, instrumentation
for module in (grid_dsda, dsda_protocol, instrumentation):
    assert Path(module.__file__).parent == Path(sys.argv[1])
result = grid_dsda.dsda_from_csv('synthetic', (0,), grid={(0,): 1., (1,): 0.}, verbose=False)
assert result['path'] == [(0,), (1,)]
'''
    subprocess.run([sys.executable, '-I', '-c', script, str(tmp_path)],
                   cwd=tmp_path, check=True, capture_output=True, text=True)


def test_replay_utility_import_has_no_thread_or_numerical_import_side_effects():
    env = dict(os.environ)
    for index, name in enumerate(THREAD_VARIABLES):
        if index % 2:
            env.pop(name, None)
        else:
            env[name] = str(index + 2)
    script = '''import os, sys
before = dict(os.environ)
from review_comparison.dsda_protocol_replay import validate_jobs
assert dict(os.environ) == before
assert 'numpy' not in sys.modules and 'pandas' not in sys.modules
'''
    subprocess.run([sys.executable, '-c', script], cwd=ROOT, env=env, check=True)


def test_explicit_replay_startup_limits_threads_before_numerical_imports(monkeypatch):
    from review_comparison import dsda_protocol_replay as replay
    for name in THREAD_VARIABLES:
        monkeypatch.setenv(name, '8')
    imported = []

    def load(name):
        assert all(os.environ[key] == '1' for key in THREAD_VARIABLES)
        imported.append(name)

    monkeypatch.setattr(replay.importlib, 'import_module', load)
    replay.prepare_replay_runtime()
    assert imported == ['dsda_protocol', 'grid_dsda', 'case_studies.dsda_domain']


def test_historical_overnight_lookup_retains_penalty_incumbent(tmp_path, monkeypatch):
    from overnight_benchmark.worker import lookup
    from process_followup_runner import plan

    actual = cases.CASE_RUNNERS['column']['dsda']
    calls = []

    def run(**kwargs):
        calls.append(kwargs['improvement_abs_tol'])
        return actual(**kwargs)

    monkeypatch.setitem(cases.CASE_RUNNERS['column'], 'dsda', run)
    result = lookup(plan()[0], {}, tmp_path)
    assert calls == [None]
    assert result['result_record']['incumbent_trajectory'][0] == 1e6
    entries = [json.loads(line) for line in (tmp_path / result['trace']['path']).read_text().splitlines()]
    assert entries[1]['incumbent'] == 1e6
