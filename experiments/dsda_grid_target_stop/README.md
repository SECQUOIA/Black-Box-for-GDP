# Grid D-SDA common-success target stopping

This is a Grid-only follow-up to the second D-SDA absolute-improvement-tolerance experiment in `results/dsda_abs1e5_rerun_20261028/`.
It changes only target stopping and its observed incumbent while retaining strict movement acceptance `old_value - new_value > 1e-5`.
The exact modified algorithm used in that baseline return is copied here rather than assuming the repository-root `grid_dsda.py` is identical.
The baseline ZIP is identified by SHA256 `e58982f7179b73c65d83134dcbe0b25854002685812b2511b24523e861c9929e`.

The new optional `target_stop` predicate is passed the tracked observed incumbent and the unchanged per-job target.
Execution supplies the retained `adopted_analysis.hit` function, which evaluates `abs(value - target) <= 1e-5 * max(1, abs(target))` without rounding.
The tracker already records the minimum of every accepted objective callback, including evaluations that are not accepted as moves.
That minimum is used only for the target predicate and does not alter neighbor choice, direction search, movement paths, start ranking, `best_seen`, or `best_run` updates.
The movement-acceptance functions and complete single-descent implementation are unchanged from the direct baseline.
The default `target_stop=None` path preserves the original `isclose` comparison with `abs_tol=tol` and zero relative tolerance.

The existing control-flow checkpoint is after each completed descent, after the budget-exhaustion check, and before the next ranked start.
There is no new immediate callback-level termination.
If a descent has no improving neighbor but has not reached the common target criterion, the next ranked start is attempted when budget remains.
All three initial configurations are evaluated in their original order before start ranking, cached start values are reused, and repeated evaluations continue to consume budget.
Initial ranking that exhausts the budget still exits before any descent target checkpoint.
Final summary reporting uses the same success predicate but is not another search checkpoint.

The execution cohort is exactly 21 functions by five budgets `10, 30, 50, 70, 100` by seeds `0–9`, totaling 1,050 Grid D-SDA runs.
Preparation validates every function-budget seed set and rejects Process jobs, other methods, duplicated identifiers, missing pairings, and incomplete or duplicate Grid lookup coordinates.
Only saved Grid objective responses are used, and the retained solver/model import and child-process guards remain installed inside every lookup worker.
The preparation, tests, smoke, and server entry points do not invoke the original 1,190-job runner.
The standalone Grid smoke uses Ackley B10 seed 0, Csendes B100 seed 3, and Easom B100 seed 5.
These three smoke executions are recorded separately from the 1,050-run analysis cohort.

The launcher checks repository identity, current changes, and running-process metadata and locks both this workflow and the installed previous D-SDA workflow against concurrent duplicate execution.
It preserves existing files and never terminates other users' jobs.
On Dantzig it reuses `.venv-dantzig/bin/python` with Python 3.11.16, NumPy 2.4.6, SciPy 1.17.1, and pandas 2.3.3.
The retained CPU selector samples allowed logical CPUs and their SMT siblings over three one-second intervals and requires a physical core whose sampled utilization stays at or below five percent.
It pins one logical CPU, verifies worker affinity, runs sequentially, limits numerical-library threads to one, and retains the original absence of a Grid watchdog.
An idle-core observation and affinity setting do not constitute exclusive reservation.
Wall times are retained without a cross-run speedup claim, and historical configuration-cost estimates are not reused.

Prepare a sealed package without running any searches by specifying the existing baseline archive and repository.

```bash
python experiments/dsda_grid_target_stop/prepare.py \
  --repo /local/scratch/a/lee4382/repository/RBFopt_Test \
  --archive /local/scratch/a/lee4382/repository/RBFopt_Test/results/dsda_abs1e5_rerun_20261028_020753_2004611.zip
```

The printed package path contains Grid-only inputs, baseline callbacks and results, frozen source, and a complete SHA256 inventory.
Run its `test_experiment.py` and `run.py smoke --output NEW_DIRECTORY` for manual checks, or use the permanent launcher to run tests and smoke before the full cohort automatically.

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
.venv-dantzig/bin/python experiments/dsda_grid_target_stop/launch.py
```

The launcher prints a detached process PID, log path, result directory, and expected return archive path.
CPU selection and actual completion must be checked in that log, and the job continues after SSH disconnects.
Every job is validated against the exact direct baseline before receiving a completion marker with source and output hashes.
Completed and validated runs are reused during explicit resume rather than executed again.
Incomplete attempts are preserved separately, and a completed result with missing or inconsistent process evidence causes a clear stop rather than an automatic duplicate execution.

```bash
.venv-dantzig/bin/python experiments/dsda_grid_target_stop/launch.py --resume /absolute/path/to/the/existing/result_directory
```

Every new callback sequence must equal the baseline sequence or a prefix ending at the existing descent checkpoint with a successful common target test.
Descent movement paths and algorithm state before stopping must match the corresponding baseline descents after excluding measured durations.
The first target-hit callback and actual termination callback are recorded separately.
The paired table and per-budget summary retain the complete cohort denominator, including missing or failed records.
The expected baseline counts supplied in the task are used only for external cross-checking and are not hardcoded into analysis or success classification.

Verify a returned archive using only saved data and the standard library.

```bash
python experiments/dsda_grid_target_stop/verify.py --archive /path/to/returned.zip
```

This verification reads archived data without importing an optimizer, invoking a solver, spawning a subprocess, or executing source from the archive.
Original return archives, manifests, historical workflow evidence, Process runs, other methods, manuscript and Overleaf sources, and existing representative tables and figures remain unchanged.
The new results are not automatically adopted into the manuscript.
Publication uses the existing PR #52 branch and a normal push with `[skip ci]`, after the actual Dantzig return is verified.
