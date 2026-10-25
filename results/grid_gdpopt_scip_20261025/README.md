# Returned Grid GDPopt SCIP split experiments, 2026-10-25

The three returned archives contain all 63 planned first attempts, and all 63 saved solution vectors pass independent checks against the original GDP model and CSV objective.
Only 12 jobs report optimal termination, 46 terminate with errors, and five reach a time limit.
A sealed result or `all_jobs_finished=true` means that artifacts were finalized, not that optimization succeeded.
These runs therefore do not establish a clean performance comparison between SCIP and the previous solver route.
The original combined 63-job experiment on CPU 6 was not supplied and is not included, modified or stopped.

| Method | Jobs / feasible saved solutions | Target incumbents | Target without error | Reported optimal | Errors | Time limits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GLOA | 21 / 21 | 3 | 3 | 4 | 15 | 2 |
| LOA | 21 / 21 | 2 | 2 | 2 | 19 | 0 |
| RIC | 21 / 21 | 7 | 6 | 6 | 12 | 3 |
| Total | 63 / 63 | 12 | 11 | 12 | 46 | 5 |

The fixed target test is the normalized CSV objective minus the unchanged CSV minimum, with tolerance 1e-5.
Every original job remains in its method's denominator of 21.
RIC on styblinski_tang returned a target incumbent before a later network error, so the incumbent-hit count includes it while the count requiring completion without error excludes it.
GLOA hits alpine1, csendes and xin_she_yang3.
LOA hits alpine1 and xin_she_yang3.
RIC hits ackley, alpine1, csendes, rosenbrock, styblinski_tang, sum_of_squares and xin_she_yang3.
The saved solutions contain full original model variable vectors, not just an objective or an unverified pair of coordinates.
The maximum recomputed original constraint/bound violation is 0.0, and the maximum discrepancy between saved and recomputed objective is 5.551115123125783e-17.
The analytic model agrees with the supplied CSV across all 961 coordinates of each of the 21 grids.
No optimization solver was invoked during this audit.

## Actual solver execution

The benchmark journals contain 33,396 completed interface attempts: 33,352 returned calls and 44 error calls.
One additional interface call started but was interrupted by the holder_table/GLOA watchdog before its journal entry could be finalized.
Anchored execution banners confirm 33,364 actual SCIP invocations, all with model type MIP.
There are zero benchmark NLP calls, because the fixed grid configurations are handled by GDPopt preprocessing without requiring an NLP solve.
The three separate preflights contain nine additional calls, comprising three SCIP MIP and six SCIP NLP checks, and these are excluded from benchmark counts.

| Method | Journaled attempts | Returned | Interface errors | Unjournaled active | Confirmed SCIP invocations | Benchmark NLP calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GLOA | 13,557 | 13,543 | 14 | 1 | 13,545 | 0 |
| LOA | 6,275 | 6,257 | 18 | 0 | 6,265 | 0 |
| RIC | 13,564 | 13,552 | 12 | 0 | 13,554 | 0 |

The benchmark logs identify SCIP 9.2.4 (a94f778ac8) under GAMS 52.2.0.
The recorded environment contains Python 3.11.16, Pyomo 6.10.0, NumPy 2.4.6, SymPy 1.14.0 and NetworkX 3.6.1.
The GAMS executable SHA-256 is 11bd33943b5b2542afa73cbf3eb8a1f1b27eb1bde1ba56e85f8a262cfdd29245.
Each job retains the 1,800-second worker limit, relative gap 1e-5, one thread, `gams/mipstart = 0` and `timing/clocktype = 2`.
Recorded affinities are GLOA CPU 16/core 20, LOA CPU 14/core 18 and RIC CPU 12/core 16, with distinct physical cores.
The full runtime, options, input hashes and executed source inventories are retained in manifest.json and the raw archives.

## Error diagnosis and rerun decision

| Method | Network session start | Network session close | FBBT interval | Errors selected for recovery |
| --- | ---: | ---: | ---: | ---: |
| GLOA | 12 | 2 | 1 | 15 |
| LOA | 10 | 8 | 1 | 19 |
| RIC | 10 | 2 | 0 | 12 |
| Total | 32 | 12 | 2 | 46 |

The 44 network failures report an empty-response Curl error when GAMS starts or closes its network session.
The 32 start failures occur before SCIP execution, while the 12 close failures occur after SCIP has executed but before the interface returns successfully to Pyomo.
An error listing can therefore contain Normal Completion and Optimal even though the enclosing call failed, and those phrases do not override the recorded interface error.
The failed interface calls consume approximately 2,669.72 seconds in total.
The logs support a network/session failure diagnosis but do not establish that concurrent experiments caused it.

The two remaining errors are bohachevsky2/GLOA and bohachevsky2/LOA at iteration 103 and discrete indices [1, 11].
The physical coordinates are [-93.33333333333333, -26.66666666666667], and the preceding SCIP MIP call 205 returned normally.
Pyomo FBBT then raises `IntervalException: Cannot raise a negative variable to a fractional power.`
This is the fixed-exponent interval drift failure already addressed for three other grids, but bohachevsky2 was outside that earlier correction's scope.
A solver-free regression reproduces this failure, and the recovery policy applies the same exact-fixed-exponent rule to bohachevsky2.
All 961 fixed configurations are checked for preservation of their valid coordinates and objective bounds under the correction.

The user explicitly selected only the 46 error jobs for new runs.
The recovery packages contain GLOA 15, LOA 19 and RIC 12 jobs and exclude all five time limits and all twelve reported-optimal jobs.
The new policy allows at most two additional attempts of an explicitly identified network-failed interface call, with 5- and 15-second delays charged to the same original 1,800-second deadline.
All failed calls and recovery decisions remain recorded, and a failed call that changes model values, bounds or fixed flags is not retried.
This policy mitigates intermittent transport failures but cannot guarantee that the server's network or license service is healthy.
The recovery is a separate intervention, not an automatic replacement of original failures or a selection of the best complete attempt.
The new packages and separate upload, launch, tail and download commands are in [the recovery delivery directory](../runners/grid_gdpopt_scip_recovery_20261025/).
No Dantzig recovery result is claimed in this report.

## Separate unresolved GLOA result

Shubert/GLOA reports optimal termination at objective 0.08242781075119937 while the unchanged grid minimum is 0.0.
Its recorded lower and upper bounds are both approximately 0.082427810751199, so the reported lower bound exceeds a known feasible objective.
This is an invalid global-bound claim for the original grid problem, and no global-optimality certificate is assigned.
The evidence does not isolate the algorithmic cause, and it must not be presented as proof that SCIP globally solved this GDP.
It remains outside the requested error-only rerun because its recorded termination is optimal, rather than error.
All five time-limited incumbents are also preserved without rerunning.

## Historical paired comparison and cost

The October 23 SCIP-configured GDPopt runs actually used HiGHS for their benchmark MIP calls.
They are labeled as the historical HiGHS route, not as BARON NLP results or actual SCIP runs.
The old archives are re-audited and paired by grid and method, with the same analytic models, CSV inputs and target definition.
Direct Big-M/Hull results and Process GDP runs are outside this comparison.

| Method | Historical HiGHS hits | New SCIP incumbent hits | Both hit | Old only | New only | Neither |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GLOA | 18/21 | 3/21 | 3 | 15 | 0 | 3 |
| LOA | 18/21 | 2/21 | 2 | 16 | 0 | 3 |
| RIC | 18/21 | 7/21 | 7 | 11 | 0 | 3 |
| Total | 54/63 | 12/63 | 12 | 42 | 0 | 9 |

| Method | Historical sum of worker wall seconds | New sum of worker wall seconds |
| --- | ---: | ---: |
| GLOA | 19,116.90 | 15,696.83 |
| LOA | 18,472.27 | 7,987.82 |
| RIC | 19,058.49 | 15,752.95 |

These figures sum measured worker wall time and exclude separate template preparation, preflight and packaging.
They are not process CPU measurements and should not be added across parallel methods to estimate elapsed overnight duration.
Early error termination substantially shortens the new runs, so these times do not demonstrate a SCIP speedup.
The large number of interrupted searches also prevents attributing the hit-rate decrease to the optimization method or SCIP alone.

## Integrity and reproducibility

The exact three supplied ZIP files are copied to results/archives without changing any byte.
Their accompanying new .sha256 files are local checksums, not independently supplied server signatures.
All archive CRCs, internal checksums, available terminal seals, source inventories, result identities and trajectory linkages pass verification.
No previous_attempts or replaced jobs are present in these original split archives.
The original holder_table/GLOA terminal seal references `gams-n_co047e/scip.opt` and `gams-n_co047e/model.gms`, but the old packer excluded the unfinished GAMS temporary directory.
Those two missing temporary files cannot be verified from the supplied archive, and jobs.json records their expected hashes explicitly.
The active final call is counted only as an interface start, without claiming a confirmed SCIP invocation.
The new recovery packer preserves such leftover scratch files for future audits.

The audit baseline is branch revision d9bb8a9218c44c96dae544b504693d66a3daae5b.
Before adding this report, the review worktree was fast-forwarded from df060f6 to preserve the existing upstream CSTR30 publication and Overleaf updates.
No tracked baseline source, raw result, manuscript, Overleaf file or figure is changed by this audit or package preparation.
Preservation is checked against hashes of all 2,060 tracked baseline files in preservation.json.
The dirty main workspace remains separate from the review worktree.
PR 49 was already closed/merged; new commits on review/cstr15-dantzig-results preserve its review branch but do not themselves merge these additions to main.

Reproduce the original-result audit with the recorded Pyomo 6.10.0 analysis environment:

```bash
python scripts/analyze_grid_gdpopt_scip_return.py --output results/grid_gdpopt_scip_20261025
python -m pytest tests/test_grid_gdpopt_scip_return.py tests/test_grid_scip_return.py tests/test_grid_scip_recovery.py -q
```

The first two test modules validate the archived evidence, solver accounting and returned solutions, while the recovery module validates the diagnosed FBBT defect and bounded transport policy without running a benchmark solver.
All 27 audit and recovery regression tests pass, and all three packages pass the independent delivery validator.
The analysis and package validation logs record the actual commands' outcomes.
The archive-level and per-job manifests retain original provider metadata unchanged.
The main machine-readable outputs are [jobs.csv](jobs.csv), [methods.csv](methods.csv), [paired_highs_scip.csv](paired_highs_scip.csv), [failures.json](failures.json), [summary.json](summary.json) and [manifest.json](manifest.json).
