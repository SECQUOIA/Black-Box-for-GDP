# RIC SCIP error-recovery results, 25 October 2026

The supplied recovery archive contains exactly the twelve RIC jobs selected from the original error records.
All twelve return complete feasible solution vectors without an execution or interface error, and ten reach the unchanged reference target.
Nine jobs report optimal termination and three report a time limit.
Two of the optimal-termination jobs, holder_table and shubert, miss the reference and must not be treated as globally solved original GDPs.
This is a separate intervention cohort, and the original 21-job RIC record and all 63 first attempts remain unchanged.
GLOA and LOA recovery archives have not been supplied for this report.

## Results and pairing

| Grid | Original objective | Recovery objective | Recovery termination | Target hit | Worker seconds |
| --- | ---: | ---: | --- | --- | ---: |
| bohachevsky2 | 0.333333333333 | 0 | optimal | Yes | 1071.92 |
| camel3 | 0.000477449983045 | 0 | maxTimeLimit | Yes | 1789.04 |
| deflected_corrugated_spring | 0.374544109062 | 0 | optimal | Yes | 1060.99 |
| dropwave | 0.632717247663 | 0 | optimal | Yes | 1377.73 |
| griewank | 0.502194289286 | 0 | optimal | Yes | 1036.02 |
| holder_table | 0.145167239953 | 0.145167239953 | optimal | No | 1513.21 |
| hosaki | 0.784469039352 | 0 | optimal | Yes | 1630.77 |
| levy | 0.158670286876 | -1.45669888809e-19 | maxTimeLimit | Yes | 1789.39 |
| levy13 | 0.190751445087 | 0 | optimal | Yes | 1702.11 |
| rastrigin | 0.0746019317438 | 0 | optimal | Yes | 1280.74 |
| shubert | 0.466379684039 | 0.0824278107512 | optimal | No | 1238.58 |
| styblinski_tang | 0 | 0 | maxTimeLimit | Yes | 1790.67 |

All twelve paired original records have status=error and are retained, even when a feasible or target incumbent was returned before the error.
Within the selected cohort, verified target incumbents increase from 1/12 to 10/12, and target hits without an execution error increase from 0/12 to 10/12.
There is one paired hit in both attempts, nine recovery-only hits, no original-only hit and two misses in both attempts.
The existing styblinski_tang target incumbent is retained in the original count rather than being erased because its enclosing job failed.
The recovery time limits are camel3, levy and styblinski_tang, and all three returned target incumbents before termination.
A time-limited target incumbent supports the target-hit statistic but does not establish a solver optimality certificate.
All returned solutions contain 64 original variable values, and independent checks cover bounds, integrality, exclusive disjunct selection, active original constraints and the analytic objective.
The maximum recomputed original constraint/bound violation is 0.0, and the maximum saved-to-recomputed objective difference is 1.4566988880917495e-19.
The target remains normalized CSV objective minus the same CSV minimum <= 1e-5.
The model and CSV agree across all 961 coordinates for each of the twelve grids, for 11,532 checked analytic grid values.

## Descriptive RIC inventory after recovery

| Record | Target incumbents | Target without error | Errors | Reported optimal | Time limits |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original 21 first attempts | 7/21 | 6/21 | 12 | 6 | 3 |
| Nine retained attempts plus twelve recovery attempts | 16/21 | 16/21 | 0 | 15 | 6 |

The descriptive 16/21 inventory is a mixture of recovery and retained first attempts, not a uniform new 21-job experiment or a replacement first-attempt success rate.
The nine unselected first attempts remain unchanged, including the three target-missing time limits alpine2, easom and michalewicz.
The file ric_21_descriptive.csv records the selected attempt, archive and result hash for each grid.
No cross-method recovery success rate is calculated while the other recovery returns are unavailable.

## Optimal-termination mismatches and follow-up

holder_table returns objective 0.14516723995340786 at [30,1], whereas the unchanged reference minimum is 0.0.
shubert returns objective 0.08242781075119937 at [17,21], whereas the unchanged reference minimum is 0.0 at [17,22].
Their reported lower bounds equal these worse incumbents and exceed the known feasible reference minimum, so they cannot be valid lower bounds for the original GDP.
The returned grid and binary trajectories agree that holder_table selects the four reference coordinates [3,1], [3,29], [27,1] and [27,29] in its discrete solves, at iterations 153, 152, 695 and 542 respectively.
The shubert reference coordinate [17,22] appears after its discrete solve at iteration 478.
None of these five selections reaches the before_subproblem callback or becomes a target incumbent.
Both runs subsequently report that all feasible discrete configurations have been explored or cut off and terminate as optimal.
Independent original-GDP witnesses at all five coordinates are feasible and satisfy the target criterion.
A local replay of common GDPopt preprocessing with Pyomo 6.10.0 and the RIC default tolerances rejects all five witnesses through InfeasibleConstraintException.
The holder_table replay generates contradictory bounds for y during FBBT, and the shubert replay declares a constraint infeasible.
This is consistent with the previously recorded [Grid presolve diagnosis](../grid_scip_20261023/presolve_probe.json), which the network/bohachevsky2 recovery policy did not repair.
The local replay and returned callback sequence support a preprocessing failure explanation, but the local diagnostic is not a full replay of the server internal state at every iteration.
These two cases need a separately validated preprocessing correction followed by new recorded runs before an original-GDP optimum can be claimed.
Repeating the same package does not address the demonstrated defect.
The other three new time limits already meet the target metric, and extending them is only necessary for a separate completion or bound-certification question.
No new recovery package, remote run, model modification or target change is made during this analysis.

## Actual solver calls and recovery behavior

The benchmark journals and anchored execution banners both confirm 18,349 SCIP MIP calls, all returned normally.
There are zero benchmark NLP calls and zero benchmark interface errors.
The separate preflight contains one SCIP MIP and two SCIP NLP calls and is excluded from benchmark counts.
The logs identify SCIP 9.2.4 (a94f778ac8), GAMS 52.2.0 and Pyomo 6.10.0.
The recorded GAMS executable hash and Python/package versions match the original RIC environment.
The worker retains CPU 12, a one-thread environment, a shared 1,800-second job limit, relative gap 1e-5, disabled warm starts and the delivered SCIP options.
The twelve worker intervals do not overlap.
No network_recovery journal or failed interface call appears, so the network retry wrapper is not exercised in this return.
The disappearance of network errors therefore does not demonstrate that the retry mechanism recovered an observed failure.
The bohachevsky2 fixed-exponent safeguard records 280 bound resets and the job reaches its target.
Its original RIC error was a network-session close failure, so this pair alone does not isolate the safeguard effect.
The original twelve RIC errors comprised ten network-session start failures and two close failures, and their records remain preserved.

## Measured cost

The sum of recovery worker wall time is 17,281.173 seconds, approximately 4 hours 48 minutes.
The first-worker start to final-worker completion spans 17,283.168 seconds, excluding initial preflight and final packaging.
The recorded solver-interface call times sum to 13,317.494 seconds within the worker totals.
The same twelve original failed attempts consumed 6,288.755 worker seconds, and their shorter durations are not evidence of better solve performance.
The complete original 21-job RIC cohort plus all twelve recovery attempts consumes 33,034.125 recorded worker seconds, approximately 9 hours 11 minutes.
The descriptive mixed inventory contains 26,745.370 worker seconds, which omits the superseded failed-attempt costs and must not be reported as cumulative experiment cost.
All these quantities are recorded wall times, not CPU-time measurements.

## Provenance and validation

The unchanged supplied archive is [grid_gdpopt_scip_20261025_180435_dv1cn3et.zip](../archives/grid_gdpopt_scip_20261025_180435_dv1cn3et.zip).
Its SHA-256 is 12cb50af02ef7621aca15dbc73b3972256ad8ca209f876a670badec52ce1abad.
The outer checksum was calculated locally because no independent server checksum sidecar was supplied.
All 213 internal checksum entries and every terminal seal pass, with no omitted sealed file or replaced job.
All 68 executed source files match the delivered recovery package, including the unchanged 60 base-package files.
The recovery selection matches all twelve original RIC errors and binds each one to its original result hash.
The exact raw logs, complete trajectories, solution vectors, source inventories and runtime records remain in the supplied ZIP.
The analysis source revision identifies the analysis checkout, while the delivered package hashes identify execution without inventing a new provider revision.
The original manifests, raw archives, manuscript, Overleaf files and representative figures are unchanged.
The numerical comparisons are in jobs.csv, paired_runs.csv and summary.json.
The returned target-coordinate events and local witness/preprocessing probes are in target_path_events.json and target_mismatch_diagnostics.json.
The manifest records actual runtime settings, analysis source hashes and local Pyomo diagnostic-module hashes.
All 31 related tests pass, and all 10 generated audit outputs reproduce byte-for-byte in a fresh independent replay.
No optimization solver is called during the audit, witness construction or local preprocessing diagnostic.

## Reproduce the audit

From the repository root, use an existing Python environment with Pyomo 6.10.0 and the repository analysis dependencies.
Choose an empty output directory to preserve this report.

```bash
python scripts/analyze_grid_scip_recovery_ric_return.py --output /tmp/grid_ric_recovery_audit
python -m pytest tests/test_grid_scip_recovery_ric_return.py tests/test_grid_scip_return.py tests/test_grid_gdpopt_scip_return.py tests/test_grid_scip_recovery.py -q
```

PR 49 is already merged, so this record is retained on review/cstr15-dantzig-results as a post-merge follow-up and is not automatically added to main.
