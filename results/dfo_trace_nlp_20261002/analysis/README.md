# Dantzig DFO traces and all-outcome NLP costs — October 2, 2026

The original DSDA, RBFOpt and BAM lookup searches completed 139 runs each on Dantzig (417 new runs). The 139 original September 25 Dantzig FMQA traces are reused. The search objectives, seeds, starts and budgets are unchanged; separately measured NLP results were never fed back to a search.

**Verified: 556 runs, 12,778 ordered callbacks, 1,779 distinct model/size/coordinate keys, and zero missing point measurements.** All archive entries, source snapshots, job inventories, trace identities, initial designs, objective values, event clocks and recorded result histories passed the audit. The shipped run and callback CSVs were independently rebuilt and matched exactly.

## Read these results

- [Run results](dfo_runs.csv): actual DFO clocks, final solutions, target attainment and separate attached NLP cost sums.
- [Ordered callback ledger](evaluation_timings.csv): every visited coordinate, DFO timestamps, point duration, outcome and source checksum.
- [Unique point measurements](point_timings.csv): one selected result and measured cost per exact model/size/coordinate.
- [Comparison by model and budget](comparison_summary.csv) and [outcome totals](point_outcome_summary.csv).
- [Dynamic and Small Batch lookup/NLP comparison](lookup_nlp_comparison.csv): all 37 and 12 feasible coordinates, respectively.
- [Main comparison figure](runtime_and_nlp_costs.png) ([PDF](runtime_and_nlp_costs.pdf)); [all six CSTR sizes](cstr_sizes.png) ([PDF](cstr_sizes.pdf)).
- [Audit and provenance](manifest.json), [Dynamic preparations](dynamic_preparations.json), and [new measurement collection overhead](measurement_collection.csv).

## What the NLP clock includes

The point timer (`nlp_evaluation_wall_s`) includes point-specific model setup, preprocessing, the solver invocation when required, and validation. `nlp_solve_wall_s` is already inside that duration and is never added twice. Preprocessing can reject an integer configuration before an NLP solver is called: its solver time is zero, but its actual evaluation time is positive and is included. Solver-reported infeasibility is an IPOPT outcome, not a global infeasibility proof.

There are 1,076 compatible historical original measurements from September 22 and 703 new October 2 measurements. All 703 new points were rejected during preprocessing; none required a new solver invocation. The historical measurements include 592 solver-reported infeasible points and three other rejected attempts. Those three returned feasible candidates but solver warning/termination status failed the original acceptance policy; they are not relabelled infeasible. The seven recorded CSTR30 retries found accepted solutions; six of these coordinates occur in the recorded DFO paths. For those six points, use only the successful retry result and its measured time. The initial failed attempt is excluded from the comparison cost and retained in the raw records. The seventh repaired point, (6, 4), is not visited and contributes no callback cost. Retry initialization is mass_balance_zero_recycle. Other points retain their selected measured costs.

| Point outcome | Unique coordinates | Total measured evaluation seconds | Minimum seconds | Maximum seconds |
|---|---:|---:|---:|---:|
| accepted | 462 | 801.198586 | 0.760220 | 43.140607 |
| preprocessing infeasible | 728 | 293.049476 | 0.101831 | 0.824788 |
| solver reported infeasible | 589 | 1131.481849 | 0.832127 | 45.265725 |

These totals count each distinct measured coordinate once. Run-level attached sums count every actual callback, including repeats, against its separate point measurement. They are fixed-path cost estimates, not 12,778 independent NLP solves. The 384 repeated callbacks remain visible. Missing times are never zero-filled.

DFO runtime and attached NLP costs are reported in separate columns and panels. No measured combined runtime or estimated first-hit clock is asserted. October 2 DFO reruns are not substituted into the original September 10/16 records. The FMQA and reused NLP measurements come from the dates shown above; this is not a simultaneous four-method experiment.

`dfo_wall_time_s` retains each original method's timer; `trace_runner_wall_s` preserves the outer traced runner clock. Tracing overhead inside the method's timer remains in its measured runtime. Neither clock includes the separately collected point NLP costs. The October 2 jobs recorded affinity to CPU 6 (sibling 54), with one-thread settings; affinity does not reserve an otherwise idle server.

Dynamic template/discretization preparation is recorded separately because it is shared across point evaluations. The historical Dynamic preparation is 0.109006311 seconds. New worker preparation samples are retained individually; they are not charged at every callback. Premeasurement warmup/model checks and worker/process overhead are also kept in `measurement_collection.csv`, outside the point timer. They are collection costs, not hidden additions to DFO runtime.

NLP acceptance/objective differences from the frozen lookup are flagged in the callback ledger. These observations do not change the recorded DFO solution or its target attainment. The full GDPopt RIC/GLOA/LOA and Big-M/Hull results remain [separate](../../gdp_comparison_current/analysis/README.md); no direct online speed comparison is inferred.

The audit found 583 distinct CSTR coordinates (2,631 callbacks) where the lookup is feasible but the available IPOPT result was not accepted. Among accepted attempts, 26 CSTR coordinates (188 callbacks) differ from the lookup objective beyond the benchmark tolerance `1e-5 * max(1, abs(lookup))`. The cost coverage audit therefore does not certify reproduction of every lookup objective by IPOPT. These measured attempts remain in the timing totals, with their actual outcomes.

Dynamic's DFO reference is the fixed dictionary in `case_studies/dynamic_case.py`, not a CSV file. All 37 reference coordinates have accepted NLP solutions; the maximum absolute objective difference is 7.7046e-8 at (5, 8). Both select (1, 4) as best. Small Batch uses `compl_enum_small_batch_baron.csv`: all 12 feasible coordinates have accepted NLP solutions, with maximum absolute difference 6.7722e-7 at (3, 3, 3). Both select (2, 2, 1) as best. All 49 comparisons pass the relative tolerance above. No new NLP solves were run for this comparison.

## Comparison

All runs, including target failures, enter the means. Seconds are rounded here; CSVs retain full precision. Figures combine preprocessing rejection, solver-reported infeasibility and other rejected attempts into one no-accepted-solution category. This is a recorded outcome, not a claim of mathematical infeasibility. Detailed diagnostic statuses remain in the CSVs. Successful-retry points use the retry cost alone. Lookup data alone determine search paths and target attainment.

| Model | Budget | Method | Target hits / runs | Mean DFO s | Mean attached NLP s | Of which unaccepted s |
|---|---:|---|---:|---:|---:|---:|
| Column | 16 | BAM 5.0.0 | 0 / 9 | 1.186924 | 39.434566 | 5.362448 |
| Column | 16 | DSDA | 7 / 9 | 0.000746 | 46.203907 | 0.814335 |
| Column | 16 | FMQA-SA | 4 / 9 | 0.896710 | 28.076300 | 13.808195 |
| Column | 16 | RBFOpt | 4 / 9 | 6.033094 | 37.177796 | 1.781250 |
| CSTR 10 | 15 | BAM 5.0.0 | 1 / 10 | 0.792922 | 11.036398 | 10.031323 |
| CSTR 10 | 15 | DSDA | 3 / 10 | 0.000670 | 12.516093 | 11.472853 |
| CSTR 10 | 15 | FMQA-SA | 2 / 10 | 0.827857 | 12.744432 | 11.531126 |
| CSTR 10 | 15 | RBFOpt | 7 / 10 | 5.350902 | 13.248943 | 11.747384 |
| CSTR 15 | 22 | BAM 5.0.0 | 1 / 10 | 0.835596 | 18.666354 | 17.140212 |
| CSTR 15 | 22 | DSDA | 2 / 10 | 0.000809 | 29.210940 | 26.404467 |
| CSTR 15 | 22 | FMQA-SA | 1 / 10 | 1.310628 | 32.896346 | 29.197895 |
| CSTR 15 | 22 | RBFOpt | 10 / 10 | 9.704174 | 39.289969 | 24.540375 |
| CSTR 20 | 29 | BAM 5.0.0 | 2 / 10 | 1.297918 | 30.203979 | 28.068298 |
| CSTR 20 | 29 | DSDA | 3 / 10 | 0.000935 | 27.472321 | 27.112817 |
| CSTR 20 | 29 | FMQA-SA | 1 / 10 | 1.899914 | 38.895794 | 37.958731 |
| CSTR 20 | 29 | RBFOpt | 9 / 10 | 19.477836 | 34.219593 | 32.875880 |
| CSTR 25 | 36 | BAM 5.0.0 | 2 / 10 | 2.457107 | 43.660712 | 40.601081 |
| CSTR 25 | 36 | DSDA | 3 / 10 | 0.001084 | 46.303353 | 45.386557 |
| CSTR 25 | 36 | FMQA-SA | 1 / 10 | 2.401297 | 49.778061 | 48.650562 |
| CSTR 25 | 36 | RBFOpt | 10 / 10 | 35.370289 | 64.440987 | 61.733008 |
| CSTR 30 | 43 | BAM 5.0.0 | 2 / 10 | 2.379396 | 31.491868 | 6.061754 |
| CSTR 30 | 43 | DSDA | 5 / 10 | 0.001279 | 51.130458 | 0.418987 |
| CSTR 30 | 43 | FMQA-SA | 2 / 10 | 2.910601 | 62.146987 | 3.702962 |
| CSTR 30 | 43 | RBFOpt | 10 / 10 | 55.786598 | 42.126982 | 3.812683 |
| CSTR 5 | 8 | BAM 5.0.0 | 10 / 10 | 0.191965 | 24.609647 | 23.777158 |
| CSTR 5 | 8 | DSDA | 3 / 10 | 0.000425 | 21.724553 | 21.283817 |
| CSTR 5 | 8 | FMQA-SA | 2 / 10 | 0.327215 | 19.678442 | 19.154457 |
| CSTR 5 | 8 | RBFOpt | 10 / 10 | 1.846477 | 10.888595 | 10.550702 |
| Dynamic | 12 | BAM 5.0.0 | 0 / 10 | 0.032211 | 9.807900 | 0.617883 |
| Dynamic | 12 | DSDA | 4 / 10 | 0.000922 | 12.880848 | 0.189970 |
| Dynamic | 12 | FMQA-SA | 2 / 10 | 0.601819 | 8.640980 | 0.755858 |
| Dynamic | 12 | RBFOpt | 9 / 10 | 3.480766 | 11.770841 | 0.312760 |
| Dynamic | 15 | BAM 5.0.0 | 3 / 10 | 0.799710 | 12.317206 | 0.758843 |
| Dynamic | 15 | DSDA | 5 / 10 | 0.000698 | 16.288104 | 0.189970 |
| Dynamic | 15 | FMQA-SA | 3 / 10 | 0.808699 | 10.519792 | 0.976698 |
| Dynamic | 15 | RBFOpt | 10 / 10 | 6.670305 | 15.086232 | 0.346829 |
| Dynamic | 20 | BAM 5.0.0 | 3 / 10 | 0.797441 | 14.671385 | 1.227288 |
| Dynamic | 20 | DSDA | 9 / 10 | 0.000810 | 19.861245 | 0.189970 |
| Dynamic | 20 | FMQA-SA | 3 / 10 | 1.154902 | 13.963658 | 1.302199 |
| Dynamic | 20 | RBFOpt | 10 / 10 | 15.818107 | 19.189153 | 0.556216 |
| Dynamic | 30 | BAM 5.0.0 | 5 / 10 | 1.696075 | 21.661424 | 1.850664 |
| Dynamic | 30 | DSDA | 10 / 10 | 0.000979 | 24.107877 | 0.189970 |
| Dynamic | 30 | FMQA-SA | 5 / 10 | 1.843989 | 20.406483 | 1.988423 |
| Dynamic | 30 | RBFOpt | 10 / 10 | 56.888799 | 25.871452 | 1.160815 |
| Dynamic | 37 | BAM 5.0.0 | 7 / 10 | 2.111301 | 24.697069 | 2.530816 |
| Dynamic | 37 | DSDA | 10 / 10 | 0.000994 | 24.358514 | 0.189970 |
| Dynamic | 37 | FMQA-SA | 6 / 10 | 2.327349 | 25.667356 | 2.368026 |
| Dynamic | 37 | RBFOpt | 10 / 10 | 108.991334 | 31.398506 | 1.538636 |
| Dynamic | 50 | BAM 5.0.0 | 10 / 10 | 4.340043 | 33.457103 | 3.373989 |
| Dynamic | 50 | DSDA | 10 / 10 | 0.000989 | 24.358514 | 0.189970 |
| Dynamic | 50 | FMQA-SA | 7 / 10 | 3.239480 | 34.254736 | 3.228600 |
| Dynamic | 50 | RBFOpt | 10 / 10 | 278.150546 | 38.367243 | 2.642019 |
| Small Batch | 10 | BAM 5.0.0 | 10 / 10 | 0.116279 | 7.920692 | 0.000000 |
| Small Batch | 10 | DSDA | 10 / 10 | 0.000551 | 7.941120 | 0.000000 |
| Small Batch | 10 | FMQA-SA | 9 / 10 | 0.449839 | 7.906360 | 0.000000 |
| Small Batch | 10 | RBFOpt | 10 / 10 | 0.852352 | 7.931486 | 0.000000 |

## Provenance and reproduction

The original [result ZIP](../../archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip) is retained byte-for-byte with its [SHA256 sidecar](../../archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip.sha256). Paths in the ledger are archive member paths; `source_kind` identifies historical versus new measurements. The manifest identifies the two historical evidence archives. Immutable archived instructions/source snapshots are preserved in their original language for checksum integrity; all current reports, figures and instructions are in English.

```bash
python dfo_trace_analysis.py --output results/dfo_trace_nlp_20261002/analysis
```

This command only reads saved evidence and rebuilds the English reports. It executes no DFO, GDP or NLP solver.
