"""Join recorded Grid paths to measured IPOPT point costs; never run solvers.

Raw archives stay immutable. DSDA coordinates are recovered from its original
verbose log (not replayed). Profiles use absolute costs and retain failures.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "results"
OUTPUT = RESULTS / "grid_gdp_dfo_20261011"
ARCHIVES = RESULTS / "archives"
BUDGETS = (10, 30, 50, 70, 100)
METHODS = ("dsda", "rbfopt", "bam", "fmqa_sa")
GDP_METHODS = ("ric", "gloa", "loa", "bigm", "hull")
LABELS = dict(zip(METHODS + GDP_METHODS, (
    "DSDA", "RBFOpt", "BAM 5.0.0", "FMQA-SA", "GDPopt RIC*", "GDPopt GLOA*",
    "GDPopt LOA*", "Big-M / BARON", "Hull / BARON")))
COLORS = dict(zip(METHODS + GDP_METHODS, (
    "#1976b9", "#e77818", "#27952a", "#9467bd", "#8c564b", "#d35c93",
    "#65727e", "#a58e11", "#159caa")))
NAMES = {
    "dsda": "dantzig_20260910_170759_slN8tv.zip",
    "rbfopt": "grid_trace_rbfopt_20261008_190603_og2app39.zip",
    "bam": "grid_trace_bam_20261008_190603_5bh3y_t5.zip",
    "fmqa_sa": "dantzig_fmqa_grid_20260925_172020_9n7j9oh1.zip",
}
BAM_HASH = "bd4d9bf56deafa864ecdd2e676fc24bd25a6037bdb02a772ebd800eb1a935374"
TOL = 1e-5


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def table(data):
    return list(csv.DictReader(io.StringIO(data.decode())))


def read_table(path):
    return table(path.read_bytes())


def write_table(path, rows):
    stream = io.StringIO(newline="")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    w = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows({k: json.dumps(v) if isinstance(v, (list, dict)) else v
                for k, v in row.items()} for row in rows)
    raw = stream.getvalue().encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)


def load_archive(path, expected=None):
    digest = sha(path.read_bytes())
    sidecar = Path(str(path) + ".sha256")
    if expected is not None:
        require(digest == expected, f"Archive hash: {path}")
    elif sidecar.exists():
        require(digest == sidecar.read_text().split()[0], f"Archive hash: {path}")
    with zipfile.ZipFile(path) as z:
        require(z.testzip() is None, f"ZIP CRC: {path}")
        names = [n for n in z.namelist() if not n.endswith("/")]
        require(len(names) == len(set(names)), "Duplicate ZIP member")
        prefix = names[0].split("/")[0] + "/"
        require(all(n.startswith(prefix) for n in names), "ZIP root")
        data = {n[len(prefix):]: z.read(n) for n in names}
    checked = 0
    if "SHA256SUMS" in data:
        for line in data["SHA256SUMS"].decode().splitlines():
            expected_hash, name = line.split(maxsplit=1)
            name = name.lstrip("*")
            require(sha(data[name]) == expected_hash, f"Member hash: {name}")
            checked += 1
        require(checked == len(data) - 1, "Archive manifest coverage")
    return data, {"archive": path.name, "sha256": digest, "member_hashes_checked": checked}


def reference_data():
    from fmqa_benchmark.grid_protocol import verify_grid_sources
    from grid_dsda import load_grid_csv
    hashes = verify_grid_sources()
    grids = {Path(p).stem: load_grid_csv(ROOT / p)[1] for p in hashes}
    design_file = ROOT / "fmqa_benchmark/reference/grid/comparison_audit.json"
    designs = {(Path(d["csv_name"]).stem, d["seed"]): d["starting_points"]
               for d in json.loads(design_file.read_text())["grid_designs"]}
    points_path = RESULTS / "grid_gdp_20261009/raw/point_timings.csv"
    costs = {}
    for row in read_table(points_path):
        p = tuple(json.loads(row["point"]))
        key = (row["grid_name"], p)
        require(key not in costs, "Duplicate point timing")
        require(row["accepted"] == "True" and row["ipopt_invoked"] == "True"
                and row["threads"] == "1", "Unaccepted or incompatible point timing")
        require(abs(float(row["csv_objective"]) - grids[key[0]][p]) <= 1e-12,
                "Timing objective / reference mismatch")
        costs[key] = float(row["point_wall_s"])
        require(math.isfinite(costs[key]) and costs[key] > 0, "Invalid point time")
    require(set(costs) == {(g, (i, j)) for g in grids for i in range(31) for j in range(31)},
            "Incomplete 21 x 961 timings")
    return grids, designs, costs, {"point_timings_sha256": sha(points_path.read_bytes()),
                                  "reference_grids_sha256": hashes,
                                  "designs_sha256": sha(design_file.read_bytes())}


def dsda_paths(grids, designs):
    data, provenance = load_archive(ARCHIVES / NAMES["dsda"])
    records = [r for r in table(data["benchmark.csv"]) if r["method"] == "DSDA"]
    # Grid jobs precede the process benchmarks and run in benchmark.csv order.
    log = data["run.log"].decode().split("[EXIT] [1/4] grids")[0]
    blocks = log.split("Starting points ranked by initial value:")[1:]
    require(len(blocks) == len(records) == 1050, "DSDA log / result coverage")
    recovered = []
    for block_number, (record, block) in enumerate(zip(records, blocks), 1):
        name, seed = Path(record["csv_name"]).stem, int(record["seed"])
        initial = designs[name, seed]
        ranked = re.findall(r"^\d+\. \((\d+), (\d+)\) ->", block, re.M)
        require({tuple(map(int, p)) for p in ranked} == {tuple(p) for p in initial},
                "DSDA initial points mismatch")
        events = [{"point": p, "phase": "initial", "value": grids[name][tuple(p)],
                   "log_block": block_number, "log_block_line": "frozen_initial_design"}
                  for p in initial]
        for line_number, line in enumerate(block.splitlines(), 1):
            match = re.match(r"^   \((\d+), (\d+)\) -> ([-+.eE\d]+)$", line)
            phase = "neighbor"
            if match is None:
                match = re.match(r"^Line search (?:accepted|rejected): \((\d+), (\d+)\) -> ([-+.eE\d]+)$", line)
                phase = "line_search"
            if match:
                p = tuple(map(int, match.group(1, 2)))
                value = grids[name][p]
                require(abs(value - float(match.group(3))) <= 1e-11, "DSDA printed objective")
                events.append({"point": list(p), "phase": phase, "value": value,
                               "log_block": block_number, "log_block_line": line_number})
        recovered.append((name, seed, int(record["max_evals"]), events,
                          float(record["wall_time_s"]), None, record, "run.log"))
    return recovered, provenance


def traced_paths(method, path):
    data, provenance = load_archive(path, BAM_HASH if method == "bam" else None)
    recovered = []
    if method == "fmqa_sa":
        result_names = sorted(n for n in data if n.startswith("jobs/") and n.endswith("/result.json"))
    else:
        result_names = []
        for seal_name in sorted(n for n in data if n.startswith("jobs/") and n.endswith("/complete.json")):
            n = seal_name.removesuffix("complete.json") + "result.json"
            require(json.loads(data[seal_name])["result_sha256"] == sha(data[n]), "Result seal")
            result_names.append(n)
    for n in result_names:
        result = json.loads(data[n])
        require(result["status"] == "completed", "Incomplete DFO result")
        spec = result["spec"]
        directory = n.removesuffix("result.json")
        if method == "fmqa_sa":
            trace_name = directory + "evaluations.jsonl"
            events = [json.loads(l) for l in data[trace_name].splitlines()]
            record, wall, lookup = result, result["wall_time_s"], result["objective_wall_s"]
        else:
            trace_name = directory + result["trace"]["path"]
            require(sha(data[trace_name]) == result["trace"]["sha256"], "Trace seal")
            entries = [json.loads(l) for l in data[trace_name].splitlines()]
            require(entries[0]["run_key"] == spec and entries[-1]["event"] == "run_complete", "Trace identity")
            events = entries[1:-1]
            record = result["result_record"]
            require(entries[-1]["result_record"] == record, "Trace result")
            wall, lookup = result["search_wall_s"], result["lookup_wall_s"]
        require([e["evaluation_index"] for e in events] == list(range(1, len(events) + 1)), "Trace sequence")
        require(math.isclose(sum(e["objective_wall_s"] for e in events), lookup, abs_tol=1e-9), "Lookup sum")
        require(all(not e.get("exception_type") for e in events), "Failed callback")
        require(all(a["completed_elapsed_s"] <= b["completed_elapsed_s"] for a, b in zip(events, events[1:])), "Trace clocks")
        recovered.append((Path(spec["csv_name"]).stem, spec["seed"], spec["max_evaluations"],
                          events, wall, lookup, record, trace_name))
    require(len(recovered) == 1050, f"{method} expected 1050 completed paths")
    return recovered, provenance


def charge_run(method, name, seed, budget, events, wall, lookup, record, source,
               grids, designs, costs):
    """Charge actual calls in order, including repeated and initial points."""
    require(len(events) == int(record["total_evals"]) <= budget, "Callback count")
    require([e["point"] for e in events[:3]] == designs[name, seed], "Initial design order")
    history = record["incumbent_trajectory"]
    history = json.loads(history) if isinstance(history, str) else history
    require(len(history) == len(events), "History length")
    target = min(grids[name].values())
    job_id = f"grid_{name}_B{budget}_seed{seed}_{method}"
    incumbent, first_hit, sum_cost, sum_lookup = math.inf, math.inf, 0.0, 0.0
    seen, charges = set(), []
    for i, e in enumerate(events, 1):
        p = tuple(e["point"])
        require(p in grids[name], "Invalid lattice point")
        value = e["value"]
        require(math.isfinite(value) and abs(value - grids[name][p]) <= 1e-12, "Reference objective")
        incumbent = min(incumbent, value)
        require(abs(incumbent - history[i - 1]) <= 1e-12, "Incumbent history mismatch")
        if abs(incumbent - target) <= TOL * max(1.0, abs(target)) and math.isinf(first_hit):
            first_hit = i
        cost = costs[name, p]  # Missing observations fail, never filled by a mean.
        sum_cost += cost
        sum_lookup += e.get("objective_wall_s", 0.0)
        charges.append(dict(job_id=job_id, grid_name=name, method=method, seed=seed, max_evals=budget,
                            evaluation_index=i, point=list(p), phase=e["phase"], value=value,
                            incumbent=incumbent, repeated_point=p in seen, point_wall_s=cost,
                            cumulative_point_wall_s=sum_cost, objective_wall_s=e.get("objective_wall_s", ""),
                            recorded_elapsed_s=e.get("completed_elapsed_s", ""),
                            estimated_elapsed_s=(e["completed_elapsed_s"] - sum_lookup + sum_cost)
                            if "completed_elapsed_s" in e else "",
                            source_member=source, log_block=e.get("log_block", ""),
                            log_block_line=e.get("log_block_line", "")))
        seen.add(p)
    require(abs(incumbent - float(record["best_value"])) <= 1e-12, "Final objective mismatch")
    require(math.isfinite(wall) and wall > 0 and (lookup is None or 0 <= lookup <= wall), "Run timing")
    # DSDA logs lack lookup clocks: retain its entire recorded lookup runtime.
    # No local timing measurement or invented per-call subtraction is substituted.
    overhead = wall - (lookup if lookup is not None else 0)
    total = overhead + sum_cost
    hit = math.isfinite(first_hit)
    run = dict(job_id=job_id, grid_name=name, method=method, seed=seed, max_evals=budget,
               total_evals=len(events), unique_evals=len(seen), target=target, best_value=incumbent,
               target_hit=hit, first_hit_evaluation=first_hit, recorded_run_wall_s=wall,
               recorded_lookup_wall_s=lookup if lookup is not None else "",
               retained_search_wall_s=overhead, sum_point_wall_s=sum_cost, estimated_total_s=total,
               completion_cost_s=total if hit else math.inf,
               lookup_cost_removed=lookup is not None, source_member=source,
               trajectory_kind="logged_coordinates" if method == "dsda" else "callback_trace")
    return run, charges


def tts_summary(runs):
    groups = defaultdict(list)
    for r in runs:
        groups[r["grid_name"], r["method"], r["max_evals"]].append(r)
    rows = []
    for (name, method, budget), group in sorted(groups.items()):
        n, hits = len(group), sum(r["target_hit"] for r in group)
        p = hits / n
        repeats = math.inf if hits == 0 else 1 if hits == n else math.ceil(math.log(.01) / math.log1p(-p))
        median = statistics.median(r["estimated_total_s"] for r in group)
        rows.append(dict(grid_name=name, method=method, max_evals=budget, runs=n, hits=hits,
                         hit_rate=p, median_completion_s=median, runs_99=repeats, tts99_s=median * repeats))
    return rows


def cdf_points(costs, right):
    """Failures stay in the denominator; tied jumps happen at their exact cost."""
    counts = Counter(c for c in costs if math.isfinite(c))
    xs, ys, count = [0.0], [0.0], 0
    for value in sorted(counts):
        count += counts[value]
        xs.append(value)
        ys.append(count / len(costs))
    if xs[-1] < right:
        xs.append(right)
        ys.append(ys[-1])
    return xs, ys


def gdp_runs():
    base_path = RESULTS / "grid_gdp_retry_20261009/benchmark_current.csv"
    fixed_path = RESULTS / "grid_gdp_corrected_20261009/results.csv"
    base, fixed = read_table(base_path), read_table(fixed_path)
    changes = {(r["grid_name"], r["method"]): r for r in fixed}
    rows = []
    for old in base:
        key = old["grid_name"], old["method"]
        r = changes.get(key, old)
        require(key not in changes or old["status"] == "error", "Only corrected errors replaced")
        hit = r["audited_target_hit"] == "True"
        wall = float(r["worker_wall_s"]) if r.get("worker_wall_s") else None
        require(not hit or (wall is not None and wall > 0), "Missing successful GDP time")
        rows.append(dict(grid_name=key[0], method=key[1], status=r["status"],
                         termination=r["termination"], target_hit=hit,
                         measured_worker_wall_s=wall if wall is not None else "",
                         completion_cost_s=wall if hit else math.inf,
                         profile="pyomo610-grid-v1" if key in changes else "original",
                         audited_gap=r.get("audited_gap", ""),
                         source_archive=r["source_archive"], source_result=r["source_result"],
                         source_result_sha256=r["source_result_sha256"]))
    require(len(rows) == len({(r['grid_name'], r['method']) for r in rows}) == 105, "GDP matrix")
    return rows, {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in (base_path, fixed_path)}


def plot_figures(runs, summary, gdp, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import numpy as np
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42, "savefig.dpi": 200})
    figures = []
    def save(fig, name):
        for ext in ("png", "pdf"):
            kwargs = {"metadata": {"CreationDate": None, "ModDate": None}} if ext == "pdf" else {}
            fig.savefig(output / f"{name}.{ext}", bbox_inches="tight", **kwargs)
        plt.close(fig)
        figures.append(name)
    def panels(title):
        fig, axes = plt.subplots(2, 3, figsize=(14, 9), sharey=True)
        fig.suptitle(title, fontsize=17, y=.985)
        fig.subplots_adjust(wspace=.24, hspace=.36, bottom=.12, top=.90)
        axes.flat[-1].axis("off")
        return fig, axes
    handles = [Line2D([], [], color=COLORS[m], lw=2, label=LABELS[m]) for m in METHODS]
    for metric, name, title, xlabel in (
        ("first_hit_evaluation", "evaluation_profiles", "Grid GDP: success versus raw evaluation count", "Objective evaluations to first target"),
        ("completion_cost_s", "performance_profiles", "Grid GDP: success versus absolute completion time", "Completion time (s, log scale)"),
    ):
        timing = metric == "completion_cost_s"
        fig, axes = panels(title)
        right = max(r[metric] for r in runs if math.isfinite(r[metric])) * (1.2 if timing else 1)
        for ax, budget in zip(axes.flat, BUDGETS):
            for m in METHODS:
                rs = [r for r in runs if r["method"] == m and r["max_evals"] == budget]
                xs, ys = cdf_points([r[metric] for r in rs], right if timing else budget)
                if timing:
                    xs[0] = .1
                ax.step(xs, ys, where="post", color=COLORS[m], lw=1.8, alpha=.92)
            ax.set_title(f"DFO budget = {budget}")
            ax.set_ylim(0, 1.025)
            ax.set_xlim((.1, right) if timing else (0, budget))
            if timing:
                ax.set_xscale("log")
            ax.set_xlabel(xlabel)
            ax.grid(axis="y", alpha=.18)
        for ax in axes[:, 0]:
            ax.set_ylabel("Fraction reaching target")
        legend = axes.flat[-1]
        legend.legend(handles=handles, loc="upper left", frameon=False,
                      ncol=1, fontsize=10, handlelength=2.1)
        note = ("21 grids × 10 seeds per method / budget\nMeasured IPOPT costs along recorded paths\nFull completion time; failures retained\nAbsolute seconds; no solver-relative ratios"
                if timing else "21 grids × 10 seeds per method / budget\nInitial and repeated callbacks count\nFailures remain in the denominator\nRaw counts; no solver-relative ratios")
        legend.text(.02, .35, note, transform=legend.transAxes, fontsize=9, va="bottom", linespacing=1.6)
        fig.text(.06, .025, "Target: normalized objective within 1e-5 of the CSV grid minimum.", fontsize=10)
        save(fig, name)
    fig, axes = panels("Grid GDP: estimated TTS99 with measured IPOPT point costs")
    finite = [r["tts99_s"] for r in summary if math.isfinite(r["tts99_s"])]
    lower, upper = min(finite) / 1.7, max(finite) * 2.5
    for ax, budget in zip(axes.flat, BUDGETS):
        for i, m in enumerate(METHODS):
            group = [r for r in summary if r["method"] == m and r["max_evals"] == budget]
            values = np.array([r["tts99_s"] for r in group])
            good = np.isfinite(values)
            jitter = np.linspace(-.19, .19, len(values))
            ax.scatter(i + jitter[good], values[good], color=COLORS[m], s=25, alpha=.76)
            median = float(np.median(values))
            if math.isfinite(median):
                ax.hlines(median, i - .25, i + .25, color="black", lw=2)
            failed = sum(~good)
            if failed:
                ax.scatter(i, upper, marker="^", color=COLORS[m], s=30)
                ax.annotate(f"∞ × {failed}", (i, upper), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=9)
            if math.isinf(median):
                ax.annotate("median = ∞", (i, upper), xytext=(0, 22), textcoords="offset points", ha="center", fontsize=8)
        ax.set_title(f"DFO budget = {budget}")
        ax.set_xticks(range(4), ["DSDA", "RBFOpt", "BAM", "FMQA-SA"])
        ax.set_xlim(-.5, 3.5)
        ax.set_yscale("log")
        ax.set_ylim(lower, upper * 8)
        ax.grid(axis="y", alpha=.18)
    for ax in axes[:, 0]:
        ax.set_ylabel("Estimated TTS99 (s, log scale)")
    axes.flat[-1].text(.03, .85,
        "Each dot: one grid, 10 seed runs\nBlack bar: median over all 21 grids\n∞: no observed hit in 10 runs\n\nTTS99 = median completion cost × restarts\nRestarts = ceil[log(0.01) / log(1 - p)]\np = hits / 10; p = 1: one run\n\nFixed-path estimates using measured costs.\nIndependent restarts assumed.",
        transform=axes.flat[-1].transAxes, va="top", fontsize=11, linespacing=1.8)
    save(fig, "tts99")

    # GDPopt/MINLP have one run per grid and different stopping rules. Show their
    # measured outcomes directly, separately from the four-method DFO profiles.
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    grid_names = sorted({r["grid_name"] for r in gdp})
    selected = {(r["grid_name"], r["method"]): r for r in gdp}
    palette = ("#d9eddf", "#fbe3c4", "#e5e7eb")
    status = np.empty((len(grid_names), len(GDP_METHODS)), dtype=int)
    fig, ax = plt.subplots(figsize=(10, 12))
    fig.subplots_adjust(left=.31, right=.985, top=.88, bottom=.115)
    for i, grid in enumerate(grid_names):
        for j, method in enumerate(GDP_METHODS):
            row = selected[grid, method]
            unsupported = row["status"] == "unsupported_expression"
            status[i, j] = 2 if unsupported else 0 if row["target_hit"] else 1
            label = "unsupported" if unsupported else f"{row['measured_worker_wall_s']:.2f}"
            if row["termination"] == "maxTimeLimit" or row["status"] == "hard_time_limit":
                label += " T"
            if row["profile"] == "pyomo610-grid-v1":
                label += " *"
            ax.text(j, i, label, ha="center", va="center", fontsize=9, color="#222222")
    ax.imshow(status, cmap=ListedColormap(palette), vmin=0, vmax=2, aspect="auto")
    ax.set_xticks(range(len(GDP_METHODS)), ["GDPopt\nRIC", "GDPopt\nGLOA", "GDPopt\nLOA", "Big-M\nBARON", "Hull\nBARON"])
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(grid_names)), [n.replace("_", " ") for n in grid_names])
    ax.tick_params(axis="both", length=0, pad=8)
    ax.set_xticks(np.arange(-.5, len(GDP_METHODS), 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(grid_names), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.5)
    ax.tick_params(which="minor", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.suptitle("Grid GDP: GDPopt and MINLP reformulations", fontsize=17, y=.982)
    fig.legend(handles=[Patch(facecolor=c, label=l) for c, l in zip(palette, (
        "Target reached", "Target not reached", "Unsupported"))],
        loc="upper center", bbox_to_anchor=(.5, .955), frameon=False, ncol=3)
    fig.text(.04, .066, "Cell values: measured completion time (s). T: time limit; *: corrected Pyomo profile.", fontsize=10)
    fig.text(.04, .040, "Colors show target attainment within 1e-5 of the CSV minimum, not an optimality certificate.", fontsize=9)
    save(fig, "gdp_minlp_comparison")
    return figures


def update_published_aliases(output):
    """Keep existing user-facing Grid figure links pointing to the new analysis."""
    legacy = RESULTS / "fmqa_20260925/analysis/grid"
    mapping = {
        "tts99_comparison": "tts99",
        "evaluation_performance_profiles": "evaluation_profiles",
        "timing/time_performance_profiles": "performance_profiles",
        "timing/completion_time_profiles": "performance_profiles",
    }
    aliases = {}
    for target, source in mapping.items():
        for ext in ("png", "pdf"):
            data = (output / f"{source}.{ext}").read_bytes()
            path = legacy / f"{target}.{ext}"
            path.write_bytes(data)
            aliases[str(path.relative_to(ROOT))] = {"source": str((output / f"{source}.{ext}").relative_to(ROOT)),
                                                    "sha256": sha(data)}
    (legacy / "tts99_summary.csv").write_bytes((output / "tts99_summary.csv").read_bytes())
    pointer = {"analysis": str(output.relative_to(ROOT)),
               "analysis_manifest_sha256": sha((output / "manifest.json").read_bytes()),
               "scope": "Current Grid GDP path-cost figures; historical lookup benchmark.csv is not their input",
               "aliases": aliases}
    (legacy / "grid_gdp_figures.manifest.json").write_text(json.dumps(pointer, indent=2) + "\n")
    (legacy / "tts99_manifest.json").write_text(json.dumps({
        "analysis": pointer["analysis"], "analysis_manifest_sha256": pointer["analysis_manifest_sha256"],
        "time_measure": "Estimated completion cost with individually measured IPOPT point times",
        "summary_sha256": sha((legacy / "tts99_summary.csv").read_bytes()),
        "figure_aliases": {k: v for k, v in aliases.items() if "tts99_comparison" in k}}, indent=2) + "\n")
    old_timing_manifest = legacy / "timing/timing_analysis.manifest.json"
    timing = json.loads(old_timing_manifest.read_text())
    timing["scope_after_20261011"] = {
        "historical_outputs": ["time_profile_runs.csv", "time_work_summary.csv", "time_work_tradeoff.png"],
        "replaced_figures": ["time_performance_profiles.png", "completion_time_profiles.png"],
        "current_figure_manifest": "../grid_gdp_figures.manifest.json"}
    old_timing_manifest.write_text(json.dumps(timing, indent=2) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bam-archive", type=Path, default=ARCHIVES / NAMES["bam"])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--update-published", action="store_true", help="Update existing Grid figure links after generation")
    args = parser.parse_args(argv)
    require(not (args.no_figures and args.update_published), "Cannot publish aliases without regenerated figures")
    require(args.bam_archive.is_file(), f"BAM source ZIP required: {args.bam_archive}")
    grids, designs, costs, sources = reference_data()
    runs, charges, provenance = [], [], {}
    for method in METHODS:
        paths, info = (dsda_paths(grids, designs) if method == "dsda" else
                       traced_paths(method, args.bam_archive if method == "bam" else ARCHIVES / NAMES[method]))
        expected = {(g, s, b) for g in grids for s in range(10) for b in BUDGETS}
        require(len(paths) == len(expected) and {(r[0], r[1], r[2]) for r in paths} == expected, "Run matrix")
        for path in paths:
            r, c = charge_run(method, *path, grids, designs, costs)
            runs.append(r)
            charges.extend(c)
        provenance[method] = info
        print(method, len(paths), "runs;", sum(len(p[3]) for p in paths), "callbacks", flush=True)
    summary = tts_summary(runs)
    require(len(summary) == 420 and all(r["runs"] == 10 for r in summary), "TTS groups")
    gdp, gdp_sources = gdp_runs()
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, rows in (("runs.csv", runs), ("point_charges.csv.gz", charges),
                           ("tts99_summary.csv", summary), ("gdp_runs.csv", gdp)):
        write_table(args.output / filename, rows)
    figures = [] if args.no_figures else plot_figures(runs, summary, gdp, args.output)
    totals = [{"method": m, "max_evals": b, "runs": len(rs), "hits": sum(r["target_hit"] for r in rs),
               "median_completion_s": statistics.median(r["estimated_total_s"] for r in rs),
               "median_point_cost_s": statistics.median(r["sum_point_wall_s"] for r in rs)}
              for m in METHODS for b in BUDGETS
              if (rs := [r for r in runs if r["method"] == m and r["max_evals"] == b])]
    write_table(args.output / "budget_summary.csv", totals)
    artifacts = [args.output / n for n in ("runs.csv", "point_charges.csv.gz", "tts99_summary.csv",
                                           "gdp_runs.csv", "budget_summary.csv")]
    artifacts.extend(args.output / f"{name}.{ext}" for name in figures for ext in ("png", "pdf"))
    manifest = {"analysis_sha256": sha(Path(__file__).read_bytes()), "sources": sources,
                "archives": provenance, "gdp_sources": gdp_sources,
                "runs": len(runs), "callbacks": len(charges), "timed_points": len(costs),
                "callbacks_by_method": dict(Counter(r["method"] for r in charges)),
                "repeated_callbacks_by_method": dict(Counter(r["method"] for r in charges if r["repeated_point"])),
                "figures": figures, "target_tolerance": TOL,
                "profile_methods": list(METHODS),
                "gdp_figure": "Separate per-grid time/outcome matrix in gdp_minlp_comparison; excluded from performance profiles",
                "time_metric": "Full successful-run completion; lookup replacement plus sum of point_wall_s",
                "dsda_exception": "Original log has no lookup clocks; entire historical runtime retained (lookup cost not subtracted)",
                "gdp_selection": "Original + 11 unchanged-profile network retries + 10 explicitly labelled corrected error retries; not selected by speed or objective",
                "unsupported_policy": "Keep all 21 grids in each GDP/MINLP denominator; unsupported = infinite cost",
                "evaluation_metric": "First target-hit callback index, including initial/repeated callbacks; DFO only",
                "tts99_definition": "Median total completion over all 10 seeds times ceil(log(.01)/log(1-hits/10)); 0 hits => infinity; 10 hits => one run",
                "artifacts_sha256": {p.name: sha(p.read_bytes()) for p in sorted(artifacts)}}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if args.update_published:
        update_published_aliases(args.output)
    print(json.dumps({"runs": len(runs), "callbacks": len(charges), "output": str(args.output)}))


if __name__ == "__main__":
    main()
