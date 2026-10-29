"""Build three immutable recovery packages from the verified split deliveries."""
import hashlib
import json
from pathlib import Path
import zipfile

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[1]
BASE = ROOT / 'results/runners/grid_gdpopt_scip_split_20261025'
OUTPUT = ROOT / 'results/runners/grid_gdpopt_scip_recovery_20261025'
AUDIT = ROOT / 'results/grid_gdpopt_scip_20261025'
CPUS = {'ric': 12, 'loa': 14, 'gloa': 16}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(data):
    return (json.dumps(data, indent=2) + '\n').encode()


def build():
    jobs = json.loads((AUDIT / 'jobs.json').read_text())
    selected = [j for j in jobs if j['status'] == 'error']
    assert len(jobs) == 63 and len(selected) == 46
    assert {m: sum(j['method'] == m for j in selected) for m in CPUS} == {'ric': 12, 'loa': 19, 'gloa': 15}
    inventories = json.loads((AUDIT / 'manifest.json').read_text())['archives']
    build_manifest = json.loads((BASE / 'BUILD_MANIFEST.json').read_text())
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if list(OUTPUT.glob('*.zip')):
        raise FileExistsError('Delivered recovery packages are immutable; choose another output/tag.')
    evidence = []
    for method, cpu in CPUS.items():
        base = next(r for r in build_manifest['packages'] if r['method'] == method)
        archive = BASE / base['archive']
        assert sha(archive.read_bytes()) == base['sha256']
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            old = {n[len(archive.stem)+1:]: z.read(n) for n in z.namelist() if not n.endswith('/')}
        for line in old['SHA256SUMS'].decode().splitlines():
            checksum, name = line.split('  ', 1)
            assert sha(old[name]) == checksum
        payload = {k: v for k, v in old.items() if k not in {'SHA256SUMS', 'PACKAGE_MANIFEST.json'}}
        chosen = [j for j in selected if j['method'] == method]
        raw = ROOT / 'results/archives' / chosen[0]['archive']
        # Bind selection back to immutable raw result records, not only a CSV.
        with zipfile.ZipFile(raw) as z:
            for j in chosen:
                data = z.read(raw.stem + f"/benchmark/{j['grid_name']}/{method}/result.json")
                assert sha(data) == j['result_sha256'] and json.loads(data)['status'] == 'error'
        selection = dict(policy='All original status=error jobs; no best-of selection; time limits excluded.',
                         original_archive=raw.name, original_archive_sha256=sha(raw.read_bytes()),
                         jobs=[{k: j[k] for k in ('grid_name', 'method', 'status', 'failure_kind',
                                                 'result_sha256', 'target_hit_verified')} for j in chosen])
        payload['RECOVERY_SELECTION.json'] = encoded(selection)
        package = json.loads(payload['gdp_scip_package.json'])
        package.update(planned_jobs=len(chosen), recovery_grids=[j['grid_name'] for j in chosen],
                       recovery_policy='grid-scip-network-and-bohachevsky2-v1')
        payload['gdp_scip_package.json'] = encoded(package)
        for name in ('grid_recovery.py', 'run_method.py'):
            payload[name] = (SOURCE / name).read_bytes()
        controller = payload['gdp_scip_experiments.py'].decode()
        before = "and p.name != '.lock' and not p.name.endswith('.tmp')\n                   and not any(s.startswith('gams-') for s in p.relative_to(directory).parts))"
        after = "and p.name != '.lock' and not p.name.endswith('.tmp'))"
        assert controller.count(before) == 1
        controller = controller.replace(before, after)
        before = 'Existing pyomo610-grid-v1 only; no new FBBT or GLOA patches'
        assert controller.count(before) == 1
        controller = controller.replace(before, 'Existing pyomo610-grid-v1 plus grid-scip-network-and-bohachevsky2-v1; see recovery_policy.json')
        payload['gdp_scip_experiments.py'] = controller.encode()
        payload['README.md'] = (SOURCE / 'README.md').read_bytes() + (
            f'\nThis package contains {len(chosen)} {method.upper()} error jobs and uses CPU {cpu}.\n'
            f'Its cumulative worker budget is at most {len(chosen) / 2:g} hours, plus preflight and packaging.\n').encode()
        changed = sorted(n for n in old if n in payload and old[n] != payload[n])
        assert changed == ['README.md', 'gdp_scip_experiments.py', 'gdp_scip_package.json', 'run_method.py']
        unchanged = {n: sha(d) for n, d in old.items() if n in payload and payload[n] == d}
        # Preserve all model, solver interface, reference and historical fix bytes.
        assert all(n in unchanged for n in old if n.startswith(('gdp_models/', 'benchmark_grids/')))
        payload['RECOVERY_PROVENANCE.json'] = encoded(dict(
            baseline_revision='d9bb8a9218c44c96dae544b504693d66a3daae5b',
            base_package=archive.name, base_package_sha256=base['sha256'],
            audit_jobs_sha256=sha((AUDIT / 'jobs.json').read_bytes()),
            builder_sha256=sha(Path(__file__).read_bytes()), changed_base_files=changed,
            added_files=['grid_recovery.py', 'RECOVERY_SELECTION.json', 'RECOVERY_PROVENANCE.json'],
            unchanged_base_files=unchanged, original_return_evidence=inventories,
            controller_changes=['Keep leftover GAMS scratch files after a watchdog stop.', 'Record the new correction policy.']))
        manifest = json.loads(old['PACKAGE_MANIFEST.json'])
        manifest.update(recovery_policy=package['recovery_policy'],
                        files=[{'path': n, 'sha256': sha(d)} for n, d in sorted(payload.items())])
        payload['PACKAGE_MANIFEST.json'] = encoded(manifest)
        payload['SHA256SUMS'] = ''.join(f'{sha(d)}  {n}\n' for n, d in sorted(payload.items())).encode()
        stem = f'grid_gdpopt_scip_recovery_{method}_dantzig_20261025'
        output = OUTPUT / (stem + '.zip')
        with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in sorted(payload.items()):
                info = zipfile.ZipInfo(stem + '/' + name, date_time=(2026, 10, 25, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
                z.writestr(info, data)
        checksum = sha(output.read_bytes())
        output.with_suffix('.zip.sha256').write_text(f'{checksum}  {output.name}\n')
        evidence.append(dict(method=method, cpu=cpu, jobs=len(chosen), archive=output.name,
                             sha256=checksum, bytes=output.stat().st_size, unchanged_files=len(unchanged)))
    (OUTPUT / 'BUILD_MANIFEST.json').write_bytes(encoded(evidence))
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    build()
