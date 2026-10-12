"""Plot completion-time profiles and individual runs; retain aggregate TTS99 data.

Run with: python -m scripts.plot_dantzig_performance
No optimizer or NLP solver is executed.
"""

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import statistics

from benchmark_analysis import runs_to_target_probability
from scripts.plot_dantzig_cost_breakdown import (
    LABELS, METHODS, OUTPUT, ROOT, load_runs, read_csv, sha, write_csv, input_hashes,
)

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullLocator


PANELS = (("column", "", 16, "Column"), ("cstr", "30", 43, "CSTR 30"),
          ("small_batch", "", 10, "Small Batch (27 points)"),
          *(("dynamic", "", budget, "Dynamic") for budget in (12, 15, 20, 30, 37, 50)))
COLORS = ("#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd")
BASELINES = ("ric", "gloa", "loa", "bigm", "hull")
FULL_PANELS = (*(("cstr", str(size), budget, f"CSTR {size}") for size, budget in
                ((5, 8), (10, 15), (15, 22), (20, 29), (25, 36), (30, 43))),
               PANELS[0], PANELS[2], PANELS[-1])
GDP_SOURCE = ROOT / "results/gdp_comparison_current/analysis"


def performance_tables(runs):
    """Keep failed paired runs in profiles and all run times in TTS99 medians."""
    pairs, groups = defaultdict(list), defaultdict(list)
    for row in runs:
        if not math.isfinite(row["estimated_total_s"]) or row["estimated_total_s"] <= 0:
            raise ValueError("Invalid completion cost")
        key = row["case"], row["cstr_size"], row["budget"]
        pairs[(*key, row["seed"])].append(row)
        groups[(*key, row["method"])].append(row)
    profiles = []
    for group in pairs.values():
        if Counter(r["method"] for r in group) != Counter(METHODS):
            raise ValueError("Profile requires one run per method and paired seed")
        for row in group:
            profiles.append({**row, "profile_completion_s": row["estimated_total_s"]
                             if row["lookup_target_hit"] else math.inf})
    summary = []
    for (case, size, budget, method), group in groups.items():
        hits = sum(r["lookup_target_hit"] for r in group)
        rate = hits / len(group)
        repeats = runs_to_target_probability(rate)
        median = statistics.median(r["estimated_total_s"] for r in group)
        summary.append({"case": case, "cstr_size": size, "budget": budget, "method": method,
                        "runs": len(group), "target_hits": hits, "hit_rate": rate,
                        "median_completion_s": median, "runs_99": repeats, "tts99_s": repeats * median})
    return profiles, summary


def panel_rows(rows, panel):
    return [r for r in rows if (r["case"], r["cstr_size"], r["budget"]) == panel[:3]]


def plot_profiles(profiles):
    fig, axes = plt.subplots(3, 3, figsize=(13.8, 10))
    for ax, panel in zip(axes.flat, PANELS):
        group = panel_rows(profiles, panel)
        # Keep the recorded costs even when no method reaches the target.
        costs = [r["estimated_total_s"] for r in group]
        left, right = min(costs) / 1.15, max(costs) * 1.15
        for method, color in zip(METHODS, COLORS):
            values = [r["profile_completion_s"] for r in group if r["method"] == method]
            steps = sorted({left, right, *(v for v in values if math.isfinite(v))})
            ax.step(steps, [sum(v <= x for v in values) / len(values) for x in steps],
                    where="post", color=color, linewidth=1.8)
        ax.set(xscale="log", xlim=(left, right), ylim=(0, 1.035),
               yticks=(0, .25, .5, .75, 1), xlabel="Completion time (s, log scale)",
               ylabel="Fraction of all runs reaching target")
        candidates = [m * 10.**p
                      for p in range(math.floor(math.log10(left)), math.ceil(math.log10(right)) + 1)
                      for m in (1, 2, 5)]
        ticks = [x for x in candidates if left <= x <= right]
        if len(ticks) < 3:
            ticks = [x for x in MaxNLocator(nbins=4).tick_values(left, right) if left <= x <= right]
        ax.xaxis.set_major_locator(FixedLocator(ticks))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.set_title(f"{panel[3]}, B={panel[2]}\n{len(group) // 4} paired starts", fontsize=11)
        ax.grid(alpha=.2, linewidth=.6)
    decorate(fig, "Process GDP: success versus absolute completion time",
             "All paired starts remain in the denominator, including target failures.")
    return fig


def plot_scatter(runs):
    fig, axes = plt.subplots(3, 3, figsize=(14.8, 10.4))
    plotted, summaries = [], []
    for ax, panel in zip(axes.flat, PANELS):
        group = panel_rows(runs, panel)
        values = [r['estimated_total_s'] for r in group]
        lower, upper = min(values) / 1.22, max(values) * 1.6
        seeds = sorted({r['seed'] for r in group})
        offsets = {seed: -.28 + .56 * rank / (len(seeds) - 1)
                   for rank, seed in enumerate(seeds)}
        for i, (method, color) in enumerate(zip(METHODS, COLORS)):
            selected = sorted((r for r in group if r['method'] == method), key=lambda r: r['seed'])
            for hit, marker in ((True, 'o'), (False, 'x')):
                subset = [r for r in selected if r['lookup_target_hit'] == hit]
                xs = [i + offsets[r['seed']] for r in subset]
                ys = [r['estimated_total_s'] for r in subset]
                if subset:
                    ax.scatter(xs, ys, color=color, marker=marker, s=30 if hit else 38,
                               linewidths=0 if hit else 1.5, alpha=.88, zorder=3)
                    plotted.extend(r['job_id'] for r in subset)
            median = statistics.median(r['estimated_total_s'] for r in selected)
            ax.hlines(median, i - .34, i + .34, color='#222222', linewidth=1.1,
                      alpha=.85, zorder=2)
            hits = sum(r['lookup_target_hit'] for r in selected)
            ax.text(i, .96, f'{hits}/{len(selected)}', transform=ax.get_xaxis_transform(),
                    ha='center', va='top', color='#555555', fontsize=9)
            summaries.append({'case': panel[0], 'cstr_size': panel[1], 'budget': panel[2],
                              'method': method, 'runs': len(selected), 'target_hits': hits,
                              'median_completion_s': median})
        ticks = [m * 10**p for p in range(-2, 6) for m in (1, 2, 5)
                 if lower <= m * 10**p <= upper]
        if len(ticks) < 2:
            exponent = math.floor(math.log10(min(values)))
            ticks = [m * 10**exponent for m in range(1, 21)
                     if lower <= m * 10**exponent <= upper]
        ax.set(yscale='log', ylim=(lower, upper), xlim=(-.6, 3.6),
               xticks=range(4), xticklabels=LABELS, ylabel='Estimated completion time (s)')
        ax.yaxis.set_major_locator(FixedLocator(ticks))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:g}'))
        ax.yaxis.set_minor_locator(NullLocator())
        ax.set_title(f'{panel[3]}, B={panel[2]}\n{len(seeds)} runs per method', fontsize=11, pad=11)
        ax.tick_params(axis='x', labelsize=9, length=0, pad=7)
        ax.tick_params(axis='y', labelsize=9)
        ax.grid(axis='y', color='#dce1e5', linewidth=.6, alpha=.8)
        ax.set_axisbelow(True)
    expected = [r['job_id'] for r in runs]
    if len(plotted) != len(set(plotted)) or set(plotted) != set(expected):
        raise ValueError('Scatter omitted or duplicated runs')
    _, tts_summary = performance_tables(runs)
    for row in summaries:
        ref = next(r for r in tts_summary if all(r[k] == row[k] for k in
                   ('case', 'cstr_size', 'budget', 'method')))
        if any(row[k] != ref[k] for k in ('runs', 'target_hits', 'median_completion_s')):
            raise ValueError('Scatter summary differs from the TTS99 source groups')
    fig.subplots_adjust(left=.065, right=.985, bottom=.095, top=.83, hspace=.61, wspace=.30)
    fig.suptitle('NLP-inclusive completion times by run', fontsize=18, y=.982)
    fig.text(.5, .94, 'One point per start; all target outcomes included', ha='center',
             fontsize=11, color='#444444')
    handles = [Line2D([], [], color='#555555', marker='o', linestyle='none', markersize=6,
                      label='Target reached'),
               Line2D([], [], color='#555555', marker='x', linestyle='none', markersize=7,
                      markeredgewidth=1.5, label='Target missed'),
               Line2D([], [], color='#222222', linewidth=1.1, label='Median across runs')]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, .918), ncol=3,
               frameon=False, fontsize=10, columnspacing=2.5)
    fig.text(.5, .052, 'Logarithmic y-axes. Labels: hits/runs. Horizontal offsets follow seed order.',
             ha='center', fontsize=9, color='#444444')
    fig.text(.5, .027, 'Fixed-path time estimates from DFO traces and separate NLP point timings; target outcomes from recorded searches.',
             ha='center', fontsize=9, color='#555555')
    return fig, summaries


def build_run_scatter(output=OUTPUT):
    runs, _, preparation, inputs, source_manifest = load_runs(PANELS)
    output.mkdir(parents=True, exist_ok=True)
    prefix = 'completion_time_scatter'
    with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 9,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.edgecolor': '#555555', 'axes.linewidth': .7,
                         'pdf.fonttype': 42}):
        fig, summaries = plot_scatter(runs)
        for ext in ('png', 'pdf'):
            fig.savefig(output / f'{prefix}.{ext}', dpi=220, facecolor='white',
                        metadata={'CreationDate': None} if ext == 'pdf' else None)
        plt.close(fig)
    for ext in ('png', 'pdf'):
        # Keep existing published URLs, with the figure labeled as completion time.
        (output / f'tts99.{ext}').write_bytes((output / f'{prefix}.{ext}').read_bytes())
    write_csv(output / f'{prefix}_runs.csv', runs)
    artifacts = [f'{prefix}.{ext}' for ext in ('png', 'pdf')] + [f'{prefix}_runs.csv', 'tts99.png', 'tts99.pdf']
    manifest = {
        'kind': 'individual_run_completion_time_scatter', 'runs': len(runs),
        'panels': [list(p) for p in PANELS], 'groups': summaries,
        'y_metric': 'estimated_total_s; no per-run TTS99 is claimed',
        'legacy_figure_aliases': {'tts99.png': f'{prefix}.png', 'tts99.pdf': f'{prefix}.pdf'},
        'formula': 'DFO runtime - lookup time + separate NLP point costs + one Dynamic preparation',
        'target_definition': 'Recorded lookup target within 1e-5 * max(1, abs(target))',
        'markers': {'circle': 'lookup target hit', 'cross': 'lookup target missed',
                    'black_line': 'median completion estimate across all runs'},
        'horizontal_offsets': 'Seed order, fixed across methods within each panel',
        'all_target_failures_included': True, 'measured_online_runtime': False,
        'point_cost_policy': source_manifest['cost_policy'],
        'dynamic_preparation_reference': preparation,
        'sources': input_hashes(inputs, source_manifest),
        'followup_selection': source_manifest.get('followup_selection'),
        'scripts': {str(p.relative_to(ROOT)): sha(p) for p in
                    (Path(__file__), ROOT / 'scripts/plot_dantzig_cost_breakdown.py',
                     ROOT / 'scripts/plot_dantzig_run_scatter.py')},
        'artifacts': {name: sha(output / name) for name in artifacts},
    }
    scatter_manifest_path = output / f'{prefix}.manifest.json'
    scatter_manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    performance_manifest_path = output / 'performance.manifest.json'
    if performance_manifest_path.exists():
        performance_manifest = json.loads(performance_manifest_path.read_text())
        performance_manifest['completion_time_scatter'] = {
            'manifest': scatter_manifest_path.name, 'runs': len(runs),
            'y_metric': 'estimated_total_s', 'legacy_filenames': ['tts99.png', 'tts99.pdf'],
        }
        performance_manifest['scripts'].update(manifest['scripts'])
        performance_manifest['artifacts'].update(manifest['artifacts'])
        performance_manifest['artifacts'][scatter_manifest_path.name] = sha(scatter_manifest_path)
        performance_manifest_path.write_text(json.dumps(performance_manifest, indent=2) + '\n')
    print(json.dumps({'runs_plotted': len(runs), 'groups': len(summaries),
                      'output': str(output)}, indent=2))

    return manifest


def decorate(fig, title, note):
    fig.subplots_adjust(left=.066, right=.984, bottom=.115, top=.84, hspace=.65, wspace=.32)
    fig.suptitle(title, fontsize=18, y=.98)
    fig.legend([Line2D([], [], color=c, linewidth=2) for c in COLORS], LABELS,
               loc="upper center", bbox_to_anchor=(.5, .948), ncol=4, frameon=False, fontsize=11)
    fig.text(.5, .055, note, ha="center", fontsize=9.2)
    fig.text(.5, .027, "Fixed-path completion estimates from DFO traces and separate NLP point timings; completion times, not first-hit times.",
             ha="center", fontsize=9, color="#555555")


def full_benchmark():
    """Bring in every selected GDPopt/MINLP run without turning it into seed trials."""
    inventory = json.loads((GDP_SOURCE / "artifact_checksums.json").read_text())
    if sha(GDP_SOURCE / "comparison.csv") != inventory["comparison.csv"]:
        raise ValueError("GDP/MINLP comparison checksum mismatch")
    baseline = read_csv(GDP_SOURCE / "comparison.csv")
    expected = {(p[0], p[1], method) for p in FULL_PANELS for method in BASELINES}
    keys = [(r["case"], r["cstr_size"], r["method"]) for r in baseline]
    if len(keys) != 45 or set(keys) != expected:
        raise ValueError("Expected all 45 unique selected GDPopt/MINLP jobs")
    runs, means, _, _, _ = load_runs(FULL_PANELS)
    rows = []
    for row in means:
        group = [r for r in runs if
                 (r["case"], r["cstr_size"], r["budget"], r["method"]) ==
                 (row["case"], row["cstr_size"], row["budget"], row["method"])]
        attained = sum(float(r["recorded_best_value"]) <= float(r["target_value"]) +
                       1e-5 * max(1, abs(float(r["target_value"]))) for r in group)
        if attained != row["lookup_target_hits"]:
            raise ValueError("DFO attainment differs from the published target matches")
        rows.append({"case": row["case"], "cstr_size": row["cstr_size"], "method": row["method"],
                     "family": "DFO", "dfo_budget": row["budget"], "runs": row["runs"],
                     "completion_s": row["estimated_total_s"], "clock_kind": "mean_fixed_path_estimate",
                     "target_attained": attained, "time_limits": 0, "bound_conflicts": 0,
                     "final_objective": statistics.mean(float(r["recorded_best_value"]) for r in group),
                     "objective_statistic": "mean", "target_value": float(group[0]["target_value"]),
                     "source": "; ".join(sorted({r["source"] for r in group}))})
    for row in baseline:
        duration = float(row["measured_total_with_preparation_s"])
        if not math.isfinite(duration) or duration <= 0 or row["source_host"] != "dantzig.ecn.purdue.edu":
            raise ValueError("Invalid GDP/MINLP source or completion time")
        rows.append({"case": row["case"], "cstr_size": row["cstr_size"], "method": row["method"],
                     "family": "GDPopt" if row["method"] in BASELINES[:3] else "MINLP", "dfo_budget": "",
                     "runs": 1, "completion_s": duration, "clock_kind": "single_measured_completion_with_preparation",
                     "target_attained": int(row["target_attained"] == "True"),
                     "time_limits": int(row["termination"] == "maxTimeLimit"),
                     "bound_conflicts": int(row["bound_conflict_with_saved_solution"] == "True"),
                     "final_objective": float(row["objective"]), "objective_statistic": "single_run",
                     "target_value": float(row["target_value"]), "source": row["source_directory"]})
    return rows


def plot_full_benchmark(rows):
    fig, ax = plt.subplots(figsize=(16.8, 7.8))
    ax.axis("off")
    cells = []
    for panel in FULL_PANELS:
        line = [f"{panel[3]}\nDFO B={panel[2]}"]
        for method in (*METHODS, *BASELINES):
            r = next(r for r in rows if (r["case"], r["cstr_size"], r["method"]) == (*panel[:2], method))
            markers = (" TL" if r["time_limits"] else "") + (" †" if r["bound_conflicts"] else "")
            line.append(f"{r['completion_s']:.2f} s{markers}\n{r['target_attained']}/{r['runs']}")
        cells.append(line)
    table = ax.table(cellText=cells, colLabels=("Model", *LABELS, "RIC\nGDPopt", "GLOA\nGDPopt",
                    "LOA\nGDPopt", "Big-M\nMINLP", "Hull\nMINLP"), cellLoc="center",
                     colWidths=[.13] + [.096] * 9, bbox=(0, .16, 1, .73))
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#d7dfe5")
        cell.set_linewidth(.6)
        if row == 0:
            cell.set_facecolor("#dcebf5" if 1 <= col <= 4 else "#e7e9eb")
            cell.set_text_props(weight="bold")
        elif row % 2:
            cell.set_facecolor("#f7f9fb")
    fig.suptitle("DFO, GDPopt and MINLP completion times — all nine models", fontsize=18, y=.97)
    fig.text(.5, .907, "Each cell: completion time / target attainment count. All 45 GDPopt and MINLP jobs are included.",
             ha="center", fontsize=11)
    fig.text(.5, .128, "DFO: mean estimated completion time over 10 starts. GDPopt/MINLP: one measured run per model, including template preparation.",
             ha="center", fontsize=10)
    fig.text(.5, .098, "Target attained: final objective ≤ lookup target + tolerance. TL: time limit. †: reported bound conflicts with a saved feasible solution.",
             ha="center", fontsize=10)
    fig.text(.5, .068, "GDPopt: BARON + HiGHS (Oct 1). Big-M/Hull: BARON (Sep 25). All on Dantzig; different dates/CPUs. Completion times, not first-hit times.",
             ha="center", fontsize=10)
    fig.text(.5, .038, "CSTR5–25 DFO costs include NLP attempts that did not reproduce feasible lookup outcomes; the recorded search targets remain lookup-based.",
             ha="center", fontsize=9.5, color="#555555")
    return fig


def build(output=OUTPUT):
    runs, _, preparation, inputs, source_manifest = load_runs(PANELS)
    profiles, summary = performance_tables(runs)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "performance_profile_runs.csv", profiles)
    write_csv(output / "tts99_summary.csv", summary)
    benchmark = full_benchmark()
    write_csv(output / "all_method_completion_times.csv", benchmark)
    (output / "gdp_minlp_runs.csv").write_bytes((GDP_SOURCE / "comparison.csv").read_bytes())
    scatter_manifest = build_run_scatter(output)
    artifacts = ["performance_profile_runs.csv", "tts99_summary.csv", "all_method_completion_times.csv", "gdp_minlp_runs.csv",
                 "completion_time_scatter.manifest.json", *scatter_manifest["artifacts"]]
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False}):
        for name, fig in (("performance_profiles", plot_profiles(profiles)),
                          ("all_method_completion_times", plot_full_benchmark(benchmark))):
            for ext in ("png", "pdf"):
                filename = f"{name}.{ext}"
                fig.savefig(output / filename, dpi=220, facecolor="white",
                            metadata={"CreationDate": None} if ext == "pdf" else None)
                artifacts.append(filename)
            plt.close(fig)
    manifest = {"panels": [list(p) for p in PANELS], "runs": len(runs),
                "time_kind": "fixed_path_completion_estimate", "measured_online_runtime": False,
                "time_formula": "DFO runtime - lookup calls + selected point costs + one Dynamic preparation per run",
                "target_definition": "Frozen lookup target within 1e-5 * max(1, abs(target))",
                "profile_definition": "Fraction of all runs reaching the target with estimated completion time <= t seconds; target failures have infinite profile_completion_s and stay in the denominator",
                "profile_metric": "profile_completion_s; absolute seconds, no relative normalization",
                "profile_xscale": "log",
                "profile_methods": list(METHODS),
                "tts99_definition": "Median completion time over all seeds * ceil(log(0.01) / log(1 - observed hit rate)); p=0: infinity, p=1: one run",
                "tts99_assumption": "Independent restarts with the observed hit probability; an estimate from 10 runs, not a 99% confidence guarantee",
                "completion_time_scatter": {"manifest": "completion_time_scatter.manifest.json",
                                            "runs": len(runs), "y_metric": "estimated_total_s",
                                            "legacy_filenames": ["tts99.png", "tts99.pdf"]},
                "point_cost_policy": source_manifest["cost_policy"], "dynamic_preparation_reference": preparation,
                "sources": input_hashes(inputs, source_manifest),
                "followup_selection": source_manifest.get("followup_selection"),
                "gdp_minlp_source": {str((GDP_SOURCE / "comparison.csv").relative_to(ROOT)): sha(GDP_SOURCE / "comparison.csv")},
                "gdp_minlp_runs": 45, "all_method_comparison_rows": len(benchmark),
                "gdp_minlp_policy": "Single measured completion per method/model; preserve time limits, target attainment and bound conflicts; no restart probability or TTS99 inferred from one run",
                "scripts": {str(path.relative_to(ROOT)): sha(path) for path in
                            (Path(__file__), ROOT / "scripts/plot_dantzig_run_scatter.py",
                             ROOT / "scripts/plot_dantzig_cost_breakdown.py", ROOT / "benchmark_analysis.py")},
                "artifacts": {name: sha(output / name) for name in artifacts}}
    (output / "performance.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output": str(output), "panels": len(PANELS), "runs": len(runs)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    build(parser.parse_args().output_dir)
