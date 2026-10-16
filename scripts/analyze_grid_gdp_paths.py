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
    "fmqa_sa": "fmqa_qhd_20261012_034123_8kcczd4b.zip",
}
BAM_HASH = "bd4d9bf56deafa864ecdd2e676fc24bd25a6037bdb02a772ebd800eb1a935374"
TOL = 1e-5
TTS_MARKERS = dict(zip(BUDGETS, ("o", "s", "D", "^", "P")))
TTS_INFINITE_COUNTS = dict(zip(METHODS, (
    (17, 4, 4, 4, 4), (7, 2, 0, 0, 0), (9, 7, 4, 3, 2), (15, 6, 2, 1, 0))))


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
        if method == "fmqa_sa" and spec["case_name"] != "grid":
            continue
        directory = n.removesuffix("result.json")
        if method == "fmqa_sa":
            trace_name = directory + "evaluations.jsonl"
            entries = [json.loads(line) for line in data[trace_name].splitlines()]
            require(spec["surrogate_backend"] == "pytorch_qhd_data", "Default FMQA must use QHD")
            require(sha(data[trace_name]) == result["trace"]["sha256"], "QHD trace seal")
            require(entries[0]["run_key"] == spec and entries[-1]["result_record"] == result["result_record"], "QHD trace identity")
            events = [e for e in entries if e["event"] == "evaluation"]
            record = result["result_record"]
            wall, lookup = record["wall_time_s"], result["fmqa_state"]["objective_wall_s"]
        else:
            trace_name = directory + result["trace"]["path"]
            require(sha(data[trace_name]) == result["trace"]["sha256"], "Trace seal")
            entries = [json.loads(line) for line in data[trace_name].splitlines()]
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


def load_tts99_groups(path):
    """Read the 420 published values verbatim; only subgroup medians are derived."""
    rows = read_table(path)
    names = {r["grid_name"] for r in rows}
    keys = [(r["grid_name"], r["method"], int(r["max_evals"])) for r in rows]
    expected = {(name, method, budget) for name in names for method in METHODS for budget in BUDGETS}
    require(len(names) == 21 and len(rows) == len(set(keys)) == 420 and set(keys) == expected,
            "TTS99 requires 420 unique combinations: 21 grids x 4 methods x 5 budgets")
    values = {key: float(row["tts99_s"]) for key, row in zip(keys, rows)}
    require(all(v > 0 and (math.isfinite(v) or v == math.inf) for v in values.values()),
            "TTS99 values must be positive finite seconds or positive infinity")
    groups = []
    for method in METHODS:
        for index, budget in enumerate(BUDGETS):
            group = [values[name, method, budget] for name in sorted(names)]
            infinite = sum(v == math.inf for v in group)
            require(infinite == TTS_INFINITE_COUNTS[method][index],
                    f"Unexpected infinite TTS99 count for {method}, B={budget}: {infinite}")
            groups.append({"method": method, "budget": budget, "grids": sorted(names),
                           "values": group, "infinite": infinite, "median": statistics.median(group)})
    return groups


def plot_tts99(groups):
    """One shared log axis; infinities are annotations, never finite observations."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import LogLocator, NullFormatter

    names = groups[0]["grids"]
    # Stable, evenly spread offsets keyed by grid, independent of CSV row order.
    ordering = sorted(names, key=lambda name: sha(name.encode()))
    jitter = {name: -.21 + .42 * rank / (len(names) - 1) for rank, name in enumerate(ordering)}
    finite = [v for group in groups for v in group["values"] if math.isfinite(v)]
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#555555", "axes.linewidth": .7}):
        fig, ax = plt.subplots(figsize=(9, 4.7))
        fig.subplots_adjust(left=.085, right=.985, bottom=.21, top=.82)
        positions = []
        for group in groups:
            method, budget = group["method"], group["budget"]
            x = 6 * METHODS.index(method) + BUDGETS.index(budget)
            positions.append(x)
            points = [(name, value) for name, value in zip(group["grids"], group["values"])
                      if math.isfinite(value)]
            collection = ax.scatter([x + jitter[name] for name, _ in points], [v for _, v in points],
                                   marker=TTS_MARKERS[budget], color=COLORS[method], s=23,
                                   alpha=.78, edgecolors="none", zorder=3)
            collection.set_gid(f"tts99-points-{method}-{budget}")
            if math.isfinite(group["median"]):
                line = ax.hlines(group["median"], x - .31, x + .31, colors="black", linewidth=1.5, zorder=4)
                line.set_gid(f"tts99-median-{method}-{budget}")
            else:
                label = ax.text(x, 1.125, "median = ∞", transform=ax.get_xaxis_transform(),
                                ha="center", va="bottom", fontsize=8, clip_on=False)
                label.set_gid(f"tts99-infinite-median-{method}-{budget}")
            count = ax.text(x, 1.035, f"∞×{group['infinite']}", transform=ax.get_xaxis_transform(),
                            ha="center", va="bottom", fontsize=8.5, color=COLORS[method], clip_on=False)
            count.set_gid(f"tts99-infinity-{method}-{budget}")
        ax.set(yscale="log", ylim=(min(finite) / 1.6, 10 ** math.ceil(math.log10(max(finite)))),
               xlim=(-.65, 22.65), ylabel="Estimated TTS99 (s, log scale)")
        ax.yaxis.label.set_fontsize(10)
        ax.yaxis.set_major_locator(LogLocator(base=10))
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set_xticks(positions, [str(b) for _ in METHODS for b in BUDGETS])
        # Keep budget labels entirely below the spine, with method labels below them.
        ax.tick_params(axis="x", length=0, pad=10, labelsize=9)
        ax.tick_params(axis="y", which="both", labelsize=9)
        ax.grid(axis="y", which="major", color="#dce1e5", linewidth=.6)
        ax.set_axisbelow(True)
        for index, method in enumerate(METHODS):
            label = ax.text(index * 6 + 2, -.18, "BAM" if method == "bam" else LABELS[method],
                            transform=ax.get_xaxis_transform(), ha="center", va="top",
                            fontsize=11, fontweight="semibold", color=COLORS[method], clip_on=False)
            label.set_gid(f"tts99-method-{method}")
        handles = [Line2D([], [], color="#555555", marker=TTS_MARKERS[b], linestyle="none",
                          markersize=5.5, markeredgewidth=0, label=f"B={b}") for b in BUDGETS]
        handles.append(Line2D([], [], color="black", linewidth=1.5, label="Median"))
        fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.53, .995), ncol=6,
                   frameon=False, fontsize=9, handlelength=1.5, columnspacing=1.5, handletextpad=.5)
    return fig


def render_tts99(output):
    """Render only TTS99 from the existing CSV; do not run cost/summary analysis."""
    import matplotlib.pyplot as plt
    source = output / "tts99_summary.csv"
    digest = sha(source.read_bytes())
    groups = load_tts99_groups(source)
    fig = plot_tts99(groups)
    try:
        with plt.rc_context({"pdf.fonttype": 42}):
            fig.savefig(output / "tts99.png", dpi=600, facecolor="white")
            fig.savefig(output / "tts99.pdf", facecolor="white",
                        metadata={"CreationDate": None, "ModDate": None, "Title": None})
    finally:
        plt.close(fig)
    require(sha(source.read_bytes()) == digest, "TTS99 source CSV changed while plotting")
    return {"source": source.name, "source_sha256": digest,
            "plotting_script_sha256": sha(Path(__file__).read_bytes()),
            "layout": "one log axis; method groups with adjacent budget columns; no title or narrative",
            "methods": list(METHODS), "budgets": list(BUDGETS),
            "budget_markers": {str(b): marker for b, marker in TTS_MARKERS.items()},
            "observations": 420, "finite_observations": sum(math.isfinite(v) for g in groups for v in g["values"]),
            "infinite_counts": {m: list(TTS_INFINITE_COUNTS[m]) for m in METHODS},
            "median": "Separate extended-real median of all 21 values in each method-budget subgroup",
            "jitter": "Small fixed offsets by SHA256-sorted grid name; identical across subgroups",
            "png_dpi": 600, "pdf_fonttype": 42}


def regenerate_tts99(output, *, update_published=False):
    path = output / "manifest.json"
    manifest = json.loads(path.read_text())
    for name, digest in manifest["artifacts_sha256"].items():
        require(sha((output / name).read_bytes()) == digest, f"Published artifact changed: {name}")
    # Preserve analysis_sha256: it identifies the unchanged numerical analysis.
    # Record this figure-only renderer's source hash separately.
    manifest["tts99_figure"] = render_tts99(output)
    for ext in ("png", "pdf"):
        name = f"tts99.{ext}"
        manifest["artifacts_sha256"][name] = sha((output / name).read_bytes())
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    if update_published:
        update_published_aliases(output, tts99_only=True)
    print(json.dumps({"output": str(output), "figure_only": "tts99", "observations": 420,
                      "scientific_data_recomputed": False}))


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
        save(fig, name)
    render_tts99(output)
    figures.append("tts99")

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
    fig.legend(handles=[Patch(facecolor=c, label=label) for c, label in zip(palette, (
        "Target reached", "Target not reached", "Unsupported"))],
        loc="upper center", bbox_to_anchor=(.5, .955), frameon=False, ncol=3)
    fig.text(.04, .066, "Cell values: measured completion time (s). T: time limit; *: corrected Pyomo profile.", fontsize=10)
    fig.text(.04, .040, "Colors show target attainment within 1e-5 of the CSV minimum, not an optimality certificate.", fontsize=9)
    save(fig, "gdp_minlp_comparison")
    return figures


def update_published_aliases(output, *, tts99_only=False):
    """Keep existing user-facing Grid figure links pointing to the new analysis."""
    legacy = RESULTS / "fmqa_20260925/analysis/grid"
    mapping = {
        "tts99_comparison": "tts99",
        "evaluation_performance_profiles": "evaluation_profiles",
        "timing/time_performance_profiles": "performance_profiles",
        "timing/completion_time_profiles": "performance_profiles",
    }
    if tts99_only:
        mapping = {"tts99_comparison": "tts99"}
        aliases = json.loads((legacy / "grid_gdp_figures.manifest.json").read_text())["aliases"]
        require((legacy / "tts99_summary.csv").read_bytes() == (output / "tts99_summary.csv").read_bytes(),
                "Figure-only update cannot replace a different alias summary CSV")
    else:
        aliases = {}
    for target, source in mapping.items():
        for ext in ("png", "pdf"):
            data = (output / f"{source}.{ext}").read_bytes()
            path = legacy / f"{target}.{ext}"
            path.write_bytes(data)
            aliases[str(path.relative_to(ROOT))] = {"source": str((output / f"{source}.{ext}").relative_to(ROOT)),
                                                    "sha256": sha(data)}
    if not tts99_only:
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
    if tts99_only:
        return
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
    parser.add_argument("--tts99-only", action="store_true",
                        help="Redraw only TTS99 from the existing summary CSV; never recalculate data")
    parser.add_argument("--update-published", action="store_true", help="Update existing Grid figure links after generation")
    args = parser.parse_args(argv)
    require(not (args.no_figures and args.update_published), "Cannot publish aliases without regenerated figures")
    require(not (args.no_figures and args.tts99_only), "--tts99-only cannot be combined with --no-figures")
    if args.tts99_only:
        regenerate_tts99(args.output, update_published=args.update_published)
        return
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
                "fmqa_backend": "pytorch_qhd_data",
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
