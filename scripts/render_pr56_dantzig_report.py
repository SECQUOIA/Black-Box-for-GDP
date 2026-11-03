#!/usr/bin/env python3
"""Render the audited PR56 tables; reads data only, never runs experiments."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

METHODS = (
    "dsda",
    "rbfopt_msrsm_genetic",
    "bam",
    "fmqa_sa",
    "uniform_without_replacement",
    "nomad",
    "miso",
)
LABELS = ("D-SDA", "RBFOpt (genetic)", "BAM", "FMQA-SA", "Uniform", "NOMAD", "MISO")
COLORS = ("#666666", "#0072B2", "#E69F00", "#CC79A7", "#999933", "#009E73", "#D55E00")
CONDITIONS = (
    ("cstr_5", 8),
    ("cstr_10", 15),
    ("cstr_15", 22),
    ("cstr_20", 29),
    ("cstr_25", 36),
    ("cstr_30", 43),
    ("column", 13),
    ("small_batch", 10),
    ("dynamic", 12),
    ("dynamic", 15),
    ("dynamic", 20),
    ("dynamic", 30),
    ("dynamic", 37),
    ("dynamic", 50),
)


def case_label(case, budget):
    name = case.replace("cstr_", "CSTR ").replace("small_batch", "Small Batch")
    return f"{name.title() if case in ('column', 'dynamic') else name} (B={budget})"


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def table(headers, rows):
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *("| " + " | ".join(map(str, row)) + " |" for row in rows),
        ]
    )


def save_figure(fig, output, stem):
    fig.savefig(
        output / (stem + ".png"),
        dpi=180,
        facecolor="white",
        metadata={"Software": "PR56 audited-data renderer"},
    )
    fig.savefig(
        output / (stem + ".svg"),
        facecolor="white",
        metadata={"Date": None, "Creator": "PR56 audited-data renderer"},
    )
    plt.close(fig)


def render(folder):
    analysis = folder / "analysis"
    summary = json.loads((analysis / "summary.json").read_text())
    audit = json.loads((analysis / "validation.json").read_text())
    assert audit["validation_passed"]
    grid = {
        (int(r["budget"]), r["method"]): r
        for r in read_csv(analysis / "grid_budgets.csv")
    }
    process = {
        (r["case"], int(r["budget"]), r["method"]): r
        for r in read_csv(analysis / "process_conditions.csv")
    }
    overall = {(r["scope"], r["method"]): r for r in summary["overall_comparison"]}
    figures = folder / "figures"
    figures.mkdir(exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "svg.hashsalt": "pr56-c4d7db6b",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    budgets = [10, 30, 50, 70, 100]
    fig, ax = plt.subplots(figsize=(10, 6.4))
    for i, (method, label, color) in enumerate(zip(METHODS, LABELS, COLORS)):
        y = [int(grid[b, method]["hits"]) / 210 * 100 for b in budgets]
        ax.plot(
            budgets,
            y,
            label=label,
            color=color,
            marker=("o", "s", "^", "D", "v", "P", "X")[i],
            linewidth=2.4 if method in ("miso", "rbfopt_msrsm_genetic") else 1.6,
            linestyle="--" if method == "uniform_without_replacement" else "-",
        )
    ax.scatter(
        [100],
        [110 / 210 * 100],
        facecolors="white",
        edgecolors=COLORS[5],
        s=70,
        zorder=6,
    )
    ax.annotate(
        "NOMAD crash-as-miss sensitivity:\n110/210 at B=100",
        xy=(100, 110 / 210 * 100),
        xytext=(58, 31),
        fontsize=9,
        arrowprops={"arrowstyle": "->", "color": COLORS[5]},
        color=COLORS[5],
    )
    ax.set(
        xlim=(6, 104),
        ylim=(0, 100),
        xticks=budgets,
        xlabel="Evaluation budget B",
        ylabel="Target hits (%) — 210 runs per budget",
        title="Grid target attainment: completed Dantzig return and archived baselines",
    )
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="upper left", ncol=2, frameon=False, fontsize=9)
    fig.subplots_adjust(left=0.09, right=0.98, top=0.90, bottom=0.19)
    fig.text(
        0.09,
        0.055,
        "21 functions × 10 seeds per budget. NOMAD uses the frozen path-scoring policy; 21 terminal crashes at B=100.\n"
        "Historical baselines are unchanged; RBFOpt denotes the genetic-search primary implementation.\n"
        "These are observed hit rates, without a claim of statistical dominance. Stopping rules remain method-specific.",
        fontsize=8.5,
        color="#444444",
    )
    save_figure(fig, figures, "grid_target_hits")

    values = np.array(
        [[int(process[c, b, m]["hits"]) for m in METHODS] for c, b in CONDITIONS]
    )
    fig, ax = plt.subplots(figsize=(10, 8.4))
    im = ax.imshow(values, vmin=0, vmax=10, cmap="Blues", aspect="auto")
    ax.set_xticks(range(7), LABELS, rotation=24, ha="left")
    ax.tick_params(top=True, labeltop=True, bottom=False, labelbottom=False, length=0)
    ax.set_yticks(range(14), [case_label(c, b) for c, b in CONDITIONS])
    for i in range(14):
        for j in range(7):
            ax.text(
                j,
                i,
                str(values[i, j]),
                ha="center",
                va="center",
                color="white" if values[i, j] >= 6 else "#182B3A",
                fontsize=11,
            )
    for boundary in (5.5, 6.5, 7.5):
        ax.axhline(boundary, color="white", linewidth=2.4)
    ax.axvline(4.5, color="#D55E00", linewidth=2)
    fig.colorbar(
        im,
        ax=ax,
        fraction=0.035,
        pad=0.035,
        ticks=[0, 2, 4, 6, 8, 10],
        label="Target hits out of 10 paired seeds",
    )
    fig.subplots_adjust(left=0.23, right=0.92, top=0.83, bottom=0.13)
    fig.suptitle("Process target attainment by condition", y=0.98, fontsize=14)
    fig.text(
        0.23,
        0.045,
        "Five archived primary methods | NOMAD and MISO from the Dantzig return.\n"
        "Dynamic rows reuse seeds at different budgets; they are not independent replications.\n"
        "No condition-wise contrast survives Holm correction across the 70 exploratory paired tests.",
        fontsize=8.7,
        color="#444444",
    )
    save_figure(fig, figures, "process_target_hits")

    total_table = table(
        ["Method", "Grid hits / 1,050", "Process hits / 140"],
        [
            [
                label,
                f"{overall['grid', method]['hits']} ({overall['grid', method]['hits'] / 1050:.1%})",
                f"{overall['process', method]['hits']} ({overall['process', method]['hits'] / 140:.1%})",
            ]
            for method, label in zip(METHODS, LABELS)
        ],
    )
    grid_table = table(
        ["Budget", *LABELS],
        [[b, *(grid[b, m]["hits"] for m in METHODS)] for b in budgets],
    )
    process_table = table(
        ["Condition", *LABELS],
        [
            [case_label(c, b), *(process[c, b, m]["hits"] for m in METHODS)]
            for c, b in CONDITIONS
        ],
    )
    timing_table = table(
        [
            "Condition",
            "Method",
            "Hits / 10",
            "NLP-work equivalent, median",
            "Search s, median",
            "Reconstructed completion s, median [Q25, Q75]",
        ],
        [
            [
                case_label(c, b),
                LABELS[METHODS.index(m)],
                process[c, b, m]["hits"],
                f"{float(process[c, b, m]['nlp_solves_median']):g}",
                f"{float(process[c, b, m]['retained_search_s_median']):.3f}",
                f"{float(process[c, b, m]['completion_s_median']):.2f} [{float(process[c, b, m]['completion_s_q25']):.2f}, {float(process[c, b, m]['completion_s_q75']):.2f}]",
            ]
            for c, b in (("cstr_30", 43), ("column", 13), ("dynamic", 50))
            for m in ("dsda", "rbfopt_msrsm_genetic", "nomad", "miso")
        ],
    )
    dsda_table = table(
        [
            "Variant",
            "Hits / 140",
            "Callbacks",
            "Full-budget runs",
            "Completion s, median [Q25, Q75]",
        ],
        [
            [
                r["method"],
                r["hits"],
                r["callbacks"],
                r["full_budget_runs"],
                f"{r['completion_s_median']:.2f} [{r['completion_s_q25']:.2f}, {r['completion_s_q75']:.2f}]",
            ]
            for r in sorted(
                summary["dsda"]["variant_summaries"],
                key=lambda r: (
                    "dsda_single",
                    "dsda_ranked",
                    "dsda_ranked_random",
                ).index(r["method"]),
            )
        ],
    )
    report = f"""# PR #56: completed Dantzig experiments, 31 October 2026

Completed Dantzig results for [PR #56](https://github.com/SECQUOIA/Black-Box-for-GDP/pull/56), executed at revision `{summary["revision"]}`. This report adds analysis of the returned data; it does not alter the manuscript, optimizer implementations, targets, budgets, or native result statuses. No new optimization or NLP solves were performed for this analysis. [Manuscript review notes](MANUSCRIPT_REVIEW.md) identify the claims and figures that need revision.

## Findings

All **2,800 planned result records** are present: D-SDA 420, NOMAD 1,190, and MISO 1,190. Independent reconstruction from the per-run results and callbacks passes. There are no missing or duplicate jobs. The return is not an entirely crash-free campaign: 21 NOMAD jobs retain the terminal status `crashed_identical_reruns`.

MISO has the largest aggregate hit count in both suites, but its advantage over the primary RBFOpt configuration is modest in aggregate and varies by condition. It records 678 vs 658 Grid hits (+20; +1.9 percentage points) and 120 vs 114 Process hits (+6; +4.3 points). MISO is computationally more expensive in several conditions. These results require revising any general claim that RBFOpt has the largest hit count across the expanded comparison.

The five historical primary methods are retained without rerunning them. **RBFOpt means `rbfopt_msrsm_genetic`**, as in the manuscript's primary comparison. The solver-search RBFOpt and BAM prefix controls remain separate in [historical_control_runs.csv](analysis/historical_control_runs.csv); in particular, the older solver control has a different Column budget and must not be silently substituted into this comparison.

{total_table}

NOMAD's adopted score includes target hits observed before a reproducible terminal crash. If every terminal crash is instead counted as a miss, NOMAD has **510/1,050 Grid hits and 92/140 Process hits, 602/1,190 overall**, versus 618 under the frozen policy. This is a sensitivity analysis, not a change to the archived outcomes.

## Grid comparison

Each cell below is a target-hit count out of 210 (21 functions × ten seeds). The five budget cohorts together contain 1,050 jobs per method; repeated functions and seeds across budgets are not independent benchmark replications.

{grid_table}

![Grid target attainment](figures/grid_target_hits.png)

MISO leads at B=30, 70, and 100; RBFOpt leads at B=50, and BAM leads at B=10. At B=100, MISO reaches 181/210 (86.2%), RBFOpt 171/210 (81.4%), and NOMAD 126/210 (60.0%). All 21 terminal NOMAD crashes occur at B=100; 16 have already reached the target, so the crash-as-miss sensitivity is 110/210 (52.4%). The NOMAD timing summaries at this budget have **189 observations, not 210**. Their missingness is algorithm-dependent and not random.

## Process comparison

Each cell is the target-hit count out of the same ten paired seeds. There are 14 model–budget conditions and 140 jobs per method.

{process_table}

![Process target attainment](figures/process_target_hits.png)

MISO reaches 43/60 CSTR targets versus RBFOpt's 45/60: it improves to 30/30 over CSTR20–30, versus 24/30 for RBFOpt, but obtains only 13/30 on CSTR5–15 versus 21/30. MISO improves Column from 4/10 to 10/10 and Small Batch from 5/10 to 7/10 relative to RBFOpt. Both reach all 60 targets across the six Dynamic budgets. NOMAD improves on D-SDA overall (92 vs 74 hits), while remaining below RBFOpt (114).

If the manuscript's primary Process cohort is expanded to all seven methods, its counts become **980 runs, 21,777 callback visits, and 2,106 distinct model/size/coordinate keys**, compared with 700, 16,041, and 2,024 previously. The new methods add 5,736 callback visits and 82 previously unvisited keys. These totals count each selected job path once; native retries and the separate restart diagnostic are excluded. The full sealed inventory contains 2,438 configurations. See [combined_configuration_coverage.csv](analysis/combined_configuration_coverage.csv).

### Exploratory paired analysis

[process_pairs.csv](analysis/process_pairs.csv) contains the individual seed pairs. [process_paired_tests.csv](analysis/process_paired_tests.csv) reports exact two-sided McNemar tests for five contrasts across 14 conditions (70 tests): NOMAD–D-SDA, NOMAD–RBFOpt, MISO–D-SDA, MISO–RBFOpt, and MISO–NOMAD. Holm correction is applied across this stated exploratory family. **No contrast survives correction at 0.05.** For example, MISO–RBFOpt on Column has six MISO-only hits, no RBFOpt-only hits, raw p=0.03125, and adjusted p=1.0. Ten paired seeds provide limited power; lack of significance does not establish equivalence. This is an added exploratory analysis, not a preregistered experiment or a change to existing manuscript test families. Dynamic budget rows reuse seeds and cannot be treated as independent replications for a pooled significance claim.

## D-SDA restart diagnostic

All **140 single-descent paths exactly reproduce the archived baseline**: callback coordinates, evaluations, best objective, hit, first-hit index, and outcome category. All 280 restarted paths preserve the original descent prefix. No baseline was edited to force this agreement.

{dsda_table}

The server's `changed_outcomes=22` means **11 distinct condition–seed jobs improve their best objective under each of the two restart variants**. It does not mean 22 new target hits. All three variants remain at **74/140 hits**, and all 22 changed comparisons remain misses. The affected jobs are CSTR10/B15 seeds 5,6,7; CSTR15/B22 seed 8; CSTR20/B29 seeds 4,8; CSTR25/B36 seed 8; and CSTR30/B43 seeds 4,5,6,8. These are material incumbent improvements, not rounding noise. [dsda_changes.csv](analysis/dsda_changes.csv) preserves each before/after objective and target.

The ranked and ranked-plus-random variants spend 930 and 959 additional callback evaluations, respectively, without adding target hits. Thus the defensible wording is “restarts do not change target-hit outcomes,” not “restarts do not change the results.” The Dantzig timing records now replace the need for a pending timing experiment. The historical primary D-SDA timing table remains unchanged; the new replay timing is reported separately here.

## Native status and retry accounting

| Method | Normal first-attempt completion | Completion after verified rerun | Repeated identical terminal crash | Other terminal failure |
| --- | --- | --- | --- | --- |
| NOMAD | 1,046 | 123 | 21 | 0 |
| MISO | 1,190 | 0 | 0 | 0 |

NOMAD has 144 initially crashing jobs. Of these, 110 recover on the first extra attempt and 13 on the second; 21 crash on all three identical paths. There are **1,368 NOMAD native attempts and 199 crashing attempts**, which must not be confused with 1,190 distinct benchmark jobs or 21 terminal crashes. Every accepted rerun follows the initial crash's coordinate sequence exactly. The policy at the frozen revision uses the observed path for target scoring even when all reruns crash identically; that status is never relabeled as normal completion. The runner's `execution_failures=0` reflects its scoring categories, not absence of native crashes. `finished_with_issues` is consistent with these 21 preserved terminal crashes.

The 21 missing search/completion times remain null. For the 123 accepted reruns, timing uses the **selected rerun's callbacks**, not the initial crash's lookup times. Reported per-job search times exclude preceding failed attempts; total retry-inclusive per-job time cannot be recovered from the preserved records because original crash durations are not available. [native_attempts.csv](analysis/native_attempts.csv), [nomad_terminal_crashes.csv](analysis/nomad_terminal_crashes.csv), and the unmodified return preserve the evidence.

## Time and NLP-work interpretation

These are searches over **stored configuration responses**. No original GDP or NLP was solved in this campaign. The field named `nlp_solves` is a historical NLP-work equivalent inferred from the stored response status; it is not a count of new solves. The budget counts callbacks, including shared starts, repeated queries, rejected responses, and MISO's additional design points.

Reconstructed completion time is the retained measured search overhead, plus historical point costs charged on every callback, plus the stored preparation cost once. It estimates a fixed observed search path; it is neither fresh online NLP runtime nor time to first target. Quartiles use all available individual runs with inclusive linear interpolation. No mean or quartile is obtained by averaging bundle summaries. Unsuccessful runs are retained, and absent timing is not zero-filled.

{timing_table}

MISO's higher hit counts have a cost: at Dynamic/B50 it and RBFOpt both reach 10/10 targets, but their median reconstructed completion times are 195.36 s and 65.14 s. At CSTR30/B43, MISO improves 9/10 to 10/10 hits and reduces the median NLP-work equivalent from 31.5 to 29.5, while increasing median completion from 101.96 s to 107.33 s. At Grid/B100, MISO's median reconstructed completion is 94.82 s versus RBFOpt's 70.81 s. Avoid describing MISO as uniformly faster or RBFOpt as uniformly more successful.

Across the returned selected runs, MISO's retained measured search time sums to 19,006.88 s (all 1,190 jobs); NOMAD's sums to 2,698.53 s (1,169 timed jobs only). Summed bundle elapsed times, which include retry and runner overhead, are 19,080.59 s and 4,171.88 s. These are sums of worker durations and overlap in wall-clock time; neither is the campaign elapsed time. Historical and new timings should be interpreted under their recorded environments and nonexclusive server scheduling, rather than as perfectly controlled CPU benchmarks.

For **MISO Grid/B100 specifically, all 210 jobs use all 100 evaluations: 21,000 callbacks**. Its ten seed bundles run on up to five distinct physical cores within the six-worker queue. Each bundle takes 631.51–724.06 s (10.5–12.1 min); their elapsed times sum to 6,870.79 s (1 h 54 min 31 s). From the first bundle start at 17:40:23 UTC to the last finish at 18:12:19 UTC, the observed span is **31 min 56 s**. Retained selected-run search time sums to 6,858.14 s. Parallel execution explains the difference between the sum of bundle durations and the observed span. It does not by itself explain a prior estimate of “10+ hours”: even the observed sum is smaller than that estimate, and the estimate's configuration and measurement basis are not established by this return. No evaluations were omitted or budgets reduced to achieve the shorter runtime.

## Preserved protocol and validation

- Source revision, the input ZIP and 263 sealed package members, Grid point-cost table, initial points and order, seeds, domains, budgets, callback responses, failure penalties, target tolerances, and original result statuses all verify. The target rule is `abs(value-target) <= 1e-5 * max(1, abs(target))`.
- MISO retains integer DDS candidate generation, disabled continuous local search, and the Small Batch extra initial design. All extra design evaluations are charged within the original budget. No algorithm source or configuration was changed for this analysis.
- The frozen NOMAD retry/path-scoring policy is preserved. The crash-as-miss score is a separately labeled sensitivity calculation only.
- Historical Grid D-SDA has a target-based stop after its descent checkpoint. NOMAD and MISO do not receive the target as a stopping criterion. These method-specific stopping rules are preserved; a shared budget does not imply identical stopping behavior. Process D-SDA has no target stop.
- The outer ZIP SHA256 and CRC, all **11,229 internal inventory hashes**, source snapshots and context provenance pass. All 2,380 MI primary rows and 38 server condition summaries are recomputed and reconciled. D-SDA's 420 records are checked separately.
- All 66 MI bundles exit zero and cover the planned job set exactly once. Required native solver preflight tests were present: **12 passed, zero skipped**. Preflight records are excluded from all benchmark statistics.
- Six workers each have one CPU, with no shared physical cores, and all recorded OpenMP/BLAS limits are one. CPU affinity was observed; this was not an exclusive scheduler reservation.

## Execution and evidence

The server source was pinned to `{summary["revision"]}` under `/local/scratch/a/lee4382/repository/RBFopt_Test/pr56_dantzig_ready_20261031_c4d7db6b`. The returned output root is `revision_20261031_173911_c4d7db6b`. NOMAD used six bundles (five Grid budgets and one Process bundle); MISO used 60 (50 Grid budget/seed bundles and ten Process seed bundles). MISO groups contain 21 Grid jobs or 14 Process jobs. All use existing sealed job IDs.

| Logical CPU | Socket | Physical core | SMT sibling pair |
| --- | --- | --- | --- |
| 28 | 0 | 36 | 28, 76 |
| 17 | 0 | 21 | 17, 65 |
| 34 | 0 | 44 | 34, 82 |
| 44 | 0 | 58 | 44, 92 |
| 45 | 0 | 59 | 45, 93 |
| 24 | 0 | 32 | 24, 72 |

The launcher began at 17:39:11 UTC, experiments ended at 18:48:11 UTC, and collection finished at 18:48:23 UTC on 2026-10-31: **69 min 11.6 s from launch to collection**. Server versions were Python 3.11.16, PyNomadBBO 4.6.0, soogo 2.1.0, NumPy 2.4.6, pandas 2.3.3, SciPy 1.17.1, and pytest 9.1.1. Full runtime, command, PID, job-list, stdout/stderr, and preflight evidence remains inside the original ZIP.

Original return SHA256:

```text
{summary["archive_sha256"]}  RETURN.zip
```

The original [RETURN.zip](evidence/RETURN.zip) is retained byte-for-byte with [its sidecar](evidence/RETURN.zip.sha256). All new explanatory material is in English; the immutable ZIP retains legacy Korean comments in its historical input package. The historical context files in `evidence/` are copied from the frozen revision and verified by the analyzer. `executed_source_manifest.json` records source-file hashes; original publication and joint-comparison manifests record baseline provenance. Raw callback logs are kept in the ZIP without flattening retry directories or overwriting native statuses.

## Reproduction

From the repository root:

```bash
python scripts/analyze_pr56_dantzig_return.py \\
  --output results/pr56_dantzig_return_20261031/analysis
python scripts/render_pr56_dantzig_report.py \\
  --results results/pr56_dantzig_return_20261031
python -m pytest tests/test_pr56_dantzig_return.py -q -p no:cacheprovider
```

The analyzer uses only Python's standard library; rendering uses Matplotlib and NumPy, and the audit tests use pytest. These commands do not import optimizers, start experiments, or require a Dantzig connection. `analysis/REPRODUCTION.json` hashes the data inputs, analyzer, and numeric outputs. `REPORT_RENDER.json` records rendering versions, script hash, and report/figure hashes. The tests cover corrupted-input rejection, replay and retry accounting, null timing, primary/control separation, and multiple-comparison calculations.

The main reviewable tables are [overall_comparison.csv](analysis/overall_comparison.csv), [grid_budgets.csv](analysis/grid_budgets.csv), [process_conditions.csv](analysis/process_conditions.csv), [dsda_conditions.csv](analysis/dsda_conditions.csv), and [validation.json](analysis/validation.json). All are derived from individual records; the immutable evidence remains the authority. This result addition leaves the manuscript and optimizer implementations unchanged.
"""
    (folder / "README.md").write_text(report)
    artifacts = [
        folder / "README.md",
        *sorted(figures.glob("*.png")),
        *sorted(figures.glob("*.svg")),
    ]
    manifest = {
        "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "matplotlib": matplotlib.__version__,
        "numpy": np.__version__,
        "data_only": True,
        "outputs_sha256": {
            str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in artifacts
        },
    }
    (folder / "REPORT_RENDER.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"report": str(folder / "README.md"), "figures": 4}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    render(parser.parse_args().results)
