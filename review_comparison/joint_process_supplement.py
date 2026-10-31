"""Non-overlapping supplement panels complementing the six main-text conditions."""

import argparse
import json
from pathlib import Path
import platform

from . import joint_process as base
from . import joint_process_ipopt as current
from . import joint_process_main as main

CONDITIONS = [c for c in base.CONDITIONS if c not in main.CONDITIONS]
METHODS = main.METHODS
REVISION = 'ba8db83e5df39c727c4a33066d582572668721dd'


def select(rows):
    selected = []
    for case, budget in CONDITIONS:
        for method in METHODS:
            group = [r for r in rows if r['case'] == case and r['method'] == method
                     and (r['family'] == 'algebraic' or r['budget'] == budget)]
            n = 10 if method in current.PRIMARY else 1
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

    with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 9,
                         'axes.titlesize': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'pdf.fonttype': 42}):
        fig, axs = plt.subplots(4, 2, figsize=(7.2, 8.6), sharex=True, sharey=True)
        for ax, (case, budget) in zip(axs.flat, CONDITIONS):
            for i, method in enumerate(METHODS):
                group = [r for r in selected if (r['case'], r['panel_budget'], r['method'])
                         == (case, budget, method)]
                dfo = method in current.PRIMARY
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
                ax.text(1.015, i, label, transform=ax.get_yaxis_transform(), va='center', fontsize=7.8)
            ax.axhline(4.5, color='#999999', lw=.7)
            ax.set(xscale='log', xlim=(.1, 3000), ylim=(9.7, -.7), yticks=range(10),
                   yticklabels=[base.LABELS[m] for m in METHODS],
                   title=f'{base.pname(case)}, B={budget}')
            ax.tick_params(axis='y', length=0, labelleft=True, labelsize=8.2)
            ax.tick_params(axis='x', labelsize=8)
            ax.grid(axis='x', which='major', alpha=.18)
        for ax in axs[-1]:
            ax.set_xlabel('Full-run completion time (s)', fontsize=9)
        handles = [Line2D([], [], marker='o', color='#0072B2', ls='', label='DFO target reached'),
                   Line2D([], [], marker='D', color='#0072B2', ls='', label='Conventional GDP target reached'),
                   Line2D([], [], marker='x', color='#D55E00', ls='', label='Target not reached'),
                   Line2D([], [], marker='|', color='#b0b0b0', markeredgecolor='#222222',
                          ms=9, lw=3, label='DFO median and Q25-Q75')]
        fig.legend(handles=handles, loc='lower center', ncol=2, frameon=False, fontsize=8,
                   bbox_to_anchor=(.5, .001))
        fig.subplots_adjust(left=.108, right=.90, top=.958, bottom=.10, hspace=.28, wspace=.70)
        fig.savefig(out / 'joint_remaining_completion.pdf', metadata={'CreationDate': None, 'ModDate': None})
        fig.savefig(out / 'joint_remaining_completion.png', dpi=180)
        plt.close(fig)


def build(root, out):
    base.require(not out.exists() or not any(out.iterdir()), 'Output must be empty')
    rows, inputs = main.load(root)
    selected = select(rows)
    out.mkdir(parents=True, exist_ok=True)
    base.write_csv(out / 'selected_runs.csv', selected)
    render(selected, out)
    (out / 'README.md').write_text('''# Supplement panels without main-text duplication

This presentation-only reduction retains the eight process conditions absent from main Figure 3.
The remaining panels are CSTR10 B=15, CSTR15 B=22, CSTR20 B=29, CSTR25 B=36, and Dynamic B=15, B=20, B=37, and B=50.
Together with `results/joint_process_main_20261030`, these panels cover all fourteen conditions exactly once.
No optimizer, NLP solver, or benchmark is rerun.

Every DFO condition retains all ten seeds, including misses, with inclusive quartiles and medians computed over all ten runs.
All underlying values, target rules, statuses, and source references are unchanged.
The 440 plotted marks comprise 400 distinct DFO runs and 25 distinct conventional GDP runs.
The same five conventional Dynamic observations are repeated for context across four budgets, not counted as additional executions.
The figure retains individual outcomes, bound flags, measured-time TL labels, and the different recorded time bases.
The previous full fourteen-condition figures and old DFO-only profile remain archived in their original result directories, but are no longer repeated in the Overleaf supplement.

The Overleaf supplement keeps the detailed conventional objective/time table and the NLP-workload table.
The old DFO-only time profile, its main-text reference, and the unused cumulative completion-time definition are removed.
The configuration-evaluation profile and reconstructed completion-cost equation remain in the main paper.
David comments, tracked changes, and underlying experiment records are preserved.

Reproduce from the repository root into a fresh directory:

```sh
python -m review_comparison.joint_process_supplement --output /tmp/joint-process-supplement
```
''')
    import matplotlib
    manifest = dict(baseline_revision=REVISION, input_sha256=inputs,
                    source_sha256={p: base.sha((root / p).read_bytes()) for p in (
                        'review_comparison/joint_process_supplement.py',
                        'review_comparison/joint_process_main.py',
                        'review_comparison/joint_process.py',
                        'review_comparison/joint_process_ipopt.py')},
                    conditions=CONDITIONS, excluded_main_conditions=main.CONDITIONS,
                    dfo_runs=sum(r['family'] == 'DFO' for r in selected),
                    conventional_distinct_runs=len({r['source'] for r in selected if r['family'] == 'algebraic'}),
                    conventional_plotted_marks=sum(r['family'] == 'algebraic' for r in selected),
                    new_solver_calls=0,
                    execution_provenance='Unchanged; see original manifests and source references.',
                    environment=dict(python=platform.python_version(), matplotlib=matplotlib.__version__),
                    reproduce='python -m review_comparison.joint_process_supplement --output /tmp/joint-process-supplement',
                    output_sha256={p.name: base.sha(p.read_bytes()) for p in sorted(out.iterdir())})
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=base.ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.root, args.output)
