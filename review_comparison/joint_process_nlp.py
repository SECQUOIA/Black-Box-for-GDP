"""NLP subproblems solved by DFO runs, GDPopt, and full enumeration; no solver calls."""

import argparse
import json
from pathlib import Path
import platform

from . import joint_process as base
from . import joint_process_main as main_figure

COVERAGE = 'results/dsda_publication_20261028/tables/configuration_coverage.csv'
CONDITIONS = [(f'cstr_{n}', b) for n, b in zip((5, 10, 15, 20, 25, 30), (8, 15, 22, 29, 36, 43))]
CONDITIONS += [('column', 13), ('small_batch', 10), ('dynamic', 12)]
GDPOPT = ['ric', 'loa', 'gloa']
DFO = main_figure.DFO
METHODS = DFO + GDPOPT
LABELS = main_figure.LABELS
HIT, MISS = '#0072B2', '#D55E00'


def enumeration(root):
    """NLP solves needed to evaluate every configuration of each DFO box."""
    data = (root / COVERAGE).read_bytes()
    counts = {}
    for row in base.csv_rows(data):
        # A solver error is an attempted NLP; logical and FBBT rejections are not.
        work = 1 if row['status'] == 'solver_error' else base.nlp_work(row['status'])
        counts[row['case']] = counts.get(row['case'], 0) + work
    return counts, base.sha(data)


def select(rows):
    selected = []
    for case, budget in CONDITIONS:
        for method in METHODS:
            group = [r for r in rows if r['case'] == case and r['method'] == method
                     and (r['family'] == 'algebraic' or r['budget'] == budget)]
            n = 10 if method in DFO else 1
            base.require(len(group) == n, f'Missing or duplicate run: {case}/{budget}/{method}')
            base.require(all(int(r['nlp_calls']) >= 1 for r in group), 'Run without an NLP solve')
            selected.extend(dict(panel_budget=budget, **r) for r in sorted(group, key=lambda r: r['seed'] or 0))
    return selected


def render(selected, counts, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.titlesize': 10,
                         'axes.spines.top': False, 'axes.spines.right': False, 'pdf.fonttype': 42}):
        fig, axs = plt.subplots(3, 3, figsize=(7.4, 9.2), sharex=True, sharey=True)
        for ax, (case, budget) in zip(axs.flat, CONDITIONS):
            ax.axvline(counts[case], color='#666666', ls='--', lw=1, zorder=0)
            ax.axvline(budget, color='#bbbbbb', ls=':', lw=1, zorder=0)
            for i, method in enumerate(METHODS):
                group = [r for r in selected if (r['case'], r['panel_budget'], r['method'])
                         == (case, budget, method)]
                dfo = method in DFO
                xs = [int(r['nlp_calls']) for r in group]
                if dfo:
                    q25, median, q75 = base.quartiles(xs)
                    ax.plot([q25, q75], [i, i], color='#b0b0b0', lw=3.3, zorder=1)
                    ax.plot(median, i, marker='|', color='#222222', ms=9, zorder=4)
                for row, x in zip(group, xs):
                    y = i + (row['seed'] - 4.5) * .055 if dfo else i
                    hit = row['target_reached']
                    ax.scatter(x, y, marker=('o' if dfo else 'D') if hit else 'x',
                               c=HIT if hit else MISS, s=13 if dfo else 22, linewidths=.8, zorder=3)
                hits = sum(r['target_reached'] for r in group)
                ax.text(1.02, i, f'{hits}/10' if dfo else ('yes' if hits else 'no'),
                        transform=ax.get_yaxis_transform(), va='center', fontsize=7.4)
            ax.axhline(len(DFO) - .5, color='#999999', lw=.7)
            ax.set(xscale='log', xlim=(.8, 1000), ylim=(len(METHODS) - .3, -.7), yticks=range(len(METHODS)),
                   yticklabels=[LABELS[m] for m in METHODS], title=f'{base.pname(case)}, B={budget}')
            ax.tick_params(axis='y', length=0, labelleft=True, labelsize=7.8)
            ax.tick_params(axis='x', labelsize=8)
            ax.grid(axis='x', which='major', alpha=.18)
        for ax in axs[-1]:
            ax.set_xlabel('NLP subproblems solved', fontsize=9)
        handles = [Line2D([], [], marker='o', color=HIT, ls='', label='DFO target reached'),
                   Line2D([], [], marker='D', color=HIT, ls='', label='GDPopt target reached'),
                   Line2D([], [], marker='x', color=MISS, ls='', label='Target not reached'),
                   Line2D([], [], marker='|', color='#b0b0b0', markeredgecolor='#222222', ms=9, lw=3,
                          label='DFO median and Q25-Q75'),
                   Line2D([], [], color='#666666', ls='--', label='Full enumeration'),
                   Line2D([], [], color='#bbbbbb', ls=':', label='Evaluation budget B')]
        fig.legend(handles=handles, loc='lower center', ncol=3, frameon=False, fontsize=8,
                   bbox_to_anchor=(.5, .001))
        fig.subplots_adjust(left=.105, right=.93, top=.965, bottom=.10, hspace=.30, wspace=.78)
        fig.savefig(out / 'process_nlp_solves.pdf', metadata={'CreationDate': None, 'ModDate': None})
        fig.savefig(out / 'process_nlp_solves.png', dpi=180)
        plt.close(fig)


def build(root, out):
    base.require(not out.exists() or not any(out.iterdir()), 'Output must be empty')
    rows, inputs = main_figure.load(root)
    counts, coverage_sha = enumeration(root)
    inputs[COVERAGE] = coverage_sha
    selected = select(rows)
    out.mkdir(parents=True, exist_ok=True)
    base.write_csv(out / 'selected_runs.csv', selected)
    (out / 'enumeration_nlp_solves.json').write_text(json.dumps(counts, indent=2, sort_keys=True) + '\n')
    render(selected, counts, out)
    (out / 'README.md').write_text('''# NLP subproblems solved: DFO, GDPopt, and enumeration

Presentation of existing records only; no optimizer or NLP solver is run.
Each panel shows one process model at the budget used in the main text (Dynamic at B=12).
DFO rows show all ten seeds; GDPopt rows show the single SCIP-master/IPOPT-subproblem run.
NOMAD and MISO come from the audited Dantzig return of PR #56 (`results/pr56_dantzig_return_20261031`), and D-SDA from the rerun without re-evaluated configurations (`results/dsda_no_revisit_20261031`).
DFO counts are stored fixed-configuration evaluations that reach the NLP stage; GDPopt counts are confirmed IPOPT calls.
Logical and FBBT preprocessing rejections are not NLP solves.
The dashed line is the number of NLP solves needed to evaluate every configuration in the DFO box, and the dotted line is the evaluation budget.
Direct Big-M and Hull runs are omitted because their internal NLP counts are unavailable.

```sh
python -m review_comparison.joint_process_nlp --output /tmp/joint-process-nlp
```
''')
    import matplotlib
    manifest = dict(input_sha256=inputs,
                    source_sha256={p: base.sha((root / p).read_bytes()) for p in (
                        'review_comparison/joint_process_nlp.py', 'review_comparison/joint_process_main.py',
                        'review_comparison/joint_process.py', 'review_comparison/joint_process_ipopt.py',
                        'review_comparison/mi_dfo_runs.py', 'review_comparison/dsda_no_revisit_runs.py')},
                    conditions=CONDITIONS, enumeration_nlp_solves=counts, new_solver_calls=0,
                    environment=dict(python=platform.python_version(), matplotlib=matplotlib.__version__),
                    reproduce='python -m review_comparison.joint_process_nlp --output /tmp/joint-process-nlp',
                    output_sha256={p.name: base.sha(p.read_bytes()) for p in sorted(out.iterdir())})
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=base.ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.root, args.output)
