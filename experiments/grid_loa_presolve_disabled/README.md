# Selective LOA validation with subproblem presolve disabled

This diagnostic starts from the source and configuration actually returned in grid_gdpopt_scip_20261025_180441_051rkijg.zip.
The review revision is 24df0376881409a533b98d9a8490c902eef38b5b.
It covers only holder_table, michalewicz and shubert with LOA.
It does not update the original 21-grid performance inventory or publication material.

## Logging correction delivery

The original delivery stopped before its first optimizer call because Pyomo ConfigDict solver arguments were passed directly to the JSON recorder.
The v2 delivery converts those two logging values with ConfigDict.value(), without changing the live configuration or solve arguments.
The reported original run has zero fixed solver calls and zero full LOA runs, so it supplies no evidence about the effect of disabling presolve.
The v2 launcher first checks the preserved original result ZIP, its source identity, checksums, first-worker error, counters, launch ledger and absence of solver execution artifacts.
It accepts only the exact serialization failure with zero optimizer calls and refuses any prior solver attempt or other failure.
This is a pre-solver logging repair, not a retry of an evaluated or failed optimization configuration.
The original ZIP and exclusive execution claim remain untouched.
The new output directory is results/grid_loa_presolve_disabled_20261025_v2, and the returned ZIP includes the original stopped ZIP and its verification record.
The new runner has its own exclusive claim and retains the six-call and three-run limits, without any automatic resume path.

The only full-LOA algorithm-option change is an explicit subproblem_presolve=False keyword in the archived GDPopt call.
The keyword is conditional on the separate diagnostic configuration, and the existing default call passes no additional option.
The package preserves all 68 original source files under original_source and places execution copies under execution.
Only execution/gdp_models/comparison.py differs among the archived files, through the single conditional keyword insertion shown in comparison_option.diff.
The additional launcher and analyzer provide gating, logging and reproducibility without editing installed Pyomo files or FBBT implementation functions.
All historical model-specific correction code remains present, but none of those corrections applies to these three grids.
The original network retry function remains active, and full-job attempts and backoff consume the original 1,800-second shared deadline.

The [Pyomo 6.10.0 implementation](https://pyomo.readthedocs.io/en/6.10.0/_modules/pyomo/contrib/gdpopt/solve_subproblem.html) routes subproblem_presolve=False directly to the appropriate subproblem solver.
The option bypasses FBBT, fixed-variable detection, zero-term removal and trivial-constraint deactivation in that preprocessing block.
Solver routing and runtime may therefore change even though the original mathematical model and acceptance tolerance do not.
The actual full-run configuration is captured from GDPopt's own effective-configuration log before it begins optimization.
The capture rejects a missing false setting or a changed mip_presolve setting.
The full effective-configuration text and the actual solver-call journals are retained.

## Fixed configurations and stopping rule

The grid coordinates are CSV indices in 0..30.
The sequence is holder_table [3,1], [3,29], [27,1], [27,29], followed by michalewicz [21,15] and shubert [17,22].
Each configuration starts with a fresh model through the historical diagnostic construction path.
An original-GDP witness and a separate default-presolve probe are recorded before the disabled-presolve solve.
The witness is not used as a solver-returned solution or transferred into a later full run.
The disabled path calls Pyomo's existing solve_subproblem function with the official configuration flag set to false.
There is one actual solver-interface invocation at most per fixed configuration, at most six in total, and a 60-second worker deadline for each.
The original GAMS interface reserves a small portion of that deadline for validation, so the actual solver limit is no greater than 60 seconds.
The preserved network policy cannot retry within that short budget, and a durable one-call guard independently prevents a second invocation.
No separate optimization preflight is performed.
GAMS version checking uses its audit command, and the first actual fixed solve verifies the SCIP 9.2.4 execution banner.

A fixed gate requires an actual SCIP invocation, a returned solver solution, independently feasible original GDP variables and the unchanged target criterion.
Original constraint/bound acceptance and target tolerance are 1e-5, with no new tighter numeric acceptance criterion.
The objective is evaluated from the original expression using returned variables and is never replaced by a CSV value.
The first failed fixed gate ends the sequence immediately and prevents all full LOA runs.
If all six pass, the launcher runs exactly the three named LOA jobs once each, with the original 1,800-second deadlines and original midpoint initialization.
Each full job receives a new unsolved template, never a fixed-diagnostic solution or warm start.
A persistent exclusive execution_claim.json prevents a second invocation of the delivered experiment.
There is no resume, retry-the-whole-job or budget-extension mode.
Only subprocess groups created by this diagnostic can be terminated by its inherited watchdog.

## Environment and records

Server execution requires Dantzig, the original GAMS executable and hash, Pyomo 6.10.0, the recorded Python/package versions, CPU 14 and the original one-thread environment.
The baseline SCIP version is 9.2.4, GAMS is 52.2.0 and Python is 3.11.16.
The three relevant installed Pyomo modules must match the recorded local Pyomo 6.10.0 diagnostic source hashes and remain unchanged.
Historical Dantzig module-byte hashes were not recorded, so the manifest explicitly distinguishes that local reference from the original server version records.
An environment mismatch stops execution and is recorded without installation, upgrade or solver substitution.
CPU affinity is not an exclusive-core reservation.
The unchanged prior network policy and correction profiles are identified separately from the new option delta.

The result ZIP contains source inventories, actual configurations, environment records, fixed probes and calls, full trajectories, returned variables, independent original-GDP checks, bounds, timing, retries and SHA256 inventories.
The analyzer compares all three problems with the preserved baseline without replacing existing results.
Reference-path records distinguish discrete selection, bypassed presolve, evaluation entry, return and target incumbents.
An optimal termination string never sets global_optimality_certified to true.
A reported lower bound above the known feasible reference remains explicitly marked as inconsistent.
The result analysis invokes no optimization solver and can be reproduced in a fresh output directory.

From the extracted package root on Dantzig, launch the one-use diagnostic with the following command.

```bash
bash execution/run_diagnostic.sh run
```

## Build and local validation

```bash
python experiments/grid_loa_presolve_disabled/build_package.py --output <fresh delivery directory>
python <extracted package>/execution/diagnostic.py inspect --output <fresh inspection.json>
python -m pytest tests/test_grid_loa_presolve_disabled.py tests/test_grid_scip_recovery.py tests/test_grid_scip_recovery_loa_return.py tests/test_grid_scip_return.py tests/test_grid_gdpopt_scip_return.py -q
```

The inspect mode is solver-free and cannot establish actual SCIP success.
See results/grid_loa_presolve_disabled_20261025_v2 for the corrected package, server commands and local validation.
The original delivery and its preparation evidence remain in results/grid_loa_presolve_disabled_20261025.
