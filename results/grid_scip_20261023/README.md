# Dantzig Grid-GDP results and actual solver usage

Results returned on October 23, 2026; English report and historical solver-call
comparison updated on October 24, 2026.

**All 105 jobs returned a variable vector in `solution.json`, and all 105 pass
an independent check against the original GDP at the existing `1e-5`
tolerance.** SCIP Big-M and Hull each reached the reference target on 21/21
grids. GDPopt GLOA, LOA and RIC each reached it on 18/21 grids, for 96/105 target
hits overall. The concern is the quality of some GDPopt solutions and the
meaning of their `optimal` termination, rather than an absence of returned
solutions.

**The Grid GDPopt experiments did not compare actual BARON and SCIP NLP
solves.** The original BARON-configured run and the new SCIP-configured runs
both called HiGHS throughout their recorded benchmark solver journals. BARON
and SCIP were actually used for the respective direct MINLP reformulations.
Section 2 separates configuration, benchmark calls and preflight calls.

This analysis invokes no optimization solver. Original return archives,
execution records and manuscript results are preserved. The three GDPopt ZIPs
came from `results/archives`; the MINLP ZIP and supplied checksum were imported
from the user's Downloads directory. The initial audit was committed as
`a2e68eef64314fc0f28fe96f16b48546375e8186`, after PR 49 had merged at head
`ef93072d1ac28dbcf22ecc8b448f3e6869fbbdaf`. Follow-up commits on
`review/cstr15-dantzig-results` are therefore not part of PR 49's merged diff.

## 1. Returned solutions and method outcomes

All jobs used Dantzig GAMS 52.2.0, Pyomo 6.10.0, a 1,800-second method limit and
one thread. The Grid formulas and all 21 reference CSVs match the executed
source snapshots byte-for-byte. A target hit means a normalized objective gap
of `<= 1e-5` from the reference minimum. See [summary.csv](summary.csv),
[per-job results](jobs.csv) and the [archive audit](audit.json).

| Method | Returned, valid solutions | Target hits | `optimal` terminations | Time limits | `optimal` but target missed | Sum of method time (s) |
|---|---:|---:|---:|---:|---:|---:|
| SCIP Big-M | 21/21 | 21/21 | 21 | 0 | 0 | 24.469 |
| SCIP Hull | 21/21 | 21/21 | 21 | 0 | 0 | 16.386 |
| GDPopt GLOA | 21/21 | 18/21 | 18 | 3 | 2 | 19,116.235 |
| GDPopt LOA | 21/21 | 18/21 | 17 | 4 | 2 | 18,471.434 |
| GDPopt RIC | 21/21 | 18/21 | 17 | 4 | 2 | 19,057.874 |

Times sum `method_wall_s` from each `result.json`, excluding model/CSV
preparation and preflight. The 42 MINLP jobs total 40.855 seconds; medians are
0.655 seconds for Big-M and 0.533 seconds for Hull. These measurements describe
this finite Grid formulation, not general MINLP or Process-case performance.
GDPopt `status=finished` includes time-limit termination, so termination is
counted separately.

All 42 Big-M/Hull records have a true runner global-certificate flag and also
reach the reference target. All 63 GDPopt records have a false global-certificate
flag. A GDPopt `optimal` string alone is not treated as a global certificate.

## 2. Configured solvers versus actual calls

### October 23 SCIP-configured runs

The configuration replaced GDPopt's BARON NLP solver with SCIP while retaining
HiGHS for MILP. However, **all 61,063 recorded benchmark calls across the 63
GDPopt jobs were to HiGHS**, with model type `mip`. Benchmark SCIP NLP calls and
BARON calls were both zero.

| Method | Actual benchmark calls |
|---|---:|
| Big-M/Hull | SCIP MINLP: 42 |
| GLOA | HiGHS MIP: 20,778 |
| LOA | HiGHS MIP: 19,299 |
| RIC | HiGHS MIP: 20,986 |

After the two coordinates are fixed and GDPopt presolve reduces a subproblem
to a linear model, `solve_subproblem` routes it to the configured MIP solver,
HiGHS. The journal's `mip` label does not imply that every reduced subproblem
still has integer variables. Each GDPopt ZIP also records two SCIP NLP calls
during preflight; these are excluded from the benchmark counts.

### Original BARON-configured run and retries

The [historical call audit](legacy_solver_calls.json) reads the original
`benchmark/*/*/solver_calls.jsonl` members, verifies archive hashes and all
internal checksums, and retains each journal path and recorded solver policy.
It excludes preflight and the separate IPOPT point-enumeration phase. Counts
include recorded failed calls; a call count is not a count of successful solves.

| Archive / attempt | GDPopt jobs with journals | HiGHS calls: GLOA | HiGHS calls: LOA | HiGHS calls: RIC | Total HiGHS calls | BARON / SCIP GDPopt calls |
|---|---:|---:|---:|---:|---:|---:|
| [Original Grid run](../archives/grid_gdp_run_20261008_210901_dw5vq37s.zip) | 63 | 14,278 | 14,035 | 13,271 | 41,584 | 0 / 0 |
| [Unchanged-profile retry](../archives/grid_gdp_retry_all_20261009_153057_czhvd9w7.zip) | 21 | 5,475 | 5,303 | 8,336 | 19,114 | 0 / 0 |
| [Corrected-profile retry](../archives/grid_gdp_retry_fixed_all_20261009_204028_lu6vdgkt.zip) | 10 | 2,857 | 2,877 | 2,684 | 8,418 | 0 / 0 |

These are separate attempts, not additional unique benchmark cases. The
original direct Big-M/Hull run did call BARON: five supported grids per method,
ten MINLP calls in total. The other 16 grids per method were marked unsupported
and did not call BARON. The new SCIP reformulations cover all 21 grids per
method; their full-set timings therefore have different coverage from the old
BARON timings.

**Neither the original nor the new Grid GDPopt run measured an NLP speedup
from BARON to SCIP.** The solver setting changed, but the observed benchmark
solver remained HiGHS. Differences between these runs cannot be attributed to
BARON-versus-SCIP NLP performance.

This conclusion is specific to these Grid records. The preserved diagnostic
for **CSTR15 GLOA A12** records two actual HiGHS calls and two actual BARON calls.
Its nonlinear subproblems did reach BARON. The diagnostic records BARON
`LPSol 8` / `NLPSol 9` (CLP/CBC and IPOPT); it does not establish the internal
IPOPT version from the original logs. See the [original diagnostic report](../../diagnostics/gdpopt_20261023/REPORT.md).

## 3. Independent solution checks and missed targets

The audit restores all 64 original variables from each `solution.json` (66 for
Csendes). It never substitutes constructor initial values for missing returned
variables. Checks cover variable bounds, binary integrality, both XORs, selected
disjunct equalities, the Csendes reciprocal relations and the original analytic
objective. Selected coordinates are compared with the reference CSV. The model
audit also checks all 961 analytic grid values per function against its CSV.

The maximum original-GDP violation is `1.9808652753638967e-6`. The maximum
absolute difference between saved and recalculated objectives is
`3.1170855730844047e-17`. All 105 solutions pass the existing `1e-5` feasibility
criterion. At a stricter `1e-8`, 102/105 pass; the exceptions are below. Returned
variables were not rounded or overwritten.

| Grid / method | Maximum original-GDP violation |
|---|---:|
| deflected_corrugated_spring / Hull | 1.9808652753638967e-6 |
| michalewicz / Hull | 5.02655339573721e-8 |
| sum_of_squares / Big-M | 3.4970414e-8 |

All three GDPopt methods miss the same three functions and return the same
points. Every reference minimum below is zero. Coordinates are CSV indices
from 0 to 30, not physical coordinates.

| Grid | Returned point, all three methods | Returned normalized objective | Reference minimizer(s) | Termination |
|---|---|---:|---|---|
| Holder Table | (0,1) | 0.14516723995340786 | (3,1), (27,1) | All three reach the time limit |
| Michalewicz | (22,15) | 0.08649170482029742 | (21,15) | All three report `optimal` |
| Shubert | (17,21) | 0.08242781075119937 | (17,22) | All three report `optimal` |

SCIP Big-M/Hull return reference minimizers for these functions too. Their
complete variable vectors and raw GAMS statuses provide direct evidence of
better feasible solutions in the same model than the GDPopt returns for
Michalewicz and Shubert.

Eight of the eleven time-limit cases already reached the target: Levy and
Levy13 for GLOA; Hosaki, Levy13 and Styblinski-Tang for LOA; and Levy, Levy13 and
Styblinski-Tang for RIC. The other three are Holder Table. A time limit does
not imply that no solution was returned.

## 4. Coordinate traces and presolve diagnostics

Each GDPopt job's `grid_path.jsonl` records before/after coordinates for
subproblems that pass presolve. For each method, only 458 distinct Michalewicz
points and 74 distinct Shubert points reach these callbacks. The reference
minimizer is absent in every case. Both functions record 962 GDPopt iterations;
this must not be interpreted as 961 successful objective evaluations. GLOA and
RIC have identical callback coordinate order for each of these two functions,
while LOA has a different order.

Because callbacks occur after presolve, an absent callback does not prove that
the master never selected that configuration. These ZIPs do not contain a full
Dantzig candidate-to-presolve-to-no-good trace. The same limitation applies to
the earlier diagnostic records.

Without invoking an optimizer, local replay used the identical Grid formulas
and the common GDPopt presolve in Pyomo 6.10.0. [presolve_probe.json](presolve_probe.json)
records source hashes, inverse-trigonometric propagation inputs/outputs,
exceptions and outcomes.

| Grid / point | Local presolve outcome |
|---|---|
| Michalewicz (21,15), reference minimizer | FBBT infeasible: x lower bound 2.199114857512855 exceeds upper bound 0.9424777960769378 |
| Michalewicz (22,15), returned point | Passes |
| Shubert (17,22), reference minimizer | FBBT `InfeasibleConstraintException` |
| Shubert (17,21), returned point | Passes |
| Holder Table (3,1) and (27,1), reference minimizers | FBBT infeasible: y lower bound -3.233037281025837 exceeds upper bound -9.333333333333336 |
| Holder Table (0,1), returned point | Passes |

The local rejection of feasible reference minimizers before a solver call is
consistent with the failures in the new returns. It also suggests that time
budget alone is not a sufficient explanation for Holder Table. This replay is
not a direct observation of every original server candidate. The existing
singleton-sine candidate patch has not been shown sufficient for Shubert or
Holder Table, and no patched optimization run or timing result is established
by this audit.

## 5. Relationship to the supplied GDPopt diagnostic package

The [original diagnostic report](../../diagnostics/gdpopt_20261023/REPORT.md)
and [preservation index](../../diagnostics/gdpopt_20261023/INDEX.md) accompany
this English synthesis. `dantzig_package.zip` contains original-log analysis,
solver-free probes, candidate patches and a prepared diagnostic runner. It is
not a completed new server experiment. Its `execution_accounting.json` records
zero additional full GDPopt runs, zero independent fixed-configuration
optimizations and zero additional internal solver calls. **There is no evidence
yet that applying those candidate patches restores solution quality or
optimality on Dantzig.**

For Grid Michalewicz, the earlier diagnostic traced FBBT inverse propagation
of a singleton sine argument: a bound reversal of approximately `2.22e-16`
causes propagation to jump to another sine branch. The new SCIP-configured
runs again return (22,15), objective 0.08649170482029742, with 458 distinct
callback points, consistent with that diagnosis. The existing
`pyomo610-grid-v1` corrections concern fixed exponents and Alpine1/LOA; they
are separate from the candidate singleton-sine patch.

For CSTR15 GLOA A12, the reported objective 3.522552007803194 exceeds the
independently validated W03 objective 2.8293940632857595. The diagnostic finds
that an initial GLOA convex cut uses `ccSlope` instead of `cvSlope`, creating
15 cut violations in W03's active reactor disjuncts, with a maximum violation
of 36.01008109919173. Changing only the slope in a local cut reconstruction
removes those transformed-master violations. The precise constraint causing
the final original master FBBT contradiction has not been fully reconstructed.

The audit extracted a temporary copy of the package and reran its five
original solver-free regression checks successfully. Original inputs and the
sealed diagnostic report remain unchanged; no CSTR optimization was rerun.
The CSTR cut defect is not asserted to explain every Grid method's failure;
Grid RIC also exhibits the missed targets.

## 6. Integrity, reproduction and scope

The four new return ZIPs passed CRC checks, internal SHA256SUMS, all job seals
and executed-source hashes in `run.json`. The diagnostic ZIP's internal
manifest and all 235 supplied external SHA256 entries match the preserved
bytes. The supplied MINLP sidecar is preserved. The three GDPopt ZIPs arrived
without external sidecars, so their sidecars were generated from the received
bytes; they are not represented as sender-provided checksums.

Raw solver logs, full solution vectors, coordinate and solver-call journals,
and executed sources are retained in the [MINLP](../archives/grid_scip_minlp_20261023_143526_ce02ov4c.zip),
[GLOA](../archives/grid_scip_gloa_20261023_143538_k3722s6a.zip),
[LOA](../archives/grid_scip_loa_20261023_143545_30_v346o.zip) and
[RIC](../archives/grid_scip_ric_20261023_143553_new9tgw4.zip) ZIPs.
Each `solution_member` in [jobs.json](jobs.json) locates the returned vector.

From the repository root:

```bash
python scripts/analyze_grid_scip_return.py --output /tmp/grid-scip-audit
python -m pytest tests/test_grid_scip_return.py -q
python scripts/audit_legacy_grid_solver_calls.py \
  --output /tmp/grid-legacy-solver-calls.json
PYOMO_CONFIG_DIR=/path/to/existing/pyomo-config \
  python scripts/probe_grid_scip_presolve.py --output /tmp/grid-scip-presolve.json
```

The solution auditor has seven regression checks covering missing variables,
inconsistent coordinates/XOR selections, forged objectives and target flags,
and altered archive bytes. Its five JSON/CSV outputs reproduced byte-for-byte
in a separate output directory. The presolve probe uses Pyomo 6.10.0 and the
existing MC++ environment; it does not rerun the complete algorithms. Details
of the original audit are in [validation.json](validation.json).

The October 24 follow-up translates this report, adds the reproducible
historical call inventory and corrects the old README's conflation of solver
settings with actual calls. The three historical ZIPs also passed their outer
hashes, sidecars, CRCs and internal checksums. [english_update_validation.json](english_update_validation.json)
records follow-up checks. The installed Pyomo, optimization runners, archived
source snapshots, historical performance tables and manuscript are unchanged.
