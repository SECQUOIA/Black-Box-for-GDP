# FMQA-SA versus uniform sampling: paired target attainment

This is a follow-up statistical analysis of completed runs, with no optimization or NLP evaluations.
The original return archive, execution logs, analysis tables and audit remain unchanged.

## Inputs and pairing

The input is `results/review_comparison_20261020/tables/completed_runs.csv` with SHA256 `f0764696a4846d391e8d040781e8e32bde72829654e13ca6c1342cf768d1843f`.
The CLI verifies the input against `results/review_comparison_20261020/manifest.json` before reading its records.
The review baseline is `8eb6f310e4e462467596e28ffa37d6bcd83dacb2` and the historical execution provider remains `38d917ef75ef6767c2a9f238d88be19bf0b89160`.
The paired methods are `fmqa_sa` and `uniform_without_replacement`, joined by `(scope, case, budget, seed)`.
Every planned condition must have exactly seeds 0–9 for both methods, and missing, duplicate or unexpected keys stop the analysis.
There are 1,050 Grid pairs and 140 Process pairs, with no incomplete pairs omitted.
Success is the retained `category == target_reached`, and all other completed categories remain in the denominator.
`paired_runs.csv` retains both original categories, both success indicators and their difference of −1, 0 or +1.
The difference is always FMQA-SA minus uniform, so a positive difference favors FMQA-SA on target attainment.

## Bootstrap and ordering

The unmodified `review_comparison.analysis.paired_interval` uses seed 20261020 and 2,000 replicates for every summary.
Grid resamples 21 whole function vectors with replacement separately at each budget, preserving all ten paired seeds inside each vector.
The 210 runs at one budget are not treated as independent repetitions of the same problem.
Process resamples ten paired seeds separately within each of the 14 model–budget conditions.
The six Dynamic budgets are not pooled as independent problems, and the Process total below is descriptive only.
Pair rows sort lexicographically by scope and case, then numerically by budget and seed.
Bootstrap input vectors sort lexicographically by function name and numerically by seed, independently of CSV input order.
Summary rows list the five Grid budgets in ascending order, followed by Process case names in lexical order and budgets in ascending order.
Each interval uses the sorted replicate values at zero-based indices 50 and 1950, matching the existing helper.
These are exploratory, descriptive percentile intervals, without equivalence testing or multiple-comparison correction.
Ten seeds and boundary outcomes can produce degenerate intervals, and these comparisons do not establish general superiority.

## Results

Differences and interval endpoints below are percentage points, while the CSV stores proportions.

| Scope | Case | Budget | Pairs | FMQA hits | Uniform hits | Difference (pp) | Descriptive 95% interval (pp) |
|---|---|---:|---:|---:|---:|---:|---|
| grid | all_functions | 10 | 210 | 16 | 14 | +0.95 | [-0.95, +2.86] |
| grid | all_functions | 30 | 210 | 47 | 25 | +10.48 | [+4.29, +16.19] |
| grid | all_functions | 50 | 210 | 76 | 29 | +22.38 | [+14.76, +30.00] |
| grid | all_functions | 70 | 210 | 102 | 36 | +31.43 | [+22.38, +40.00] |
| grid | all_functions | 100 | 210 | 129 | 45 | +40.00 | [+28.57, +52.38] |
| process | column | 16 | 10 | 4 | 0 | +40.00 | [+10.00, +70.00] |
| process | cstr_10 | 15 | 10 | 2 | 1 | +10.00 | [+0.00, +30.00] |
| process | cstr_15 | 22 | 10 | 1 | 2 | -10.00 | [-30.00, +0.00] |
| process | cstr_20 | 29 | 10 | 1 | 2 | -10.00 | [-30.00, +0.00] |
| process | cstr_25 | 36 | 10 | 1 | 1 | +0.00 | [+0.00, +0.00] |
| process | cstr_30 | 43 | 10 | 1 | 1 | +0.00 | [+0.00, +0.00] |
| process | cstr_5 | 8 | 10 | 3 | 4 | -10.00 | [-40.00, +20.00] |
| process | dynamic | 12 | 10 | 2 | 0 | +20.00 | [+0.00, +50.00] |
| process | dynamic | 15 | 10 | 3 | 3 | +0.00 | [-40.00, +40.00] |
| process | dynamic | 20 | 10 | 3 | 3 | +0.00 | [-40.00, +40.00] |
| process | dynamic | 30 | 10 | 4 | 4 | +0.00 | [-30.00, +30.00] |
| process | dynamic | 37 | 10 | 5 | 5 | +0.00 | [-40.00, +40.00] |
| process | dynamic | 50 | 10 | 6 | 6 | +0.00 | [-40.00, +40.00] |
| process | small_batch | 10 | 10 | 6 | 4 | +20.00 | [-30.00, +60.00] |

The descriptive Process total is FMQA-SA 42/140 versus uniform 36/140, a difference of +4.29 percentage points.
No pooled Process interval is calculated.
The Grid point estimates favor FMQA-SA at all five budgets, with larger observed differences at higher budgets.
The Grid B10 interval includes zero, while the intervals for B30 through B100 lie above zero under this descriptive procedure.
Process differences vary by condition, including ties and conditions favoring uniform.
The four joint outcomes in `paired_success.csv` distinguish agreement from discordant seeds even when marginal hit counts match.
This comparison cannot separate the causal contributions of FMQA learning, fitted weights, QUBO conversion, annealing or fallback.
The separate [limited FMQA diagnostic](../../review_diagnostics_20261020/README.md) verifies seven reconstructed fits; historical fitted weights remain unavailable.
The later [CSTR15 follow-up](../../review_feasibility_tautology_20261020/summary.json), retained in commit `854a1a7fc5a20a5489d82ef7991a16aaf89025f3`, passed the `1e-8` numerical feasibility check on the original GDP with objective `2.8293940632857546` and maximum unscaled violation `3.3306690738754696e-16`.
The recorded A12 lower-bound discrepancy persists, with a difference of `0.6931579445174396`.
This is numerical evidence for the retained point, not a proof of exact mathematical feasibility, global optimality or a solver defect.
Earlier option errors and the no-solution `TOO_FEW_DOF` follow-up remain historical records; this status correction does not synchronize manuscript files or change these paired counts.
The original manifests retain their historical hashes; [status_correction.json](../status_correction.json) separately records the documentation-only updates and preserved evidence.

## Reproduce locally or on Dantzig

Run from this repository checkout using Python 3.10 or newer with only the standard library.
The output directory must not exist, so the command cannot overwrite retained results.

```bash
ANALYSIS_PARENT=$(mktemp -d "${TMPDIR:-/tmp}/fmqa-uniform.XXXXXX")
python -m review_comparison.fmqa_uniform \
  --input results/review_comparison_20261020/tables/completed_runs.csv \
  --manifest results/review_comparison_20261020/manifest.json \
  --output "$ANALYSIS_PARENT/fmqa_uniform"
```

Outputs are `paired_runs.csv`, `paired_success.csv` (19 rows), this README and a separate provenance `manifest.json`.
The manifest records input, source and output SHA256 values, execution environment, bootstrap settings and the descriptive Process total.
The source SHA256 values identify the exact analysis code, while the generation HEAD and historical execution revision have distinct meanings.
CSV bytes are deterministic, whereas the manifest also records the actual generation time, environment and paths.

## Validation commands

The regression tests exercise invalid pairing, outcome signs, all four joint outcomes, function grouping and separate Process conditions.
The published manifest also records completed validation checks and the test log hash, which are not recreated by running the analysis alone.
Run the existing archive audit into a fresh directory to verify the retained analysis independently.

```bash
python -m pytest -q tests/test_review_comparison_fmqa_uniform.py tests/test_review_comparison.py tests/test_review_comparison_audit.py tests/test_final_process_artifacts.py
python -m review_comparison.audit --output "$ANALYSIS_PARENT/original_audit"
```
