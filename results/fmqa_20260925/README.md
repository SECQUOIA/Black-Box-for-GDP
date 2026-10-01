# FMQA-SA benchmark refresh — September 25, 2026

Current FMQA data replace the contaminated September 22 runs. The old FMQA raw datasets, ZIP copies and derived comparisons have been deleted from the working tree. Original DSDA/RBFOpt/BAM data and NLP point measurements are unchanged.

## Verified source data

| Dataset | Completed | CPU / physical core / sibling | Raw data | Original ZIP |
|---|---:|---|---|---|
| QHDOpt Grid | 1,050 / 1,050 | 0 / 0 / 48 | [benchmark.csv](grid/benchmark.csv) | [Grid archive](../archives/dantzig_fmqa_grid_20260925_172020_9n7j9oh1.zip) |
| GDP process cases | 139 / 139 | 4 / 4 / 52 | [process_case_studies.csv](case/process_case_studies.csv) | [Case archive](../archives/dantzig_fmqa_20260925_174150_2m7pmr0d.zip) |

Both ran on Dantzig with one-thread settings. The two FMQA jobs and the September 25 full-GDP rerun used distinct physical cores (0, 4 and 2 respectively). CPU affinity is not an exclusive reservation; no claim of an otherwise idle server is made. The [GDPopt/BARON rerun](../gdp_comparison_20260925/analysis/README.md) now supplies all full-GDP baselines below. Its 36 saved solutions passed independent original-GDP feasibility checks; the contaminated September 22 full-GDP files were removed.

All 4,964 internal checksums, source snapshots, objective traces, initial designs and CSV records passed validation. All runs completed their evaluation budgets with no worker errors. The plans, hyperparameters, evaluated coordinates and incumbent sequences match the previous experiment; completion and callback clocks are new. See [publication.json](publication.json) and [validation.json](validation.json).

## Current Grid comparison

The comparison contains 21 problems × 10 seeds × 5 budgets × 4 methods = 4,200 rows. Each run starts from the same three ordered points. Target success uses `abs(f - target) <= 1e-5 * max(1, abs(target))`.

| Budget | DSDA success | RBFOpt success | BAM 5.0.0 success | FMQA-SA success | FMQA median completion (s) |
|---:|---:|---:|---:|---:|---:|
| 10 | 6.2% | 21.4% | 52.9% | 8.6% | 0.4977 |
| 30 | 35.7% | 63.3% | 55.2% | 20.5% | 1.9540 |
| 50 | 42.4% | 71.9% | 57.6% | 31.9% | 3.4518 |
| 70 | 48.1% | 76.2% | 62.9% | 45.7% | 4.9835 |
| 100 | 49.5% | 81.9% | 70.0% | 56.7% | 7.3416 |

The evaluation-based conclusions are unchanged. Timing profiles, time/work plots and TTS99 now use the new FMQA measurements. TTS99 is estimated per problem/budget from ten seeds using median full-run time times the required independent restart count; zero observed successes give an infinite estimate, not proof of impossibility.

## GDP case and NLP-inclusive comparisons

- [Lookup comparison](analysis/case/README.md): 556 paired rows for DSDA, RBFOpt, BAM 5.0.0 and FMQA-SA.
- [Corrected Dantzig timing comparison](analysis/nlp/README.md): all 556 original server completion clocks and outcomes, with archive identity checks and no Mac traces.
- **October 1 correction:** withdraw the mixed Mac/Dantzig NLP totals, first-hit profiles, CSTR30 cost-transfer profiles and DFO-versus-GDP completion/quality chart.
- The original DSDA/RBFOpt/BAM archives have completion times but lack complete ordered evaluation coordinates and first-hit timestamps. Their NLP-inclusive totals remain missing; they are not filled using Mac paths.
- FMQA's original Dantzig traces support separate NLP-cost estimates. Successful evaluations are charged, failed attempts excluded, infeasible lookups cost zero by the stated assumption, and Dynamic preparation is added once. Exact costs for CSTR5–25 remain missing.
- Full-GDP completion times remain available separately in the [GDP audit](../gdp_comparison_20260925/analysis/README.md). Lookup-only runtimes are not compared with full-GDP runtimes as an end-to-end speedup.

## Figure index

The figure index below lists the current, supported comparisons. PNG/PDF files are excluded from Git by user instruction; raw data, comparison tables, code and manifests are committed. Local links below open the images; on a fresh checkout regenerate them first.

| Figure | Local PNG |
|---|---|
| Grid: first-hit evaluation-count performance profiles | [Open](analysis/grid/evaluation_performance_profiles.png) |
| Grid: convergence by evaluation count | [Open](analysis/grid/convergence_curves.png) |
| Grid: estimated TTS99 | [Open](analysis/grid/tts99_comparison.png) |
| Grid: relative completion-time profiles | [Open](analysis/grid/timing/time_performance_profiles.png) |
| Grid: absolute completion-time profiles | [Open](analysis/grid/timing/completion_time_profiles.png) |
| Grid: completion time versus evaluations/iterations | [Open](analysis/grid/timing/time_work_tradeoff.png) |
| GDP cases: lookup target hits and run costs | [Open](analysis/case/case_study_overview.png) |
| GDP cases: lookup convergence | [Open](analysis/case/evaluation_convergence.png) |
| GDP cases: lookup completion-time performance profiles | [Open](analysis/case/timing/time_performance_profiles.png) |
| GDP cases: absolute lookup completion times | [Open](analysis/case/timing/completion_time_profiles.png) |
| GDP cases: lookup time versus evaluations/iterations | [Open](analysis/case/timing/time_work_tradeoff.png) |
| GDP cases: corrected Dantzig relative completion-time profiles | [Open](analysis/nlp/time_performance_profiles.png) |
| GDP cases: corrected Dantzig absolute completion times | [Open](analysis/nlp/completion_time_profiles.png) |
| GDP cases: original Dantzig mean lookup runtimes (replaces cost breakdown) | [Open](analysis/nlp/cost_breakdown.png) |
| GDP cases: corrected Dantzig time/work comparison | [Open](analysis/nlp/time_work_tradeoff.png) |

## Reproduce

From the repository root (choose a new output root for the NLP analysis):

```bash
python fmqa_compare.py --dataset grid --fmqa-results results/archives/dantzig_fmqa_grid_20260925_172020_9n7j9oh1.zip --output-dir results/fmqa_rebuilt/analysis/grid --time-profiles
python fmqa_compare.py --dataset case --fmqa-results results/archives/dantzig_fmqa_20260925_174150_2m7pmr0d.zip --output-dir results/fmqa_rebuilt/analysis/case --time-profiles
python nlp_cost_analysis.py --output results/fmqa_rebuilt/analysis/nlp
```

The timing command verifies the original Dantzig and BAM archives, reads the September 25 FMQA archive, and retains the curated point costs and tracked full-GDP results under `results/gdp_comparison_20260925/raw/`. Original ZIPs are available under `results/archives/`. Run `python gdp_comparison_analysis.py` to independently recheck the full-GDP saved solutions and regenerate its summary table without solving.

```bash
(cd results/fmqa_20260925/case && shasum -a 256 -c SHA256SUMS)
(cd results/fmqa_20260925/grid && shasum -a 256 -c SHA256SUMS)
shasum -a 256 -c results/archives/SHA256SUMS
```
