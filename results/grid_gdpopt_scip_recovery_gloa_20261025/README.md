# GLOA SCIP error-recovery results, 25 October 2026

The supplied archive contains exactly the fifteen GLOA jobs selected from the original error records.
All fifteen return complete feasible solution vectors without an execution or interface error, and fourteen reach the unchanged reference target.
Fourteen jobs report optimal termination and one reports a time limit.
The optimal-termination job michalewicz misses the reference and must not be treated as a globally solved original GDP.
This is a separate recovery cohort, and the original 21-job GLOA record and all 63 first attempts remain unchanged.
The RIC recovery is already available, while the LOA recovery has not been supplied for this report.

## Results and pairing

| Grid | Original objective | Recovery objective | Recovery termination | Target hit | Worker seconds |
| --- | ---: | ---: | --- | --- | ---: |
| ackley | 0.71163551499 | -3.11708557145e-17 | optimal | Yes | 1035.17 |
| alpine2 | 0.067232632911 | 0 | optimal | Yes | 1487.75 |
| bohachevsky2 | 0.333333333333 | 0 | optimal | Yes | 1059.44 |
| camel3 | 0.00823601220753 | 0 | optimal | Yes | 1709.83 |
| deflected_corrugated_spring | 0.327236476179 | 0 | optimal | Yes | 1032.61 |
| dropwave | 0.712592729024 | 0 | optimal | Yes | 1085.96 |
| easom | 0.872286613186 | 0 | optimal | Yes | 1508.09 |
| griewank | 0.00888939076362 | 0 | optimal | Yes | 1075.07 |
| hosaki | 0.462962962963 | 0 | optimal | Yes | 1691.01 |
| levy | 0.0262415542784 | -1.45669888809e-19 | optimal | Yes | 1778.98 |
| michalewicz | 0.444774584349 | 0.0864917048203 | optimal | No | 1558.12 |
| rastrigin | 0.0149270033742 | 0 | optimal | Yes | 1263.61 |
| rosenbrock | 0.149371190495 | 0 | optimal | Yes | 1060.71 |
| styblinski_tang | 0.01068955134 | 0 | maxTimeLimit | Yes | 1789.31 |
| sum_of_squares | 0.00444444444444 | 0 | optimal | Yes | 1243.00 |

Every selected original record has status=error and remains preserved.
The fifteen paired target counts increase from 0/15 to 14/15, with fourteen recovery-only hits, no original-only hit, no hit in both attempts and one miss in both attempts.
The sole new time limit, styblinski_tang, returns its target incumbent before termination.
A time-limited target incumbent supports the target-hit statistic but does not establish a solver optimality certificate.
All fifteen returned solutions contain 64 original variable values, and independent checks cover bounds, integrality, exclusive disjunct selection, active original constraints and the analytic objective.
The maximum recomputed original constraint/bound violation is 0.0, and the maximum saved-to-recomputed objective difference is 3.117085571445524e-17.
The target remains normalized CSV objective minus the same CSV minimum <= 1e-5.
All 961 lattice coordinates are evaluated analytically for each of the fifteen grids, for 14,415 checked values, with no optimizer call.
The tiny negative recomputed ackley objective is floating-point roundoff relative to the unchanged zero CSV reference.

## Descriptive GLOA inventory after recovery

| Record | Target incumbents | Target without error | Errors | Reported optimal | Time limits |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original 21 first attempts | 3/21 | 3/21 | 15 | 4 | 2 |
| Six retained attempts plus fifteen recovery attempts | 17/21 | 17/21 | 0 | 18 | 3 |

The descriptive 17/21 inventory is a mixture of recovery and retained first attempts, not a uniform new 21-job experiment or a replacement first-attempt success rate.
The six unselected first attempts remain unchanged.
The four remaining target misses in this mixed inventory are holder_table, levy13, shubert and michalewicz.
The retained holder_table and levy13 attempts end at time limits, and the retained shubert attempt reports optimal despite missing the reference.
The error-only recovery selection deliberately excludes those three non-error attempts, so the new zero-error count does not imply that every original GDP has been solved correctly.
The file gloa_21_descriptive.csv records the selected attempt, archive and result hash for each grid.

## Michalewicz mismatch and follow-up

The returned objective is 0.08649170482029742 at [22,15], whereas the unchanged reference minimum is 0.0 at [21,15].
The reported lower and upper bounds are both 0.086491704820297 and exceed the known feasible reference minimum, so the reported lower bound is not valid for the original GDP.
The returned discrete trajectory selects the reference coordinate [21,15] at iteration 671, elapsed time 899.0933273758274 seconds and 977 completed solver calls.
That selection never reaches the before_subproblem callback and does not become an incumbent.
The run subsequently reports that all feasible discrete configurations have been explored or cut off and terminates as optimal.
An independently constructed original-GDP witness at [21,15] is feasible, has zero maximum original violation and satisfies the unchanged target criterion.
A solver-free local probe of common GDPopt preprocessing with Pyomo 6.10.0 and the GLOA default tolerances rejects that witness during feasibility-based bound tightening (FBBT).
The exact local exception is recorded below.

```text
InfeasibleConstraintException: Lower bound (2.199114857512855) computed for variable x is larger than the computed upper bound (0.9424777960769378).
```

The returned callback evidence and local probe support a false preprocessing rejection, consistent with the earlier Grid presolve diagnosis and the RIC recovery mismatches.
The local probe is not a full replay of the Dantzig internal state at every iteration, and its constructed witness is not presented as a returned solution.
A separately validated preprocessing correction and a new recorded run are needed before claiming a globally solved original michalewicz GDP.
Repeating the same package does not address the demonstrated defect.
The retained shubert mismatch and the RIC holder_table/shubert mismatches remain relevant to that correction.
No new remote optimization, preprocessing patch, reference change or recovery ZIP is created during this audit.

## Comparison with the RIC recovery

The RIC recovery contains twelve selected errors and ten target hits, whereas the GLOA recovery contains fifteen selected errors and fourteen target hits.
Those different selected cohorts do not support a method ranking from 10/12 versus 14/15.
The nine common recovered problems are bohachevsky2, camel3, deflected_corrugated_spring, dropwave, griewank, hosaki, levy, rastrigin and styblinski_tang.
Both methods reach the unchanged target on all nine common problems.
The common-grid objectives, terminations and worker times are recorded in paired_common_ric_gloa.csv.
The RIC input is verified against its committed artifact checksum, whose value is retained in ric_gloa_recovery_comparison.json.
The existing RIC report is preserved as the earlier record, including its then-current statement that the GLOA return was unavailable.

## Actual solver calls and recovery behavior

The benchmark journals and anchored execution banners confirm 22,280 SCIP MIP calls, all returned normally.
There are zero benchmark NLP calls and zero benchmark interface errors.
The separate preflight contains one SCIP MIP and two SCIP NLP calls and is excluded from benchmark counts.
Thus SCIP is actually invoked for the discrete subproblems, while these fixed-coordinate Grid benchmarks do not require a benchmark NLP solver call.
The logs identify SCIP 9.2.4 (a94f778ac8), GAMS 52.2.0, Python 3.11.16 and Pyomo 6.10.0.
The recorded GAMS executable hash, Python/package versions and MC++ library hash match the original GLOA environment.
The worker retains CPU 16, physical core 20, SMT siblings 16 and 64, and effective affinity [16].
Affinity is not an exclusive core reservation, and these data do not isolate a CPU-placement effect.
The one-thread environment, shared 1,800-second job budget, relative gap 1e-5, disabled warm starts and delivered SCIP options are retained.
The SCIP option-file entries are gams/mipstart = 0 and timing/clocktype = 2.
The fifteen worker intervals do not overlap.
No network_recovery journal or failed interface call appears, so the network retry wrapper is not exercised in this return.
The disappearance of network errors therefore does not demonstrate that the wrapper recovered an observed network failure.
The original fifteen errors comprised twelve network-session start failures, two close failures and one Pyomo FBBT interval failure.
The original FBBT interval failure belongs to bohachevsky2, whose recovery records 280 fixed-exponent bound resets and reaches the target.
That safeguard does not repair the separate demonstrated michalewicz false rejection.

## Measured cost

The sum of recovery worker wall time is 20,378.653 seconds, approximately 5 hours 40 minutes.
The first-worker start to final-worker completion spans 20,381.645 seconds, excluding initial preflight and final packaging.
The recorded solver-interface call times sum to 15,717.482 seconds within the worker totals.
The same fifteen original failed attempts consumed 10,340.357 worker seconds, and their shorter durations are not evidence of better solve performance.
The complete original 21-job GLOA cohort plus all fifteen recovery attempts consumes 36,075.483 recorded worker seconds, approximately 10 hours 1 minute.
The descriptive mixed inventory contains 25,735.125 worker seconds, which omits superseded failed-attempt costs and must not be reported as cumulative experiment cost.
These are recorded wall times, not CPU-time measurements.

## Provenance and validation

The unchanged supplied archive is [grid_gdpopt_scip_20261025_180450_9ac86u_v.zip](../archives/grid_gdpopt_scip_20261025_180450_9ac86u_v.zip).
Its SHA-256 is 3f8df01e2012ee780e19478a5bfa7c92978d0f471b27d91031db11799a445d90.
The outer checksum was calculated locally because no independent server checksum sidecar was supplied.
All 248 internal checksum entries and every terminal seal pass, with no omitted sealed file or replaced job.
All 68 executed source files match the delivered recovery package, including 60 unchanged base-package files.
The recovery selection matches all fifteen original GLOA errors and binds each to its original result hash.
The exact raw logs, complete trajectories, solution vectors, source inventories and runtime records remain in the supplied ZIP.
The manifest records the analysis source revision and hashes, delivered package hashes, actual runtime settings and local Pyomo diagnostic-module hashes without changing the provider revision.
The numerical comparisons are in jobs.csv, paired_runs.csv and summary.json.
The returned target-coordinate events and local witness/preprocessing probes are in target_path_events.json and target_mismatch_diagnostics.json.
All 31 related tests pass, and all 12 generated audit outputs reproduce byte-for-byte in a fresh replay.
All 2,258 previously tracked files retain their original hashes, including existing reports, raw archives, manuscript, Overleaf files and representative figures.
The main checkout remains at its original clean revision.
The preservation and replay records provide the corresponding machine-readable checks.
No optimization solver is called during the audit, witness construction or local preprocessing diagnostic.

## Reproduce the audit

From the repository root, use a Python environment with Pyomo 6.10.0 and the repository analysis dependencies.
Choose an empty output directory to preserve this report.

```bash
python scripts/analyze_grid_scip_recovery_gloa_return.py --output /tmp/grid_gloa_recovery_audit
python -m pytest tests/test_grid_scip_recovery_gloa_return.py tests/test_grid_scip_return.py tests/test_grid_gdpopt_scip_return.py tests/test_grid_scip_recovery.py -q
```

PR 49 is already merged, so this record is retained on review/cstr15-dantzig-results as a post-merge follow-up and is not automatically added to main.
