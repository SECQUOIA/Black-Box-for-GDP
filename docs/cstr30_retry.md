# Dantzig: seven isolated CSTR30 retries

The returned Dantzig run succeeded at all seven points and is included in the
[merged timing dataset](../results/gdp_point_timings_20260922/README.md). The shell
wrapper described below is local and is not tracked. From a fresh repository
checkout, use the Python command (after setup in [the server guide](gdp_dantzig.md)):

```bash
.venv-dantzig-gdp/bin/python cstr30_retry.py run \
  --executable /package/gams/52.2/gams --expected-gams-version 52.2
```

Set the thread environment from that guide first. `--point 5,3` selects one
point. The Python source bundle includes a shell wrapper only when present
locally; neither solving nor packaging requires it.

## Original local ZIP transfer workflow

This small runner retries only `(5,1), (5,3), (6,2), (6,4), (23,2), (26,2),
(29,3)` with GAMS 52.2/IPOPT (MUMPS). Every point runs sequentially in a new
Python process. All seven use the verified zero-recycle mass-balance
initialization. The original objective, constraints, bounds and fixed values
are checked unchanged, and the initial residual must be <=1e-8.

The ZIP extracts into its own `cstr30_retry_runner/` folder. It includes a
snapshot of the minimal GDP code, not environments, original model checkouts,
benchmark results or solver licenses. It reuses the existing server GDP
environment and `external/dsda-gdp` checkout. No installation is needed.

Upload from the Mac:

```bash
scp ~/Repos/RBFopt_Test/results/dantzig_review/cstr30_retry_runner.zip \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

Run on Dantzig:

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
unzip -o cstr30_retry_runner.zip
cd cstr30_retry_runner
sha256sum -c RETRY_RUNNER_SHA256SUMS
bash run_cstr30_retry_dantzig.sh run
```

The known GAMS executable `/package/gams/52.2/gams` is selected automatically.
`GAMS_BIN` overrides it. `GDP_REPOSITORY` changes the existing repository path,
and `GDP_PYTHON` can select an existing environment. Local validation on a
different GAMS version requires an explicit `GDP_GAMS_VERSION` override.

Each point has a 60-second GAMS solve limit and a 180-second worker-process
limit. Failed/crashed/timed-out workers do not prevent later points from
running. A timeout terminates the worker process group, including its solver.
This isolates state between points; it does not establish that a loop caused
the earlier failures. Feasible initialization resolved the local failures.

To run an individual point manually:

```bash
bash run_cstr30_retry_dantzig.sh run --point 5,3
```

Each command creates a new result folder and ZIP. The seven-point default is
already seven independent Python invocations. No solver fallback or silent
retry is performed. If a point still fails, its record and log are preserved.

Results are printed at the end:

```text
RESULT_DIR=/local/scratch/a/lee4382/repository/RBFopt_Test/results/dantzig_cstr30_retry_DATE_ID
RESULT_ZIP=/local/scratch/a/lee4382/repository/RBFopt_Test/results/dantzig_cstr30_retry_DATE_ID.zip
```

The ZIP contains `run.json` (source/runtime/parent identity), `summary.json`,
`evaluations.csv`, one JSON record and log per point, runner source, and
SHA256 checksums. `complete` means every selected point was attempted;
`all_accepted` means all selected attempts passed the solver and primal checks.
The controller packages partial results on Ctrl+C. After a forced termination,
package saved records with:

```bash
bash run_cstr30_retry_dantzig.sh pack --run-dir /absolute/path/to/RESULT_DIR
```

Download the printed ZIP to the Mac (replace the name with the actual output):

```bash
scp lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/dantzig_cstr30_retry_DATE_ID.zip \
  ~/Downloads/
```

`solve_wall_s` includes the GAMS interface and optimizer. `total_wall_s`
additionally includes model preparation, the new initialization and validation.
`worker_process_wall_s` also includes Python startup/imports and process exit.
For crashes that cannot return an evaluation timer, the latter remains recorded.
These overlapping timings must not be added together.

This is a **new initialization policy**, recorded as
`mass_balance_zero_recycle`. The original raw attempts remain preserved in the published dataset.
The parent run and parent ZIP SHA256 are recorded for a later reviewed merge.
Keep both the original failed attempt and the new attempt when accounting for
retry cost. The returned results can be joined by case, CSTR size, integer
coordinates and solver. The returned Dantzig results have now been merged with explicit retry provenance;
local validation measurements are excluded.
