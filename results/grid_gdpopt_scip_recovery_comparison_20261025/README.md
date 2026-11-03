# RIC, GLOA and LOA SCIP recovery comparison, 25 October 2026

All three recovery archives are now available and contain exactly the 46 jobs selected from the original execution errors.
All 46 return independently feasible complete solution vectors without an execution or solver-interface error, and 40 reach the unchanged target.
The six recovery misses report optimal termination despite returning values above the known original-GDP minima.
The remaining shared scientific defect concerns false preprocessing rejection in holder_table, michalewicz and shubert, rather than an observed SCIP interface failure in these returns.
On every common recovery subset, the compared methods agree on which problems reach the target.
The numerical ordering of the mixed 21-problem inventories therefore does not establish a method ranking.

## Recovery cohorts

| Method | Target hits | Reported optimal | Optimal but misses | Time limits | Worker hours | SCIP MIP calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RIC | 10/12 | 9 | 2 | 3 | 4.800 | 18,349 |
| GLOA | 14/15 | 14 | 1 | 1 | 5.661 | 22,280 |
| LOA | 16/19 | 16 | 3 | 3 | 7.186 | 26,877 |

All seven new time-limited attempts return target incumbents.
Those attempts count toward target attainment without being labelled solver-certified optima.
The independent audits verify original variable bounds, integrality, active constraints, disjunct selections and objectives, with maximum original constraint/bound violation 0.0.
The target remains normalized CSV objective minus its unchanged minimum <= 1e-5 for all methods and attempts.
The differing recovery denominators are fixed by the original error selection and are not chosen to improve a success rate.
The original first attempts remain preserved, including the RIC styblinski_tang target incumbent returned before an execution error.

## Original and descriptive 21-grid inventories

| Method | Original target incumbents | Original targets without error | Original errors | Retained + recovered | Descriptive target hits |
| --- | ---: | ---: | ---: | --- | ---: |
| RIC | 7/21 | 6/21 | 12 | 9 + 12 | 16/21 |
| GLOA | 3/21 | 3/21 | 15 | 6 + 15 | 17/21 |
| LOA | 2/21 | 2/21 | 19 | 2 + 19 | 18/21 |

The original 63 attempts contain 12 target incumbents, of which 11 are in non-error attempts, plus 46 execution errors and five target-missing time limits.
The descriptive mixed inventory contains 51/63 target hits and no execution error, while retaining every original non-error attempt.
It includes seven optimal-termination misses and five time-limited misses, so zero execution errors is not equivalent to every GDP being solved successfully.
The complete original cost and all failed attempts remain visible rather than being overwritten by the mixed inventory.
The 21-grid matrix with attempt cohort, archive and result hash is in grid_21_comparison.csv.
The individual RIC and GLOA reports remain unchanged as historical records, including their then-current archive-availability statements.

## Same-problem recovery comparisons

| Pair | Common recovered grids | Both hit | First only | Second only | Both miss |
| --- | ---: | ---: | ---: | ---: | ---: |
| RIC / GLOA | 9 | 9 | 0 | 0 | 0 |
| RIC / LOA | 12 | 10 | 0 | 0 | 2 |
| GLOA / LOA | 15 | 14 | 0 | 0 | 1 |

All three methods share nine recovered grids, and all three reach the target on each of those nine.
The shared grids are bohachevsky2, camel3, deflected_corrugated_spring, dropwave, griewank, hosaki, levy, rastrigin and styblinski_tang.
RIC and LOA jointly miss holder_table and shubert in their common recovery subset, while GLOA and LOA jointly miss michalewicz in theirs.
There is no common recovery problem on which one method reaches the target and the paired method does not.
The common_nine_timing records restrict the timing comparison to the same nine problems.

| Method | Target hits | Sum worker seconds | Median worker seconds | Sum recorded first-target seconds |
| --- | ---: | ---: | ---: | ---: |
| RIC | 9/9 | 12827.263 | 1377.732 | 9795.436 |
| GLOA | 9/9 | 12485.822 | 1263.610 | 9496.837 |
| LOA | 9/9 | 13122.622 | 1415.642 | 9959.139 |

GLOA has the smallest recorded worker-time sum on this common subset, but the data contain only one attempt per method and problem under concurrent server activity.
The different nonexclusive CPU affinities and time-limited runs prevent attributing these small timing differences to an intrinsic algorithm or CPU effect.
The first-target times are incumbent callback times within each method run, whereas worker totals also include worker overhead and work performed after reaching the target.
Neither sum is a new equal-budget benchmark or a parallel makespan measurement.

The comparison additionally removes wall-clock fields and compares callback event, iteration, coordinate and completed-call-index sequences.
For all 9 RIC/GLOA pairs, all 12 RIC/LOA pairs and all 15 GLOA/LOA pairs, the shorter recorded sequence is an exact prefix of the longer one.
The complete sequences are identical for 6/9, 8/12 and 12/15 pairs, respectively.
Every unequal-length pair involves at least one time-limited attempt.
This observed common trajectory behavior is specific to these returned fixed-grid jobs and does not establish mathematical equivalence of the algorithms on general Process GDPs.
The detailed objective, timing, termination and sequence comparisons are in paired_common_recovery.csv.

## What remains unresolved

R denotes a recovery attempt, and F denotes a retained first attempt in the following table.

| Grid | RIC | GLOA | LOA |
| --- | --- | --- | --- |
| alpine2 | Miss / time limit (F) | Target (R) | Target (R) |
| easom | Miss / time limit (F) | Target (R) | Target (R) |
| holder_table | Miss / optimal (R) | Miss / time limit (F) | Miss / optimal (R) |
| levy13 | Target (R) | Miss / time limit (F) | Target (R) |
| michalewicz | Miss / time limit (F) | Miss / optimal (R) | Miss / optimal (R) |
| shubert | Miss / optimal (R) | Miss / optimal (F) | Miss / optimal (R) |

At least one method reaches the target on 18 of the 21 grids, and all three reach it on 15 grids.
Every method misses holder_table, michalewicz and shubert in the available descriptive inventory.
LOA's additional mixed-inventory hit over GLOA is levy13, where LOA was rerun and GLOA's first-attempt time limit was retained.
LOA's two additional mixed-inventory hits over RIC are alpine2 and easom, where RIC's first-attempt time limits were retained.
These differences concern different attempt cohorts and do not demonstrate superiority on matched recovery attempts.

| Grid | Shared returned objective | Original reference | Demonstrated recovery preprocessing witnesses |
| --- | ---: | ---: | --- |
| holder_table | 0.14516723995340786 | 0 | RIC and LOA, four reference points each |
| michalewicz | 0.08649170482029742 | 0 | GLOA and LOA, reference point [21,15] |
| shubert | 0.08242781075119937 | 0 | RIC and LOA, reference point [17,22] |

For those diagnosed recovery runs, returned logs select the reference coordinates in discrete solves but record no before_subproblem callback at them.
Independent original-GDP witnesses satisfy every checked active constraint and bound and achieve the reference value.
The local Pyomo 6.10.0 common GDPopt preprocessing probe rejects all twelve method-coordinate witnesses through FBBT infeasibility exceptions.
The holder_table witnesses produce contradictory y bounds, the michalewicz witnesses produce contradictory x bounds, and the shubert witnesses produce constraint-infeasibility exceptions.
The local probe and returned trajectory provide mutually consistent evidence of false preprocessing rejection without constituting a full replay of every server iteration state.
The same objective in RIC's retained michalewicz time limit or GLOA's retained holder_table time limit does not independently establish the full cause of those particular earlier attempts.
The retained GLOA shubert attempt also has an optimal-termination mismatch and remains included in the unresolved inventory.
Reported lower bounds equal to the worse incumbent cannot certify the original problem when a verified feasible reference witness has a lower objective.
This evidence identifies a GDPopt/Pyomo preprocessing path requiring correction and does not establish a defect in the SCIP optimization core.

A justified next experiment would validate a preprocessing correction on all three affected grids and every reference witness before recording new method-specific runs.
Repeating the unchanged ZIP or increasing time limits does not repair a deterministic false rejection.
The target-missing retained time limits on RIC alpine2/easom and GLOA levy13 are a separate completion question, not proof of the same preprocessing defect.
The seven recovery time limits already satisfy the target metric and require extension only if bound certification or full termination is the new objective.
No new solver runs, modified targets, preprocessing fixes or replacement experiment packages are created by this comparison.

## Actual SCIP use and computation cost

Across the 46 recovery jobs, execution banners and call journals confirm 67,506 SCIP MIP invocations and zero benchmark NLP invocations.
The separate package preflights contribute three SCIP MIP and six SCIP NLP calls and are excluded from the benchmark totals.
SCIP therefore actually solves the discrete subproblems, while these returned Grid runs do not test comparative SCIP NLP performance.
All three use SCIP 9.2.4, GAMS 52.2.0 and Pyomo 6.10.0, with the same GAMS executable hash, one-thread settings, 1,800-second shared job limit and relative gap 1e-5.
The CPU affinities are RIC 12, GLOA 16 and LOA 14, with no exclusive-core reservation.
No network retry wrapper is exercised in any recovery return, so the absence of failures does not demonstrate a successful retry of an observed network outage.
The bohachevsky2 fixed-exponent safeguard is exercised in all three recoveries, but it does not fix the distinct false-rejection problem on the three remaining grids.

The recovery worker totals sum to 63,530.750 seconds, approximately 17 hours 39 minutes.
The complete 63 first attempts plus all 46 recovery attempts sum to 102,968.351 worker seconds, approximately 28 hours 36 minutes.
The descriptive mixed inventory sums to 78,376.881 worker seconds and omits superseded failed-attempt costs.
These sums measure recorded worker wall-time consumption across packages and are not CPU seconds or elapsed time for the simultaneously running experiments.
Per-method original, recovery, mixed-inventory and cumulative costs are retained in methods.csv.

## Provenance and validation

The [RIC audit](../grid_gdpopt_scip_recovery_ric_20261025/README.md), [GLOA audit](../grid_gdpopt_scip_recovery_gloa_20261025/README.md) and [LOA audit](../grid_gdpopt_scip_recovery_loa_20261025/README.md) bind their returned archives to the delivered packages and original error selections.
The comparison verifies each input report file against its artifact checksum, each recovery ZIP against its recorded archive hash and each trajectory against its sealed path hash.
The manifest records exact input hashes and analysis source hashes.
Every grid-method key is unique, all original 63 records are retained, and the selected recovery set is exactly the 46 original execution errors.
All target references and tolerances remain unchanged.
All 42 related tests pass, including the three independent return audits and comparison checks rejecting incomplete recovery sets and altered references.
The ten LOA audit outputs and sixteen comparison outputs reproduce byte-for-byte in separate fresh replays.
All 2,280 previously tracked regular files and the existing submodule state are unchanged, and the main checkout remains clean at its original revision.
The raw supplied LOA ZIP is preserved byte-for-byte, and no existing raw archive, manifest, report, manuscript, Overleaf source or representative figure is edited.
The outer LOA checksum was computed locally because no independent server checksum sidecar was supplied.
No optimization solver is called by the audit, witness construction, preprocessing probes or comparison.

## Reproduce

Use a Python environment with Pyomo 6.10.0 and the repository analysis dependencies, and select fresh output directories.
The comparison reads the preserved per-method audit artifacts in the repository.

```bash
python scripts/analyze_grid_scip_recovery_loa_return.py --output /tmp/grid_loa_recovery_audit
python scripts/compare_grid_scip_recoveries.py --output /tmp/grid_three_recovery_comparison
python -m pytest tests/test_grid_scip_recovery_loa_return.py tests/test_grid_scip_recovery_comparison.py tests/test_grid_scip_recovery_gloa_return.py tests/test_grid_scip_recovery_ric_return.py tests/test_grid_scip_return.py tests/test_grid_gdpopt_scip_return.py tests/test_grid_scip_recovery.py -q
```

PR 49 is already merged, so this analysis is retained as a follow-up on review/cstr15-dantzig-results and is not automatically incorporated into main or the manuscript's representative results.
