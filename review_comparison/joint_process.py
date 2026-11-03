"""Descriptive joint DFO/algebraic comparison from retained records; no solvers."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import statistics
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DFO = 'results/dsda_publication_20261028'
ALG = 'results/process_scip_four_analysis_20261026'
BASE_REVISION = 'd5e6ee5af33f569697a17e9c30b3dc919afb6856'
METHODS = ['dsda', 'rbfopt_msrsm_genetic', 'bam', 'fmqa_sa', 'uniform_without_replacement']
ALG_METHODS = ['bigm', 'hull', 'gloa', 'loa', 'ric']
LABELS = dict(zip(METHODS + ALG_METHODS,
                  ['D-SDA', 'RBFOpt', 'BAM', 'FMQA-SA', 'Uniform', 'Big-M', 'Hull', 'GLOA', 'LOA', 'RIC']))
CONDITIONS = [(f'cstr_{n}', b) for n, b in zip((5, 10, 15, 20, 25, 30), (8, 15, 22, 29, 36, 43))]
CONDITIONS += [('column', 13), ('small_batch', 10)] + [('dynamic', b) for b in (12, 15, 20, 30, 37, 50)]


def require(test, message):
    if not test:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def csv_rows(data):
    return list(csv.DictReader(io.StringIO(data.decode())))


def truth(value):
    require(value in (True, False, 'True', 'False'), f'Invalid Boolean: {value!r}')
    return value is True or value == 'True'


def key(r):
    return r['case'], int(r['budget']), int(r['seed']), r['method']


def point(value):
    return tuple(json.loads(value) if isinstance(value, str) else value)


def pname(case):
    return 'CSTR' + case[5:] if case.startswith('cstr_') else {'column': 'Column', 'small_batch': 'Small Batch', 'dynamic': 'Dynamic'}[case]


def validate_runs(dfo, alg):
    keys = [key(r) for r in dfo]
    expected = {(c, b, s, m) for c, b in CONDITIONS for s in range(10) for m in METHODS}
    require(len(keys) == len(set(keys)) and set(keys) == expected, 'Missing, duplicate, or unexpected DFO run')
    keys = [(r['instance_id'], r['method']) for r in alg]
    expected = {(c, m) for c in {c for c, _ in CONDITIONS} for m in ALG_METHODS}
    require(len(keys) == len(set(keys)) and set(keys) == expected, 'Missing, duplicate, or unexpected algebraic run')


def nlp_work(status):
    # Failed NLP returns remain work; logical/FBBT rejections do not invoke an NLP.
    if status in ('accepted', 'rejected'):
        return 1
    if status in ('preprocessing_infeasible', 'logical_infeasible'):
        return 0
    raise ValueError(f'Unclassified visited evaluation status: {status}')


def checked_events(events, row, inventory):
    events = sorted(events, key=lambda e: int(e['index']))
    require([int(e['index']) for e in events] == list(range(1, int(row['evaluations']) + 1)),
            f'Missing or duplicate callback: {key(row)}')
    count = 0
    first = None
    for e in events:
        config = inventory[row['case'], point(e['point'])]
        require(truth(e['accepted']) == truth(config['accepted']), 'Callback acceptance mismatch')
        count += nlp_work(config['status'])
        if row['first_hit'] and int(e['index']) == int(row['first_hit']):
            first = count
    return events, count, first


def quartiles(values):
    return statistics.quantiles(values, n=4, method='inclusive')


def load(root):
    inputs = {}

    def read(path, expected=None):
        data = (root / path).read_bytes()
        inputs[path] = sha(data)
        require(expected is None or inputs[path] == expected, f'Input hash mismatch: {path}')
        return data

    def published(directory, name):
        manifest = json.loads(read(directory + '/manifest.json'))
        return csv_rows(read(directory + '/' + name, manifest['outputs_sha256'][name]))

    dfo = [r for r in published(DFO, 'tables/run_records.csv') if r['scope'] == 'process' and r['method'] in METHODS]
    coverage = published(DFO, 'tables/configuration_coverage.csv')
    inventory = {(r['case'], point(r['coordinates'])): r for r in coverage}
    require(len(inventory) == len(coverage), 'Duplicate configuration inventory')
    read(ALG + '/manifest.json')
    checks = json.loads(read(ALG + '/artifact_checksums.json'))
    alg = csv_rows(read(ALG + '/jobs.csv', checks[ALG + '/jobs.csv']))
    calls = csv_rows(read(ALG + '/solver_calls.csv', checks[ALG + '/solver_calls.csv']))
    validate_runs(dfo, alg)

    sources = {}
    sources['dsda'] = published(DFO, 'tables/dsda_callbacks.csv')
    sources['column'] = published('results/column_publication_20261025', 'tables/column_callbacks.csv')
    sources['cstr30'] = published('results/cstr30_publication_20261025', 'tables/cstr30_callbacks.csv')
    sources['penalty'] = published('results/cstr_penalty_1e6_analysis_20261022', 'callback_paths.csv')
    oldpath = 'results/process_ipopt_bam_v2_20261015/tables/callbacks.csv'
    oldcheck = json.loads(read('reproduction/validation/checkout_replay.json'))
    sources['historical'] = csv_rows(read(oldpath, oldcheck['outputs']['process_replay/tables/callbacks.csv']))
    events = {name: defaultdict(list) for name in sources}
    case_budget = {c: b for c, b in CONDITIONS if c != 'dynamic'}
    for name, rows in sources.items():
        for e in rows:
            if name == 'dsda' and e['scope'] != 'process':
                continue
            if name == 'penalty' and e['policy'] != '1e6':
                continue
            e = dict(e)
            if name == 'dsda':
                e['method'] = 'dsda'
            if name == 'column':
                e['case'] = 'column'
            if name == 'penalty':
                e['budget'] = case_budget[e['case']]
            if e['method'] == 'rbfopt':
                e['method'] = 'rbfopt_msrsm_solver' if name == 'historical' else 'rbfopt_msrsm_genetic'
            events[name][key(e)].append(e)

    oldmanifest = json.loads(read('results/review_comparison_20261020/manifest.json'))
    archive = oldmanifest['return_archive']
    read(archive['path'], archive['sha256'])
    callback_rows, output = [], []
    observed = Counter()
    with zipfile.ZipFile(root / archive['path']) as z:
        for r in sorted(dfo, key=key):
            if r['method'] == 'dsda':
                ev = events['dsda'][key(r)]
            elif r['case'] == 'column':
                ev = events['column'][key(r)]
            elif r['case'] == 'cstr_30':
                ev = events['cstr30'][key(r)]
            elif r['record_source'].startswith('jobs/'):
                member = archive['root'] + '/' + r['record_source'] + '/evaluations.jsonl'
                ev = [json.loads(line) for line in z.read(member).splitlines()]
            elif r['record_source'].startswith('results/cstr_penalty'):
                ev = events['penalty'][key(r)]
            else:
                require(r['record_source'] == 'historical_process_runs.csv', 'Unknown DFO provenance')
                ev = events['historical'][key(r)]
            ev, nlp, first = checked_events(ev, r, inventory)
            require(truth(r['hit']) == (r['category'] == 'target_reached') == bool(r['first_hit']), 'DFO target mismatch')
            time = float(r['total_s'])
            require(math.isfinite(time) and time > 0, 'Missing DFO completion cost')
            for e in ev:
                config = inventory[r['case'], point(e['point'])]
                observed[r['case'], point(e['point']), r['method']] += 1
                callback_rows.append(dict(case=r['case'], budget=r['budget'], seed=r['seed'], method=r['method'],
                                          index=e['index'], point=json.dumps(point(e['point'])),
                                          status=config['status'], corresponding_nlp_calls=nlp_work(config['status'])))
            output.append(dict(case=r['case'], budget=int(r['budget']), seed=int(r['seed']), method=r['method'],
                               family='DFO', completion_s=time, time_basis='reconstructed_full_run',
                               objective=r['best_objective'], target_reached=truth(r['hit']),
                               target_rule='absolute_reference_agreement', category=r['category'],
                               callbacks=int(r['evaluations']), nlp_calls=nlp, nlp_first_target=first,
                               nlp_basis='corresponding_stored_fixed_configuration_evaluations',
                               nlp_unconfirmed_attempts=0, bound_conflict=False, source=r['record_source']))
    for config in coverage:
        for method in METHODS:
            require(observed[config['case'], point(config['coordinates']), method] == int(config[method]),
                    'Reconstructed paths differ from current publication coverage')
    for r in sorted(alg, key=lambda x: (x['instance_id'], x['method'])):
        cc = [c for c in calls if c['instance_id'] == r['instance_id'] and c['method'] == r['method'] and c['mtype'] == 'nlp']
        nlp = sum(truth(c['actual_solver_start_confirmed']) for c in cc)
        uncertain = sum(not truth(c['actual_solver_start_confirmed']) for c in cc)
        time = float(r['total_with_preparation_s'])
        require(math.isfinite(time) and time > 0, 'Missing algebraic completion time')
        output.append(dict(case=r['instance_id'], budget='', seed='', method=r['method'], family='algebraic',
                           completion_s=time, time_basis='measured_full_run_including_preparation',
                           objective=r['objective'], target_reached=truth(r['target_attained']),
                           target_rule='at_or_below_reference', category=r['normalized_outcome'],
                           callbacks='', nlp_calls=nlp if r['method'] in ('gloa', 'loa', 'ric') else '',
                           nlp_first_target='', nlp_basis='confirmed_SCIP_NLP_interface_calls' if cc else 'not_available',
                           nlp_unconfirmed_attempts=uncertain, bound_conflict=truth(r['bound_conflict']),
                           source=r['archive'] + '#' + r['job_member']))
    return output, callback_rows, inputs


def summaries(rows):
    output = []
    for family in ('DFO', 'algebraic'):
        groups = defaultdict(list)
        for r in rows:
            if r['family'] == family:
                groups[r['case'], r['budget'], r['method']].append(r)
        for (case, budget, method), rr in sorted(groups.items()):
            q = quartiles([r['completion_s'] for r in rr]) if family == 'DFO' else [rr[0]['completion_s']] * 3
            ns = [r['nlp_calls'] for r in rr]
            nq = quartiles(ns) if family == 'DFO' else [ns[0]] * 3
            output.append(dict(case=case, budget=budget, method=method, family=family, runs=len(rr),
                               target_hits=sum(r['target_reached'] for r in rr),
                               completion_q25_s=q[0] if family == 'DFO' else '', completion_q50_s=q[1],
                               completion_q75_s=q[2] if family == 'DFO' else '',
                               nlp_q25=nq[0] if family == 'DFO' else '', nlp_q50=nq[1],
                               nlp_q75=nq[2] if family == 'DFO' else '',
                               nlp_unconfirmed_attempts=sum(r['nlp_unconfirmed_attempts'] for r in rr),
                               bound_conflict=any(r['bound_conflict'] for r in rr)))
    return output


def render(rows, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    groups = [('joint_cstr_completion', CONDITIONS[:6]), ('joint_other_completion', CONDITIONS[6:])]
    with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 8, 'axes.titlesize': 9,
                         'axes.spines.top': False, 'axes.spines.right': False, 'pdf.fonttype': 42}):
        for name, conditions in groups:
            nr = math.ceil(len(conditions) / 2)
            panel_height = 1.93 if nr == 4 else 2.05
            fig, axs = plt.subplots(nr, 2, figsize=(7.2, panel_height * nr + .55), sharex=True, sharey=True)
            for ax, (case, budget) in zip(axs.flat, conditions):
                for i, method in enumerate(METHODS + ALG_METHODS):
                    rr = [r for r in rows if r['case'] == case and r['method'] == method and (r['family'] == 'algebraic' or r['budget'] == budget)]
                    require(len(rr) == (10 if method in METHODS else 1), 'Wrong plotted sample size')
                    require(all(.1 <= r['completion_s'] <= 3000 for r in rr), 'Run outside plotted time range')
                    if len(rr) == 10:
                        q = quartiles([r['completion_s'] for r in rr])
                        ax.plot([q[0], q[2]], [i, i], color='#bababa', lw=2.8, zorder=1)
                        ax.plot(q[1], i, marker='|', color='#333333', ms=7, zorder=2)
                    for r in rr:
                        y = i + (r['seed'] - 4.5) * .045 if len(rr) == 10 else i
                        marker = ('o' if len(rr) == 10 else 'D') if r['target_reached'] else 'x'
                        color = '#00786e' if r['target_reached'] else '#a54124'
                        ax.scatter(r['completion_s'], y, marker=marker, c=color, s=12 if len(rr) == 10 else 20,
                                   linewidths=.7, zorder=3)
                        if r['bound_conflict']:
                            ax.annotate('*', (r['completion_s'], y), xytext=(3, 2), textcoords='offset points', fontsize=9)
                    hit = sum(r['target_reached'] for r in rr)
                    ax.text(1.015, i, f'{hit}/10' if len(rr) == 10 else ('yes' if hit else 'no'),
                            transform=ax.get_yaxis_transform(), va='center', fontsize=7)
                ax.axhline(4.5, color='#999999', lw=.6)
                ax.set(xscale='log', xlim=(.1, 3000), ylim=(9.7, -.7), yticks=range(10),
                       yticklabels=[LABELS[m] for m in METHODS + ALG_METHODS], title=f'{pname(case)}, B={budget}')
                ax.tick_params(axis='y', length=0, labelleft=True, labelsize=7.5)
                ax.tick_params(axis='x', labelsize=7)
                ax.grid(axis='x', which='major', alpha=.18)
            for ax in axs[-1]:
                ax.set_xlabel('Full-run completion time (s)', fontsize=8)
            legend = [Line2D([], [], marker='o', color='#00786e', ls='', label='DFO target reached'),
                      Line2D([], [], marker='D', color='#00786e', ls='', label='Algebraic target reached'),
                      Line2D([], [], marker='x', color='#a54124', ls='', label='Target not reached')]
            fig.legend(handles=legend, loc='lower center', ncol=3, frameon=False, fontsize=7.5, bbox_to_anchor=(.5, .002))
            fig.subplots_adjust(left=.105, right=.94, top=.955, bottom=.095 if nr == 3 else .075, hspace=.42, wspace=.48)
            fig.savefig(out / (name + '.pdf'), metadata={'CreationDate': None, 'ModDate': None})
            fig.savefig(out / (name + '.png'), dpi=150)
            plt.close(fig)


def table_tex(summary):
    lines = [r'\begin{table}[htbp]\centering\small',
             r'\caption{NLP workload in the recorded process comparisons.',
             r'DFO entries are median counts of corresponding fixed-configuration NLP evaluations over ten seeds; GDPopt entries count confirmed SCIP NLP interface calls in one run.',
             r'Logical and preprocessing rejections are excluded; rejected NLP returns are retained.',
             r'These counts are not internal solver iterations or equally costly subproblems.}',
             r'\label{tab:joint-nlp-workload}',
             r'\setlength{\tabcolsep}{3.5pt}', r'\begin{tabular}{lrrrrrrrrr}\toprule',
             r'Case & \(B\) & D-SDA & RBFOpt & BAM & FMQA-SA & Uniform & GLOA & LOA & RIC\\\midrule']
    for case, budget in CONDITIONS:
        cells = []
        for m in METHODS + ['gloa', 'loa', 'ric']:
            r = next(r for r in summary if r['case'] == case and r['method'] == m and (r['family'] == 'algebraic' or r['budget'] == budget))
            cells.append(f"{r['nlp_q50']:g}" + (r'\(^{\dagger}\)' if r['nlp_unconfirmed_attempts'] else ''))
        lines.append(' & '.join([pname(case), str(budget), *cells]) + r' \\')
    lines += [r'\bottomrule\end{tabular}', r'\par\smallskip', r'\begin{minipage}{0.98\linewidth}\footnotesize',
              r'The same single Dynamic GDPopt execution is repeated across budget rows for reference.',
              r'\(^{\dagger}\)CSTR25 LOA and CSTR30 RIC each have one additional NLP interface attempt without a confirmed solver start; these attempts are excluded.',
              r'Internal NLP counts for direct Big-\(M\) and Hull are unavailable and are not treated as zero.',
              r'\end{minipage}', r'\end{table}', r'\FloatBarrier']
    return '\n'.join(lines) + '\n'


def supplement_tex(summary):
    text = r'''\clearpage
\section{Joint comparison with algebraic methods}
\label{sec:supp-joint-comparison}
Figures~\ref{fig:joint-cstr-completion} and \ref{fig:joint-other-completion} place the recorded DFO and algebraic results on the same completion-time axis.
DFO times are reconstructed from the stored search paths and separately measured configuration costs; algebraic times are measured and include preparation.
Each DFO condition has ten seeds, whereas each algebraic method has one run per problem.
The original target rules are retained: absolute agreement with the reference for DFO, and a feasible objective at or below the reference for algebraic methods, using the stated tolerance.
This descriptive comparison does not estimate an algebraic success probability.

'''
    text += table_tex(summary) + '\n'
    for name, label, cases in [('joint_cstr_completion', 'joint-cstr-completion', 'the six CSTR cases'),
                               ('joint_other_completion', 'joint-other-completion', 'Column, Small Batch, and the six Dynamic budgets')]:
        text += '\\begin{figure}[p]\n\\centering\n' + f'\\includegraphics[width=\\linewidth]{{figures/{name}.pdf}}\n'
        text += '\\caption{Joint completion-time comparison for ' + cases + '.\n'
        text += r'''Each DFO dot represents one seed; gray segments show Q25--Q75 and vertical ticks show medians across all ten runs.
Diamonds represent successful single algebraic runs; crosses indicate target misses in either group.
Right-hand labels give DFO hits out of ten or the algebraic yes/no outcome.
Asterisks retain the bound-inconsistency flags discussed in Section~\ref{sec:bound-audit}.
The horizontal axis is logarithmic and shows full-run completion, not first-target time.
'''
        if cases.startswith('Column'):
            text += 'The same single algebraic Dynamic run appears in each budget panel; these are not additional runs.\n'
        text += '}\n\\label{fig:' + label + '}\n\\end{figure}\n\\FloatBarrier\n\n'
    return text


def write_csv(path, rows):
    # Rows from different sources carry different fields; keep every field in first-seen order.
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def build(root, out):
    require(not out.exists() or not any(out.iterdir()), 'Output must be empty')
    rows, callbacks, inputs = load(root)
    summary = summaries(rows)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / 'joint_runs.csv', rows)
    write_csv(out / 'joint_summary.csv', summary)
    write_csv(out / 'dfo_nlp_callbacks.csv', callbacks)
    (out / 'supplement_fragment.tex').write_text(supplement_tex(summary))
    render(rows, out)
    counts = dict(dfo_runs=sum(r['family'] == 'DFO' for r in rows), algebraic_runs=sum(r['family'] == 'algebraic' for r in rows),
                  dfo_callbacks=len(callbacks), corresponding_dfo_nlp_evaluations=sum(r['corresponding_nlp_calls'] for r in callbacks),
                  new_optimizer_or_nlp_calls=0)
    (out / 'README.md').write_text('''# Joint process comparison

This exploratory supplement compares existing DFO and algebraic records without running any optimizer or solver.
The two figures retain all fourteen DFO conditions and all forty-five algebraic runs.
Each DFO method has ten seeds per condition; each algebraic method has one execution per problem.
The six Dynamic panels reuse the same five algebraic observations for context, not as new replicates.
No algebraic success probability, confidence interval, or inferential paired comparison is estimated.

DFO completion costs are reconstructed full-run estimates, with repeated evaluations charged along the recorded path.
Algebraic costs use the recorded total including preparation, retaining time limits and missing accepted solutions.
Neither is plotted as first-target time.
DFO target status uses the archived absolute reference agreement; algebraic status uses the archived feasible at-or-below-reference rule.
Bound-conflict flags are retained and do not certify optimality.
The plot shows Q25, Q50, and Q75 with inclusive linear interpolation at rank (n-1)p for DFO only.
Summary rows keep the original sample sizes; the algebraic rows have blank quartile fields.

The NLP table maps every DFO callback to its current archived configuration status.
Accepted and rejected NLP evaluations count as one; logical and preprocessing rejections count as zero.
The one CSTR30 solver-error configuration was never visited by the current cohort; any visited unclassified status raises an error.
Counts describe corresponding NLP work on the recorded path, not actual online calls during lookup-only search.
GDPopt counts confirmed SCIP NLP interface invocations, including unsuccessful returns, rather than internal IPOPT iterations.
One CSTR25 LOA attempt and one CSTR30 RIC attempt lack a confirmed solver start and are reported separately.
Direct Big-M and Hull internal NLP counts are unavailable, not zero.
NLP calls differ in formulation and computational effort; the count alone does not establish efficiency.

Input hashes are verified against the original analysis manifests and checksum inventories.
All 700 DFO run keys, 45 algebraic run keys, callback sequences, and current coverage counts are checked.
No historical archive, analysis, execution revision, target definition, or solver result is replaced.
The supplement text uses one sentence per source line.

Reproduce from the repository root into a new directory:

```sh
python -m review_comparison.joint_process --output /tmp/joint-process-review
```
''')
    import matplotlib
    manifest = dict(baseline_revision=BASE_REVISION, publication_data_revision='49d4bcbeb10fe49b74fe2333d27829046e93bf03',
                    counts=counts, input_sha256=inputs,
                    source_sha256={'review_comparison/joint_process.py': sha(Path(__file__).read_bytes())},
                    environment={'python': platform.python_version(), 'matplotlib': matplotlib.__version__},
                    reproduce='python -m review_comparison.joint_process --output /tmp/joint-process-review',
                    execution_provenance='Unchanged; retained in the input manifests.',
                    output_sha256={p.name: sha(p.read_bytes()) for p in sorted(out.iterdir()) if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.output), indent=2))


if __name__ == '__main__':
    main()
