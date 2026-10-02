# Original DFO traces and separate coordinate NLP timings

The completed October 2 experiment is published in the [verified English report](../results/dfo_trace_nlp_20261002/analysis/README.md). No rerun is needed to use these results.

This runner uses the existing DFO implementations, settings and lookup objectives. The earlier expanded `dantzig_nlp_overnight_20261002.zip` is withdrawn; do not launch it.

## Scope

1. Run the original DSDA, RBFOpt and BAM configurations 139 times each on Dantzig: 417 lookup runs. Record actual runtime and every callback coordinate in order. Preserve initial designs, seeds, evaluation budgets and each algorithm's original handling of infeasible lookup values.
2. Measure NLP evaluation costs at visited coordinates only. Reuse verified original Dantzig attempts with matching model, size, solver, initialization and time limit. Measure only missing coordinates. Retain preprocessing rejection, infeasibility and solver failure times.
3. Reuse the original 139 Dantzig FMQA traces. No additional FMQA experiment is run.

NLP results are measured separately and never fed into the searches. This runner does not launch the withdrawn 556-run online experiment, full-grid enumeration or GDPopt jobs.

## Output

| File | Contents |
|---|---|
| `analysis/dfo_runs.csv` | Recorded DFO time, final result and source identity |
| `analysis/evaluation_timings.csv` | Ordered callback coordinates, DFO timestamps and separate point costs |
| `analysis/point_timings.csv` | Point evaluation time, solver invocation time, outcome and source |

The runner also saves `dfo_time_summary.csv`, an English `analysis/README.md`, and a coverage audit. The publication command below adds the outcome breakdown, run-level attached costs and figures.

- `nlp_evaluation_wall_s` includes point-specific model setup, preprocessing, solver invocation when needed and validation.
- `nlp_solve_wall_s` is a subset of evaluation time, not an additional cost.
- A preprocessing rejection can have zero solver time and a positive measured evaluation time. The evaluation time is included.
- Repeated callback coordinates remain in the ledger and link to the same separately measured attempt.
- A successful retry with different initialization does not replace the original attempt. Missing costs remain blank.
- Dynamic template preparation is recorded separately in `dynamic_preparations.json`.
- Premeasurement warmup/model checks and process overhead are preserved separately from the point timer.
- A local solver's infeasibility report is not a global infeasibility certificate. Other rejected/failed attempts remain distinct.

Defaults: CPU **6**, GAMS **52.2 / IPOPT (MUMPS)**, **60 seconds** per point solve. RBFOpt retains its original BONMIN/IPOPT settings. Explicit `NLP_SOLVER=baron` changes only the separate point measurement solver; historical IPOPT costs are then not reused.

## Build an English runner bundle

The original executed ZIP is frozen evidence and must not be rewritten to change its source hashes. The current bundle command includes English instructions as `README.md`:

```bash
python -m overnight_benchmark bundle --output results/runners/dantzig_dfo_trace_nlp_english.zip
```

## Upload and run a new experiment

These commands are for a deliberately requested new run, not for importing the completed results.

On the Mac:

```bash
scp results/runners/dantzig_dfo_trace_nlp_english.zip{,.sha256} \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

On Dantzig:

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
sha256sum -c dantzig_dfo_trace_nlp_english.zip.sha256
unzip dantzig_dfo_trace_nlp_english.zip
cd dantzig_dfo_trace_nlp_english
bash run_dfo_trace_nlp_dantzig.sh setup
bash run_dfo_trace_nlp_dantzig.sh check > preflight.log 2>&1
```

After a successful preflight:

```bash
nohup bash run_dfo_trace_nlp_dantzig.sh run > dfo_trace_nlp.log 2>&1 < /dev/null &
echo $! > dfo_trace_nlp.pid
tail -f dfo_trace_nlp.log
```

The setup command clones the existing BAM environment into a separate environment. Server locations can be configured through `NLP_REPOSITORY`, `NLP_BASE_ENV`, `NLP_ENV`, `NLP_CONDA`, `COIN_BIN`, `GAMS_BIN`, `BAM_LICENSE_FILE` and `RBFOPT_GDP_SOURCES`.

## Resume and download

A nohup process continues after SSH disconnection. `RUN_DIR=...` in the log identifies the result directory. Resume with the same source bundle after confirming the previous process has exited. Completed jobs are skipped and interrupted attempts are preserved.

```bash
RUN_DIR=/local/scratch/a/lee4382/repository/RBFopt_Test/results/dfo_trace_nlp/ACTUAL_RUN_DIRECTORY
bash run_dfo_trace_nlp_dantzig.sh status --run-dir "$RUN_DIR"
nohup bash run_dfo_trace_nlp_dantzig.sh resume --run-dir "$RUN_DIR" > resume.log 2>&1 < /dev/null &
```

Completion automatically creates a ZIP and `.zip.sha256` beside the result directory. They preserve callback traces, point results, available solver logs, conditions, source hashes and tables.

```bash
# On the Mac, replace ACTUAL_RUN_DIRECTORY with the name printed by the runner.
scp 'lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/dfo_trace_nlp/ACTUAL_RUN_DIRECTORY.zip*' ~/Downloads/
```

## Rebuild the completed English report

```bash
python dfo_trace_analysis.py --output results/dfo_trace_nlp_20261002/analysis
```

This reads saved archives only. It does not run an optimizer or solver.
