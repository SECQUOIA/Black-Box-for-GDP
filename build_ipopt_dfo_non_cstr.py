"""Build the non-CSTR Dantzig runner; no process models or solvers are imported."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

import ipopt_dfo_non_cstr as runner
from result_archives import archived_directory, datasets

ROOT = Path(__file__).resolve().parent
ORIGINAL = datasets()['original-ipopt-evaluations']
FILES = ['ipopt_dfo_non_cstr.py', 'run_ipopt_dfo_non_cstr_dantzig.sh', 'docs/ipopt_dfo_non_cstr_dantzig.txt',
         'grid_dsda.py', 'instrumentation.py', 'evaluation_trace.py', 'cpu_affinity.py', 'LICENSE',
         'case_studies/__init__.py', 'case_studies/common.py', 'fmqa_benchmark/__init__.py',
         'fmqa_benchmark/protocol.py', 'fmqa_benchmark/optimizer.py', 'fmqa_benchmark/qhd_surrogate.py']


def plan():
    from case_studies.common import generate_lhc_starting_points
    reference = runner.read(ROOT / 'benchmark_protocols/ipopt_dfo_process_designs.json')['process']
    rows = []
    for case, case_config in runner.CASES.items():
        for seed in range(10):
            starts = [list(p) for p in generate_lhc_starting_points(
                len(case_config['lower']), 3, case_config['lower'], case_config['upper'], seed)]
            old = [r for r in reference if r['case_name'] == case and r['seed'] == seed]
            if any(r['starting_points'] != starts for r in old):
                raise ValueError(f'Original LHC design mismatch: {case}/{seed}')
            for budget in case_config['budgets']:
                for method in runner.METHODS:
                    rows.append({'job_id': f'{case}_B{budget}_seed{seed}_{method}', 'case': case,
                                 'seed': seed, 'budget': budget, 'lower': case_config['lower'],
                                 'upper': case_config['upper'], 'starts': starts,
                                 'settings': runner.SETTINGS[method], 'method': method})
    assert len(rows) == 320 and len({r['job_id'] for r in rows}) == 320
    return rows


def add_original_inputs(entries, source):
    source_checks = dict(line.split('  ', 1)[::-1] for line in (source / 'SHA256SUMS').read_text().splitlines())
    for case in runner.CASES:
        d = source / 'gams_ipopt' / case
        manifest = runner.read(d / 'manifest.json')
        paths = [d / name for name in ('evaluations.csv', 'manifest.json', 'summary.json')]
        paths += sorted((d / 'records').glob('*.json'))
        if (d / 'preparation.json').exists():
            paths.append(d / 'preparation.json')
        checks = {}
        for p in paths:
            digest = runner.sha(p)
            assert digest == source_checks[p.relative_to(source).as_posix()], p
            name = p.relative_to(d).as_posix()
            entries[f'inputs/{case}/{name}'] = p.read_bytes()
            checks[name] = digest
        with (d / 'evaluations.csv').open() as stream:
            for row in csv.DictReader(stream):
                record = runner.read(d / 'records' / f'point_{int(row["point_index"]):06d}.json')
                assert record['point'] == json.loads(row['point'])
                assert record['case'] == case and record['solver'] == 'gams_ipopt'
                assert record['accepted'] == (row['accepted'] == 'True')
                for field in ('objective', 'candidate_objective', *runner.TIMES):
                    assert (float(row[field]) if row[field] else None) == record.get(field), (case, row['point'], field)
        info = {'source_archive': ORIGINAL['archive'], 'source_archive_sha256': ORIGINAL['sha256'],
                'source_directory': f"{ORIGINAL['archive']}!/{ORIGINAL['archive_root']}/gams_ipopt/{case}",
                'source_csv_absolute_at_build': f"{ROOT / ORIGINAL['archive']}!/{ORIGINAL['archive_root']}/gams_ipopt/{case}/evaluations.csv",
                'files_sha256': checks, 'attempt_selection': 'Original single enumeration attempt; no retries or best-of merging',
                'model': {'column': '17 maximum trays; min_trays=8; xD=xB=0.95; feed tray 9',
                          'dynamic': '9 stages; mode_transfer=False; nfe=30,ncp=3,LAGRANGE-RADAU',
                          'small_batch': 'Original 3 stages; unit counts 1..3 in each stage'}[case],
                'upstream': manifest['runtime']['source'], 'initialization': manifest['runtime']['initialization'],
                'acceptance': 'SOLVESTAT=1; MODELSTAT in {1,2}; solver status not error/aborted; optimal/locallyOptimal/globallyOptimal; finite objective; primal violation <=1e-5',
                'logical_exclusion_evidence': 'evidence/models.py.txt, evidence/domains.py.txt and pinned upstream model/logic source',
                'cost_scope': 'Same selected row; Dynamic template preparation separately preserved; absent measurements remain null'}
        entries[f'inputs/{case}/provenance.json'] = (json.dumps(info, indent=2) + '\n').encode()
        # Evidence is text only. No executable GDP model or legacy lookup is bundled.
        for name, digest in manifest['runtime']['source']['files_sha256'].items():
            folder = 'ld-sda-dynamic' if case == 'dynamic' else 'dsda-gdp'
            p = ROOT / 'external' / folder / name
            assert runner.sha(p) == digest, p
            entries[f'evidence/{case}/{name}.txt'] = p.read_bytes()
    for name in ('models.py', 'domains.py', 'evaluation.py', 'solvers.py'):
        p = source / 'source/gdp_models' / name
        assert runner.sha(p) == source_checks[p.relative_to(source).as_posix()]
        entries[f'evidence/{name}.txt'] = p.read_bytes()


def build(output, methods=None):
    selected = set(runner.METHODS if methods is None else methods)
    if not selected or not selected <= set(runner.METHODS):
        raise ValueError('Select one or more known methods')
    selected_plan = [spec for spec in plan() if spec['method'] in selected]
    entries = {name: (ROOT / name).read_bytes() for name in FILES}
    entries['README.txt'] = entries['docs/ipopt_dfo_non_cstr_dantzig.txt']
    vendor = ROOT / 'fmqa_benchmark/vendor/qhd'
    provenance = runner.read(vendor / 'provenance.json')
    for name, digest in provenance['files_sha256'].items():
        p = vendor / name
        assert runner.sha(p) == digest
        entries[str(p.relative_to(ROOT))] = p.read_bytes()
    entries[str((vendor / 'provenance.json').relative_to(ROOT))] = (vendor / 'provenance.json').read_bytes()
    with archived_directory(ROOT / ORIGINAL['archive']) as source:
        add_original_inputs(entries, source)
    entries['plan.json'] = (json.dumps(selected_plan, indent=2) + '\n').encode()
    entries['build_provenance.json'] = (json.dumps({
        'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
        'builder_sha256': runner.sha(Path(__file__)),
        'note': 'Working-tree source hashes are authoritative; no preexisting files modified by the builder.',
        'algorithm_settings_sources': {
            p: runner.sha(ROOT / p) for p in ('benchmark_protocols/ipopt_dfo_process_designs.json',
                 'benchmark_protocols/ipopt_dfo_cstr_designs.json', 'small_batch_rbfopt_solver.py',
                 'process_dsda_fairness.py', 'case_studies/common.py')},
        'target_tolerance_source': 'process_dsda_fairness.py:300; abs(value-target)<=1e-5*max(1,abs(target))',
        'initial_design': 'Original scipy.stats.qmc.LatinHypercube, scale (ub-lb), numpy.rint, distinct lattice points; no feasibility filter',
        'initial_design_generation_versions': {n: importlib.metadata.version(n) for n in ('numpy', 'scipy')},
        'rbfopt_surrogate_solver_permission': 'User explicitly permitted internal Bonmin/IPOPT on 2026-10-15; process GDP/NLP calls prohibited',
        'watchdog_seconds': 2100, 'prior_runner_not_reused': 'process_ipopt_rerun_20261015',
    }, indent=2) + '\n').encode()
    with tempfile.TemporaryDirectory(prefix='ipopt-lookup-input-check-') as temporary:
        root = Path(temporary)
        for name, data in entries.items():
            if name.startswith('inputs/'):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
        for case in runner.CASES:
            table, _ = runner.load_table(root, case)
            print(case, 'rows', len(table), 'accepted', sum(r['accepted'] == 'True' for r in table.values()))
    entries['SHA256SUMS'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in sorted(entries.items())).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr('ipopt_dfo_non_cstr_runner/' + name, data)
    output.with_suffix('.zip.sha256').write_text(f'{runner.sha(output)}  {output.name}\n')
    print('RUNNER_ZIP=' + str(output.resolve()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--methods', nargs='+', choices=runner.METHODS, help='Default: all; use bam for the budget-fix rerun')
    args = parser.parse_args()
    build(args.output, methods=args.methods)
