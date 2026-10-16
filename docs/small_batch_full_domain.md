# Small Batch: full original GDP domain

The original GDP allows each of its three unit counts to range from 1 to 3.
The earlier DFO experiment restricted the first two coordinates to 2–3, leaving
12 feasible configurations. This experiment searches all 27 configurations.
The archived Dantzig GAMS/IPOPT-profile enumeration contains 12 accepted points
and 15 preprocessing-infeasible points: feasible fraction 12/27 = 4/9.
That fraction describes the domain, not a predicted optimizer success rate.

All 15 infeasible configurations were rejected by FBBT, before IPOPT was called.
Their solver time is zero; their measured point-evaluation cost is positive,
0.04396854–0.04832519 seconds (mean 0.04552516 seconds). These costs include
the work required to identify infeasibility and are charged for each callback.
Their raw records, source-member checksums, original archive checksum, and all
12 accepted point measurements are in
`benchmark_protocols/small_batch_full_domain.json`.

## Experiment

- DSDA, RBFOpt, BAM 5.0.0, and FMQA-SA: 10 runs each, seeds 0–9; 40 jobs total.
- Bounds: `[1,1,1]` through `[3,3,3]` for every method.
- Three shared LHC initial points per seed; all three count toward budget 10.
- Frozen designs use the original SciPy 1.17.1 generator on the new bounds.
  Each of these ten designs has at least one feasible start; no seed is removed
  or resampled. FMQA reads the frozen coordinates despite its different SciPy version.
- RBFOpt: MSRSM, sampling global search, automatic RBF, one CPU.
- DSDA: original diagonal-neighbor algorithm and first tie break; all 27
  coordinates are eligible neighbors. The domain mapping contains coordinate
  keys only, with no feasible mask or objective values. Infeasible neighbors
  must be evaluated and count against the budget.
- DSDA/RBFOpt return a fixed penalty of 1e6 for infeasible calls. BAM receives
  its native NaN infeasibility response. FMQA retains raw infinity and its
  existing report penalty of 1e6. All 12 feasible values are below the penalty.
- FMQA: 1000 epochs, learning rate 0.01, 100 SA reads, 1000 sweeps, 1800 seconds.
- Sequential isolated workers, one selected Linux logical CPU, numerical
  threads limited to one; 2100-second worker watchdog. Same existing separate
  DFO and FMQA environments as the preceding 14-job follow-up.

The lookup objective retains the original feasible CSV values. An infeasible
configuration is backed by an actual enumeration record, not just an absent CSV
entry. Optimizers receive only objective callbacks and the declared bounds;
the known target and measurement times are used for validation/reporting.

The result ZIP includes ordered callbacks, repeated and infeasible evaluations,
method and outer-runner clocks, result records, logs, original solver/data source
snapshots, and FMQA proposal records. Every callback is flushed and fsynced.
`evaluation_costs.csv` attaches archived point measurements to actual callbacks.
`completion_estimates.csv` uses each method's original `wall_time_s`:

`estimated completion = method time - lookup-call time + sum(point costs)`.

These are estimates along recorded paths. No online GDP/NLP optimization is
performed by this run. The 27 measured point costs are already available, so
NLP enumeration need not be repeated. Existing restricted-domain results remain
separate until the new 40-run archive is validated and selected for plotting.

## Build and upload from the Mac

```bash
cd /Users/albertlee0125/Repos/RBFopt_Test
.venv-trace-bam5/bin/python process_followup_runner.py bundle \
  --experiment small_batch_full_domain \
  --output /private/tmp/small_batch_full_domain_dantzig_20261012.zip

scp /private/tmp/small_batch_full_domain_dantzig_20261012.zip \
    /private/tmp/small_batch_full_domain_dantzig_20261012.zip.sha256 \
    lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

## Run on Dantzig

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
sha256sum -c small_batch_full_domain_dantzig_20261012.zip.sha256
unzip small_batch_full_domain_dantzig_20261012.zip
cd small_batch_full_domain_runner

PROCESS_CPU=6 nohup bash run_small_batch_full_domain_dantzig.sh run \
  > ../small_batch_full_domain.log 2>&1 &

tail -f ../small_batch_full_domain.log
```

`run` checks environments and exercises solvers before beginning the 40 jobs.
It uses `.venv-dantzig-nlp-overnight` (fallback `.venv-dantzig-grid-trace`) and
`.venv-dantzig-fmqa`, without changing installed packages. Existing overrides
`PROCESS_DFO_ENV`, `PROCESS_FMQA_ENV`, `PROCESS_CONDA`, `COIN_BIN`, and
`BAM_LICENSE_FILE` work as before. A separate `check` is optional.

The first log entry prints `RUN_DIR`. Results are under
`results/small_batch_full_domain/small_batch_full_domain_<timestamp>_<suffix>/`.
Successful completion requires `planned_runs=40`, `completed_runs=40`,
`all_completed=true`, and `callbacks_missing_point_cost=0`. Up to 400 actual
callbacks are possible; a method may terminate before spending its full budget.
A completed run can miss the optimum without being an execution error.
`RESULT_ZIP=...` identifies the final download.

## Resume, pack, and download

```bash
# Dantzig: use the RUN_DIR printed by the original invocation.
SMALL_RUN=/local/scratch/a/lee4382/repository/RBFopt_Test/results/small_batch_full_domain/small_batch_full_domain_TIMESTAMP_SUFFIX

nohup bash run_small_batch_full_domain_dantzig.sh resume \
  --run-dir "$SMALL_RUN" --retry-errors \
  >> ../small_batch_full_domain.log 2>&1 &

tail -f ../small_batch_full_domain.log

# After it stops:
bash run_small_batch_full_domain_dantzig.sh pack --run-dir "$SMALL_RUN"
```

Completed jobs are checksum-verified and skipped. An interrupted job restarts
from its seed; its earlier partial trace is retained in `previous_attempts/`.
Errors/timeouts require `--retry-errors`. This does not resume a solver's internal
state or combine partial attempts into one replication.

```bash
# Mac: replace the basename with RESULT_ZIP's actual basename.
scp lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/small_batch_full_domain/small_batch_full_domain_TIMESTAMP_SUFFIX.zip \
    ~/Downloads/
```
