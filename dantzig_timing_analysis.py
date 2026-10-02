"""Rebuild process timing comparisons from archived Dantzig runs only."""

import csv
import hashlib
import json
from pathlib import Path
import zipfile

from fmqa_benchmark.protocol import REFERENCE, key, problem
from fmqa_compare import audit_fmqa, combine, result_directory
from nlp_cost_analysis import (
    METHODS, ROOT, baseline_comparison, jsonl, load_costs, normalize_run,
    read_json, reconstruct, sha, target_hit, write_csv, write_json,
)


def verify_dantzig_reference(archive_path, reference):
    """Require the exact archived CSV/manifest and the recorded Dantzig host."""
    with zipfile.ZipFile(archive_path) as archive:
        platforms = [n for n in archive.namelist() if n.endswith('/platform.txt')]
        if len(platforms) != 1:
            raise ValueError('Missing unique archived platform record')
        platform = archive.read(platforms[0]).decode().strip()
        if not platform.startswith('Linux dantzig.ecn.purdue.edu '):
            raise ValueError('Baseline was not recorded on Dantzig')
        for suffix in ('csv', 'manifest.json'):
            names = [n for n in archive.namelist() if n.endswith('/process_case_studies.' + suffix)]
            expected = (REFERENCE / f'{reference}.{suffix}').read_bytes()
            if len(names) != 1 or archive.read(names[0]) != expected:
                raise ValueError(f'{reference} differs from the archived Dantzig {suffix}')
    return {'kind': reference, 'path': str(archive_path), 'sha256': sha(archive_path),
            'host': 'dantzig.ecn.purdue.edu', 'platform': platform,
            'csv_sha256': sha(REFERENCE / f'{reference}.csv'),
            'manifest_sha256': sha(REFERENCE / f'{reference}.manifest.json')}


def measured_rows(csv_path, plan, source_by_method):
    specs = {key(s): s for s in plan}
    targets = {key(s): problem(s)['target'] for s in plan}
    with Path(csv_path).open(newline='') as stream:
        source_rows = list(csv.DictReader(stream))
    rows = []
    for record in source_rows:
        spec, target = specs[key(record)], targets[key(record)]
        rows.append({
            'case_name': spec['case_name'], 'grid_size': spec['grid_size'],
            'csv_name': record['csv_name'], 'method': record['method'],
            'seed': int(record['seed']), 'n_starts': int(record['n_starts']),
            'max_evals': int(record['max_evals']), 'total_evals': int(record['total_evals']),
            'lookup_best_value': float(record['best_value']), 'target_value': target,
            'lookup_solved': target_hit(float(record['best_value']), target),
            'measured_lookup_completion_s': float(record['wall_time_s']),
            'time_kind': 'measured_dantzig_lookup_completion',
            'source': source_by_method[record['method']], 'host': 'dantzig.ecn.purdue.edu',
            'nlp_inclusive_estimate_s': None, 'nlp_selected_attempts_s': None,
            'nlp_cost_status': 'missing_original_dantzig_evaluation_coordinates',
            'first_hit_time_s': None,
        })
    if len(rows) != 4 * len(plan):
        raise ValueError('Incomplete four-method Dantzig comparison')
    return rows


def runtime_figure(output, rows):
    import matplotlib.pyplot as plt
    import pandas as pd
    frame = pd.DataFrame(rows)
    selected = frame[((frame.case_name != 'cstr') | (frame.grid_size == 30)) &
                     ((frame.case_name != 'dynamic') | (frame.max_evals == 50))]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    names = {'column': 'Column', 'cstr': 'CSTR 30', 'small_batch': 'Small Batch', 'dynamic': 'Dynamic'}
    for ax, case in zip(axes.flat, names):
        group = selected[selected.case_name == case]
        means = group.groupby('method').measured_lookup_completion_s.mean().reindex(METHODS)
        ax.bar(range(4), means, color='#537896', zorder=3)
        ax.set_yscale('log')
        for i, value in enumerate(means):
            ax.annotate(f'{value:.4g}s', (i, value), xytext=(0, 5), textcoords='offset points',
                        ha='center', fontsize=9)
        ax.set(xticks=range(4), xticklabels=METHODS, ylabel='Mean recorded lookup run time (s, log scale)',
               title=f"{names[case]}, B={int(group.max_evals.iloc[0])}",
               ylim=(min(means) / 3, max(means) * 6))
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('Recorded Dantzig runtimes — all runs, including target failures', fontsize=15)
    fig.text(.5, .018,
             'Original DSDA/RBFOpt, BAM 5.0.0 and FMQA-SA server measurements.\n'
             'Lookup objectives: NLP solve costs are not included. Completion times, not first-hit times.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .065, 1, .95))
    for extension in ('png', 'pdf'):
        # Keep the old image link working, with corrected contents and labels.
        fig.savefig(output / f'cost_breakdown.{extension}', dpi=180)
    plt.close(fig)


def build(args):
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new output directory; existing analyses are not overwritten')
    sources = [
        verify_dantzig_reference(args.original_archive, 'original'),
        verify_dantzig_reference(args.bam_archive, 'bam5'),
    ]
    costs, preparation = load_costs(args.costs, args.solver)
    with result_directory(args.fmqa) as directory:
        protocol = audit_fmqa(directory)
        if protocol['runtime']['host'] != 'dantzig.ecn.purdue.edu':
            raise ValueError('FMQA clocks must come from Dantzig')
        combined = combine(directory, output)
        combined.write_bytes(combined.read_bytes().replace(b'\r\n', b'\n'))
        combined_manifest = read_json(combined.with_suffix('.manifest.json'))
        combined_manifest['output'].update(csv_sha256=sha(combined), csv_bytes=combined.stat().st_size)
        write_json(combined.with_suffix('.manifest.json'), combined_manifest)
        sources.append({'kind': 'fmqa', 'path': str(args.fmqa), 'sha256': sha(args.fmqa),
                        'host': protocol['runtime']['host'], 'cpu': protocol['cpu']})
        source_by_method = dict(zip(METHODS, (str(args.original_archive), str(args.original_archive),
                                             str(args.bam_archive), str(args.fmqa))))
        rows = measured_rows(combined, protocol['plan'], source_by_method)
        by_key = {(key(r), r['method']): r for r in rows}
        fmqa_costs, evaluations = [], []
        for spec in protocol['plan']:
            job = directory / 'jobs' / spec['job_id']
            trace = normalize_run(spec, jsonl(job / 'evaluations.jsonl'),
                                  read_json(job / 'result.json')['wall_time_s'],
                                  str(args.fmqa) + ':' + spec['job_id'], protocol['runtime']['host'])
            cost, ledger = reconstruct(trace, costs, preparation)
            fmqa_costs.append(cost)
            evaluations.extend(ledger)
            row = by_key[key(spec), 'FMQA-SA']
            row.update(nlp_inclusive_estimate_s=cost['strict_total_s'],
                       nlp_selected_attempts_s=cost['nlp_selected_attempts_s'],
                       nlp_cost_status='exact_model_cost_estimate' if cost['strict_total_s'] is not None
                       else 'missing_exact_model_point_costs',
                       first_hit_time_s=cost['lookup_first_hit_s'])
        targets = [{'spec': s, 'target': problem(s)['target']} for s in protocol['plan']]
    write_csv(output / 'run_costs.csv', rows)
    write_csv(output / 'fmqa_nlp_run_costs.csv', fmqa_costs)
    write_csv(output / 'fmqa_nlp_evaluation_costs.csv', evaluations)
    gdp_records = baseline_comparison(args.gdp_results, output, targets)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from timing_analysis import create_timing_outputs
    from benchmark_analysis import METHOD_COLORS
    METHOD_COLORS.update({'BAM 5.0.0': '#209c49', 'FMQA-SA': '#9254b5'})
    create_timing_outputs('case', output, results_csv=combined, dpi=180)
    timing_manifest = read_json(output / 'timing_analysis.manifest.json')
    timing_manifest['csv'] = combined.name
    write_json(output / 'timing_analysis.manifest.json', timing_manifest)
    runtime_figure(output, rows)
    plt.close('all')
    import pandas as pd
    summary = pd.DataFrame(rows).groupby(['case_name', 'grid_size', 'max_evals', 'method'], dropna=False).agg(
        runs=('seed', 'size'), solved=('lookup_solved', 'sum'),
        mean_completion_s=('measured_lookup_completion_s', 'mean'),
        median_completion_s=('measured_lookup_completion_s', 'median')).reset_index()
    summary.to_csv(output / 'case_summary.csv', index=False)
    overview = {'analysis_kind': 'archived_dantzig_completion_times', 'runs': len(rows),
                'runs_per_method': {m: sum(r['method'] == m for r in rows) for m in METHODS},
                'sources': sources, 'mac_trace_runs_used': 0,
                'original_rows_without_coordinate_traces': sum(r['method'] != 'FMQA-SA' for r in rows),
                'complete_fmqa_nlp_cost_estimates': sum(r['strict_total_s'] is not None for r in fmqa_costs),
                'cost_inventory_sha256': sha(args.costs / 'SHA256SUMS'),
                'gdp_completed_baseline_rows': len(gdp_records),
                'gdp_source_directory': str(args.gdp_results.relative_to(ROOT)) if args.gdp_results.is_relative_to(ROOT) else str(args.gdp_results),
                'gdp_sources': sorted({(r['source_directory'], r['source_created_utc']) for r in gdp_records}),
                'analysis_source_sha256': {p: sha(ROOT / p) for p in ('dantzig_timing_analysis.py', 'nlp_cost_analysis.py')},
                'comparison_time': 'Original archived wall_time_s, including lookup calls; no added NLP costs',
                'first_hit_comparison_available': False,
                'correction': 'Withdraw mixed Mac/Dantzig reconstructed totals and first-hit/cost-transfer/DFO-vs-GDP speed comparisons.'}
    write_json(output / 'manifest.json', overview)
    (output / 'README.md').write_text(
        '# Dantzig process timing comparison — corrected October 1\n\n'
        'All 556 comparison rows now use the original Dantzig completion clocks and outcomes: '
        'DSDA/RBFOpt from the September 10 archive, BAM 5.0.0 from the September 16 archive, '
        'and FMQA-SA from the September 25 archive. The baseline CSVs and manifests were '
        'checked byte-for-byte against their archives, including the recorded Dantzig host. '
        '**No Mac trace is used.** Original raw datasets are unchanged.\n\n'
        'The earlier analysis mistakenly substituted Mac paths and clocks for the original '
        'DSDA/RBFOpt/BAM runs. Its reconstructed totals, first-hit profiles, cost-transfer '
        'profiles and completion/quality comparison have been withdrawn.\n\n'
        '## What the corrected figures measure\n\n'
        '- `cost_breakdown.png` / `.pdf`: replacement for the old linked image; now shows '
        '**mean recorded Dantzig lookup runtime**, with a log axis and all failed-target runs included. '
        'It does not claim an NLP/search decomposition.\n'
        '- `time_performance_profiles.png`: relative **completed-run** time profiles.\n'
        '- `completion_time_profiles.png`: absolute completed-run time profiles.\n'
        '- `time_work_tradeoff.png`: recorded runtime versus evaluations and iterations.\n'
        '- `run_costs.csv`, `case_summary.csv`, `time_profile_runs.csv`: source-preserving totals, '
        'successes and paired ratios. Failed runs remain in the denominator.\n\n'
        '## NLP costs and missing records\n\n'
        'The original 417 DSDA/RBFOpt/BAM rows do not contain complete ordered callback '
        'coordinates or first-hit timestamps. Their NLP-inclusive times and first-hit times '
        'are **missing, not zero**. Identical starts do not establish identical Mac/server paths, '
        'so neither Mac paths nor prorated clocks are substituted. All four lookup comparisons '
        'exclude NLP solves consistently.\n\n'
        'FMQA has original Dantzig coordinate traces. Its separate `fmqa_nlp_run_costs.csv` '
        'and `fmqa_nlp_evaluation_costs.csv` retain exact-model cost estimates only: successful '
        'NLP evaluations charged, infeasible lookups zero by the stated accounting assumption, '
        'earlier failed attempts excluded, Dynamic preparation once. Missing CSTR5–25 costs '
        'remain missing. These estimates are not compared with NLP-exclusive DFO clocks.\n\n'
        '`gdp_baseline_comparison.csv` retains measured full-GDP results separately, using the '
        'completed October 1 BARON/HiGHS RIC/GLOA/LOA jobs and September 25 Big-M/Hull: '
        '45 completed jobs across five methods and nine models. Absolute target matching and '
        'at-or-better target attainment are separate columns. See the '
        '[current GDP audit](../../../gdp_comparison_current/analysis/README.md). A fair '
        'NLP-inclusive four-method comparison needs complete Dantzig coordinate traces for '
        'the other methods. The original lookup timings are not online NLP solve timings.\n\n'
        '## Reproduce\n\n```bash\n'
        'python nlp_cost_analysis.py --output results/new_dantzig_timing_comparison\n```\n\n'
        'This reads archived results only; no optimizer or NLP is rerun.\n')
    # Inventory the published tables so later edits cannot silently mix sources.
    write_json(output / 'artifact_checksums.json', {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(output.iterdir()) if p.is_file() and p.name != 'artifact_checksums.json'
               and p.suffix in {'.csv', '.json', '.md', '.png', '.pdf'}})
    print(json.dumps({k: v for k, v in overview.items() if k not in {'sources', 'analysis_source_sha256'}}, indent=2))
    return overview
