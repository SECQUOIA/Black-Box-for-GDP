# NLP-inclusive cost reconstruction

Audited 556 complete coordinate traces and 12,778 callbacks. No optimizer or NLP was rerun. Original data were not modified.

## Calculation

`estimated total = same-trace search clock - recorded lookup costs + charged point costs + once-per-run Dynamic preparation`

Each lookup-feasible callback pays only the selected successful evaluation's `total_wall_s` (`accepted=true`); lookup-infeasible callbacks cost zero. For the seven repaired CSTR30 points, only the successful individual run is charged. Earlier failed runs are excluded by user instruction. The original all-attempt history remains available for provenance and does not enter reconstructed totals. Point cost already includes preparation, preprocessing, solver interface and validation: these overlapping timers are not added again. Dynamic preparation (0.1090063113 s) is charged once per run. Initial evaluations count. The separate cache sensitivity charges each coordinate's NLP only once, and is an assumption, not a claim about original solver caching.

## Exact-model results

356 runs cover Column, CSTR30, Small Batch and six Dynamic budgets. All 356 of these runs have measurements for every feasible coordinate, with infeasible evaluations assigned zero by user instruction.

| Case / budget | Method | Lookup target hits | Measured-NLP target hits on fixed path | Median first hit, successful (s) | Median completion, all (s) |
|---|---|---:|---:|---:|---:|
| column, B=16 | DSDA | 7/9 | 7/9 | 35.227 | 49.433 |
| column, B=16 | RBFOpt | 3/9 | 3/9 | 15.628 | 36.652 |
| column, B=16 | BAM 5.0.0 | 0/9 | 0/9 | — | 43.796 |
| column, B=16 | FMQA-SA | 4/9 | 4/9 | 6.277 | 11.808 |
| cstr30, B=43 | DSDA | 5/10 | 5/10 | 43.817 | 46.305 |
| cstr30, B=43 | RBFOpt | 10/10 | 10/10 | 7.435 | 78.177 |
| cstr30, B=43 | BAM 5.0.0 | 2/10 | 2/10 | 8.501 | 25.133 |
| cstr30, B=43 | FMQA-SA | 2/10 | 2/10 | 20.186 | 56.432 |
| small_batch, B=10 | DSDA | 10/10 | 10/10 | 3.151 | 7.947 |
| small_batch, B=10 | RBFOpt | 10/10 | 10/10 | 3.172 | 8.840 |
| small_batch, B=10 | BAM 5.0.0 | 10/10 | 10/10 | 3.155 | 7.947 |
| small_batch, B=10 | FMQA-SA | 9/10 | 9/10 | 4.893 | 8.355 |
| dynamic, B=12 | DSDA | 4/10 | 4/10 | 7.415 | 12.723 |
| dynamic, B=12 | RBFOpt | 9/10 | 9/10 | 8.556 | 14.488 |
| dynamic, B=12 | BAM 5.0.0 | 0/10 | 0/10 | — | 9.612 |
| dynamic, B=12 | FMQA-SA | 2/10 | 2/10 | 5.052 | 9.121 |
| dynamic, B=15 | DSDA | 5/10 | 5/10 | 8.460 | 15.804 |
| dynamic, B=15 | RBFOpt | 10/10 | 10/10 | 8.760 | 20.474 |
| dynamic, B=15 | BAM 5.0.0 | 0/10 | 0/10 | — | 10.238 |
| dynamic, B=15 | FMQA-SA | 3/10 | 3/10 | 6.290 | 10.543 |
| dynamic, B=20 | DSDA | 9/10 | 9/10 | 14.363 | 21.596 |
| dynamic, B=20 | RBFOpt | 10/10 | 10/10 | 8.749 | 28.859 |
| dynamic, B=20 | BAM 5.0.0 | 3/10 | 3/10 | 11.107 | 13.384 |
| dynamic, B=20 | FMQA-SA | 3/10 | 3/10 | 6.289 | 13.799 |
| dynamic, B=30 | DSDA | 10/10 | 10/10 | 16.779 | 26.474 |
| dynamic, B=30 | RBFOpt | 10/10 | 10/10 | 8.767 | 73.271 |
| dynamic, B=30 | BAM 5.0.0 | 5/10 | 5/10 | 13.375 | 20.558 |
| dynamic, B=30 | FMQA-SA | 5/10 | 5/10 | 12.833 | 21.057 |
| dynamic, B=37 | DSDA | 10/10 | 10/10 | 16.779 | 26.474 |
| dynamic, B=37 | RBFOpt | 10/10 | 10/10 | 9.115 | 131.055 |
| dynamic, B=37 | BAM 5.0.0 | 8/10 | 8/10 | 15.671 | 23.017 |
| dynamic, B=37 | FMQA-SA | 6/10 | 6/10 | 14.616 | 25.210 |
| dynamic, B=50 | DSDA | 10/10 | 10/10 | 16.779 | 26.474 |
| dynamic, B=50 | RBFOpt | 10/10 | 10/10 | 9.137 | 248.701 |
| dynamic, B=50 | BAM 5.0.0 | 10/10 | 10/10 | 18.733 | 32.458 |
| dynamic, B=50 | FMQA-SA | 7/10 | 7/10 | 16.396 | 34.145 |

Success-only medians must be read with their success counts. No successful run is silently substituted for a failure. Performance-profile denominators contain all paired starts, including all-method failures. Target tolerance is `1e-5 * max(1, abs(target))`.

## Declared approximations

1. **Infeasible points cost zero.** This is the user's explicit accounting assumption, applied to points marked infeasible by the original benchmark oracle, including logic/FBBT-infeasible points. Their original measured cost, if available, is preserved but not charged. This does not mean infeasibility detection was measured to be free. Failed IPOPT attempts are excluded. A feasible point without a successful measurement stays missing, not zero-cost.

2. **CSTR5–25.** The published cost table intentionally retains only CSTR30. The exact-model outputs leave those missing costs blank. `cstr30_transfer_time_profiles` is a separate scenario using the measured CSTR30 costs at the same coordinates for smaller search domains. It does not claim measured runtime of the smaller GDP models, and must not be used as a same-model runtime comparison against their full GDP solvers.

3. **Clock provenance.** DSDA/RBFOpt/BAM paths and overhead come from the complete Mac trace reruns, not recovered original Dantzig paths. Some Mac jobs overlapped. FMQA paths/overhead and all NLP point costs come from Dantzig. The FMQA archive's CPU, physical-core topology and run timestamp are recorded in `manifest.json`; CPU affinity does not establish exclusive server access. These are component-based timing estimates with heterogeneous clock provenance, not controlled measured end-to-end speedups.

The complete Mac reruns can also have different search outcomes from the old Dantzig runs despite identical initial points. For example, Column RBFOpt succeeds in 3/9 of the traced reruns versus 4/9 in the older server archive. The new figures use the actual traced outcomes; they do not silently attach new paths to old success records.

4. **Objective values.** The existing lookup trajectory is preserved. IPOPT is a local solver and some CSTR point objectives differ. Per-point discrepancies and a separate measured-NLP incumbent along the *fixed original path* are included. That second sequence does not simulate how the optimizer would react to changed observations. Neither sequence certifies a global optimum.

5. **GDP baselines.** `gdp_baseline_comparison.csv` retains measured full-GDP completion times separately, plus one shared template preparation cost. Missing saved solutions remain missing. These are completion records, not first-hit records, and are not merged into first-hit performance profiles. The previously identified CSTR initialization, lost-incumbent, Column bound and CPU-overlap qualifications still apply.

## Figures and data

- `time_performance_profiles.{png,pdf}`: exact-model cases, estimated first-hit time to the original lookup target.
- `completion_time_profiles.{png,pdf}`: full completion time, using the same reconstructed costs.
- `success_vs_time.{png,pdf}`: absolute estimated seconds versus target-hit fraction.
- `cost_breakdown.{png,pdf}`: mean completion cost components; all runs included.
- `completion_vs_quality.{png,pdf,csv}`: measured full-GDP completion versus reconstructed black-box completion, with distinct markers.
- `cstr30_transfer_time_profiles.{png,pdf}`: all original conditions, with smaller-CSTR proxies explicitly labelled.
- `run_costs.csv`, `evaluation_costs.csv`: every total and coordinate join, including provenance and missing values.
- `case_summary.csv`, `time_profile_runs.csv`: summary and performance ratios.
- `cache_sensitivity.csv`: optional within-run memoization assumption.
- `unmeasured_coordinates.csv`: explicit outstanding measurements; source data are preserved.

## Reproduce

From the repository root, with the original trace bundle, FMQA archive and GDP results at the manifest paths:

```bash
MPLCONFIGDIR=/tmp/nlp-cost-matplotlib python nlp_cost_analysis.py --output results/new_nlp_cost_comparison
```

No shell runner, server execution, Git commit or push is needed for this analysis.
