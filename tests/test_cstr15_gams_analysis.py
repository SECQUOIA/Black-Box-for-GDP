"""Returned evidence integrity and numerical replay metadata; no solver calls."""

from copy import deepcopy
import hashlib
import json
import math
import zipfile

import pytest

from review_diagnostics import cstr15_gams_analysis as a
from review_diagnostics.common import read


def test_return_zip_integrity_and_member_tampering(tmp_path):
    raw, check = a.extract_verified(a.ARCHIVE, tmp_path / 'valid')
    assert check['all_member_hashes_verified'] and (raw / 'solver_input/gams.log').is_file()
    corrupted = tmp_path / a.ARCHIVE.name
    with zipfile.ZipFile(a.ARCHIVE) as source, zipfile.ZipFile(corrupted, 'w') as target:
        for name in source.namelist():
            content = source.read(name)
            target.writestr(name, content + b' ' if name.endswith('/summary.json') else content)
    corrupted.with_suffix('.zip.sha256').write_text(hashlib.sha256(corrupted.read_bytes()).hexdigest() + '  ' + corrupted.name + '\n')
    with pytest.raises(ValueError, match='manifest hash mismatch'):
        a.extract_verified(corrupted, tmp_path / 'bad-member')
    corrupted.with_suffix('.zip.sha256').write_text('0' * 64 + '  ' + corrupted.name + '\n')
    with pytest.raises(ValueError, match='ZIP checksum mismatch'):
        a.extract_verified(corrupted, tmp_path / 'bad-zip')


def summary_pair():
    with zipfile.ZipFile(a.ARCHIVE) as z:
        saved = json.loads(z.read(next(n for n in z.namelist() if n.endswith('/summary.json'))))
    bounds = {name: {k: v for k, v in row.items() if k in ('audit_id', 'lower_bound', 'source_result', 'source_result_sha256')} for name, row in saved['bounds'].items()}
    replay = deepcopy(saved)
    replay['objective'] = math.nextafter(math.nextafter(saved['objective'], math.inf), math.inf)
    replay['bounds'] = a.g.bound_comparisons({'objective': replay['objective']}, bounds, True)
    return saved, replay, bounds


def test_small_objective_roundoff_ratios_are_checked_from_each_objective():
    saved, replay, bounds = summary_pair()
    assert not a.g.equivalent(saved['bounds']['hull']['rho'], replay['bounds']['hull']['rho'])
    result = a.derived_metadata_check(saved, replay, bounds)
    assert result['hull']['rho']['difference'] != 0
    assert saved['bounds']['hull']['rho_gt_1'] == replay['bounds']['hull']['rho_gt_1']


@pytest.mark.parametrize('defect', ['ratio', 'objective', 'status'])
def test_roundoff_handling_does_not_accept_wrong_ratios_primals_or_status(defect):
    saved, replay, bounds = summary_pair()
    if defect == 'ratio':
        replay['bounds']['hull']['rho'] += 0.01
    elif defect == 'objective':
        replay['objective'] += 1e-4
        replay['bounds'] = a.g.bound_comparisons({'objective': replay['objective']}, bounds, True)
    else:
        replay['tightened_feasibility_passed'] = False
        replay['bounds'] = a.g.bound_comparisons({'objective': replay['objective']}, bounds, False)
    with pytest.raises(ValueError):
        a.derived_metadata_check(saved, replay, bounds)


def test_residual_ranking_is_validated_without_discarding_named_rows():
    left = {'constraints': [{'name': 'a', 'violation': 1e-16}, {'name': 'b', 'violation': 2e-16}], 'bounds': [], 'passes': True}
    right = deepcopy(left)
    right['constraints'][0]['violation'] = 3e-16
    for row in (left, right):
        row['largest_residuals'] = sorted(row['constraints'], key=lambda r: r['violation'], reverse=True)
    assert a.residual_metadata_check(left, right)['ranking_identical'] is False
    wrong = deepcopy(right)
    wrong['largest_residuals'].reverse()
    with pytest.raises(ValueError, match='ranking'):
        a.residual_metadata_check(left, wrong)
    right['constraints'][0]['violation'] = 1e-3
    right['largest_residuals'] = sorted(right['constraints'], key=lambda r: r['violation'], reverse=True)
    with pytest.raises(ValueError, match='residual/configuration'):
        a.residual_metadata_check(left, right)


def test_constant_proof_rejects_false_constants_and_does_not_hide_free_rows():
    pyo = pytest.importorskip('pyomo.environ')
    m = pyo.ConcreteModel()
    m.b = pyo.Var(domain=pyo.Binary, initialize=1)
    m.b.fix()
    m.x = pyo.Var(initialize=0)
    m.valid = pyo.Constraint(expr=m.b >= 1)
    m.free = pyo.Constraint(expr=m.x >= 0)
    assert [r['name'] for r in a.constant_rows(m)] == ['valid']
    m.b.fix(0)
    with pytest.raises(ValueError, match='False constant row'):
        a.constant_rows(m)


def test_returned_analysis_reproduces_tables_without_solver(tmp_path, cstr_diagnostic_sources, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Analysis must never run or prepare a solver call')
    monkeypatch.setattr(a.g, 'run', forbidden)
    monkeypatch.setattr(a.g, 'worker', forbidden)
    monkeypatch.setattr(a.g, 'prepare', forbidden)
    first, second = tmp_path / 'first', tmp_path / 'second'
    result = a.analyze(a.ARCHIVE, first)
    a.analyze(a.ARCHIVE, second)
    assert result['new_NLP_calls_in_analysis'] == 0
    assert result['server_new_NLP_calls'] == 1
    assert result['same_original_W03_start'] and result['same_discrete_configuration']
    assert result['equations']['exact_satisfied_constant_inequalities'] == 148
    assert result['equations']['GAMS_generated_equations_including_objective'] == 156
    assert result['Dantzig_minus_local_objective'] == pytest.approx(4.884981308350689e-15, abs=1e-18)
    check = read(first / 'verification.json')
    assert check['independent_primal_and_provenance_verified']
    assert check['replayed_summary']['tightened_feasibility_passed']
    assert check['replayed_summary']['bounds']['gloa']['tightened_bound_discrepancy_persists'] is True
    assert check['replayed_summary']['bounds']['hull']['tightened_bound_discrepancy_persists'] is False
    for name in ('comparison.csv', 'bound_comparison.csv'):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    with pytest.raises(FileExistsError):
        a.analyze(a.ARCHIVE, first)
    manifest = read(first / 'manifest.json')
    for name, digest in manifest['output_sha256'].items():
        assert hashlib.sha256((first / name).read_bytes()).hexdigest() == digest
