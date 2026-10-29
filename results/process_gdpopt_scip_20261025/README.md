# Process GDPopt with SCIP: returned-result audit

The October 25 Process return contains 27 terminal jobs and 26 independently verified feasible solution vectors.
The comparison uses nine instances and one run of each GDPopt method, so counts across instances are not estimates of a repeated-seed success probability.
The NLP subsolver was actually SCIP, while the MIP master remained HiGHS.
The fixed-reference target count changes from 7/27 in the selected October 1 BARON runs to 13/27 in this SCIP return.
No optimization solver was invoked during this analysis.

## Method comparison

| Method | Verified returned solutions | BARON target hits | SCIP target hits | Both hit | SCIP only | BARON only | Neither | SCIP time limits | SCIP errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GLOA | 9/9 | 1/9 | 1/9 | 1 | 0 | 0 | 8 | 2 | 0 |
| LOA | 9/9 | 3/9 | 6/9 | 3 | 3 | 0 | 3 | 3 | 0 |
| RIC | 8/9 | 3/9 | 6/9 | 3 | 3 | 0 | 3 | 3 | 1 |

The reference values and primary rule are unchanged from `results/gdp_comparison_current/analysis/comparison.csv` and `nlp_cost_analysis.target_hit`.
The primary rule is `abs(objective - reference) <= 1e-5 * max(1, abs(reference))` on the final saved feasible objective.
The separate minimization-attainment rule is `objective <= reference + 1e-5 * max(1, abs(reference))`.
Under the attainment rule, BARON → SCIP counts are GLOA 1 → 1, LOA 4 → 6, and RIC 3 → 6.
LOA newly matches the absolute target for CSTR15, CSTR20, and CSTR25; RIC newly matches it for CSTR15, CSTR25, and CSTR30.
For CSTR15, the old BARON LOA objective 2.82935061823614 is lower than the reference 2.82939406018371, but lies outside its absolute tolerance.
The new SCIP LOA objective 2.82939406035249 matches that reference, so this additional absolute hit is not an improvement of the objective over BARON.
All 27 jobs remain in the denominator, including the missing Column RIC solution and the CSTR20 RIC error.

## Returned objectives and completion costs

The cells below show the independently recomputed objective and method wall seconds, with the watchdog clock used only when the method clock was not returned.
An asterisk marks a fixed-reference target hit, `T` marks time-limit termination, and `E` marks error termination.
The full-precision results, status fields, reference gaps, and clock provenance are in [jobs.csv](jobs.csv).

| Instance | Reference | GLOA objective; seconds | LOA objective; seconds | RIC objective; seconds |
|---|---:|---:|---:|---:|
| cstr_5 | 3.0620145764 | 3.130193364; 3.33 | 3.062009678 *; 51.86 | 3.062009678 *; 47.07 |
| cstr_10 | 2.8895369681 | 3.447953948; 4.05 | 2.889536968 *; 115.62 | 2.889536968 *; 112.27 |
| cstr_15 | 2.8293940602 | 3.522578602; 5.54 | 2.82939406 *; 345.56 | 2.82939406 *; 383.41 |
| cstr_20 | 2.7994002269 | 3.61611301; 5.43 | 2.799406418 *; 682.48 | 2.804132823; 674.89 E |
| cstr_25 | 2.7814824331 | 3.647817962; 6.52 | 2.781482593 *; 1254.43 | 2.781482593 *; 1300.25 |
| cstr_30 | 2.7695697148 | 3.154339315; 8.96 | 2.773820703; 1789.79 T | 2.76956972 *; 1792.58 T |
| column | 19346.124726 | 22271.549; 1791.33 T | 22271.549; 1791.29 T | no saved solution; 1800.03 T |
| small_batch | 167427.65711 | 167427.6514 *; 14.29 | 167427.6514 *; 19.67 | 167427.6514 *; 24.22 |
| dynamic | -212.00878719 | -119.3831027; 1790.96 T | -119.3831027; 1790.99 T | -119.3831027; 1790.94 T |

The sum of method/watchdog completion clocks is 19,397.795 s (5.39 h), and the sum of worker clocks is 19,398.232 s.
Template preparation counted once per instance adds 1.896 s; preflight, controller gaps, and packaging are outside these sums.
For compatibility with the previous comparison, per-job completion plus template preparation sums to 19,403.483 s for SCIP and 26,556.535 s for BARON.
This per-job convention charges a shared template once to each method and is not the end-to-end elapsed duration of the archive.
The observed aggregate is smaller, but the changed solver adapter, added tracing, watchdog behavior, and the early CSTR20 RIC error prevent attribution of the entire difference to NLP solver speed.
CPU affinity is recorded as provenance and is not used as a causal explanation.
These are completion costs, not time-to-first-target costs.

## Interpretation and incomplete runs

All six CSTR GLOA runs stop with `termination=optimal` after only two recorded NLP subproblem attempts per instance.
Each reported GLOA lower bound exceeds a lower feasible objective independently verified in the same returned archive.
These six bound counterexamples invalidate use of those bounds or the `optimal` text as global optimality certificates.
The [October 23 diagnostics](../../diagnostics/gdpopt_20261023/REPORT.md) contain the earlier CSTR15 cut investigation, but this audit does not infer the same cut-level cause for every new result.
No new FBBT or GLOA cut patch was applied in this run; the archived correction policy is `Existing pyomo610-grid-v1 only; no new FBBT or GLOA patches`.
All analysis rows retain `global_optimality_certified=false`; feasible returns and reference hits are separate from a global certificate.

CSTR20 RIC retains the feasible objective 2.80413282307673 but stops at call 401, a HiGHS MIP call.
Its log reports `Error when trying to close network session` and `Curl error: Server returned nothing (no headers, no data)`.
The associated listing reports normal HiGHS completion, while the Python/GAMS interface raises an error, so this evidence identifies an interface/network failure rather than a demonstrated SCIP NLP failure.
The job was not retried or replaced.

Column RIC reaches the 1,800 s watchdog with no saved `solution.json`.
Its log contains a SCIP time-limit exit and primal bound about 22271.549, but the wrapper never records the second call as returned or saves a validated incumbent.
That log bound is not counted as a returned solution.
The terminal seal lists five temporary GAMS files, including `results.dat`, that the packer intentionally omits with all `gams-*` directories.
Their hashes are retained in [manifest.json](manifest.json), but their absent contents cannot be validated or used to recover a solution from this archive.

Column GLOA/LOA and all three Dynamic methods return feasible incumbents when their first SCIP NLP reaches its time limit without the required global subproblem completion.
The returned Column objective is 22271.549001229178 against reference 19346.12472619312, and the Dynamic objective is -119.38310274514966 against reference -212.00878719112268.
These five jobs stop before continued GDPopt exploration and do not match their references.
CSTR30 LOA and RIC have raw `status=finished` but `termination=maxTimeLimit`, and the analysis classifies both as time-limited.
CSTR30 RIC nevertheless returns a target-matching incumbent, 2.76956971984611.
CSTR30 still uses constructor defaults with no upstream saved initialization in this archive, so this is not the separate material-balance/zero-recycle initialization experiment.

## Actual solver and environment evidence

The journals contain 2,368 HiGHS MIP calls and 2,341 SCIP NLP calls, including the failed HiGHS interface call.
One additional SCIP NLP call is evidenced by Column RIC `active_solver_call.json` and its full solver log, giving 2,342 actual started SCIP NLP calls and 4,710 total started benchmark calls.
The archived summary reports only journaled calls and therefore omits this one interrupted wrapper return.
Preflight contributes one separate HiGHS MIP and one separate SCIP NLP call and is excluded from benchmark totals.
The logged solver-call wall sum is 15,637.467 s and excludes the unjournaled Column RIC call, so it is not a complete solver-time total.
Logs identify SCIP 9.2.4, HiGHS 1.12.0, and SCIP’s linked Ipopt 3.14.19.
GAMS is 52.2.0, Python is 3.11.16, and Pyomo is 6.10.0 on Dantzig.
The run uses CPU 8, one thread, relative gap 1e-5, absolute gap zero, and a 1,800 s per-method worker budget.
SCIP options are `gams/mipstart = 0` and `timing/clocktype = 2`.
Previous BARON NLP subproblems used BARON with CLP and IPOPT subsolvers, while their MIP master also used HiGHS.
The selected BARON runs and the new return share the GAMS executable hash, Python/Pyomo versions, upstream model and initialization hashes, initialization labels, and recorded template bound tightening for all 27 pairs.
The frozen Python runner sources differ, including SCIP status-7 gap handling, tracing and watchdog instrumentation, so this is a comparison of returned runs with documented differences rather than a controlled single-code-change speed test.

## Integrity, solution validation, and scope

The received archive SHA-256 is `8f4fe4ecddb0e448ff667f80f7b32df2c26f6bfca12656e9ed3ebea87d0fe8d8`.
The outer sidecar stored beside it is locally calculated because no server-generated sidecar was present in Downloads.
All 1,846 internal checksum entries, 75 run-source hashes, 74 package-file hashes, and 1,728 present terminal-seal entries match.
Terminal seals are fully verifiable for 26 jobs; Column RIC has the five disclosed packer omissions.
The two user-mentioned checksum files instead authenticate the October 23 diagnostic package with SHA-256 `424b615ca564bac6a7a9c4e05b9f19e98e307d1982d9e15e2617519e8c2a28e6`.
That package passes its 231 internal and 235 external checksum checks and records zero optimization solver calls.
The old diagnostic package is preserved and is not substituted for the new Process return.

The independent validator rebuilds the original GDPs from the returned frozen source and checks objective, original constraints, selected disjuncts, Boolean logic, XOR/OR conditions, variable bounds, fixed values, and integrality.
Dynamic uses the archived 30-element, three-point Radau discretization and derivative bounds.
The audit does not invoke FBBT, GDPopt, GAMS, SCIP, BARON, or IPOPT.
It checks 10,974 serialized variable values across 26 feasible vectors, with maximum original-model violation 9.428052587384661e-7 against tolerance 1e-5.
The two Column vectors each omit unused `H_V[benzene,17]` and `H_V[toluene,17]`; the audit clears their values and confirms that all evaluated constraints and objectives remain defined, rather than filling them from initialization.
Full original vectors, logs, incumbent histories and 7,045 GDP path events remain in the unchanged ZIP.
The compact [path index](gdp_path_events.csv) retains event order, elapsed times, call indices, CSTR external coordinates, and assignment hashes linking back to the complete binary values in the ZIP.
The archive records exact executed source hashes and upstream commits but no repository-level execution revision, and the manifest reports that missing revision explicitly.
Analysis runs locally with Python 3.13.12 and Pyomo 6.10.0; this environment difference concerns saved-vector evaluation only.
The prior BARON selection, raw data, manuscript, Overleaf material, and figures are preserved.
This separate report does not promote the new SCIP results to manuscript representative results.

## Reproduction and files

From the repository root, use an environment with Pyomo 6.10.0 and the frozen models’ Python dependencies installed.

```sh
python scripts/analyze_process_scip_return.py --output /tmp/process-scip-reproduced
python -m pytest tests/test_process_scip_return.py -q
```

The analyzer verifies archive identities before loading the frozen sources and guards against construction of any optimization solver.
[paired_baron_scip.csv](paired_baron_scip.csv) contains all 27 historical/current pairs and model-provenance equality checks.
[methods.csv](methods.csv) and [summary.json](summary.json) contain aggregate counts and costs.
[solver_calls.csv](solver_calls.csv), [issues.json](issues.json), and [solution_checks.json](solution_checks.json) retain call accounting, incomplete-run details, and independent validation evidence.
[manifest.json](manifest.json) records input hashes, environment, solver settings, historical sources, source identities, and checksum limitations.
[tests.log](tests.log) records 11 passing tests, including byte-for-byte regeneration of all nine derived data files, and [preservation.json](preservation.json) records unchanged hashes for all 1,974 pre-existing tracked files.
[artifact_checksums.json](artifact_checksums.json) seals the report, data, validation records, analyzer, tests, and received archive.
The archive is [results/archives/process_gdpopt_scip_20261025_003203_eqiw7649.zip](../archives/process_gdpopt_scip_20261025_003203_eqiw7649.zip).
The report is stored on `review/cstr15-dantzig-results`, the branch associated with already-merged PR 49; this follow-up commit does not imply a new merge into main.
