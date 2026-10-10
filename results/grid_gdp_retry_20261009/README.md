# Grid GDP retry results, October 9, 2026

The supplied Dantzig retry reran exactly 21 prior errors, with the original
solver settings, CPU 6, one thread, and 1,800 s limit. **11 ended normally and
10 repeated their earlier errors.** The ZIP passed CRC validation and all
210 internal SHA-256 checks. Its runtime and model/solver sources match the
original run; only the retry coordinator and documentation changed.

## Data

- [Original retry ZIP](../archives/grid_gdp_retry_all_20261009_153057_czhvd9w7.zip)
  preserves all results, logs, saved solutions and source files.
- [Unmodified retry table](raw/benchmark.csv), [configuration](raw/run.json),
  [summary](raw/summary.json) and [retry selection](raw/retry_plan.json).
- [Audited retry table](retry_audited.csv) includes all 21 attempts.
- [Eight normally terminated target hits](retry_target_hits.csv) separates
  verified CSV-minimum hits from errors and misses. Levy/LOA reached the target
  but terminated at the time limit.
- [Current 105-case table](benchmark_current.csv) replaces the original 11 GAMS
  network-session errors with their normally terminated retries. It retains
  every other original case, including the ten repeated errors. Each row gives
  its source archive, result path and hash. Selection is independent of runtime
  and objective value; this is not a selection of the best of repeated runs.
- [Existing IPOPT point data](../grid_gdp_20261009/raw/point_timings.csv) contains
  all **20,181** original one-thread measurements. No points were remeasured.
  The [original timing analysis](../grid_gdp_20261009/README.md) gives mean
  0.652221 s and median 0.372685 s per complete point evaluation.
- [Publication metadata](publication.json) links and hashes both archives and
  the IPOPT table. The [analysis script](analyze.py) reproduces the derived CSVs.

Reproduce from the repository root using Python with Pyomo installed:

```bash
python results/grid_gdp_20261009/analyze.py
python results/grid_gdp_retry_20261009/analyze.py
```

The retry analysis loads the analytic model source preserved in the original
archive, validates saved choices, coordinates, variable bounds and objectives,
and compares the resulting expression values against the original CSVs. It
does not run any solver. Original `target_hit` fields are preserved; separate
`audited_*` fields also cover the original Levy13/RIC hard-timeout incumbent.

## Results and remaining failures

| Retried case | Outcome |
|---|---|
| easom/RIC, griewank/RIC | Optimal termination; CSV target hit |
| hosaki/RIC, GLOA, LOA | Optimal termination; CSV target hit |
| levy/RIC, GLOA | Optimal termination; CSV target hit |
| levy/LOA | Time-limit termination; CSV target hit |
| holder_table/RIC, GLOA, LOA | Reports optimal; CSV target missed by 0.14516724 normalized units |
| camel3/RIC, GLOA, LOA | Repeated FBBT `IntervalException` |
| dropwave/RIC, GLOA, LOA | Repeated FBBT `IntervalException` |
| sum_of_squares/RIC, GLOA, LOA | Repeated FBBT `IntervalException` |
| alpine1/LOA | Repeated `DifferentiationException` for `abs(0)`; saved target hit |

The current table has **62 finished, ten error, one hard time limit and 32
unsupported-expression cases**. Saved GDPopt solutions hit the reference
minimum in **45/63 cases**, including some error/timeout incumbents. This
counts validated candidate solutions, not 45 successful terminations or global
optimality certificates. Holder Table, Michalewicz and Shubert illustrate why
reported `optimal` must not be equated with the reference optimum here.

The nine FBBT failures occur before subproblem solving. A local reproduction
with Pyomo 6.10.0 and the archived formula found constant exponent bounds such
as `(2, 1.9999999999999998)` and `(6, 5.999999999999999)`. This sends negative
bases into inverse-exponent propagation, producing the misleading fractional-
power message even for integer polynomials. The Alpine1 log has lower and upper
bounds both zero before LOA attempts differentiation for an additional cut.
Blindly repeating these ten cases already reproduced all ten errors.

Any presolve/cut-order correction must be identified as a changed algorithm
profile. Corrected retries must retain the raw outcomes here, preserve original
analytic formulas and solver budgets, and must not silently replace the
unchanged-profile records in this publication.
