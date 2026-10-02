# FMQA-SA benchmark refresh — September 25, 2026

Current FMQA data replace the contaminated September 22 runs. The old FMQA raw datasets, ZIP copies and derived comparisons have been deleted from the working tree. Original DSDA/RBFOpt/BAM data and NLP point measurements are unchanged.

## Verified source data

| Dataset | Completed | CPU / physical core / sibling | Raw data | Original ZIP |
|---|---:|---|---|---|
| QHDOpt Grid | 1,050 / 1,050 | 0 / 0 / 48 | [benchmark.csv](grid/benchmark.csv) | [Grid archive](../archives/dantzig_fmqa_grid_20260925_172020_9n7j9oh1.zip) |
| GDP process cases | 139 / 139 | 4 / 4 / 52 | [process_case_studies.csv](case/process_case_studies.csv) | [Case archive](../archives/dantzig_fmqa_20260925_174150_2m7pmr0d.zip) |

Both ran on Dantzig with one-thread settings. The two FMQA jobs and the September 25 full-GDP rerun used distinct physical cores (0, 4 and 2 respectively). CPU affinity is not an exclusive reservation; no claim of an otherwise idle server is made. The [current GDP audit](../gdp_comparison_current/analysis/README.md) includes all 27 completed October 1 BARON/HiGHS GDPopt jobs (RIC/GLOA on CPU 2, LOA on CPU 6) and 18 September 25 Big-M/Hull jobs. All 45 selected saved solutions passed independent original-GDP feasibility checks.

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

## GDP case comparisons and separate NLP costs

- [Current Dantzig trace and NLP cost report](../dfo_trace_nlp_20261002/analysis/README.md): 417 October 2 DSDA/RBFOpt/BAM traces plus the original 139 FMQA traces, 12,778 callbacks and complete measurement coverage of all 1,779 visited coordinates.
- Every point evaluation cost is retained, including preprocessing rejection, solver-reported infeasibility and other rejected attempts. DFO runtime and separately measured point costs remain distinct.
- [September lookup comparison](analysis/case/README.md) and [historical Dantzig timing report](analysis/nlp/README.md) preserve the original September runs. These original DSDA/RBFOpt/BAM archives lack full callback coordinates; the October 2 rerun traces are a separately identified dataset.
- The previous mixed Mac/Dantzig reconstructed totals and the later zero-cost infeasible-point estimates are withdrawn. No Mac paths or clocks enter the current report.
- Full-GDP completion times remain separate in the [current GDP audit](../gdp_comparison_current/analysis/README.md). Lookup runtime is not presented as an online full-GDP speedup.

## Figure index

The figure index includes the current October 2 timing/cost figures and the explicitly dated historical lookup figures. At the user's latest publication request, the verified PNG/PDF figures are committed together with raw data, comparison tables, code and manifests.

| Figure | Published PNG |
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
| September GDP cases: historical relative completion-time profiles | [Open](analysis/nlp/time_performance_profiles.png) |
| September GDP cases: historical absolute completion times | [Open](analysis/nlp/completion_time_profiles.png) |
| September GDP cases: historical Dantzig mean lookup runtimes | [Open](analysis/nlp/cost_breakdown.png) |
| September GDP cases: historical time/work comparison | [Open](analysis/nlp/time_work_tradeoff.png) |
| October 2: measured DFO runtime and all-outcome NLP costs | [Open](../dfo_trace_nlp_20261002/analysis/runtime_and_nlp_costs.png) |
| October 2: all six CSTR sizes, measured DFO runtime and NLP costs | [Open](../dfo_trace_nlp_20261002/analysis/cstr_sizes.png) |
| Full GDP: RIC/GLOA/LOA/Big-M/Hull objectives and completion times, 45 completed jobs | [Open](../gdp_comparison_current/analysis/gdp_objectives_and_times.png) |

## Reproduce

From the repository root (choose a new output root for the NLP analysis):

```bash
python fmqa_compare.py --dataset grid --fmqa-results results/archives/dantzig_fmqa_grid_20260925_172020_9n7j9oh1.zip --output-dir results/fmqa_rebuilt/analysis/grid --time-profiles
python fmqa_compare.py --dataset case --fmqa-results results/archives/dantzig_fmqa_20260925_174150_2m7pmr0d.zip --output-dir results/fmqa_rebuilt/analysis/case --time-profiles
python dfo_trace_analysis.py --output results/fmqa_rebuilt/analysis/nlp
```

The timing command verifies the October 2 Dantzig trace archive, the September 25 FMQA archive and the compatible original point measurements. It includes all recorded outcomes. Full-GDP sources are selected explicitly in `results/gdp_comparison_current/selection.json`. Original archives are available under `results/archives/`. Run `python gdp_current_analysis.py` to independently recheck the selected full-GDP saved solutions and regenerate the current table without solving.

```bash
(cd results/fmqa_20260925/case && shasum -a 256 -c SHA256SUMS)
(cd results/fmqa_20260925/grid && shasum -a 256 -c SHA256SUMS)
shasum -a 256 -c results/archives/SHA256SUMS
```
