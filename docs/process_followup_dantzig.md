# Process DFO follow-up: 14 runs with full callback traces

This supplement runs only the requested process cases using the original lookup
objectives. It does not perform online GDP/NLP solves. Saved coordinates allow
the measured NLP cost of each point to be joined later, including repeated calls.
`objective_wall_s` is the lookup callback time, **not an NLP solve time**.

| Case | Method | Seeds | Total evaluation budget | Settings |
|---|---|---|---|---|
| Column | DSDA | 10 | 16 | diagonal=True, tie_break=first |
| Column | RBFOpt | 10 | 16 | MSRSM, global_search_method=solver, rbf=auto |
| Column | BAM 5.0.0 | 10 | 16 | original warm-start protocol |
| Column | FMQA-SA | 10 | 16 | original CPU FMQA/SA settings |
| Small Batch | RBFOpt | 0–9 | 10 each | MSRSM, global_search_method=sampling, rbf=auto |

Each budget includes three initial evaluations. Algorithms can terminate before
using their full budget; the trace contains their actual calls. The maximum is
164 callbacks across 14 runs. Original result files are not overwritten.

Column originally contains seeds 1–9. Seed 0's starts `(8,3), (15,9), (10,4)`
are all infeasible, so the user approved seed 10 as the additional common run.
Its frozen ordered starts are `(10,3), (13,6), (8,9)`; `(13,6)` is feasible.
Thus each Column method will have seeds 1–10 after importing the supplement.
This is a disclosed replacement of an unusable initial design, not a seed-0 run.
Small Batch uses its original seeds 0–9 and frozen initial coordinates; this
changes Gutmann to MSRSM while keeping sampling and budget 10.

FMQA uses 1000 epochs, learning rate 0.01, 100 SA reads, 1000 sweeps, and its
original 1800-second time limit. It consumes frozen coordinates directly rather
than regenerating them with its older SciPy version. DFO regenerates and checks
the same coordinates. All jobs run sequentially on one selected logical CPU,
with numerical thread limits of one. CPU affinity does not reserve an exclusive
physical core. The 2100-second worker watchdog includes process startup; hitting
it is an incomplete run, not a successful optimizer completion.

## Build and upload from the Mac

```bash
cd /Users/albertlee0125/Repos/RBFopt_Test
.venv-trace-bam5/bin/python process_followup_runner.py bundle \
  --output /private/tmp/process_followup_dantzig_20261012.zip

scp /private/tmp/process_followup_dantzig_20261012.zip \
    /private/tmp/process_followup_dantzig_20261012.zip.sha256 \
    lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

## Extract and run on Dantzig

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
sha256sum -c process_followup_dantzig_20261012.zip.sha256
unzip process_followup_dantzig_20261012.zip
cd process_followup_runner

PROCESS_CPU=6 nohup bash run_process_followup_dantzig.sh run \
  > ../process_followup.log 2>&1 &

tail -f ../process_followup.log
```

The wrapper reuses `.venv-dantzig-nlp-overnight` (fallback:
`.venv-dantzig-grid-trace`) for DSDA/RBFOpt/BAM and `.venv-dantzig-fmqa` for
FMQA. Conda environments use `conda run`; Python venvs use their own interpreter
directly. It does not install or change packages. Set `PROCESS_DFO_ENV`,
`PROCESS_FMQA_ENV`, `PROCESS_CONDA`, `COIN_BIN`, or `BAM_LICENSE_FILE` when
existing paths differ. Pin checks use `requirements-grid-trace.txt` and
`requirements-fmqa.txt`. `run` performs environment and solver smoke checks
automatically; a separate `check` command is optional. Check jobs are excluded
from the 14 experimental runs and their timings.

`RUN_DIR=...` appears first in the log. Each result is written under
`results/process_followup/process_followup_<timestamp>_<suffix>/`.
The final log prints `RESULT_ZIP=...`; a ZIP with checksums is also produced
after interrupted/failed execution when the coordinator can finish cleanup.
A machine kill may prevent ZIP creation, but completed callback writes survive
in their job directories. Actual Dantzig runtime has not been measured for this
new plan. No GDP enumeration or 1050-run grid experiment is included.

## Resume or pack

Use the exact `RUN_DIR` printed by the initial run; do not start another `run`
to resume. A completed run is reused only after checking its result, trace,
lookup values, initial points, incumbent history, clocks, and file hashes.
Failed jobs require `--retry-errors`. Incomplete interrupted jobs restart from
their seed, retaining the old partial trace in `previous_attempts/`; this is
job-level resume, not restoration of an optimizer's internal state.

```bash
# In process_followup_runner; replace the path with the printed RUN_DIR.
PROCESS_RUN=/local/scratch/a/lee4382/repository/RBFopt_Test/results/process_followup/process_followup_TIMESTAMP_SUFFIX

nohup bash run_process_followup_dantzig.sh resume \
  --run-dir "$PROCESS_RUN" --retry-errors \
  >> ../process_followup.log 2>&1 &

tail -f ../process_followup.log

# After execution stops:
bash run_process_followup_dantzig.sh status --run-dir "$PROCESS_RUN"
bash run_process_followup_dantzig.sh pack --run-dir "$PROCESS_RUN"
```

`summary.json` reports `planned_runs=14`, completion/error counts and recorded
callbacks. Require `completed_runs=14` and `all_completed=true` for the finished
supplement; finishing 14 attempts alone does not guarantee success.

## Download from the Mac

Replace the final basename with the log's `RESULT_ZIP`:

```bash
scp lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/process_followup/process_followup_TIMESTAMP_SUFFIX.zip \
    ~/Downloads/
```

## Archived evidence

- `run.json`: frozen plan, settings, source hashes, environment/solver identities.
- `source/`: complete runner/data source snapshot, without licenses or environments.
- `jobs/<id>/`: result, per-job log, checksum seal and full JSONL callback trace.
- `jobs/column_B16_seed10_fmqa_sa/proposals.jsonl`: SA candidates, selected point,
  training targets, model/SA seeds; the callback trace lists actual evaluations.
- `trajectories.csv`: ordered callbacks for completed runs, including coordinates,
  repeat flags, initial/adaptive phase, objective, incumbent, and callback clocks.
- `runs.csv`: completed/failed run outcomes and settings. No failed run is hidden.
- `previous_attempts/`: retained partial traces from retries; these are not counted
  as additional completed replications.

The DFO search clock starts on runner entry and ends on optimizer return.
FMQA retains its original optimizer clock. Both include synchronous trace writes;
validation/export and environment startup are outside the search clock. Raw
method result timing and outer worker timing are also retained. Values returned
by native solvers may differ by floating-point roundoff; callback/table values
and returned best coordinates must still agree exactly, with tolerance only for
the final native scalar. No unobserved coordinates or NLP timings are inferred.
