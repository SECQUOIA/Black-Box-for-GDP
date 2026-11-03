"""Compare sealed RIC/GLOA/LOA recovery audits while retaining first attempts."""

import argparse
import hashlib
from itertools import combinations
import json
from pathlib import Path
import statistics
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import analyze_grid_gdpopt_scip_return as first  # noqa: E402

METHODS = ('ric', 'gloa', 'loa')
BASE_REVISION = '7a8b26a2d33e5d280594307b6ffd55fdcf10afea'
require, save, csvwrite, digest = first.require, first.save, first.csvwrite, first.digest


def verified_input(directory, name, hashes):
    checks = dict((name, sha) for sha, name in
                  (line.split('  ', 1) for line in (directory / 'ARTIFACT_SHA256SUMS').read_text().splitlines()))
    path = directory / name
    sha = digest(path.read_bytes())
    expected = checks.get(name, checks.get(str(path.relative_to(ROOT))))
    require(sha == expected, 'Changed audit input: ' + str(path))
    hashes[str(path.relative_to(ROOT))] = sha
    return json.loads(path.read_text())


def indexed(rows, method):
    result = {r['grid_name']: r for r in rows}
    require(len(result) == len(rows), 'Duplicate grid in ' + method)
    require(all(r['method'] == method for r in rows), 'Mixed method input')
    return result


def measures(rows):
    return dict(jobs=len(rows), target_hits=sum(r['target_hit_verified'] for r in rows),
                target_hits_without_error=sum(r['target_hit_verified'] and r['status'] != 'error' for r in rows),
                errors=sum(r['status'] == 'error' for r in rows),
                reported_optimal=sum(r['termination'] == 'optimal' for r in rows),
                optimal_but_misses_target=sum(r['termination'] == 'optimal' and not r['target_hit_verified'] for r in rows),
                time_limits=sum(r['termination'] == 'maxTimeLimit' for r in rows),
                time_limits_with_target=sum(r['termination'] == 'maxTimeLimit' and r['target_hit_verified'] for r in rows),
                worker_wall_s=sum(r['worker_wall_s'] for r in rows))


def select_descriptive(baseline, recovery):
    require(set(recovery) == {g for g, r in baseline.items() if r['status'] == 'error'},
            'Recovery must contain every original error and no non-error attempt')
    require(all(recovery[g]['reference_minimum'] == baseline[g]['reference_minimum'] for g in recovery),
            'Reference changed across attempts')
    return {g: recovery.get(g, r) for g, r in baseline.items()}


def trajectory_signatures(archive, method, jobs):
    result = {}
    with zipfile.ZipFile(archive) as z:
        for grid, row in jobs.items():
            path = f'{archive.stem}/benchmark/{grid}/{method}/grid_path.jsonl'
            data = z.read(path)
            require(digest(data) == row['grid_path_sha256'], 'Trajectory hash changed')
            trace = [json.loads(line) for line in data.splitlines() if line.strip()]
            result[grid] = [(r['event'], r['iteration'], r.get('grid_point'), r['completed_solver_calls']) for r in trace]
    return result


def compare(output):
    require(not output.exists() or not any(output.iterdir()), 'Use a fresh output directory')
    output.mkdir(parents=True, exist_ok=True)
    hashes, baseline, recovery, selected, manifests, trajectories = {}, {}, {}, {}, {}, {}
    baseline_rows = verified_input(ROOT / 'results/grid_gdpopt_scip_20261025', 'jobs.json', hashes)
    require(len(baseline_rows) == 63, 'Original denominator changed')
    method_rows, diagnostics = [], []
    for method in METHODS:
        baseline[method] = indexed([r for r in baseline_rows if r['method'] == method], method)
        require(set(baseline[method]) == set(first.old.GRID_NAMES), 'Original grid set changed')
        directory = ROOT / f'results/grid_gdpopt_scip_recovery_{method}_20261025'
        recovery[method] = indexed(verified_input(directory, 'jobs.json', hashes), method)
        manifests[method] = verified_input(directory, 'manifest.json', hashes)
        s = verified_input(directory, 'summary.json', hashes)
        for d in verified_input(directory, 'target_mismatch_diagnostics.json', hashes):
            diagnostics.append(dict(method=method, **d))
        require(s['target_tolerance'] == 1e-5, 'Target tolerance changed')
        archive = ROOT / 'results/archives' / manifests[method]['archive']['archive']
        archive_sha = digest(archive.read_bytes())
        require(archive_sha == manifests[method]['archive']['sha256'], 'Recovery archive changed')
        hashes[str(archive.relative_to(ROOT))] = archive_sha
        selected[method] = select_descriptive(baseline[method], recovery[method])
        trajectories[method] = trajectory_signatures(archive, method, recovery[method])
        rows = list(recovery[method].values())
        require(all(r['original_gdp_feasible'] for r in rows), 'Invalid returned solution')
        require(s['recovery']['target_hits'] == measures(rows)['target_hits'], 'Recovery summary differs')
        record = dict(method=method)
        for label, data in [('original', list(baseline[method].values())), ('recovery', rows),
                            ('descriptive', list(selected[method].values()))]:
            record.update({label + '_' + k: v for k, v in measures(data).items()})
        record.update(retained_first_attempts=21-len(rows), cpu=manifests[method]['archive']['runtime']['affinity']['cpu'],
                      benchmark_scip_mip_calls=sum(r['confirmed_scip_invocations'] for r in rows),
                      benchmark_nlp_calls=sum(r['benchmark_nlp_calls'] for r in rows),
                      network_retries=sum(r['network_retries'] for r in rows),
                      cumulative_all_attempts_worker_s=record['original_worker_wall_s']+record['recovery_worker_wall_s'])
        method_rows.append(record)

    wide, mismatches, timeouts = [], [], []
    for grid in first.old.GRID_NAMES:
        require(len({selected[m][grid]['reference_minimum'] for m in METHODS}) == 1, 'Cross-method reference changed')
        row = dict(grid_name=grid, reference_minimum=selected['ric'][grid]['reference_minimum'])
        for method in METHODS:
            data = selected[method][grid]
            cohort = 'recovery' if grid in recovery[method] else 'retained_first_attempt'
            detail = dict(grid_name=grid, method=method, attempt_cohort=cohort,
                          target_hit=data['target_hit_verified'], status=data['status'], termination=data['termination'],
                          objective=data['objective_recomputed'], grid_point=data['grid_point'],
                          worker_wall_s=data['worker_wall_s'], result_sha256=data['result_sha256'],
                          archive=manifests[method]['archive']['archive'] if cohort == 'recovery' else data['archive'])
            if data['termination'] == 'optimal' and not data['target_hit_verified']:
                mismatches.append(detail)
            if data['termination'] == 'maxTimeLimit':
                timeouts.append(detail)
            row.update({method + '_' + k: v for k, v in detail.items() if k not in ('method', 'grid_name')})
        row['methods_reaching_target'] = sum(selected[m][grid]['target_hit_verified'] for m in METHODS)
        wide.append(row)

    pairs, pair_summaries = [], []
    for a, b in combinations(METHODS, 2):
        shared = sorted(set(recovery[a]) & set(recovery[b]))
        both = only_a = only_b = neither = 0
        for grid in shared:
            x, y = recovery[a][grid], recovery[b][grid]
            ta, tb = x['target_hit_verified'], y['target_hit_verified']
            both += ta and tb
            only_a += ta and not tb
            only_b += not ta and tb
            neither += not ta and not tb
            sa, sb = trajectories[a][grid], trajectories[b][grid]
            prefix = 0
            for ea, eb in zip(sa, sb):
                if ea != eb:
                    break
                prefix += 1
            pairs.append(dict(method_a=a, method_b=b, grid_name=grid, a_target=ta, b_target=tb,
                              a_objective=x['objective_recomputed'], b_objective=y['objective_recomputed'],
                              a_termination=x['termination'], b_termination=y['termination'],
                              a_worker_s=x['worker_wall_s'], b_worker_s=y['worker_wall_s'],
                              a_first_target_s=x['first_target_incumbent_s'], b_first_target_s=y['first_target_incumbent_s'],
                              a_trace_events=len(sa), b_trace_events=len(sb), common_trace_prefix=prefix,
                              equal_event_iteration_coordinate_call_sequence=sa == sb,
                              shorter_trace_is_prefix=prefix == min(len(sa), len(sb))))
        pair_summaries.append(dict(method_a=a, method_b=b, common_jobs=len(shared), both_hit=both,
                                   a_only=only_a, b_only=only_b, neither=neither))

    common = sorted(set.intersection(*(set(recovery[m]) for m in METHODS)))
    common_timing = []
    for method in METHODS:
        rows = [recovery[method][g] for g in common]
        times = [r['first_target_incumbent_s'] for r in rows if r['target_hit_verified']]
        require(all(t is not None for t in times), 'Target incumbent lacks recorded time')
        common_timing.append(dict(method=method, common_jobs=len(rows), target_hits=len(times),
                                  worker_wall_s=sum(r['worker_wall_s'] for r in rows),
                                  median_worker_wall_s=statistics.median(r['worker_wall_s'] for r in rows),
                                  sum_first_target_s=sum(times), median_first_target_s=statistics.median(times),
                                  benchmark_scip_mip_calls=sum(r['confirmed_scip_invocations'] for r in rows)))
    overall = dict(methods=METHODS, original_attempts=measures(baseline_rows),
                   recovery_attempts=measures([r for m in METHODS for r in recovery[m].values()]),
                   descriptive_inventory=measures([r for m in METHODS for r in selected[m].values()]),
                   common_recovery_grids=common, pairwise_common_recovery=pair_summaries,
                   every_method_misses=[r['grid_name'] for r in wide if r['methods_reaching_target'] == 0],
                   any_method_misses=[r['grid_name'] for r in wide if r['methods_reaching_target'] < 3],
                   grids_with_at_least_one_target_hit=sum(r['methods_reaching_target'] > 0 for r in wide),
                   grids_with_all_three_target_hits=sum(r['methods_reaching_target'] == 3 for r in wide),
                   cumulative_worker_s=sum(r['cumulative_all_attempts_worker_s'] for r in method_rows),
                   benchmark_recovery_scip_mip_calls=sum(r['benchmark_scip_mip_calls'] for r in method_rows),
                   benchmark_recovery_nlp_calls=sum(r['benchmark_nlp_calls'] for r in method_rows),
                   network_retry_events=sum(r['network_retries'] for r in method_rows),
                   separate_recovery_preflight_calls={'scip/mip': 3, 'scip/nlp': 6},
                   target_tolerance=1e-5, optimization_calls_during_analysis=0,
                   scope='Descriptive mixtures retain every original non-error attempt; common recovery pairs are separate.',
                   timing_scope='Worker wall-time sums across concurrent packages are resource totals, not elapsed makespan.',
                   ranking_limit='One run per method/grid, unequal recovery subsets and nonexclusive CPUs do not establish method superiority.')
    for name, data in [('methods', method_rows), ('grid_21_comparison', wide), ('paired_common_recovery', pairs),
                       ('common_nine_timing', common_timing), ('optimal_target_mismatches', mismatches), ('time_limits', timeouts)]:
        save(output / (name + '.json'), data)
        csvwrite(output / (name + '.csv'), data)
    save(output / 'target_mismatch_diagnostics.json', diagnostics)
    save(output / 'summary.json', overall)
    save(output / 'manifest.json', dict(source_base_revision=BASE_REVISION, input_sha256=hashes,
         analysis_source_sha256={str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                'scripts/analyze_grid_gdpopt_scip_return.py': digest(Path(first.__file__).read_bytes()),
                                'scripts/analyze_grid_scip_return.py': digest(Path(first.old.__file__).read_bytes())},
         original_provider_manifests_unchanged=True, optimization_calls=0))
    save(output / 'verification.json', dict(original_attempts=63, recovery_attempts=sum(len(v) for v in recovery.values()),
         descriptive_attempts=sum(len(v) for v in selected.values()), all_inputs_hash_verified=True,
         selection_equals_original_errors=True, unchanged_reference_and_tolerance=True,
         no_missing_or_duplicate_grid_method=True, no_new_optimization=True))
    print(json.dumps(overall, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    compare(parser.parse_args().output)
