"""Paired FMQA-SA versus uniform analysis of frozen completed records; no solves."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import io
from pathlib import Path
import platform
import shlex
import subprocess
import sys

from .analysis import paired_interval
from .common import read, save, sha, writecsv


REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "results/review_comparison_20261020"
BASE_REVISION = "8eb6f310e4e462467596e28ffa37d6bcd83dacb2"
INPUT_MEMBER = "tables/completed_runs.csv"
METHODS = ("fmqa_sa", "uniform_without_replacement")
SEEDS = tuple(range(10))
GRID_CASES = tuple(
    sorted(
        (
            "ackley",
            "alpine1",
            "alpine2",
            "bohachevsky2",
            "camel3",
            "csendes",
            "deflected_corrugated_spring",
            "dropwave",
            "easom",
            "griewank",
            "holder_table",
            "hosaki",
            "levy",
            "levy13",
            "michalewicz",
            "rastrigin",
            "rosenbrock",
            "shubert",
            "styblinski_tang",
            "sum_of_squares",
            "xin_she_yang3",
        )
    )
)
GRID_BUDGETS = (10, 30, 50, 70, 100)
PROCESS_CONDITIONS = tuple(
    sorted(
        (
            ("cstr_5", 8),
            ("cstr_10", 15),
            ("cstr_15", 22),
            ("cstr_20", 29),
            ("cstr_25", 36),
            ("cstr_30", 43),
            ("column", 16),
            ("small_batch", 10),
            *(("dynamic", b) for b in (12, 15, 20, 30, 37, 50)),
        )
    )
)
BOOTSTRAP_SEED = 20261020
REPLICATIONS = 2000
DIRECTION = "fmqa_sa - uniform_without_replacement"
LIMITATIONS = (
    "Exploratory descriptive percentile interval; no equivalence test, "
    "multiplicity correction or general superiority claim; only ten seeds per "
    "condition; boundary intervals may degenerate; no pooled Process inference."
)


def pair_runs(rows):
    """Require every planned condition and both methods' exact seed set."""
    expected = {
        ("grid", case, budget, seed)
        for case in GRID_CASES
        for budget in GRID_BUDGETS
        for seed in SEEDS
    } | {
        ("process", case, budget, seed)
        for case, budget in PROCESS_CONDITIONS
        for seed in SEEDS
    }
    selected = {method: {} for method in METHODS}
    for line, row in enumerate(rows, start=2):
        method = row.get("method")
        if method not in selected:
            continue
        try:
            key = (row["scope"], row["case"], int(row["budget"]), int(row["seed"]))
            category = row["category"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid pairing key/category on input row {line}: {row}"
            ) from exc
        if key not in expected:
            raise ValueError(
                f"Unexpected condition or seed for {method} on row {line}: {key}"
            )
        if key in selected[method]:
            raise ValueError(f"Duplicate pairing key for {method} on row {line}: {key}")
        if category not in {"target_reached", "target_not_reached", "execution_failed"}:
            raise ValueError(
                f"Incomplete or unknown category for {method} {key}: {category!r}"
            )
        selected[method][key] = category
    for method in METHODS:
        missing = sorted(expected - selected[method].keys())
        if missing:
            raise ValueError(
                f"Missing {len(missing)} pairing keys for {method}: {missing}"
            )
    pairs = []
    for key in sorted(expected):
        fmqa, uniform = (selected[method][key] for method in METHODS)
        a, b = fmqa == "target_reached", uniform == "target_reached"
        pairs.append(
            dict(zip(("scope", "case", "budget", "seed"), key))
            | {
                "fmqa_category": fmqa,
                "uniform_category": uniform,
                "fmqa_success": a,
                "uniform_success": b,
                "success_difference": int(a) - int(b),
            }
        )
    return pairs


def outcome_counts(pairs):
    """Keep execution failures in the non-success outcomes and denominator."""
    outcomes = Counter((p["fmqa_success"], p["uniform_success"]) for p in pairs)
    n = len(pairs)
    a = sum(p["fmqa_success"] for p in pairs)
    b = sum(p["uniform_success"] for p in pairs)
    return {
        "pairs": n,
        "fmqa_target_reached": a,
        "uniform_target_reached": b,
        "fmqa_success_rate": a / n,
        "uniform_success_rate": b / n,
        "both_success": outcomes[True, True],
        "fmqa_only_success": outcomes[True, False],
        "uniform_only_success": outcomes[False, True],
        "neither_success": outcomes[False, False],
        "fmqa_execution_failed": sum(
            p["fmqa_category"] == "execution_failed" for p in pairs
        ),
        "uniform_execution_failed": sum(
            p["uniform_category"] == "execution_failed" for p in pairs
        ),
        "mean_paired_success_difference": sum(p["success_difference"] for p in pairs)
        / n,
    }


def summarize_pairs(pairs):
    """Input comes from pair_runs; retain function vectors and separate conditions."""
    grouped = defaultdict(list)
    for p in pairs:
        key = (
            ("grid", "all_functions", p["budget"])
            if p["scope"] == "grid"
            else ("process", p["case"], p["budget"])
        )
        grouped[key].append(p)
    summaries = []
    for (scope, case, budget), records in sorted(grouped.items()):
        records.sort(key=lambda p: (p["case"], p["seed"]))
        vectors = defaultdict(list)
        for p in records:
            vectors[p["case"]].append(p["success_difference"])
        groups = [vectors[c] for c in sorted(vectors)]
        lo, hi = paired_interval(
            groups,
            seed=BOOTSTRAP_SEED,
            replications=REPLICATIONS,
            clustered=scope == "grid",
        )
        summaries.append(
            {
                "scope": scope,
                "case": case,
                "budget": budget,
                "direction": DIRECTION,
                **outcome_counts(records),
                "expected_pairs": len(vectors) * len(SEEDS),
                "complete": True,
                "conditions": len(vectors),
                "seeds_per_condition": len(SEEDS),
                "seed_set": "0,1,2,3,4,5,6,7,8,9",
                "missing_pairs": 0,
                "duplicate_pairs": 0,
                "descriptive_95_low": lo,
                "descriptive_95_high": hi,
                "bootstrap_unit": "function_with_ten_paired_seeds"
                if scope == "grid"
                else "paired_seed",
                "bootstrap_seed": BOOTSTRAP_SEED,
                "bootstrap_replications": REPLICATIONS,
                "interval_method": "analysis.paired_interval; sorted draws at indices 50 and 1950",
                "interpretation": LIMITATIONS,
            }
        )
    return summaries


def _git(*args):
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO), *args], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _path(path):
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def report(summaries, process_total, input_sha, provider):
    """One sentence per prose line; table values are calculated from paired records."""
    lines = [
        "# FMQA-SA versus uniform sampling: paired target attainment",
        "",
        "This is a follow-up statistical analysis of completed runs, with no optimization or NLP evaluations.",
        "The original return archive, execution logs, analysis tables and audit remain unchanged.",
        "",
        "## Inputs and pairing",
        "",
        f"The input is `results/review_comparison_20261020/{INPUT_MEMBER}` with SHA256 `{input_sha}`.",
        "The CLI verifies the input against `results/review_comparison_20261020/manifest.json` before reading its records.",
        f"The review baseline is `{BASE_REVISION}` and the historical execution provider remains `{provider}`.",
        "The paired methods are `fmqa_sa` and `uniform_without_replacement`, joined by `(scope, case, budget, seed)`.",
        "Every planned condition must have exactly seeds 0–9 for both methods, and missing, duplicate or unexpected keys stop the analysis.",
        "There are 1,050 Grid pairs and 140 Process pairs, with no incomplete pairs omitted.",
        "Success is the retained `category == target_reached`, and all other completed categories remain in the denominator.",
        "`paired_runs.csv` retains both original categories, both success indicators and their difference of −1, 0 or +1.",
        "The difference is always FMQA-SA minus uniform, so a positive difference favors FMQA-SA on target attainment.",
        "",
        "## Bootstrap and ordering",
        "",
        "The unmodified `review_comparison.analysis.paired_interval` uses seed 20261020 and 2,000 replicates for every summary.",
        "Grid resamples 21 whole function vectors with replacement separately at each budget, preserving all ten paired seeds inside each vector.",
        "The 210 runs at one budget are not treated as independent repetitions of the same problem.",
        "Process resamples ten paired seeds separately within each of the 14 model–budget conditions.",
        "The six Dynamic budgets are not pooled as independent problems, and the Process total below is descriptive only.",
        "Pair rows sort lexicographically by scope and case, then numerically by budget and seed.",
        "Bootstrap input vectors sort lexicographically by function name and numerically by seed, independently of CSV input order.",
        "Summary rows list the five Grid budgets in ascending order, followed by Process case names in lexical order and budgets in ascending order.",
        "Each interval uses the sorted replicate values at zero-based indices 50 and 1950, matching the existing helper.",
        "These are exploratory, descriptive percentile intervals, without equivalence testing or multiple-comparison correction.",
        "Ten seeds and boundary outcomes can produce degenerate intervals, and these comparisons do not establish general superiority.",
        "",
        "## Results",
        "",
        "Differences and interval endpoints below are percentage points, while the CSV stores proportions.",
        "",
        "| Scope | Case | Budget | Pairs | FMQA hits | Uniform hits | Difference (pp) | Descriptive 95% interval (pp) |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in summaries:
        lines.append(
            f"| {r['scope']} | {r['case']} | {r['budget']} | {r['pairs']} | "
            f"{r['fmqa_target_reached']} | {r['uniform_target_reached']} | "
            f"{100 * r['mean_paired_success_difference']:+.2f} | "
            f"[{100 * r['descriptive_95_low']:+.2f}, {100 * r['descriptive_95_high']:+.2f}] |"
        )
    lines += [
        "",
        f"The descriptive Process total is FMQA-SA {process_total['fmqa_target_reached']}/{process_total['pairs']} versus uniform {process_total['uniform_target_reached']}/{process_total['pairs']}, a difference of {100 * process_total['mean_paired_success_difference']:+.2f} percentage points.",
        "No pooled Process interval is calculated.",
        "The Grid point estimates favor FMQA-SA at all five budgets, with larger observed differences at higher budgets.",
        "The Grid B10 interval includes zero, while the intervals for B30 through B100 lie above zero under this descriptive procedure.",
        "Process differences vary by condition, including ties and conditions favoring uniform.",
        "The four joint outcomes in `paired_success.csv` distinguish agreement from discordant seeds even when marginal hit counts match.",
        "This comparison cannot separate the causal contributions of FMQA learning, fitted weights, QUBO conversion, annealing or fallback.",
        "The separate [limited FMQA diagnostic](../../review_diagnostics_20261020/README.md) verifies seven reconstructed fits; historical fitted weights remain unavailable.",
        "The later [CSTR15 follow-up](../../review_feasibility_tautology_20261020/summary.json), retained in commit `854a1a7fc5a20a5489d82ef7991a16aaf89025f3`, passed the `1e-8` numerical feasibility check on the original GDP with objective `2.8293940632857546` and maximum unscaled violation `3.3306690738754696e-16`.",
        "The recorded A12 lower-bound discrepancy persists, with a difference of `0.6931579445174396`.",
        "This is numerical evidence for the retained point, not a proof of exact mathematical feasibility, global optimality or a solver defect.",
        "Earlier option errors and the no-solution `TOO_FEW_DOF` follow-up remain historical records; this status correction does not synchronize manuscript files or change these paired counts.",
        "The original manifests retain their historical hashes; [status_correction.json](../status_correction.json) separately records the documentation-only updates and preserved evidence.",
        "",
        "## Reproduce locally or on Dantzig",
        "",
        "Run from this repository checkout using Python 3.10 or newer with only the standard library.",
        "The output directory must not exist, so the command cannot overwrite retained results.",
        "",
        "```bash",
        'ANALYSIS_PARENT=$(mktemp -d "${TMPDIR:-/tmp}/fmqa-uniform.XXXXXX")',
        "python -m review_comparison.fmqa_uniform \\",
        "  --input results/review_comparison_20261020/tables/completed_runs.csv \\",
        "  --manifest results/review_comparison_20261020/manifest.json \\",
        '  --output "$ANALYSIS_PARENT/fmqa_uniform"',
        "```",
        "",
        "Outputs are `paired_runs.csv`, `paired_success.csv` (19 rows), this README and a separate provenance `manifest.json`.",
        "The manifest records input, source and output SHA256 values, execution environment, bootstrap settings and the descriptive Process total.",
        "The source SHA256 values identify the exact analysis code, while the generation HEAD and historical execution revision have distinct meanings.",
        "CSV bytes are deterministic, whereas the manifest also records the actual generation time, environment and paths.",
        "",
        "## Validation commands",
        "",
        "The regression tests exercise invalid pairing, outcome signs, all four joint outcomes, function grouping and separate Process conditions.",
        "The published manifest also records completed validation checks and the test log hash, which are not recreated by running the analysis alone.",
        "Run the existing archive audit into a fresh directory to verify the retained analysis independently.",
        "",
        "```bash",
        "python -m pytest -q tests/test_review_comparison_fmqa_uniform.py tests/test_review_comparison.py tests/test_review_comparison_audit.py tests/test_final_process_artifacts.py",
        'python -m review_comparison.audit --output "$ANALYSIS_PARENT/original_audit"',
        "```",
        "",
    ]
    return "\n".join(lines)


def run(input_path, output, manifest_path):
    input_path, output, manifest_path = (
        Path(p).resolve() for p in (input_path, output, manifest_path)
    )
    if output.exists():
        raise FileExistsError(f"Output directory already exists: {output}")
    manifest = read(manifest_path)
    data = input_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    expected = manifest["published_files_sha256"][INPUT_MEMBER]
    if digest != expected:
        raise ValueError(
            f"Input SHA256 mismatch: {input_path}; expected {expected}, got {digest}"
        )
    for name in ("review_comparison/analysis.py", "review_comparison/common.py"):
        if sha(REPO / name) != manifest["analysis_sources_sha256"][name]:
            raise ValueError(
                f"Frozen analysis source differs from original manifest: {name}"
            )
    pairs = pair_runs(csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")))
    summaries = summarize_pairs(pairs)
    total = outcome_counts([p for p in pairs if p["scope"] == "process"])
    output.mkdir(parents=True, exist_ok=False)
    writecsv(output / "paired_runs.csv", pairs)
    writecsv(output / "paired_success.csv", summaries)
    provider = manifest["execution_provider_revision"]
    (output / "README.md").write_text(
        report(summaries, total, digest, provider), encoding="utf-8"
    )
    source_names = (
        "review_comparison/fmqa_uniform.py",
        "review_comparison/analysis.py",
        "review_comparison/common.py",
    )
    command = shlex.join(
        [
            "python",
            "-m",
            "review_comparison.fmqa_uniform",
            "--input",
            _path(input_path),
            "--manifest",
            _path(manifest_path),
            "--output",
            "<new-output-directory>",
        ]
    )
    save(
        output / "manifest.json",
        {
            "schema": 1,
            "analysis_kind": "Follow-up analysis of completed records; no optimization or NLP evaluation",
            "baseline_revision": BASE_REVISION,
            "repository_head_at_generation": _git("rev-parse", "HEAD"),
            "analysis_source_worktree_status": _git(
                "status", "--porcelain", "--", *source_names
            ),
            "publication_revision": "Use the commit containing these files; exact source hashes below identify the analysis.",
            "execution_provider_revision": provider,
            "original_manifest": {
                "path": _path(manifest_path),
                "sha256": sha(manifest_path),
            },
            "input": {
                "path": _path(input_path),
                "sha256": digest,
                "original_manifest_member": INPUT_MEMBER,
            },
            "analysis_sources_sha256": {
                name: sha(REPO / name) for name in source_names
            },
            "outputs_sha256": {
                name: sha(output / name)
                for name in ("paired_runs.csv", "paired_success.csv", "README.md")
            },
            "pairing": {
                "key": ["scope", "case", "budget", "seed"],
                "methods": list(METHODS),
                "success": 'category == "target_reached"',
                "direction": DIRECTION,
                "pairs": len(pairs),
                "grid_pairs": sum(p["scope"] == "grid" for p in pairs),
                "process_pairs": total["pairs"],
                "summary_rows": len(summaries),
                "complete": True,
                "grid_cases": GRID_CASES,
                "grid_budgets": GRID_BUDGETS,
                "process_conditions": PROCESS_CONDITIONS,
                "seeds_per_condition": SEEDS,
                "row_order": "scope, case (lexical), budget (numeric), seed (numeric)",
            },
            "bootstrap": {
                "function": "review_comparison.analysis.paired_interval",
                "seed": BOOTSTRAP_SEED,
                "replications": REPLICATIONS,
                "interval": "descriptive percentile 95%; indices 50, 1950",
                "grid_unit": "whole function vector of ten paired seeds, clustered=True",
                "process_unit": "paired seed within one model-budget condition, clustered=False",
                "input_order": "functions lexical, seeds numeric; new RNG per summary",
                "limitations": LIMITATIONS,
            },
            "process_total_descriptive_only": total,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "environment": {
                "python": sys.version,
                "implementation": platform.python_implementation(),
                "executable": sys.executable,
                "platform": platform.platform(),
                "dependencies": "Python standard library only",
            },
            "reproduce": command,
        },
    )
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=RESULTS / INPUT_MEMBER)
    parser.add_argument("--manifest", type=Path, default=RESULTS / "manifest.json")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New directory; existing outputs refused",
    )
    args = parser.parse_args()
    print(run(args.input, args.output, args.manifest))


if __name__ == "__main__":
    main()
