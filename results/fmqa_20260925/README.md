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
- [NLP-inclusive reconstruction](analysis/nlp/README.md): 556 coordinate traces and 12,778 callbacks; 356 exact-model runs have every required feasible-point cost.
- Charge only the selected successful NLP evaluation; exclude earlier failed attempts. Infeasible points cost zero by the specified assumption. Charge Dynamic preparation once per run.
- CSTR5–25 do not have exact-model point costs in the curated table; show their CSTR30 transfer scenario separately.
- FMQA clocks use the September 25 CPU 4 run. Other DFO search clocks in the NLP reconstruction are the recorded Mac trace reruns; the totals are component-based estimates, not measured online GDP executions.
- The eight-method completion/quality figure uses the new CPU 2 full-GDP measurements. It remains an exploratory comparison against reconstructed DFO times and original lookup objectives. BARON bound conflicts for Column/Big-M, CSTR10/Hull and CSTR30/Hull are flagged in the full-GDP audit and comparison tables.

## Figure index

All 17 figure types have been regenerated locally. PNG/PDF files are excluded from Git by user instruction; raw data, comparison tables, code and manifests are committed. Local links below open the images; on a fresh checkout regenerate them first.

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
| GDP cases: NLP-inclusive first-hit time profiles | [Open](analysis/nlp/time_performance_profiles.png) |
| GDP cases: NLP-inclusive completion-time profiles | [Open](analysis/nlp/completion_time_profiles.png) |
| GDP cases: target-hit fraction versus NLP-inclusive seconds | [Open](analysis/nlp/success_vs_time.png) |
| GDP cases: search overhead and successful NLP costs | [Open](analysis/nlp/cost_breakdown.png) |
| GDP cases: DFO versus September 25 GDPopt/BARON completion and quality | [Open](analysis/nlp/completion_vs_quality.png) |
| CSTR5–25: explicitly labelled CSTR30 cost-transfer scenario | [Open](analysis/nlp/cstr30_transfer_time_profiles.png) |

## Reproduce

From the repository root (choose a new output root for the NLP analysis):

```bash
python fmqa_compare.py --dataset grid --fmqa-results results/archives/dantzig_fmqa_grid_20260925_172020_9n7j9oh1.zip --output-dir results/fmqa_rebuilt/analysis/grid --time-profiles
python fmqa_compare.py --dataset case --fmqa-results results/archives/dantzig_fmqa_20260925_174150_2m7pmr0d.zip --output-dir results/fmqa_rebuilt/analysis/case --time-profiles
python nlp_cost_analysis.py --output results/fmqa_rebuilt/analysis/nlp
```

The NLP command uses the original trace bundle, curated point costs and the tracked full-GDP results under `results/gdp_comparison_20260925/raw/`. Original ZIPs are available under `results/archives/`. Run `python gdp_comparison_analysis.py` to independently recheck the full-GDP saved solutions and regenerate its summary table without solving.

```bash
(cd results/fmqa_20260925/case && shasum -a 256 -c SHA256SUMS)
(cd results/fmqa_20260925/grid && shasum -a 256 -c SHA256SUMS)
shasum -a 256 -c results/archives/SHA256SUMS
```
