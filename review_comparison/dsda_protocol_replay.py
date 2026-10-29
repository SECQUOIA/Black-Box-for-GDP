"""Solver-free equivalence replay of the adopted D-SDA records (issue #53)."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.abc
import io
import json
import math
import os
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {
    'grid': ('dsda_grid_target_stop_20261028_032943_2346732',
             '3611ba036df02ef8b155e32be7557c4bf7b88dfa1a5aff6e91c6d82fe7fb135a'),
    'process': ('dsda_abs1e5_rerun_20261028_020753_2004611',
                'e58982f7179b73c65d83134dcbe0b25854002685812b2511b24523e861c9929e'),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return json.loads(json.dumps(value, allow_nan=False))


def search_state(value):
    """Exclude measured durations and new reporting fields, not search state."""
    if isinstance(value, dict):
        return {k: search_state(v) for k, v in value.items() if k not in {
            'wall_time_s', 'objective_wall_times', 'observed_best_value', 'target_reached',
        }}
    if isinstance(value, (list, tuple)):
        return [search_state(v) for v in value]
    return value


def first_difference(a, b, path='state'):
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return f'{path}: different keys {a.keys() ^ b.keys()}'
        for k in a:
            if a[k] != b[k]:
                return first_difference(a[k], b[k], path + '.' + k)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return f'{path}: lengths {len(a)} != {len(b)}'
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return first_difference(x, y, f'{path}[{i}]')
    return f'{path}: {a!r} != {b!r}'


def key(job):
    spec = job['spec']
    return spec['scope'], spec['case'], spec['budget'], spec['seed']


def validate_jobs(jobs, scope):
    require(scope in ARCHIVES, 'Unknown replay scope')
    expected = 1050 if scope == 'grid' else 140
    require(len(jobs) == expected, 'Incomplete job population')
    require(len({key(j) for j in jobs}) == expected, 'Duplicate pairing key')
    require(len({j['spec']['job_id'] for j in jobs}) == expected, 'Duplicate job ID')
    groups = defaultdict(set)
    for job in jobs:
        s = job['spec']
        require(s['scope'] == scope and s['method'] == 'dsda', 'Wrong scope or method')
        require(len(s['starts']) == 3, 'Changed initial design size')
        groups[s['case'], s['budget']].add(s['seed'])
    require(all(seeds == set(range(10)) for seeds in groups.values()), 'Incomplete seed set')
    if scope == 'grid':
        cases = {s[0] for s in groups}
        require(len(cases) == 21 and set(groups) == {
            (case, b) for case in cases for b in (10, 30, 50, 70, 100)
        }, 'Wrong Grid conditions')
    else:
        require(len(groups) == 14, 'Wrong Process conditions')


def response_table(events):
    """Index responses by configuration, never by the expected callback number."""
    table = {}
    for event in events:
        point = tuple(event['point'])
        response = event['raw_objective'], event['accepted']
        require(point not in table or table[point] == response,
                f'Inconsistent stored response at {point}')
        table[point] = response
    return table


def read_response(table, point):
    point = tuple(point)
    if point not in table:
        raise KeyError(f'Missing stored lookup response at {point}; no solver fallback')
    return table[point]


def common_event(index, point, value, accepted):
    return dict(index=index, point=list(point), raw_objective=value, accepted=accepted,
                phase='initial' if index <= 3 else 'adaptive')


def event_projection(events):
    return [{k: e[k] for k in ('index', 'point', 'raw_objective', 'accepted', 'phase')}
            for e in events]


class BudgetStop(Exception):
    """Historical Process callback B is recorded before raising, without return."""


class ProcessResponses:
    def __init__(self, table, spec):
        self.table, self.spec = table, spec
        self.events, self.wall_times = [], []

    @property
    def call_count(self):
        return len(self.events)

    def __call__(self, point):
        require(self.call_count < self.spec['budget'], 'Callback beyond hard budget')
        if self.call_count < 3:
            require(list(point) == self.spec['starts'][self.call_count], 'Changed initial order')
        value, accepted = read_response(self.table, point)
        event = common_event(self.call_count + 1, point, value, accepted)
        terminal = event['index'] == self.spec['budget']
        event.update(method_value=value if accepted else 1e6,
                     callback_exit='budget_stop' if terminal else 'return',
                     value_returned_to_optimizer=not terminal)
        self.events.append(event)
        self.wall_times.append(0.0)
        if terminal:
            raise BudgetStop()
        return event['method_value']


def replay_grid(job, responses, domain):
    from dsda_protocol import ObservedObjective
    from grid_dsda import run_dsda_from_best_starting_points

    s = job['spec']
    events = []

    def lookup(point):
        value, accepted = read_response(responses, point)
        require(accepted and math.isfinite(value), 'Invalid Grid response')
        events.append(common_event(len(events) + 1, point, value, accepted))
        return value

    tracker = ObservedObjective(lookup)
    result = run_dsda_from_best_starting_points(
        s['case'] + '.csv', s['starts'], target_value=job['target'],
        max_points_explored=s['budget'], verbose=False, grid=domain,
        tracked_objective=tracker, **s['settings'],
    )
    return events, [r['path'] for r in result['runs']], (
        result['stop_reason'] or 'all_ranked_starts_exhausted'), result


def replay_process(job, responses):
    from grid_dsda import dsda_from_csv
    from case_studies.dsda_domain import box_membership, rank_observed_starts

    s = job['spec']
    oracle = ProcessResponses(responses, s)
    start, value, _, _ = rank_observed_starts(s['starts'], oracle, penalty=1e6)
    partial = {}

    # Read-only observation of an unwound frame mirrors the retained campaign's
    # terminal-exception recorder; it never changes search code or return values.
    def capture(frame, event, arg):
        frame.f_trace_lines = False
        if frame.f_code is dsda_from_csv.__code__:
            if event == 'exception' and isinstance(arg[1], BudgetStop):
                partial.update({k: frame.f_locals.get(k) for k in (
                    'path', 'history', 'current', 'current_val', 'best_seen_point',
                    'best_seen_value', 'major_iter')})
            return capture
        return None

    previous_trace = sys.gettrace()
    sys.settrace(capture)
    try:
        result = dsda_from_csv(
            'IPOPT_lookup', start, start_value=value,
            grid=box_membership(s['lower'], s['upper']), tracked_objective=oracle,
            max_points_explored=s['budget'] - 3, verbose=False, **s['settings'],
        )
    except BudgetStop:
        require(bool(partial), 'Missing terminal movement state')
        return oracle.events, partial['path'], 'budget_stop', partial
    finally:
        sys.settrace(previous_trace)
    return oracle.events, result['path'], 'no_improving_neighbor', result


def compare(job, expected, old_events, new_events, path, reason, state):
    from dsda_protocol import common_target_reached

    require(expected['spec'] == job['spec'], 'Pairing conditions differ')
    require(expected['error'] is None, 'Failed reference run')
    old, new = event_projection(old_events), event_projection(new_events)
    for i in range(max(len(old), len(new))):
        a = old[i] if i < len(old) else None
        b = new[i] if i < len(new) else None
        require(a == b, f'{job["spec"]["job_id"]}: first callback divergence {i + 1}: {a} != {b}')
    require(canonical(path) == expected['path'], 'Movement path mismatch')
    require(reason == expected['termination'], 'Termination mismatch')
    target = job['target']
    accepted = [e for e in new_events if e['accepted']]
    best = min(e['raw_objective'] for e in accepted) if accepted else None
    first = next((e['index'] for e in accepted if common_target_reached(e['raw_objective'], target)), None)
    hit = common_target_reached(best, target)
    require((best, hit, first, len(new_events)) == (
        expected['best_objective'], expected['hit'], expected['first_hit'], expected['evaluations']
    ), 'Observed best, target, first-hit, or callback count mismatch')
    if job['spec']['scope'] == 'grid':
        require(state['target_stop_checks'] == expected['algorithm_result']['target_stop_checks'],
                'Checkpoint mismatch')
        require(state['target_reached'] == hit and state['result_record']['found_optimum'] == hit,
                'Grid success reporting mismatch')
        require(canonical([r['history'] for r in state['runs']]) ==
                [r['history'] for r in expected['algorithm_result']['runs']], 'Grid history mismatch')
    else:
        for a, b in zip(old_events, new_events):
            require(all(a[k] == b[k] for k in (
                'method_value', 'callback_exit', 'value_returned_to_optimizer'
            )), 'Process response or terminal delivery mismatch')
        old_state = expected['algorithm_result'] or expected['partial_algorithm_state']
        require(canonical(state['history']) == old_state['history'], 'Process history mismatch')
    old_state = expected['algorithm_result'] or expected.get('partial_algorithm_state')
    actual_state, expected_state = search_state(state), search_state(old_state)
    if actual_state != expected_state:
        raise ValueError(job['spec']['job_id'] + ': ' + first_difference(actual_state, expected_state))
    return dict(scope=key(job)[0], case=key(job)[1], budget=key(job)[2], seed=key(job)[3],
                callbacks=len(new_events), hit=hit, first_hit=first, termination=reason,
                callback_order_equal=True, movement_path_equal=True)


def install_guard():
    attempts = []
    forbidden = {'pyomo', 'gams', 'pyscipopt', 'gdp', 'gdp_models', 'rbfopt',
                 'bam', 'cyipopt', 'fmqa_benchmark'}

    class Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split('.')[0] in forbidden:
                attempts.append('import:' + fullname)
                raise RuntimeError('Solver/model/other-method import prohibited: ' + fullname)

    require(not forbidden.intersection(sys.modules), 'Solver module already imported')
    sys.meta_path.insert(0, Blocker())

    def audit(event, args):
        if event in {'subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.exec', 'os.fork', 'os.forkpty'}:
            attempts.append(event)
            raise RuntimeError('External process prohibited during replay: ' + event)

    sys.addaudithook(audit)
    return attempts


def prepare_replay_runtime():
    """Explicit replay startup; importing validation helpers changes no settings."""
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS'):
        os.environ[name] = '1'
    # Warm numerical dependencies before installing the no-child-process guard.
    for module in ('dsda_protocol', 'grid_dsda', 'case_studies.dsda_domain'):
        importlib.import_module(module)


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    prepare_replay_runtime()
    attempts = install_guard()
    paired, inputs = [], {}
    for scope, (stem, digest) in ARCHIVES.items():
        archive = ROOT / 'results/archives' / (stem + '.zip')
        require(sha(archive) == digest, f'Archive hash mismatch: {archive}')
        inputs[str(archive.relative_to(ROOT))] = digest
        with ZipFile(archive) as z:
            prefix = stem + '/'

            def read(name):
                return json.loads(z.read(prefix + name))

            jobs = [j for j in read('reproduction/inputs/jobs.json') if j['spec']['scope'] == scope]
            validate_jobs(jobs, scope)
            stored = {}
            responses, domains = {}, {}
            for job in jobs:
                s = job['spec']
                jid = s['job_id']
                record = read(f'runs/{jid}/result.json')
                events = [json.loads(line) for line in z.read(prefix + f'runs/{jid}/callbacks.jsonl').splitlines()]
                require(record['spec'] == s, 'Condition mismatch in saved run')
                stored[jid] = record, events
                if scope == 'grid':
                    responses[s['case']] = response_table(
                        [common_event(0, p, v, a) for p, (v, a) in responses.get(s['case'], {}).items()] + events)
            for job in jobs:
                s = job['spec']
                case = s['case']
                if case not in domains:
                    if scope == 'grid':
                        rows = list(csv.DictReader(io.StringIO(z.read(prefix + f'reproduction/inputs/grids/{case}.csv').decode())))
                        domains[case] = dict.fromkeys((int(r['x']), int(r['y'])) for r in rows)
                    else:
                        rows = list(csv.DictReader(io.StringIO(z.read(prefix + f'reproduction/inputs/process/{case}_full.csv').decode())))
                        require(len(rows) == len({r['point'] for r in rows}), 'Duplicate Process lookup point')
                        responses[case] = {tuple(json.loads(r['point'])): (
                            float(r['objective']) if r['accepted'] == 'True' else None,
                            r['accepted'] == 'True') for r in rows}
                        domains[case] = True
                expected, old_events = stored[s['job_id']]
                if scope == 'grid':
                    events, path, reason, state = replay_grid(job, responses[case], domains[case])
                else:
                    events, path, reason, state = replay_process(job, responses[case])
                paired.append(compare(job, expected, old_events, events, path, reason, state))
        print(f'{scope}: {sum(r["scope"] == scope for r in paired)} exact replays', flush=True)
    counts = Counter((r['scope'], r['budget']) for r in paired if r['hit'])
    report = dict(
        purpose='Code equivalence only; no performance experiment or publication replacement',
        completed=len(paired), failed=0, missing=0,
        grid_hits={str(b): counts['grid', b] for b in (10, 30, 50, 70, 100)},
        process_hits=sum(r['hit'] for r in paired if r['scope'] == 'process'),
        grid_callbacks=sum(r['callbacks'] for r in paired if r['scope'] == 'grid'),
        process_callbacks=sum(r['callbacks'] for r in paired if r['scope'] == 'process'),
        all_callback_orders_paths_checkpoints_and_terminations_equal=True,
        solver_calls=0, process_nlp_calls=0, blocked_attempts=attempts,
        input_sha256=inputs,
        source_sha256={str(p.relative_to(ROOT)): sha(p) for p in (
            ROOT / 'grid_dsda.py', ROOT / 'dsda_protocol.py', Path(__file__),
            ROOT / 'case_studies/dsda_domain.py', ROOT / 'benchmark.py',
            ROOT / 'instrumentation.py',
            *(ROOT / f'case_studies/{case}_dsda.py' for case in (
                'cstr', 'column', 'small_batch', 'dynamic')))},
        environment=dict(python=sys.version, platform=sys.platform, machine=os.uname().machine),
    )
    require(not attempts, 'Blocked solver attempt occurred')
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    with (output / 'paired_runs.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(paired[0]))
        writer.writeheader()
        writer.writerows(paired)
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
