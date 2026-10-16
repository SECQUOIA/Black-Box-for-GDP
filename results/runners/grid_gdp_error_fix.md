# Corrected retry package for the ten remaining Grid GDP errors

[Download the runner ZIP](grid_gdp_error_fix_runner.zip) and
[its SHA-256](grid_gdp_error_fix_runner.zip.sha256).
The package contains the complete source, all 21 reference grids, instructions,
and `tests/test_grid_retry_fixes.py`. Its 47 internal file hashes were verified.

The package explicitly selects the `pyomo610-grid-v1` correction profile:

- Keep each fixed exponent's FBBT interval equal to its actual constant value.
  This prevents roundoff from routing integer powers of negative coordinates
  into fractional-exponent propagation.
- On Alpine1/LOA, check the existing finite bound-convergence criterion before
  another OA cut. The recorded lower and upper bounds were already zero before
  differentiation of `abs(0)` raised an error.

Original formulas, CSVs, GAMS 52.2, Pyomo 6.10.0, HiGHS/BARON choices, CPU 6,
one thread and 1,800 s method budgets are retained. Presolve/cut behavior is
explicitly changed and labelled in run/result metadata. These results must be
reported as a corrected profile, separately from unchanged-profile benchmarks.
The 20,181 IPOPT measurements are not repeated.

The local validation suite passed **168 tests**, including reproducing the
original errors, checking all 2,883 affected grid points, and restricted
candidate-set GDPopt smoke solves. Native HiGHS/MC++ smoke solves are not
substitutes for the full Dantzig GAMS benchmark. The packaged dry run selects
exactly ten benchmark pairs and zero points from the supplied retry archive.

The [completed corrected Dantzig run](../grid_gdp_corrected_20261009/README.md)
has ten saved CSV-minimum hits, seven optimal terminations and three time
limits, with no errors. The commands below reproduce the selected retry.

From the Mac:

```bash
scp /Users/albertlee0125/Repos/RBFopt_Test/results/runners/grid_gdp_error_fix_runner.zip \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

From Dantzig, extract into a new package directory:

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
unzip -n grid_gdp_error_fix_runner.zip -d grid_gdp_error_fix_package
cd grid_gdp_error_fix_package/grid_gdp_runner
sha256sum -c SHA256SUMS

bash run_grid_gdp_dantzig.sh retry-errors \
  --run-dir /local/scratch/a/lee4382/repository/RBFopt_Test/results/grid_gdp_benchmark/grid_gdp_retry_all_20261009_153057_czhvd9w7 \
  --retry-fix-profile pyomo610-grid-v1 --dry-run

GRID_GDP_CPU=6 nohup bash run_grid_gdp_dantzig.sh retry-errors \
  --run-dir /local/scratch/a/lee4382/repository/RBFopt_Test/results/grid_gdp_benchmark/grid_gdp_retry_all_20261009_153057_czhvd9w7 \
  --retry-fix-profile pyomo610-grid-v1 \
  > /local/scratch/a/lee4382/repository/RBFopt_Test/grid_gdp_fixed_retry.log 2>&1 &

tail -f /local/scratch/a/lee4382/repository/RBFopt_Test/grid_gdp_fixed_retry.log
```

The plan must say `planned_benchmarks: 10`, `planned_points: 0`:
Alpine1/LOA; Camel3, Dropwave and Sum of Squares each with RIC/GLOA/LOA.
It creates `grid_gdp_retry_fixed_all_...` and prints `RUN_DIR` and finally
`RESULT_ZIP`. It does not overwrite either previous run or rerun Holder Table
misses, timeouts or BARON-unsupported cases. Ten method budgets total at most
five hours, plus setup/watchdog/packaging overhead; this is a cap, not a runtime
prediction. Errors remain visible and are never automatically retried forever.

The [published retry results](../grid_gdp_retry_20261009/README.md) retain the
unchanged-profile outcomes and link the original IPOPT data.
