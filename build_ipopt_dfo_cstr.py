"""Freeze the CSTR-only Dantzig DFO bundle. No process models/solvers imported."""
import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

import ipopt_dfo_cstr as runner
from result_archives import archived_directory, datasets

ROOT = Path(__file__).resolve().parent
ORIGINAL = datasets()['original-ipopt-evaluations']
BOX_ARCHIVES = {
    (5, 10, 15): ROOT / 'results/cstr_box_ipopt/dantzig_cstr_box_ipopt_20261015_155116_eqpg0g41.zip',
    (20, 25): ROOT / 'results/archives/dantzig_cstr_box_ipopt_20261015_162507_3bnp0xm3.zip',
}
EXPECTED_ARCHIVE_HASHES = {
    (5, 10, 15): '8ae882d99e9309692b9ed773f2a87f076149f9b15d786d2e283fe0655c4a3e53',
    (20, 25): '38f1f99098113f67a0cec623eff88dfdf3e10bda2c7c07a5a356cbabce527677',
}
FILES = ['ipopt_dfo_cstr.py', 'run_ipopt_dfo_cstr_dantzig.sh', 'docs/ipopt_dfo_cstr_dantzig.txt',
         'grid_dsda.py', 'instrumentation.py', 'evaluation_trace.py', 'cpu_affinity.py', 'LICENSE',
         'case_studies/__init__.py', 'case_studies/common.py', 'fmqa_benchmark/__init__.py',
         'fmqa_benchmark/protocol.py', 'fmqa_benchmark/optimizer.py', 'fmqa_benchmark/qhd_surrogate.py']


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def plan():
    from case_studies.common import generate_lhc_starting_points
    references = [runner.read(ROOT / 'benchmark_protocols/fmqa_qhd_plan.json')['process'],
                  runner.read(ROOT / 'benchmark_protocols/process_dsda_fairness_reference.json')['plan']]
    rows = []
    for case, config in runner.CASES.items():
        for seed in range(10):
            starts = [list(p) for p in generate_lhc_starting_points(2, 3, config['lower'], config['upper'], seed)]
            for reference in references:
                old = [r for r in reference if r['case_name'] == 'cstr'
                       and r['grid_size'] == config['size'] and r['seed'] == seed]
                if len(old) != 1 or old[0]['starting_points'] != starts or old[0]['max_evaluations'] != config['budgets'][0]:
                    raise ValueError(f'Original LHC design/budget mismatch: {case}/{seed}')
            for method in runner.METHODS:
                budget = config['budgets'][0]
                rows.append({'job_id': f'{case}_B{budget}_seed{seed}_{method}', 'case': case,
                             'cstr_size': config['size'], 'seed': seed, 'budget': budget,
                             'lower': config['lower'], 'upper': config['upper'], 'starts': starts,
                             'settings': runner.SETTINGS[method], 'method': method})
    assert len(rows) == len({r['job_id'] for r in rows}) == 240
    return rows


def check_pairs(files, n):
    rows = list(csv.DictReader(io.StringIO(files['evaluations.csv'].decode())))
    names = set()
    for row in rows:
        point = json.loads(row['point'])
        name = (f'records/cstr_{n}_{point[0]:02d}_{point[1]:02d}.json' if n < 30
                else f'records/point_{int(row["point_index"]):06d}.json')
        if name in names:
            raise ValueError(f'Duplicate original attempt: {n}/{point}')
        names.add(name)
        record = json.loads(files[name])
        assert record['point'] == point and record['cstr_size'] == n and row['cstr_size'] == str(n)
        assert record['case'] == row['case'] == 'cstr' and record['solver'] == row['solver'] == 'gams_ipopt'
        assert record['accepted'] == (row['accepted'] == 'True')
        for field in ('status', 'termination', 'initialization', 'solver_status'):
            assert (row.get(field) or None) == record.get(field), (n, point, field)
        for field in ('objective', 'candidate_objective', *runner.TIMES):
            assert (float(row[field]) if row.get(field) else None) == record.get(field), (n, point, field)
        if n < 30:
            assert record['initialization_requested'] == 'mass_balance_zero_recycle'
            if point[1] <= point[0]:
                assert record['constraints_and_bounds_unchanged'] is True
                assert record['initial_primal_violation'] <= 1e-8
    if names != {name for name in files if name.startswith('records/')}:
        raise ValueError(f'Extra/ambiguous attempt records for N={n}')


def add_input(entries, n, files, info):
    check_pairs(files, n)
    case = f'cstr_{n}'
    info.update(availability='ready', cstr_size=n, initialization=runner.CASES[case]['initialization'],
        files_sha256={name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        attempt_selection='Single original attempt per coordinate; no retries or merging',
        acceptance='GAMS SOLVESTAT=1; MODELSTAT in {1,2}; optimal-class termination; solver status not error/aborted; finite objective; primal violation <=1e-5',
        logical_exclusion='y>x contradicts the active reactor/recycle GDP logic; see frozen evidence/models.py.txt and gdp_reactor.py.txt',
        cost_scope='Same coordinate and selected original attempt; unmeasured exclusions have unknown cost')
    entries.update({f'inputs/{case}/{name}': data for name, data in files.items()})
    entries[f'inputs/{case}/provenance.json'] = encoded(info)


def box_inputs(entries, sizes, archive):
    if runner.sha(archive) != EXPECTED_ARCHIVE_HASHES[sizes]:
        raise ValueError(f'Archive hash changed: {archive}')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError(f'Archive CRC failed: {archive}')
        prefix = archive.stem + '/'
        contents = {}
        for line in z.read(prefix + 'SHA256SUMS').decode().splitlines():
            digest, name = line.split('  ', 1)
            data = z.read(prefix + name)
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f'Original archive checksum mismatch: {name}')
            contents[name] = data
        run = json.loads(contents['run.json'])
        for n in sizes:
            files = {name: contents[name] for name in ('run.json', 'summary.json')}
            files['evaluations.csv'] = contents[f'cstr_{n}/evaluations.csv']
            files.update({name: data for name, data in contents.items() if name.startswith(f'records/cstr_{n}_')})
            info = {'source_archive': str(archive.relative_to(ROOT)), 'source_archive_sha256': runner.sha(archive),
                    'source_csv': f'{archive.relative_to(ROOT)}!/{prefix}cstr_{n}/evaluations.csv',
                    'source_csv_absolute_at_build': f'{archive}!/{prefix}cstr_{n}/evaluations.csv',
                    'upstream': run['runtime'][str(n)]['source'], 'verified_archive_files': len(contents)}
            add_input(entries, n, files, info)
        for name, data in contents.items():
            if name.startswith('source/') and name.endswith(('.py', '.txt', '.sh')):
                entries[f'evidence/box_{"_".join(map(str, sizes))}/{name}.txt'] = data


def old_input(entries):
    with archived_directory(ROOT / ORIGINAL["archive"]) as source:
        _old_input(entries, source)


def _old_input(entries, source):
    n = 30
    directory = source / 'gams_ipopt/cstr_30'
    checks = dict(line.split('  ', 1)[::-1] for line in (source / 'SHA256SUMS').read_text().splitlines())
    paths = [directory / name for name in ('evaluations.csv', 'manifest.json', 'summary.json')]
    paths += sorted((directory / 'records').glob('*.json'))
    files = {}
    for p in paths:
        if runner.sha(p) != checks[p.relative_to(source).as_posix()]:
            raise ValueError(f'N30 original checksum mismatch: {p}')
        files[p.relative_to(directory).as_posix()] = p.read_bytes()
    manifest = json.loads(files['manifest.json'])
    add_input(entries, n, files, {'source_archive': ORIGINAL['archive'], 'source_archive_sha256': ORIGINAL['sha256'],
        'source_csv': f"{ORIGINAL['archive']}!/{ORIGINAL['archive_root']}/gams_ipopt/cstr_30/evaluations.csv",
        'source_csv_absolute_at_build': f"{ROOT / ORIGINAL['archive']}!/{ORIGINAL['archive_root']}/gams_ipopt/cstr_30/evaluations.csv",
        'upstream': manifest['runtime']['source'],
        'record_selection_note': 'Original completed 465-row table, including all seven rejections; later retry studies are not merged'})
    for name in ('models.py', 'domains.py', 'evaluation.py', 'solvers.py'):
        p = source / 'source/gdp_models' / name
        assert runner.sha(p) == checks[p.relative_to(source).as_posix()]
        entries[f'evidence/cstr_30/{name}.txt'] = p.read_bytes()


def build(output, methods=None):
    selected = set(runner.METHODS if methods is None else methods)
    if not selected or not selected <= set(runner.METHODS):
        raise ValueError('Select one or more known methods')
    selected_plan = [spec for spec in plan() if spec['method'] in selected]
    entries = {name: (ROOT / name).read_bytes() for name in FILES}
    entries['README.txt'] = entries['docs/ipopt_dfo_cstr_dantzig.txt']
    vendor = ROOT / 'fmqa_benchmark/vendor/qhd'
    for name, digest in runner.read(vendor / 'provenance.json')['files_sha256'].items():
        p = vendor / name
        assert runner.sha(p) == digest
        entries[p.relative_to(ROOT).as_posix()] = p.read_bytes()
    entries['fmqa_benchmark/vendor/qhd/provenance.json'] = (vendor / 'provenance.json').read_bytes()
    for sizes, archive in BOX_ARCHIVES.items():
        partial = {}
        try:
            box_inputs(partial, sizes, archive)
            entries.update(partial)
        except (OSError, ValueError, KeyError, AssertionError, zipfile.BadZipFile) as error:
            for n in sizes:
                entries[f'inputs/cstr_{n}/provenance.json'] = encoded({'availability': 'not_ready',
                    'unavailable_reason': f'{type(error).__name__}: {error}'})
    partial = {}
    try:
        old_input(partial)
        entries.update(partial)
    except (OSError, ValueError, KeyError, AssertionError) as error:
        entries['inputs/cstr_30/provenance.json'] = encoded({'availability': 'not_ready',
            'unavailable_reason': f'{type(error).__name__}: {error}'})
    # Pinned upstream model evidence is text, never executable in this bundle.
    for name in ('gdp/cstr/gdp_reactor.py', 'gdp/dsda/dsda_functions.py', 'main_cstr.py'):
        p = ROOT / 'external/dsda-gdp' / name
        for n in runner.BUDGETS:
            info = json.loads(entries[f'inputs/cstr_{n}/provenance.json'])
            if info['availability'] == 'ready':
                assert runner.sha(p) == info['upstream']['files_sha256'][name], p
        entries[f'evidence/upstream/{name}.txt'] = p.read_bytes()
    entries['plan.json'] = encoded(selected_plan)
    source_names = ('benchmark_protocols/fmqa_qhd_plan.json', 'benchmark_protocols/process_dsda_fairness_reference.json',
                    'case_studies/cstr_rbfopt.py', 'case_studies/cstr_bam.py', 'case_studies/bam_common.py',
                    'case_studies/cstr_dsda.py', 'case_studies/cstr_case.py', 'case_studies/common.py', 'process_dsda_fairness.py')
    entries['build_provenance.json'] = encoded({
        'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
        'builder_sha256': runner.sha(Path(__file__)), 'algorithm_source_hashes': {p: runner.sha(ROOT / p) for p in source_names},
        'implementation_note': 'Independent CSTR runner snapshot; non-CSTR runner and files are not modified or imported',
        'target_tolerance_source': 'process_dsda_fairness.py:300; abs(value-target)<=1e-5*max(1,abs(target))',
        'initial_design': 'Original LatinHypercube, scale ub-lb, numpy.rint, distinct lattice points; no feasibility filter',
        'initial_design_generation_versions': {n: importlib.metadata.version(n) for n in ('numpy', 'scipy')},
        'user_authorized_auxiliary_solvers': 'Original surrogate/candidate solvers retained, including BAM native BARON and RBFOpt Bonmin/IPOPT',
        'process_evaluation': 'Frozen accepted IPOPT CSV only; no process models or enumeration executed',
        'published_target_is_report_only': True,
    })
    with tempfile.TemporaryDirectory(prefix='cstr-dfo-freeze-') as temporary:
        root = Path(temporary)
        for name, data in entries.items():
            if name.startswith('inputs/'):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
        reports = runner.write_input_report(root, root)
        for report in reports:
            print(report['case'], report['availability'], report.get('processed_rows'), report.get('accepted'), report.get('reason', ''))
        entries['inputs_report.json'] = (root / 'inputs_report.json').read_bytes()
        entries['inputs_report.csv'] = (root / 'inputs_report.csv').read_bytes()
    entries['SHA256SUMS'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in sorted(entries.items())).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr('ipopt_dfo_cstr_runner/' + name, data)
    output.with_suffix('.zip.sha256').write_text(f'{runner.sha(output)}  {output.name}\n')
    print('RUNNER_ZIP=' + str(output.resolve()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--methods', nargs='+', choices=runner.METHODS, help='Default: all; use bam for the budget-fix rerun')
    args = parser.parse_args()
    build(args.output, methods=args.methods)
