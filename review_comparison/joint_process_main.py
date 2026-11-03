"""Six-condition main-text view of existing joint records; no solver calls."""

import argparse
import json
from pathlib import Path
import platform

from . import joint_process as base
from . import joint_process_ipopt as current
from . import dsda_no_revisit_runs as dsda
from . import mi_dfo_runs as mi

INPUT = 'results/joint_process_scip_ipopt_20261030'
REVISION = '341d9c6b6e790ba15318113083e43a4489c8b68e'
CONDITIONS = [('cstr_5', 8), ('cstr_30', 43), ('column', 13),
              ('small_batch', 10), ('dynamic', 12), ('dynamic', 30)]
# DFO methods in the order of the manuscript tables, then the conventional GDP methods.
DFO = ['dsda', 'nomad', 'rbfopt_msrsm_genetic', 'miso', 'bam', 'fmqa_sa', 'uniform_without_replacement']
CONVENTIONAL = ['gloa', 'loa', 'ric', 'bigm', 'hull']
base.require(sorted(DFO) == sorted(current.PRIMARY + mi.METHODS), 'DFO method list changed')
base.require(sorted(CONVENTIONAL) == sorted(base.ALG_METHODS), 'Conventional method list changed')
METHODS = DFO + CONVENTIONAL
LABELS = {**base.LABELS, **mi.LABELS}


def load(root):
    inputs = {}

    def read(path, expected=None):
        data = (root / path).read_bytes()
        inputs[path] = base.sha(data)
        base.require(expected is None or inputs[path] == expected, f'Input hash mismatch: {path}')
        return data

    manifest = json.loads(read(INPUT + '/manifest.json'))
    rows = [current.typed(r) for r in base.csv_rows(read(
        INPUT + '/joint_runs.csv', manifest['output_sha256']['joint_runs.csv']))]
    base.validate_runs([r for r in rows if r['family'] == 'DFO'],
                       [dict(instance_id=r['case'], method=r['method'])
                        for r in rows if r['family'] == 'algebraic'])
    jobs = json.loads(read(current.NEW + '/jobs.json',
                           manifest['input_sha256'][current.NEW + '/jobs.json']))
    direct = base.csv_rows(read(current.DIRECT + '/jobs.csv',
                                manifest['input_sha256'][current.DIRECT + '/jobs.csv']))
    terminations = {(r['instance_id'], r['method']): r['termination']
                    for r in jobs if r['scope'] == 'process'}
    terminations.update({(r['instance_id'], r['method']): r['termination']
                         for r in direct if r['method'] in ('bigm', 'hull')})
    for row in rows:
        row['termination'] = (terminations[row['case'], row['method']]
                              if row['family'] == 'algebraic' else '')
        row['time_limit'] = row['termination'] == 'maxTimeLimit'
    # D-SDA without re-evaluated configurations, and NOMAD and MISO, from the audited Dantzig returns.
    rows = [r for r in rows if not (r['family'] == 'DFO' and r['method'] == 'dsda')]
    rows += dsda.process_joint_rows(root, inputs) + mi.process_joint_rows(root, inputs)
    return rows, inputs


def select(rows):
    """Keep all seeds/outcomes; repeat Dynamic conventional marks, not runs."""
    selected = []
    for case, budget in CONDITIONS:
        for method in METHODS:
            group = [r for r in rows if r['case'] == case and r['method'] == method
                     and (r['family'] == 'algebraic' or r['budget'] == budget)]
            n = 10 if method in DFO else 1
            base.require(len(group) == n, f'Missing or duplicate plotted run: {case}/{budget}/{method}')
            if n == 10:
                base.require({r['seed'] for r in group} == set(range(10)), 'Incomplete seed set')
                group = sorted(group, key=lambda r: r['seed'])
            base.require(all(.1 <= r['completion_s'] <= 3000 for r in group), 'Run outside time axis')
            selected.extend(dict(panel_budget=budget, **r) for r in group)
    return selected


def render(selected, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.titlesize': 12, 'axes.spines.top': False,
                         'axes.spines.right': False, 'pdf.fonttype': 42}):
        fig, axs = plt.subplots(3, 2, figsize=(7.2, 9.0), sharex=True, sharey=True)
        for ax, (case, budget) in zip(axs.flat, CONDITIONS):
            for i, method in enumerate(METHODS):
                group = [r for r in selected if (r['case'], r['panel_budget'], r['method'])
                         == (case, budget, method)]
                dfo = method in DFO
                if dfo:
                    q25, median, q75 = base.quartiles([r['completion_s'] for r in group])
                    ax.plot([q25, q75], [i, i], color='#b0b0b0', lw=3.3, zorder=1)
                    ax.plot(median, i, marker='|', color='#222222', ms=9, zorder=4)
                for row in group:
                    y = i + (row['seed'] - 4.5) * .055 if dfo else i
                    hit = row['target_reached']
                    marker = ('o' if dfo else 'D') if hit else 'x'
                    color = '#0072B2' if hit else '#D55E00'
                    ax.scatter(row['completion_s'], y, marker=marker, c=color,
                               s=13 if dfo else 22, linewidths=.8, zorder=3)
                    if row['bound_conflict']:
                        ax.annotate('*', (row['completion_s'], y), xytext=(3, 2),
                                    textcoords='offset points', fontsize=10)
                hits = sum(r['target_reached'] for r in group)
                label = f'{hits}/10' if dfo else ('yes' if hits else 'no')
                if not dfo and group[0]['time_limit']:
                    label += ' TL'
                ax.text(1.015, i, label, transform=ax.get_yaxis_transform(), va='center', fontsize=10)
            ax.axhline(len(DFO) - .5, color='#999999', lw=.7)
            ax.set(xscale='log', xlim=(.1, 3000), ylim=(len(METHODS) - .3, -.7), yticks=range(len(METHODS)),
                   yticklabels=[LABELS[m] for m in METHODS],
                   title=f'{base.pname(case)}, B={budget}')
            ax.tick_params(axis='y', length=0, labelleft=True, labelsize=10.5)
            ax.tick_params(axis='x', labelsize=10)
            ax.grid(axis='x', which='major', alpha=.18)
        for ax in axs[-1]:
            ax.set_xlabel('Full-run completion time (s)', fontsize=11)
        handles = [Line2D([], [], marker='o', color='#0072B2', ls='', label='DFO target reached'),
                   Line2D([], [], marker='D', color='#0072B2', ls='', label='Conventional GDP target reached'),
                   Line2D([], [], marker='x', color='#D55E00', ls='', label='Target not reached'),
                   Line2D([], [], marker='|', color='#b0b0b0', markeredgecolor='#222222',
                          ms=9, lw=3, label='DFO median and Q25-Q75')]
        fig.legend(handles=handles, loc='lower center', ncol=2, frameon=False, fontsize=10,
                   bbox_to_anchor=(.5, .001))
        fig.subplots_adjust(left=.13, right=.885, top=.962, bottom=.105, hspace=.30, wspace=.86)
        fig.savefig(out / 'process_joint_completion.pdf', metadata={'CreationDate': None, 'ModDate': None})
        fig.savefig(out / 'process_joint_completion.png', dpi=180)
        plt.close(fig)


def build(root, out):
    base.require(not out.exists() or not any(out.iterdir()), 'Output must be empty')
    rows, inputs = load(root)
    selected = select(rows)
    out.mkdir(parents=True, exist_ok=True)
    base.write_csv(out / 'selected_runs.csv', selected)
    render(selected, out)
    (out / 'README.md').write_text('''# Main-text joint process completion comparison

This presentation-only follow-up uses the completed joint SCIP-master/IPOPT-subproblem analysis.
No optimizer, NLP solver, or benchmark is rerun.
The six panels show CSTR5 B=8, CSTR30 B=43, Column B=13, Small Batch B=10, and Dynamic B=12 and B=30.
The CSTR endpoints and two Dynamic budgets connect the target-rate and cost examples discussed in the main text.
The full fourteen-condition figures remain in `results/joint_process_scip_ipopt_20261030`.

All ten DFO seeds per method and condition remain visible, including misses and failures.
Gray intervals and median ticks summarize all ten completion estimates using inclusive, linearly interpolated quartiles.
Conventional GDP methods each contribute one observation, not an estimated success probability.
The two Dynamic panels repeat the same five conventional observations, so 450 plotted marks represent 445 distinct saved runs.
These are 420 DFO runs and 25 distinct conventional runs.
NOMAD and MISO come from the audited Dantzig return of PR #56 (`results/pr56_dantzig_return_20261031`), and D-SDA from the rerun without re-evaluated configurations (`results/dsda_no_revisit_20261031`).
The right-hand labels show DFO hits out of ten or the single conventional yes/no outcome.
Stars retain the existing bound-conflict flags.
TL labels retain reported `maxTimeLimit` outcomes, including those whose measured time is below the configured 1800-second limit.
The axis retains actual measured times; no value is silently replaced by 1800.

DFO full-run completion costs are reconstructed from search overhead and separately measured configuration costs.
Conventional completion times are measured and include model preparation.
These are neither first-hit times nor equal-work NLP counts.
Existing target rules, completion times, statuses, source links, and execution revisions are unchanged.
The detailed conventional objective/time table and the former DFO-only completion profiles are retained in the Overleaf supplement.
This directory supplies the new figure rather than replacing historical manuscript bundles.

Reproduce from the repository root into a fresh directory:

```sh
python -m review_comparison.joint_process_main --output /tmp/joint-process-main
```
''')
    import matplotlib
    manifest = dict(baseline_revision=REVISION, input_sha256=inputs,
                    source_sha256={p: base.sha((root / p).read_bytes()) for p in (
                        'review_comparison/joint_process_main.py', 'review_comparison/joint_process.py',
                        'review_comparison/joint_process_ipopt.py', 'review_comparison/mi_dfo_runs.py',
                        'review_comparison/dsda_no_revisit_runs.py')},
                    conditions=CONDITIONS, dfo_runs=420, conventional_distinct_runs=25,
                    conventional_plotted_marks=30, new_solver_calls=0,
                    execution_provenance='Unchanged; see original manifests and source references.',
                    environment=dict(python=platform.python_version(), matplotlib=matplotlib.__version__),
                    reproduce='python -m review_comparison.joint_process_main --output /tmp/joint-process-main',
                    output_sha256={p.name: base.sha(p.read_bytes()) for p in sorted(out.iterdir())})
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=base.ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.root, args.output)
