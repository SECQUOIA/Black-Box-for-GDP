"""Build four immutable Process SCIP deliveries from the preserved returned source."""
import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ARCHIVE = ROOT / 'results/archives/process_gdpopt_scip_20261025_003203_eqiw7649.zip'
EXPECTED_SHA = '8f4fe4ecddb0e448ff667f80f7b32df2c26f6bfca12656e9ed3ebea87d0fe8d8'
REVISION = 'dfde838896b4ce350771f7691f973d28a58f8f43'
GROUPS = {'minlp': (['bigm', 'hull'], 18), 'ric': (['ric'], 20), 'loa': (['loa'], 22), 'gloa': (['gloa'], 24)}
STAMP = '20261026'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


def original():
    data = ARCHIVE.read_bytes()
    assert sha(data) == EXPECTED_SHA, 'Original returned archive changed'
    with zipfile.ZipFile(ARCHIVE) as z:
        assert z.testzip() is None
        prefix = ARCHIVE.stem + '/'
        run = json.loads(z.read(prefix + 'run.json'))
        source = {n[len(prefix + 'source/'):]: z.read(n) for n in z.namelist() if n.startswith(prefix + 'source/')}
    for name, digest in run['source_sha256'].items():
        assert sha(source[name]) == digest, name
    rows = list(csv.DictReader((ROOT / 'results/process_gdpopt_scip_20261025/jobs.csv').open()))
    references = {r['instance_id']: float(r['target_value']) for r in rows}
    assert len(references) == 9 and all(float(r['target_value']) == references[r['instance_id']] for r in rows)
    return source, run, references


def build(output):
    output = output.resolve()
    assert not output.exists(), 'Use a fresh delivery directory; never overwrite existing ZIPs'
    source, old, references = original()
    output.mkdir(parents=True)
    entries = []
    for group, (methods, cpu) in GROUPS.items():
        stem = f'process_scip_{group}_dantzig_{STAMP}'
        config = {k: v for k, v in old['config'].items() if k not in ('peer_cpu', 'grids')}
        config.update(kind='process_scip_four_20261026', group=group, tag=STAMP,
                      methods=methods, planned_jobs=9*len(methods), cpu=cpu,
                      mip_solver='scip', nlp_solver='scip', minlp_solver='scip',
                      output_tag=f'process_scip_{group}_{STAMP}')
        payload = {'source/' + n: data for n, data in source.items()}
        payload.update({n: (HERE / n).read_bytes() for n in ('runner.py', 'run.sh', 'README.md')})
        payload['grid_recovery.py'] = (ROOT / 'experiments/grid_scip_recovery/grid_recovery.py').read_bytes()
        payload['solution_audit.py'] = (ROOT / 'scripts/analyze_process_scip_return.py').read_bytes()
        payload['config.json'] = encoded(config)
        payload['BASELINE.json'] = encoded({'archive': str(ARCHIVE.relative_to(ROOT)), 'archive_sha256': EXPECTED_SHA,
            'revision': REVISION, 'runtime': old['runtime'], 'references': references,
            'reference_source': 'results/process_gdpopt_scip_20261025/jobs.csv',
            'reference_source_sha256': sha((ROOT / 'results/process_gdpopt_scip_20261025/jobs.csv').read_bytes()),
            'original_source_sha256': {n: sha(data) for n, data in source.items()}})
        payload['MANIFEST.json'] = encoded({'baseline_revision': REVISION, 'baseline_archive_sha256': EXPECTED_SHA,
            'group': group, 'methods': methods, 'planned_benchmark_jobs': 9*len(methods),
            'preflight_optimizer_calls': 1 if group == 'minlp' else 2,
            'preflight_compile_only_calls': 18 if group == 'minlp' else 0,
            'builder_sha256': sha(Path(__file__).read_bytes()), 'unchanged_original_source_files': len(source),
            'differences': ['GDPopt MIP master HiGHS -> SCIP', 'Direct MINLP solver SCIP',
                           'One method group per package and separate CPU cores',
                           'Explicit transport-only retry wrapper inside original deadline',
                           'Effective config logging filter, heartbeat, independent returned-vector validation',
                           'Retain stopped GAMS scratch files; no model/FBBT/GLOA patch'],
            'files_sha256': {n: sha(data) for n, data in sorted(payload.items())}})
        payload['SHA256SUMS'] = ''.join(f'{sha(data)}  {n}\n' for n, data in sorted(payload.items())).encode()
        archive = output / (stem + '.zip')
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in sorted(payload.items()):
                info = zipfile.ZipInfo(stem + '/' + name, date_time=(2026, 10, 26, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
                z.writestr(info, data)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
        digest = sha(archive.read_bytes())
        archive.with_suffix('.zip.sha256').write_text(digest + '  ' + archive.name + '\n')
        entries.append({'group': group, 'methods': methods, 'cpu': cpu, 'jobs': 9*len(methods),
                        'zip': archive.name, 'sha256': digest, 'bytes': archive.stat().st_size,
                        'result_zip': f'/local/scratch/a/lee4382/repository/RBFopt_Test/results/{config["output_tag"]}/{config["output_tag"]}_result.zip'})
    (output / 'BUILD_MANIFEST.json').write_bytes(encoded({'baseline_revision': REVISION,
        'baseline_archive_sha256': EXPECTED_SHA, 'packages': entries,
        'actual_new_dantzig_benchmark_runs': 0, 'created_for_client_date': datetime(2026, 10, 26).date().isoformat()}))
    (output / 'README.md').write_bytes((HERE / 'README.md').read_bytes())
    (output / 'COMMANDS.md').write_text(commands(output, entries))
    return entries


def commands(output, entries):
    host = 'lee4382@dantzig.ecn.purdue.edu'
    repo = '/local/scratch/a/lee4382/repository/RBFopt_Test'
    lines = ['# Separate commands for the four Process SCIP packages', '',
             'Run uploads and downloads on the Mac, and run launch/monitor commands on Dantzig.',
             'The four jobs use distinct physical cores after topology verification.',
             'The following launch commands do not modify existing run directories.', '']
    for e in entries:
        stem = e['zip'][:-4]
        runner = f'{repo}/results/runners/{stem}'
        tag = f'process_scip_{e["group"]}_{STAMP}'
        lines.extend([f'## {e["group"]}: CPU {e["cpu"]}, {e["jobs"]} jobs', '', 'Upload on the Mac.', '', '```bash',
            f'scp {output / e["zip"]}{{,.sha256}} {host}:{repo}/', '```', '', 'Launch on Dantzig.', '', '```bash',
            '(', '  set -e', f'  cd {repo}', f'  sha256sum -c {e["zip"]}.sha256',
            f'  test ! -e results/runners/{stem}', f'  unzip -q {e["zip"]} -d results/runners',
            f'  nohup bash {runner}/run.sh run > {runner}/launch.log 2>&1 < /dev/null &',
            '  echo "STARTED_PID=$!"', ')', '```', '', 'Monitor progress on Dantzig.', '', '```bash',
            f'tail -n 80 -F {runner}/launch.log', '```', '',
            'After START appears, follow the current solver log on Dantzig.', '', '```bash',
            f'tail -n 80 -F "$(cat {repo}/results/{tag}/current_job.txt)/run.log"', '```', '',
            'Download on the Mac after RESULT_ZIP appears.', '', '```bash',
            f'scp {host}:{e["result_zip"]}{{,.sha256}} ~/Downloads/', '```', ''])
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(build(parser.parse_args().output), indent=2))
