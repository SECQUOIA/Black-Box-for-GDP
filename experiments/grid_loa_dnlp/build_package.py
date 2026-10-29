"""Build a separate, explicit presolve-disabled plus SCIP/DNLP follow-up."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
NAME = 'grid_loa_dnlp_dantzig_20261025'
BASE = '181728c564d2d3de18741b0bfabe8d702507ed6d'
PRIOR = ROOT / 'results/grid_loa_presolve_disabled_20261025_v2/grid_loa_presolve_disabled_dantzig_20261025_v2.zip'
PRIOR_SHA = 'e5f40878ccd3b480ee18ef08e58c0f07ff9c42a3d574265003d7a224b6ed645e'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(obj):
    return (json.dumps(obj, indent=2, allow_nan=False) + '\n').encode()


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Expected exactly one source anchor: ' + old[:100])
    return source.replace(old, new)


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    if sha(PRIOR.read_bytes()) != PRIOR_SHA:
        raise ValueError('Prior package changed')
    with zipfile.ZipFile(PRIOR) as z:
        original = {n[len(PRIOR.stem) + 1:]: z.read(n) for n in z.namelist()}
    payload = {n: b for n, b in original.items() if n not in ('DIAGNOSTIC_MANIFEST.json', 'SHA256SUMS')}
    comparison = original['execution/gdp_models/comparison.py'].decode()
    comparison = once(comparison, 'nlp_solver_args={"solver": policy["nlp"], "mtype": "nlp"},',
                      'nlp_solver_args={"solver": policy["nlp"], "mtype": "dnlp" if config.get("diagnostic_dnlp") is True else "nlp"},')
    payload['execution/gdp_models/comparison.py'] = comparison.encode()
    payload['prior_comparison_option.diff'] = original['comparison_option.diff']
    payload['comparison_option.diff'] = ''.join(difflib.unified_diff(
        original['original_source/gdp_models/comparison.py'].decode().splitlines(keepends=True),
        comparison.splitlines(keepends=True), fromfile='original_source/gdp_models/comparison.py',
        tofile='execution/gdp_models/comparison.py')).encode()
    diagnostic = original['execution/diagnostic.py'].decode()
    diagnostic = once(diagnostic, "TAG = 'grid_loa_presolve_disabled_20261025_v2'", "TAG = 'grid_loa_dnlp_20261025'")
    diagnostic = once(diagnostic, 'diagnostic_presolve_disabled=True)', 'diagnostic_presolve_disabled=True, diagnostic_dnlp=True)')
    diagnostic = once(diagnostic, "nlp_solver_args={'solver': 'scip', 'mtype': 'nlp'}", "nlp_solver_args={'solver': 'scip', 'mtype': 'dnlp'}")
    start, end = diagnostic.index('def zero_call_predecessor('), diagnostic.index('\ndef environment(')
    diagnostic = diagnostic[:start] + '''def verified_predecessor(repository):
    from dnlp_support import predecessor
    return predecessor(repository)

''' + diagnostic[end:]
    diagnostic = once(diagnostic, 'predecessor = zero_call_predecessor(repository)', 'predecessor = verified_predecessor(repository)')
    diagnostic = once(diagnostic, '    return actual\n', '    from dnlp_support import compile_preflight\n    compile_preflight(c, output)\n    return actual\n')
    diagnostic = once(diagnostic, "requested_option={'subproblem_presolve': False}",
                      "requested_option={'subproblem_presolve': False, 'nlp_solver_args': {'solver': 'scip', 'mtype': 'dnlp'}}")
    diagnostic = once(diagnostic, "        save(self.directory / 'effective_gdpopt_config.json', settings)",
                      "        from dnlp_support import nlp_options\n        settings['nlp_solver_args_verified'] = nlp_options(message)\n        save(self.directory / 'effective_gdpopt_config.json', settings)")
    payload['execution/diagnostic.py'] = diagnostic.encode()
    analyzer = original['execution/analyze_diagnostic.py'].decode()
    analyzer = once(analyzer, 'Only subproblem_presolve=False changes the full LOA optimization configuration.',
                    'This follow-up combines subproblem_presolve=False with an explicit SCIP/DNLP subproblem export.\nIt is separate from the earlier single-option diagnostic, which stopped at GAMS compilation.')
    analyzer = once(analyzer, "new_subproblem_presolve=settings.get('subproblem_presolve'),",
                    "new_subproblem_presolve=settings.get('subproblem_presolve'),\n             new_nlp_solver_args=settings.get('nlp_solver_args_verified'),")
    payload['execution/analyze_diagnostic.py'] = analyzer.encode()
    for name in ('dnlp_support.py',):
        payload['execution/' + name] = (Path(__file__).parent / name).read_bytes()
    payload['README.md'] = (Path(__file__).parent / 'README.md').read_bytes()
    changes = {n for n in original if n in payload and original[n] != payload[n]}
    payload['followup_source.diff'] = ''.join(''.join(difflib.unified_diff(original[n].decode().splitlines(keepends=True),
          payload[n].decode().splitlines(keepends=True), fromfile='prior/' + n, tofile='followup/' + n)) for n in sorted(changes)).encode()
    old = json.loads(original['DIAGNOSTIC_MANIFEST.json'])
    manifest = {k: v for k, v in old.items() if not k.startswith('logging_fix') and k != 'files_sha256'}
    manifest.update(preparation_base_revision=BASE, prior_package_sha256=PRIOR_SHA,
        experiment='Separate follow-up authorized after the v2 GAMS compilation failure',
        algorithm_option_delta={'subproblem_presolve': {'old': True, 'new': False},
            'nlp_solver_args.mtype': {'old': 'nlp', 'new': 'dnlp'}},
        default_execution_path_changed=False, compile_preflight='Six actual GAMS action=c exports before any optimizer call',
        prior_fixed_interface_calls=1, prior_confirmed_scip_invocations=0, prior_full_loa_runs=0,
        new_followup_fixed_call_cap=6, new_followup_full_loa_cap=3,
        aggregate_interface_call_cap_including_failed_v2=7, aggregate_scip_fixed_call_cap=6,
        changed_from_prior_delivery=sorted(changes), added_execution_files=['execution/dnlp_support.py'],
        files_sha256={n: sha(b) for n, b in sorted(payload.items())})
    payload['DIAGNOSTIC_MANIFEST.json'] = encode(manifest)
    payload['SHA256SUMS'] = ''.join(f'{sha(b)}  {n}\n' for n, b in sorted(payload.items())).encode()
    dest = output / (NAME + '.zip')
    with zipfile.ZipFile(dest, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for n, b in sorted(payload.items()):
            info = zipfile.ZipInfo(NAME + '/' + n, date_time=(2026, 10, 25, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            z.writestr(info, b)
    Path(str(dest) + '.sha256').write_text(f'{sha(dest.read_bytes())}  {dest.name}\n')
    (output / 'BUILD_MANIFEST.json').write_bytes(encode({**manifest, 'package': dest.name, 'package_sha256': sha(dest.read_bytes())}))
    print(dest)
    return dest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
