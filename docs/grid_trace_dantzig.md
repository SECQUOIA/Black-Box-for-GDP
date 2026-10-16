# Grid RBFOpt and BAM callback traces

This runner repeats the original **21 grids × 10 seeds × 5 total budgets**
(`10,30,50,70,100`), separately for RBFOpt and BAM 5.0.0: **1,050 runs per method**.
It uses the original CSV objectives and the 210 archived, ordered initial
designs (three points per grid/seed). Reference hashes and all historical
initial incumbent prefixes are checked before starting. No process case
studies or NLP timing jobs are run by this package.

These are new searches. Matching inputs and settings do not certify that new
adaptive paths equal the unavailable historical RBFOpt/BAM paths. RBFOpt uses
the original `MSRSM`, `rbf=auto`, solver-based global search and seeded defaults.
BAM uses the existing `x_evaluated`/`f_evaluated` warm start and remaining budget;
its seed identifies the frozen initial design, with no new native RNG option.
Each job runs in a fresh process and working directory.

The completed [RBFOpt trajectories](../results/grid_trace_rbfopt_20261010/README.md)
and [BAM archive](../results/archives/grid_trace_bam_20261008_190603_5bh3y_t5.zip)
are retained with their executed source snapshots. The
[current path-cost comparison](../results/grid_gdp_dfo_20261011/README.md)
rebuilds figures from those results without running either optimizer.

## Dantzig setup

Build an execution ZIP from the current checkout when a new experiment is
needed. From the repository root on the Mac:

```bash
python grid_trace_runner.py bundle --output /tmp/grid_dfo_trace_runner.zip
scp /tmp/grid_dfo_trace_runner.zip /tmp/grid_dfo_trace_runner.zip.sha256 \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

Extract into a new directory on Dantzig:

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
sha256sum -c grid_dfo_trace_runner.zip.sha256
unzip -n grid_dfo_trace_runner.zip -d grid_trace_package
cd grid_trace_package/grid_dfo_trace_runner
sha256sum -c SHA256SUMS
bash run_grid_trace_dantzig.sh setup
```

Setup clones `.venv-dantzig-bam` into `.venv-dantzig-grid-trace` and installs the
six pinned packages in `requirements-grid-trace.txt`. Existing environments
are not modified. Override `GRID_REPOSITORY`, `GRID_BASE_ENV`, `GRID_ENV` or
`GRID_CONDA` if their locations differ. Solver defaults are:

- `COIN_BIN=$GRID_REPOSITORY/.venv-dantzig/bin` (BONMIN and IPOPT for RBFOpt).
- `BAM_LICENSE_FILE=/local/scratch/a/lee4382/bamlice.txt` (BAM only).

No solver executables or license contents are included in either ZIP. Runtime
provenance records executable/license hashes, package versions and CPU affinity.
The BAM native version must be `2026-09-10`, matching the archived 5.0.0 rerun.

## Run the methods separately

Choose two available CPUs on different physical cores. The examples use CPUs
0 and 2; check availability and other running experiments before using them.
Affinity does not reserve a core exclusively. Each process and its solver
children are pinned to one CPU, with numerical libraries restricted to one
thread.

```bash
bash run_grid_trace_dantzig.sh plan --method rbfopt
bash run_grid_trace_dantzig.sh plan --method bam

# Use the Python installed by setup for this topology check.
/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-grid-trace/bin/python cpu_affinity.py --check-pair 0 2
bash run_grid_trace_dantzig.sh check --method rbfopt --cpu 0
bash run_grid_trace_dantzig.sh check --method bam --cpu 2

nohup bash run_grid_trace_dantzig.sh run --method rbfopt --cpu 0 > ../grid_trace_rbfopt.log 2>&1 &
nohup bash run_grid_trace_dantzig.sh run --method bam --cpu 2 > ../grid_trace_bam.log 2>&1 &
```

`check` validates the full selected plan and runs one real 10-evaluation smoke
job, discarding its temporary outputs. The two `run` commands create distinct
directories under `results/grid_dfo_trace/`; their `RUN_DIR` values are printed
in the logs. They can also be run sequentially. No new external time limit is
imposed by default; the original optimizer defaults remain in force.
An optional `--max-run-seconds N` stops the experiment on an overlong job and
keeps its partial trace. It does not mark the incomplete search as a success.

For a short test, append `--grids ackley --seeds 0 --budgets 10` to `run`.
The Python entry point is also usable directly:

```bash
python grid_trace_runner.py run --method rbfopt --cpu 0 --grids ackley --seeds 0 --budgets 10
```

## Progress, interruptions and output

```bash
bash run_grid_trace_dantzig.sh status --run-dir /absolute/path/from/RUN_DIR
bash run_grid_trace_dantzig.sh resume --run-dir /absolute/path/from/RUN_DIR
bash run_grid_trace_dantzig.sh pack --run-dir /absolute/path/from/RUN_DIR
```

Resume reuses the original method, selection, CPU and configuration. It verifies
the runtime, source hashes, completed result checksums, every trace and its
CSV objective values before skipping completed jobs. Interrupted/failed jobs
start new attempts; earlier partial JSONL files and logs remain intact. An
active coordinator or orphan worker prevents a duplicate launch. `pack` runs
only after the experiment stops. Normal exit and handled interruption also
pack results automatically; after a forced kill, use `pack` or `resume`.

The result ZIP and SHA256 sidecar are printed as `RESULT_ZIP`. It contains:

- `run.json`: frozen plan, initial coordinates and hashes, configuration,
  runtime versions, CPU and timing definitions.
- `jobs/<job>/attempt_*/lookup.traces/*.jsonl`: every actual objective callback,
  flushed immediately, including initial points and repeated coordinates.
  Incomplete attempts retain `.partial.jsonl` traces.
- `jobs/<job>/attempt_*/result.json`: optimizer result, trace checksum,
  search elapsed time, summed lookup time and evaluation-budget overrun flag.
- `jobs/<job>/attempt_*/run.log`: original optimizer output.
- `benchmark.csv`: original result schema for completed, validated jobs.
- `evaluations.csv`: flat callback table for those jobs, in evaluation order.
  Fields include job/method/grid/seed/budget, evaluation index, phase,
  `requested_point`, integer `point`, objective, incumbent, `repeated_point`,
  `objective_wall_s`, `started_elapsed_s`, `completed_elapsed_s` and trace path.
- `visited_points.json`: unique `(csv_name, point)` pairs for later point-cost
  measurement. It does not replace the ordered trace when charging repeats.
- `summary.json`, `progress.json`, `source/` and `SHA256SUMS`.

Aggregate CSVs are regenerated on completion, interruption or `pack`;
per-job JSONL and result files are the live checkpoints. Internal optimizer
cache hits that never call the objective incur no new objective evaluation
and therefore are absent from the callback trace.

Resume uses the same extracted source as the original run, including its guide
and input hashes. Historical snapshots are available under `source/` in the
published result archives. The BAM archive additionally retains the corrected
runner under `validation_fix/`. That validation-only update accepts a `1e-12`
absolute difference in the native returned scalar while preserving the point,
callback, incumbent and evaluation-count checks. A new checkout is intended
for new runs; historical resume still enforces its recorded source identity.

## Reconstructing evaluation cost later

For callback prefix `k`, use the trace's completion clock and replace the
measured lookup costs with the chosen point-evaluation costs:

```text
reconstructed_elapsed(k) = completed_elapsed_s(k)
                          - sum(objective_wall_s[1:k])
                          + sum(point_evaluation_cost[point_i], i=1..k)
```

For total search time use `search_wall_s` in place of `completed_elapsed_s(k)`.
That clock excludes input CSV loading, worker startup, post-run validation and
export, and includes optimizer setup and trace overhead. The legacy
`benchmark.csv` `wall_time_s` keeps its original optimizer-specific definition.
Repeated callbacks are charged repeatedly unless an explicit evaluation cache
is part of the intended experiment. Do not simply add NLP cost without removing
the lookup cost already included in the measured search time.

This is a reconstruction along a recorded lookup search, not a measurement of
an online run using NLP evaluations. Solver errors, time-based stopping rules,
or changed objective values can change a real online path. In these grid GDPs,
fixing both lattice coordinates leaves no continuous optimization freedom;
function evaluation, model preparation and any forced solver invocation must
be identified separately when measuring point costs.

## Rebuild the execution ZIP

```bash
python grid_trace_runner.py bundle --output /tmp/grid_dfo_trace_runner.zip
```

The command refuses to overwrite an existing ZIP. It packages only required
source files, the 21 grid CSVs, the reference audit/CSV files, this guide and
checksums. It does not require Git or access to historical archives at runtime.
