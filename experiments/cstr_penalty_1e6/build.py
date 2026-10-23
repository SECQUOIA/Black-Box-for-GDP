"""Build only the 120 authorized CSTR penalty slots from archived primary runs."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REV = 'd8a9dd63721d2049a1744316c1781429ae7ad4c0'
ARCHIVES = ['results/archives/ipopt_dfo_cstr_20261015_174637_r1dzn5tk.zip',
            'results/archives/review_comparison_20261020_124949_return_1792527395393579314.zip']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(data):
    return (json.dumps(data, indent=2, allow_nan=False) + '\n').encode()


def build(output):
    entries, provenance, archives = {}, [], []
    for name in ARCHIVES:
        path = REPO / name
        expected = Path(str(path) + '.sha256').read_text().split()[0]
        assert digest(path.read_bytes()) == expected, name
        z = zipfile.ZipFile(path)
        prefix = z.namelist()[0].split('/')[0] + '/'
        archives.append((z, prefix))
        provenance.append({'path': name, 'sha256': expected, 'root': prefix})
    old, op = archives[0]
    new, np = archives[1]
    sources = ['ipopt_dfo_cstr.py', 'grid_dsda.py', 'instrumentation.py',
               'evaluation_trace.py', 'cpu_affinity.py', 'LICENSE']
    for name in sources:
        data = old.read(op + 'reproduction/' + name)
        assert data == new.read(np + 'reproduction/frozen/cstr/' + name), name
        entries[name] = data
    for name in old.namelist():
        prefix = op + 'reproduction/inputs/'
        if name.startswith(prefix) and not name.endswith('/'):
            rel = 'inputs/' + name[len(prefix):]
            data = old.read(name)
            assert data == new.read(np + 'reproduction/frozen/cstr/' + rel), rel
            entries[rel] = data
    for n in (5, 10, 15, 20, 25, 30):
        rel = f'data/cost_table_cstr_{n}.csv'
        entries[rel] = new.read(np + 'reproduction/' + rel)
    plan = []
    for n, b in zip((5, 10, 15, 20, 25, 30), (8, 15, 22, 29, 36, 43)):
        for seed in range(10):
            shared = None
            for method in ('dsda', 'rbfopt'):
                jobid = f'cstr_{n}_B{b}_seed{seed}_{method}'
                if method == 'dsda':
                    z, prefix = old, op + 'jobs/' + jobid + '/'
                    spec = json.loads(z.read(prefix + 'spec.json'))
                    runtime = json.loads(z.read(prefix + 'runtime.json'))
                    settings = json.loads(z.read(prefix + 'actual_settings.json'))
                    result = json.loads(z.read(prefix + 'result.json'))
                else:
                    z = new
                    candidates = [x.removesuffix('job.json') for x in z.namelist()
                                  if x.startswith(np + 'jobs/' + jobid + '_msrsm_genetic/attempt_')
                                  and x.endswith('/job.json')]
                    assert len(candidates) == 1, (jobid, candidates)
                    prefix = candidates[0]
                    job = json.loads(z.read(prefix + 'job.json'))
                    seal = json.loads(z.read(prefix + 'seal.json'))
                    for name, expected in seal.items():
                        assert digest(z.read(prefix + name)) == expected
                    spec = job['original_spec']
                    spec['settings']['global_search_method'] = 'genetic'
                    runtime = json.loads(z.read(prefix + 'runtime.json'))
                    settings = json.loads(z.read(prefix + 'actual_settings.json'))
                    result = json.loads(z.read(prefix + 'result.json'))
                    assert settings['global_search_method'] == 'genetic'
                events = [json.loads(line) for line in z.read(prefix + 'callbacks.jsonl').splitlines()]
                assert [e['point'] for e in events[:3]] == spec['starts']
                assert all(e['method_value_kind'] == '+inf' for e in events if not e['accepted'])
                assert spec['budget'] == b and len(events) <= b
                if shared is not None:
                    assert shared == spec['starts']
                shared = spec['starts']
                base = 'baseline/' + jobid + '/'
                for filename in ('callbacks.jsonl', 'result.json', 'runtime.json', 'actual_settings.json'):
                    entries[base + filename] = z.read(prefix + filename)
                entries[base + ('spec.json' if method == 'dsda' else 'job.json')] = z.read(prefix + ('spec.json' if method == 'dsda' else 'job.json'))
                plan.append({'spec': {**spec, 'unaccepted_response': 1e6},
                             'reference_runtime': runtime, 'reference_settings': settings,
                             'baseline_archive': provenance[0 if method == 'dsda' else 1],
                             'baseline_member': prefix, 'hard_seconds': 2100})
    assert len(plan) == 120
    source = entries['ipopt_dfo_cstr.py'].decode()
    original = source
    anchor = '        self.spec, self.table, self.directory = spec, table, directory\n'
    addition = '''        if 'unaccepted_response' in spec:
            if spec['method'] not in ('dsda', 'rbfopt') or spec['case'] not in CASES:
                raise ValueError('Penalty override is restricted to CSTR DSDA/RBFOpt')
            penalty = spec['unaccepted_response']
            if penalty not in (1e6, '+inf'):
                raise ValueError('Only 1e6 or +inf is supported')
'''
    assert source.count(anchor) == 1
    source = source.replace(anchor, anchor + addition)
    anchor = "        terminal = self.call_count + 1 == spec['budget']\n"
    addition = '''        penalty_applied = (not accepted and state in
                           ('evaluated_unaccepted', 'logical_exclusion_unmeasured')
                           and spec.get('unaccepted_response') == 1e6)
        if penalty_applied:
            value = 1e6
'''
    assert source.count(anchor) == 1
    source = source.replace(anchor, addition + anchor)
    anchor = '        self.events.append(event)\n'
    source = source.replace(anchor, "        if 'unaccepted_response' in spec:\n            event.update(penalty_applied=penalty_applied, unaccepted_response=spec['unaccepted_response'])\n" + anchor)
    entries['ipopt_dfo_cstr.py'] = source.encode()
    entries['provenance/penalty.patch'] = ''.join(difflib.unified_diff(
        original.splitlines(True), source.splitlines(True),
        fromfile='a/ipopt_dfo_cstr.py', tofile='b/ipopt_dfo_cstr.py')).encode()
    entries['provenance/original_ipopt_dfo_cstr.py.txt'] = original.encode()
    entries['plan.json'] = encoded(plan)
    # Confirm the PR49 implementation is consistent with these archived paths.
    pr_hashes = {}
    for name in ('ipopt_dfo_cstr.py', 'grid_dsda.py', 'review_comparison/worker.py',
                 'review_comparison/manuscript.py'):
        data = subprocess.check_output(['git', '-C', str(REPO), 'show', REV + ':' + name])
        assert data == (REPO / name).read_bytes(), name
        pr_hashes[name] = digest(data)
        entries['provenance/pr49/' + name + '.txt'] = data
    for name in ('runner.py', 'test_runner.py', 'run_dantzig.sh', 'README.txt', 'build.py'):
        entries[name] = (HERE / name).read_bytes()
    for path in sorted((HERE / 'validation').glob('*')):
        if path.is_file():
            entries['validation/' + path.name] = path.read_bytes()
    entries['provenance/manifest.json'] = encoded({
        'repository': 'SECQUOIA/Black-Box-for-GDP', 'pr': 49, 'pr_head': REV,
        'commit_created': False, 'archives': provenance, 'pr_source_sha256': pr_hashes,
        'baseline': 'DSDA original IPOPT 20261015; RBFOpt primary genetic 20261020',
        'frozen_source_note': 'Archived algorithm source retained; current PR has BAM budget, FMQA context, import and watchdog maintenance. New controller uses current watchdog cleanup; DSDA/RBFOpt optimizer blocks remain identical.',
        'factor': 'unaccepted_response +inf -> 1000000; 120 slots; starts read from archived callbacks',
        'inputs_and_targets_modified': False})
    # Current watchdog implementation handles remaining auxiliary child processes.
    current = (REPO / 'ipopt_dfo_cstr.py').read_text()
    checks = {}
    for label, start, end in [
        ('rbfopt_optimizer_block_identical', "    if method == 'rbfopt':", "    if method == 'bam':"),
        ('dsda_optimizer_block_identical', '    from grid_dsda import dsda_from_csv', '\n\ndef preflight(')]:
        left = original[original.index('def optimize('):]
        right = current[current.index('def optimize('):]
        checks[label] = left[left.index(start):left.index(end)] == right[right.index(start):right.index(end)]
        assert checks[label], label
    checks['grid_dsda_source_identical'] = entries['grid_dsda.py'] == (REPO / 'grid_dsda.py').read_bytes()
    assert checks['grid_dsda_source_identical']
    entries['provenance/compatibility.json'] = encoded(checks)
    entries['provenance/archived_vs_pr49.patch'] = ''.join(difflib.unified_diff(
        original.splitlines(True), current.splitlines(True),
        fromfile='archived/ipopt_dfo_cstr.py', tofile='pr49/ipopt_dfo_cstr.py')).encode()
    cleanup = current[current.index('def _stop_process_group('):current.index('def launch(')]
    entries['watchdog.py'] = ('import os\nimport signal\nimport time\n' + cleanup).encode()
    entries['SHA256SUMS'] = ''.join(f'{digest(data)}  {name}\n' for name, data in sorted(entries.items())).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(entries.items()):
            z.writestr('cstr_penalty_1e6_runner/' + name, data)
    Path(str(output) + '.sha256').write_text(f'{digest(output.read_bytes())}  {output.name}\n')
    for z, _ in archives:
        z.close()
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output.resolve())
