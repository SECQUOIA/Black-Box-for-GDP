"""Build a sealed, self-contained CSTR15 GAMS runner without invoking a solver."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
PIN = '3e469dbeea8931670b8cd6752014ab7a767d3af5'


def build(output):
    from review_diagnostics import cstr15_gams as task

    output = Path(output).resolve()
    if output.exists() or output.with_suffix('.zip.sha256').exists():
        raise FileExistsError(output)
    members = {}
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    prefixes = ('gdp_models/', 'review_diagnostics/', 'review_comparison/',
                'reproduction/data/algebraic_audit/',
                'results/review_feasibility_followup_20261020/',
                'results/review_feasibility_tautology_20261020/')
    source = ROOT / 'external/dsda-gdp'
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != PIN:
        raise ValueError('Pinned model source checkout missing or changed')
    for name in tracked:
        p = ROOT / name
        if not p.is_file():
            continue
        if name.startswith(prefixes):
            # No manuscript, figures or unrelated runner artifacts are packaged.
            if p.suffix in {'.tex', '.bib', '.pdf', '.png'}:
                continue
            if name.startswith(('gdp_models/', 'review_diagnostics/', 'review_comparison/')) and p.suffix != '.py':
                continue
            members[name] = p.read_bytes()
    selection = json.loads((task.INPUT / 'selection.json').read_text())
    for name in selection['feasibility']['inputs_sha256']:
        members[name] = (ROOT / name).read_bytes()
    archive = selection['feasibility']['witness']['archive']
    for name in [*task.SOURCES, archive, task.HISTORY, 'LICENSE', 'run_cstr15_dantzig_check.sh', 'docs/cstr15_dantzig_check.md',
                 'build_cstr15_dantzig_check.py', 'tests/test_cstr15_gams.py', 'requirements-gdp.txt',
                 'docs/validation/cstr15_dantzig_preparation_20261021.json']:
        members[name] = (ROOT / name).read_bytes()
    for relative in ['gdp/cstr/gdp_reactor.py', 'gdp/dsda/cstr_15_initialization.json', 'gdp/dsda/model_serializer.py']:
        data = subprocess.check_output(['git', '-C', str(source), 'show', f'{PIN}:{relative}'])
        if data != (source / relative).read_bytes():
            raise ValueError('Pinned source file changed: ' + relative)
        members['external/dsda-gdp/' + relative] = data
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest = {'schema': 1, 'kind': task.ALLOCATION, 'code_revision': revision,
                'submodules': {'external/dsda-gdp': PIN},
                'files': [{'path': name, 'sha256': hashlib.sha256(data).hexdigest()} for name, data in sorted(members.items())],
                'compute_status': 'not_executed', 'new_NLP_calls_by_builder': 0,
                'historical_success_revision': '854a1a7fc5a20a5489d82ef7991a16aaf89025f3'}
    members['PACKAGE_MANIFEST.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    members['RUNNER_SHA256SUMS'] = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n' for name, data in sorted(members.items())).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo('cstr15_dantzig_runner/' + name, date_time=(2026, 10, 21, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    output.with_suffix('.zip.sha256').write_text(hashlib.sha256(output.read_bytes()).hexdigest() + '  ' + output.name + '\n')
    print(output)
    print(output.with_suffix('.zip.sha256'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
