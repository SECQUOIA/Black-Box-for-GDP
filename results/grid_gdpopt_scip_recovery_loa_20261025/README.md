# LOA SCIP error-recovery results, 25 October 2026

The supplied archive contains exactly the nineteen LOA jobs selected from the original error records.
All nineteen return complete feasible solution vectors without an execution or solver-interface error, and sixteen reach the unchanged target.
Sixteen jobs report optimal termination, but holder_table, michalewicz and shubert miss the known reference minimum despite that status.
The three time-limited jobs, camel3, hosaki and styblinski_tang, all return target incumbents.
The [three-method comparison](../grid_gdpopt_scip_recovery_comparison_20261025/README.md) combines this audit with the previously preserved RIC and GLOA audits.

## Returned results

| Grid | Original objective | Recovery objective | Recovery termination | Target hit | Worker seconds |
| --- | ---: | ---: | --- | --- | ---: |
| ackley | 0.185129697572 | -3.11708557145e-17 | optimal | Yes | 1070.52 |
| alpine2 | 0.067232632911 | 0 | optimal | Yes | 1520.06 |
| bohachevsky2 | 0.333333333333 | 0 | optimal | Yes | 1102.27 |
| camel3 | 0.00823601220753 | 0 | maxTimeLimit | Yes | 1793.81 |
| csendes | 0.0831184498223 | 1.98083506531e-08 | optimal | Yes | 71.50 |
| deflected_corrugated_spring | 0.586566395815 | 0 | optimal | Yes | 1213.47 |
| dropwave | 0.858915094867 | 0 | optimal | Yes | 1171.04 |
| easom | 0.990638096199 | 0 | optimal | Yes | 1556.17 |
| griewank | 0.502194289286 | 0 | optimal | Yes | 1088.36 |
| holder_table | 0.145167239953 | 0.145167239953 | optimal | No | 1623.76 |
| hosaki | 0.421875 | 0 | maxTimeLimit | Yes | 1790.63 |
| levy | 0.12668295837 | -1.45669888809e-19 | optimal | Yes | 1758.27 |
| levy13 | 0.263005780347 | 0 | optimal | Yes | 1762.14 |
| michalewicz | 0.444774584349 | 0.0864917048203 | optimal | No | 1490.76 |
| rastrigin | 0.0149270033742 | 0 | optimal | Yes | 1415.64 |
| rosenbrock | 0.0402526260099 | 0 | optimal | Yes | 1265.56 |
| shubert | 0.49457510048 | 0.0824278107512 | optimal | No | 1278.45 |
| styblinski_tang | 0.165386931647 | 0 | maxTimeLimit | Yes | 1789.13 |
| sum_of_squares | 0.62962962963 | 0 | optimal | Yes | 1109.38 |

The original nineteen error records remain unchanged, and the paired target count changes from 0/19 to 16/19.
There are sixteen recovery-only hits, no original-only hit, no paired hit in both attempts and three misses in both attempts.
All returned vectors contain 64 original variable values and pass independent bounds, integrality, exclusive-disjunct and active-original-constraint checks.
The maximum original violation is 0.0, and the maximum saved-to-recomputed objective difference is 3.117085571445524e-17.
The same analytic objectives are checked across 961 coordinates per grid, or 18,259 lattice values in total.
The target remains normalized CSV objective minus its unchanged minimum <= 1e-5.
Tiny floating-point differences near zero are retained in the numerical records.
The csendes objective is within that tolerance even though it is not exactly zero.
The descriptive inventory combines these nineteen recoveries with the two unchanged first attempts, alpine1 and xin_she_yang3, giving 18/21 target hits compared with 2/21 originally.
This mixture is not a uniformly rerun 21-job experiment and does not replace the original first-attempt record.

## The three optimal-termination mismatches

| Grid | Returned point | Returned objective | Reference minimum | Reference points checked |
| --- | --- | ---: | ---: | --- |
| holder_table | [30,1] | 0.14516723995340786 | 0 | [3,1], [3,29], [27,1], [27,29] |
| michalewicz | [22,15] | 0.08649170482029742 | 0 | [21,15] |
| shubert | [17,21] | 0.08242781075119937 | 0 | [17,22] |

Each reported lower bound equals the worse incumbent and exceeds a known feasible original-GDP objective, so it is not a valid lower bound for the original problem.
The returned discrete trajectory selects all six reference coordinates exactly once, and none reaches a before_subproblem callback.
The holder_table reference points occur at iterations 153, 152, 695 and 542 in the table's listed order.
The michalewicz reference point occurs at iteration 671, and the shubert reference point occurs at iteration 478.
Independent original-GDP witnesses at all six points are feasible and satisfy the unchanged target criterion.
A solver-free local probe of common GDPopt preprocessing under Pyomo 6.10.0 and LOA default tolerances rejects all six through InfeasibleConstraintException.
The holder_table probes produce contradictory bounds for y, the michalewicz probe produces contradictory bounds for x, and the shubert probe declares a constraint infeasible.
The exact exceptions, original-GDP witnesses and returned callback evidence are preserved in target_mismatch_diagnostics.json.
This supports a false preprocessing rejection shared with the previously diagnosed RIC and GLOA cases.
It does not identify a SCIP core defect, and the local probe is not a full replay of every internal Dantzig iteration state.
A separately validated preprocessing correction and new recorded runs are needed before claiming these three original GDPs are globally solved.
Repeating the unchanged package or merely extending its time limit does not address this demonstrated defect.
The three new time limits already satisfy the target metric, though they do not provide solver optimality certificates.
No remote optimization, model correction or new recovery package is created in this analysis.

## Solver, environment and recovery behavior

The benchmark journals and anchored banners confirm 26,877 SCIP MIP calls, all returned normally, with zero benchmark NLP calls.
The separate preflight has one SCIP MIP and two SCIP NLP calls and is excluded from benchmark counts.
SCIP 9.2.4 (a94f778ac8), GAMS 52.2.0, Python 3.11.16 and Pyomo 6.10.0 match the recorded baseline environment.
The GAMS executable hash and Python package versions match the original LOA run.
The LOA runtime records no MC++ library hash, as in the original LOA record.
CPU affinity is [14], physical core 18, with SMT siblings 14 and 62, and the recorded thread environment is uniformly one thread.
Affinity is not an exclusive core reservation.
The original shared 1,800-second job budget, relative gap 1e-5, disabled warm starts and SCIP options gams/mipstart = 0 and timing/clocktype = 2 are retained.
All nineteen worker intervals are sequential within the LOA package.
There are no network retry events or interface failures, so this return does not exercise the network retry wrapper.
The original LOA errors consist of ten network-session start failures, eight session-close failures and one bohachevsky2 FBBT interval failure.
The bohachevsky2 recovery records 280 fixed-exponent bound resets and reaches its target, while the separate false-rejection defect remains.

## Measured cost

The nineteen recovery workers consume 25,870.924 recorded wall seconds, approximately 7 hours 11 minutes.
The first-worker start to final-worker completion spans 25,875.324 seconds, excluding initial preflight and final packaging.
Solver-interface call times sum to 19,804.498 seconds within the worker totals.
The nineteen failed original attempts consumed 7,962.359 worker seconds, and shorter failed attempts are not evidence of better solve performance.
All original 21 LOA attempts plus the nineteen recoveries consume 33,858.744 worker seconds, approximately 9 hours 24 minutes.
The mixed 21-job inventory contains 25,896.385 worker seconds and omits superseded failure costs, so it is not cumulative experiment cost.
These are wall-time measurements, not CPU-time measurements.

## Provenance and validation

The unchanged raw archive is [grid_gdpopt_scip_20261025_180441_051rkijg.zip](../archives/grid_gdpopt_scip_20261025_180441_051rkijg.zip).
Its SHA-256 is 69ec44f83c20817a33f51a94ec2e1a3e01ad37031cb3f8c37aae4993eafe1f50.
The outer checksum is calculated locally because an independent server checksum sidecar was not supplied.
All 293 internal checksums and all terminal artifact seals pass.
The 68 executed source files match the delivered recovery package, including 60 unchanged base-package files.
The selection binds exactly the nineteen original LOA errors to their original result hashes.
Raw logs, full trajectories, solution vectors, source inventories and runtime settings remain in the original ZIP.
The manifest records the baseline archive, delivered package, execution settings, analysis source hashes and local diagnostic module hashes without changing provider metadata.
The combined validation runs 42 related tests, including all three recovery audits and the comparison safeguards.
All ten generated LOA audit files reproduce byte-for-byte in a fresh replay.
The [comparison preservation record](../grid_gdpopt_scip_recovery_comparison_20261025/preservation.json) verifies all 2,280 prior tracked regular files, existing submodule state and the clean main checkout.
No original result, prior report, manuscript, Overleaf source or representative figure is modified.

## Reproduce

Use a Python environment with Pyomo 6.10.0 and the repository analysis dependencies, and choose an empty output directory.

```bash
python scripts/analyze_grid_scip_recovery_loa_return.py --output /tmp/grid_loa_recovery_audit
```

The comparison report records the complete test command and three-method replay command.
PR 49 is already merged, so these records are follow-up commits on review/cstr15-dantzig-results and are not automatically included in main.
