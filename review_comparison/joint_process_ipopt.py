"""Refresh the joint process figures from completed SCIP--IPOPT records only."""

import argparse
from collections import Counter
import copy
import json
import math
from pathlib import Path
import platform
import zipfile

from . import joint_process as old

ROOT = old.ROOT
PREVIOUS = 'results/joint_process_comparison_20261029'
NEW = 'results/gdpopt_scip_ipopt_analysis_20261030'
DIRECT = 'results/process_scip_four_analysis_20261026'
REVISION = '329c6f93f4940436425582ae60323c0c9f95b581'
PRIMARY = ['bam', 'dsda', 'fmqa_sa', 'rbfopt_msrsm_genetic', 'uniform_without_replacement']
GDPOPT = ('gloa', 'loa', 'ric')


def typed(row):
    row = dict(row)
    for name in ('budget', 'seed', 'callbacks', 'nlp_calls', 'nlp_first_target', 'nlp_unconfirmed_attempts'):
        if row[name] != '':
            row[name] = int(row[name])
    row['completion_s'] = float(row['completion_s'])
    for name in ('target_reached', 'bound_conflict'):
        row[name] = old.truth(row[name])
    return row


def validate_new(jobs):
    keys = [(r['instance_id'], r['method']) for r in jobs]
    expected = {(c, m) for c in {c for c, _ in old.CONDITIONS} for m in GDPOPT}
    old.require(len(keys) == len(set(keys)) and set(keys) == expected,
                'Missing, duplicate, or unexpected SCIP--IPOPT process job')


def call_counts(calls, expected):
    ipopt = [c for c in calls if c['solver'].lower() == 'ipopt']
    old.require(all(c['mtype'].lower() == 'nlp' for c in ipopt), 'Unexpected IPOPT problem type')
    confirmed = sum(c.get('observed', {}).get('solver_starts', []).count('IPOPT') for c in ipopt)
    unconfirmed = sum('IPOPT' not in c.get('observed', {}).get('solver_starts', []) for c in ipopt)
    old.require(confirmed == expected, 'IPOPT execution count disagrees with archived analysis')
    return confirmed, unconfirmed


def bound_flags(records):
    """Use the best checked saved feasible point among the current 45 runs."""
    result = []
    for r in records:
        peers = [v for v in records if v['case'] == r['case'] and v['feasible']]
        old.require(bool(peers), 'No checked feasible witness')
        witness = min(peers, key=lambda v: v['objective'])
        tolerance = 1e-5 * max(1.0, abs(witness['objective']))
        delta = None if r['lower_bound'] is None else r['lower_bound'] - witness['objective']
        result.append(dict(case=r['case'], method=r['method'], lower_bound=r['lower_bound'],
                           witness_method=witness['method'], witness_objective=witness['objective'],
                           tolerance=tolerance, rho=None if delta is None else delta / tolerance,
                           bound_conflict=delta is not None and delta > tolerance))
    return result


def load(root):
    inputs = {}

    def read(path, expected=None):
        data = (root / path).read_bytes()
        inputs[path] = old.sha(data)
        old.require(expected is None or inputs[path] == expected, f'Input hash mismatch: {path}')
        return data

    manifest = json.loads(read(PREVIOUS + '/manifest.json'))
    data = read(PREVIOUS + '/joint_runs.csv', manifest['output_sha256']['joint_runs.csv'])
    rows = [typed(r) for r in old.csv_rows(data)]
    original = copy.deepcopy(rows)
    old.validate_runs([r for r in rows if r['family'] == 'DFO'],
                      [dict(instance_id=r['case'], method=r['method']) for r in rows if r['family'] == 'algebraic'])
    checksums = {}
    for line in read(NEW + '/SHA256SUMS').decode().splitlines():
        digest, name = line.split(None, 1)
        checksums[name.strip()] = digest
    jobs = [r for r in json.loads(read(NEW + '/jobs.json', checksums['jobs.json'])) if r['scope'] == 'process']
    validate_new(jobs)
    checks = {r['job_id']: r for r in json.loads(read(NEW + '/solution_checks.json', checksums['solution_checks.json']))}
    direct_sums = json.loads(read(DIRECT + '/artifact_checksums.json'))
    direct = [r for r in old.csv_rows(read(DIRECT + '/jobs.csv', direct_sums[DIRECT + '/jobs.csv']))
              if r['method'] in ('bigm', 'hull')]
    records = [dict(case=r['instance_id'], method=r['method'],
                    objective=float(r['objective']) if r['objective'] else None,
                    feasible=old.truth(r['original_gdp_feasible']),
                    lower_bound=float(r['reported_lower_bound']) if r['reported_lower_bound'] else None)
               for r in direct]
    records += [dict(case=r['instance_id'], method=r['method'], objective=r['objective'],
                     feasible=checks[r['job_id']]['original_gdp_feasible'], lower_bound=r['reported_lower_bound'])
                for r in jobs]
    flags = bound_flags(records)
    flag_map = {(r['case'], r['method']): r['bound_conflict'] for r in flags}
    packages = {}
    try:
        for job in sorted(jobs, key=lambda r: r['job_id']):
            package = job['package_id']
            if package not in packages:
                name = 'evidence/' + package + '.zip'
                read(NEW + '/' + name, checksums[name])
                packages[package] = zipfile.ZipFile(root / NEW / name)
            z = packages[package]
            prefix = 'run/jobs/' + job['job_id'] + '/'
            raw = z.read(prefix + 'result.json')
            old.require(old.sha(raw) == job['result_sha256'], 'Result hash mismatch')
            raw = z.read(prefix + 'solution.json')
            old.require(old.sha(raw) == job['solution_sha256'], 'Solution hash mismatch')
            calls = [json.loads(line) for line in z.read(prefix + 'solver_calls.jsonl').splitlines()]
            nlp, uncertain = call_counts(calls, job['actual_ipopt_calls'])
            old.require(job['original_gdp_feasible'] and checks[job['job_id']]['original_gdp_feasible'],
                        'Process saved-vector validation failed')
            rr = [r for r in rows if r['family'] == 'algebraic' and
                  (r['case'], r['method']) == (job['instance_id'], job['method'])]
            old.require(len(rr) == 1, 'Replacement must have one historical slot')
            rr[0].update(completion_s=job['completion_with_preparation_seconds'], objective=job['objective'],
                         target_reached=job['target_attained'], category=job['termination'], nlp_calls=nlp,
                         nlp_basis='confirmed_IPOPT_NLP_interface_calls', nlp_unconfirmed_attempts=uncertain,
                         source=NEW + '/evidence/' + package + '.zip#' + prefix + 'result.json')
    finally:
        for z in packages.values():
            z.close()
    for r in rows:
        if r['family'] == 'algebraic':
            r['bound_conflict'] = flag_map[r['case'], r['method']]
        old.require(math.isfinite(r['completion_s']) and r['completion_s'] > 0, 'Invalid completion time')
    old.require([r for r in rows if r['family'] == 'DFO'] == [r for r in original if r['family'] == 'DFO'],
                'DFO rows changed')
    for r, before in zip(rows, original):
        if r['method'] in ('bigm', 'hull'):
            old.require({k: v for k, v in r.items() if k != 'bound_conflict'} ==
                        {k: v for k, v in before.items() if k != 'bound_conflict'}, 'Direct SCIP data changed')
    return rows, flags, inputs


def render(rows, out):
    """Keep the existing alphabetical DFO layout and individual observations."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    methods = PRIMARY + old.ALG_METHODS
    groups = [('joint_cstr_completion', old.CONDITIONS[:6]), ('joint_other_completion', old.CONDITIONS[6:])]
    with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 8, 'axes.titlesize': 9,
                         'axes.spines.top': False, 'axes.spines.right': False, 'pdf.fonttype': 42}):
        for name, conditions in groups:
            nr = math.ceil(len(conditions) / 2)
            height = 1.93 if nr == 4 else 2.05
            fig, axs = plt.subplots(nr, 2, figsize=(7.2, height * nr + .55), sharex=True, sharey=True)
            for ax, (case, budget) in zip(axs.flat, conditions):
                for i, method in enumerate(methods):
                    rr = [r for r in rows if r['case'] == case and r['method'] == method and
                          (r['family'] == 'algebraic' or r['budget'] == budget)]
                    old.require(len(rr) == (10 if method in PRIMARY else 1), 'Wrong plotted sample size')
                    old.require(all(.1 <= r['completion_s'] <= 3000 for r in rr), 'Run outside time range')
                    if len(rr) == 10:
                        q = old.quartiles([r['completion_s'] for r in rr])
                        ax.plot([q[0], q[2]], [i, i], color='#bababa', lw=2.8, zorder=1)
                        ax.plot(q[1], i, marker='|', color='#333333', ms=7, zorder=2)
                    for r in rr:
                        y = i + (r['seed'] - 4.5) * .045 if len(rr) == 10 else i
                        marker = ('o' if len(rr) == 10 else 'D') if r['target_reached'] else 'x'
                        color = '#00786e' if r['target_reached'] else '#a54124'
                        ax.scatter(r['completion_s'], y, marker=marker, c=color, s=12 if len(rr) == 10 else 20,
                                   linewidths=.7, zorder=3)
                        if r['bound_conflict']:
                            ax.annotate('*', (r['completion_s'], y), xytext=(3, 2),
                                        textcoords='offset points', fontsize=9)
                    hits = sum(r['target_reached'] for r in rr)
                    ax.text(1.015, i, f'{hits}/10' if len(rr) == 10 else ('yes' if hits else 'no'),
                            transform=ax.get_yaxis_transform(), va='center', fontsize=7)
                ax.axhline(4.5, color='#999999', lw=.6)
                ax.set(xscale='log', xlim=(.1, 3000), ylim=(9.7, -.7), yticks=range(10),
                       yticklabels=[old.LABELS[m] for m in methods], title=f'{old.pname(case)}, B={budget}')
                ax.tick_params(axis='y', length=0, labelleft=True, labelsize=7.5)
                ax.tick_params(axis='x', labelsize=7)
                ax.grid(axis='x', which='major', alpha=.18)
            for ax in axs[-1]:
                ax.set_xlabel('Full-run completion time (s)', fontsize=8)
            legend = [Line2D([], [], marker='o', color='#00786e', ls='', label='DFO target reached'),
                      Line2D([], [], marker='D', color='#00786e', ls='', label='Conventional GDP target reached'),
                      Line2D([], [], marker='x', color='#a54124', ls='', label='Target not reached')]
            fig.legend(handles=legend, loc='lower center', ncol=3, frameon=False, fontsize=7.5,
                       bbox_to_anchor=(.5, .002))
            fig.subplots_adjust(left=.105, right=.94, top=.955, bottom=.095 if nr == 3 else .075,
                                hspace=.42, wspace=.48)
            fig.savefig(out / (name + '.pdf'), metadata={'CreationDate': None, 'ModDate': None})
            fig.savefig(out / (name + '.png'), dpi=160)
            plt.close(fig)


def supplement(summary):
    text = old.supplement_tex(summary)
    text = text.replace('algebraic methods', 'conventional GDP methods')
    text = text.replace('algebraic results', 'conventional GDP results')
    text = text.replace('algebraic times', 'conventional GDP times')
    text = text.replace('algebraic method', 'conventional GDP method')
    text = text.replace('an algebraic success probability', 'a success probability for conventional GDP methods')
    text = text.replace('algebraic runs', 'conventional GDP runs')
    text = text.replace('algebraic yes/no outcome', 'conventional GDP yes/no outcome')
    text = text.replace('algebraic Dynamic run', 'conventional GDP Dynamic run')
    text = text.replace('NLP workload in the recorded process comparisons.',
                        r'NLP workload in the process comparisons with \texttt{SCIP}--\texttt{IPOPT} GDPopt.')
    text = text.replace('confirmed SCIP NLP interface calls', 'confirmed IPOPT NLP interface calls')
    old_note = (r'\(^{\dagger}\)CSTR25 LOA and CSTR30 RIC each have one additional NLP interface attempt '
                'without a confirmed solver start; these attempts are excluded.')
    unknown = [r for r in summary if r['family'] == 'algebraic' and r['nlp_unconfirmed_attempts']]
    if unknown:
        details = '; '.join(f"{old.pname(r['case'])} {old.LABELS[r['method']]}: {r['nlp_unconfirmed_attempts']}"
                            for r in unknown)
        text = text.replace(old_note, r'\(^{\dagger}\)Excluded NLP attempts without a confirmed solver start: ' + details + '.')
    else:
        text = text.replace(old_note + '\n', '')
    anchor = 'DFO times are reconstructed'
    text = text.replace(anchor, r'GDPopt uses \texttt{SCIP} for master problems and \texttt{IPOPT} for NLP subproblems; direct Big-\(M\) and Hull retain their \texttt{SCIP} results.' + '\n' + anchor)
    return text.rstrip() + '\n'


def build(root, out):
    old.require(not out.exists() or not any(out.iterdir()), 'Output must be empty')
    rows, flags, inputs = load(root)
    summary = old.summaries(rows)
    out.mkdir(parents=True, exist_ok=True)
    old.write_csv(out / 'joint_runs.csv', rows)
    old.write_csv(out / 'joint_summary.csv', summary)
    old.write_csv(out / 'bound_flags.csv', flags)
    (out / 'supplement_fragment.tex').write_text(supplement(summary))
    render(rows, out)
    counts = dict(dfo_runs=sum(r['family'] == 'DFO' for r in rows),
                  algebraic_runs=sum(r['family'] == 'algebraic' for r in rows),
                  new_gdpopt_runs=sum(r['method'] in GDPOPT for r in rows),
                  actual_ipopt_calls=sum(r['nlp_calls'] for r in rows if r['method'] in GDPOPT),
                  unconfirmed_ipopt_attempts=sum(r['nlp_unconfirmed_attempts'] for r in rows if r['method'] in GDPOPT),
                  bound_flags=sum(r['bound_conflict'] for r in flags), new_solver_calls=0)
    hits = Counter(r['method'] for r in rows if r['family'] == 'algebraic' and r['target_reached'])
    (out / 'README.md').write_text('''# Updated joint process comparison

This follow-up replaces the 27 GDPopt observations with the completed SCIP-master/IPOPT-subproblem campaign.
All 700 DFO observations and all 18 direct Big-M/Hull SCIP observations retain their previous values, time definitions and target rules.
The source revision is `''' + REVISION + '''`.
The earlier joint comparison remains unchanged in `results/joint_process_comparison_20261029`.
No optimizer, NLP solver or benchmark is rerun by this analysis.

DFO points show ten seeds, with inclusive Q25--Q75 intervals and median ticks.
Each conventional GDP method contributes one measured observation per problem, without an estimated success probability.
The six Dynamic panels reuse the same five conventional observations, not additional replications.
Times are full-run completion costs: reconstructed evaluation plus search cost for DFO, and measured completion plus preparation for conventional methods.
Neither axis represents time to first target.
Target misses, time limits and runs without accepted solutions remain visible.
The existing absolute-reference rule for DFO and feasible-at-or-below-reference rule for conventional methods are preserved.
The DFO display order is BAM, D-SDA, FMQA-SA, RBFOpt and Uniform.

The workload table keeps the corresponding fixed-configuration DFO NLP counts and uses confirmed IPOPT execution banners in the new GDPopt journals.
Preprocessing rejections do not count as NLP solves; unsuccessful solver returns do count when an execution is confirmed.
DFO median counts can be fractional because each condition has ten seeds.
These counts do not equate formulation, initialization, internal iterations or computational effort.
Direct Big-M/Hull internal NLP counts remain unavailable, not zero.

Bound flags are recomputed against the best independently checked saved feasible point in the current 45-run cohort.
Thus a retained direct result can acquire a flag when the new campaign supplies a better checked witness.
Flags match the updated main process table and S7; they do not certify global optimality.
Existing logs, manifests, execution revisions, historical reports and original figure generators remain unchanged.

| Method | Target hits out of nine |
| --- | ---: |
''' + ''.join(f'| {old.LABELS[m]} | {hits[m]} |\n' for m in old.ALG_METHODS) + '''
Reproduce from the repository root into a fresh directory:

```sh
python -m review_comparison.joint_process_ipopt --output /tmp/joint-process-ipopt
python -m pytest tests/test_joint_process_ipopt.py tests/test_joint_process.py -q
```
''')
    import matplotlib
    manifest = dict(baseline_revision=REVISION, counts=counts, input_sha256=inputs,
                    source_sha256={str(p.relative_to(root)): old.sha(p.read_bytes())
                                   for p in (Path(__file__), Path(old.__file__))},
                    environment=dict(python=platform.python_version(), matplotlib=matplotlib.__version__),
                    reproduce='python -m review_comparison.joint_process_ipopt --output /tmp/joint-process-ipopt',
                    execution_provenance='Unchanged; retained in the original manifests and evidence archives.',
                    output_sha256={p.name: old.sha(p.read_bytes()) for p in sorted(out.iterdir()) if p.is_file()})
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
