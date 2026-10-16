# Small Batch RBFOpt: MSRSM with solver-based search

This supplement reruns **only RBFOpt**, using `algorithm=MSRSM`,
`global_search_method=solver`, and `rbf=auto`, matching the other process cases.
Bonmin solves RBFOpt's surrogate MINLPs; IPOPT is available for the auxiliary
NLPs that RBFOpt requests. This is not a new enumeration of the GDP subproblems.

The domain remains `{1,2,3}^3` (27 configurations). Seeds 0–9 retain the exact
ordered three-point initial designs in `benchmark_protocols/small_batch_full_domain.json`.
The budget is **10 total objective callbacks per run, including the three starts**.
Infeasible and repeated callbacks count toward that budget. The original lookup
values, infeasibility penalty, and archived Dantzig point costs are unchanged.
No feasible-only filtering, seed replacement, or solver option tuning is applied.
RBFOpt uses one CPU and its original auxiliary-solver defaults (including Bonmin's
45-second time limit per auxiliary solve). The worker watchdog is 2,100 seconds
per seed; timeouts are reported as failures and are never counted as completion.

The script records every objective callback durably, as well as every actual
Bonmin/IPOPT invocation made through RBFOpt's Pyomo solver interface. Auxiliary
solver options, termination conditions, exceptions and elapsed times are saved;
RBFOpt's own handling of nonoptimal auxiliary solves is preserved. Completed runs
must contain a valid callback trace and at least one actual Bonmin invocation.
The summary distinguishes nonoptimal auxiliary solves from failed benchmark runs.
Tracing overhead is included in the optimizer wall time.

The previous sampling results remain archived. These new results are intended to
replace only the ten Small Batch RBFOpt runs once the returned ZIP is validated.
DSDA, BAM and FMQA-SA are not rerun or changed.

## Dantzig

Extract the provided ZIP in `/local/scratch/a/lee4382/repository/RBFopt_Test`.
The independent folder is `small_batch_rbfopt_solver_runner`.
The existing `.venv-dantzig-nlp-overnight` environment is used, falling back to
`.venv-dantzig-grid-trace` if absent. `PROCESS_DFO_ENV` overrides the choice.
The exact package pins are in `requirements-small-batch-rbfopt-solver.txt`.
Native Bonmin/IPOPT executables default to `.venv-dantzig/bin` (`COIN_BIN` override).
FMQA, BAM, GAMS and their licenses are not required by this experiment.

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test/small_batch_rbfopt_solver_runner
bash run_small_batch_rbfopt_solver_dantzig.sh check
```

After the check succeeds, launch all ten seeds sequentially:

```bash
PROCESS_CPU=6 nohup bash run_small_batch_rbfopt_solver_dantzig.sh run \
  > ../small_batch_rbfopt_solver.log 2>&1 &
tail -f ../small_batch_rbfopt_solver.log
```

One logical CPU is selected using affinity and library thread counts are set to
one. Other users' processes can still share that CPU. CPU 6 can be changed with
`PROCESS_CPU` before creating a run. The run logs its absolute `RUN_DIR`; on
completion it prints `RESULT_ZIP=...`. Expected success: `planned_runs=10`,
`completed_runs=10`, `failed_runs=0`, `all_completed=true`.

To resume after interruption, use the **same extracted code** and printed run
directory. Completed runs are validated and reused, and incomplete/failed
attempts are retained before retrying:

```bash
nohup bash run_small_batch_rbfopt_solver_dantzig.sh resume \
  --run-dir /absolute/path/from/RUN_DIR --retry-errors \
  >> ../small_batch_rbfopt_solver.log 2>&1 &
```

Do not run two coordinators on the same run directory. After stopping a run,
`status --run-dir ...` or `pack --run-dir ...` validates existing results and
reports or packages the partial run.

## Output

- `run.json`: frozen plan, source hashes, versions, solver binary hashes and CPU.
- `jobs/*/lookup.traces/*.jsonl`: ordered starts and adaptive coordinates, objective,
  incumbent, repeated-point flag and callback times; flushed to disk per event.
- `jobs/*/solver_calls.jsonl`: actual auxiliary-solver starts and returns/errors.
- `jobs/*/run.log`, `result.json`, `terminal.json`: optimizer output and integrity checks.
- `trajectories.csv`, `auxiliary_solver_calls.csv`: aggregated traces.
- `evaluation_costs.csv`, `completion_estimates.csv`: every callback joined to its
  archived point time, including repeats and infeasibility processing.
- `summary.json`: completion, timing coverage, and auxiliary-solver totals.

Estimated NLP-inclusive completion time is the recorded optimizer time minus
lookup callback time plus the measured point costs along that run's trajectory.
It remains a reconstructed cost, not measured online GDP/NLP runtime.

Local diagnostic runs must use `--allow-other-host` and remain separate from
publication data. They are not a substitute for the Dantzig benchmark.
