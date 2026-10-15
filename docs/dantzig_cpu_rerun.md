# FMQA and GDP rerun on separate physical cores

The September 22 FMQA Grid run and full-GDP comparison both used CPU 0 and
overlapped. Those contaminated result archives and derived comparisons were
removed by user instruction after verification of the replacement runs.
Do not resume the old runs or combine their timings with the new measurements.

The September 25 replacements are now available: [FMQA results](../results/fmqa_20260925/README.md)
and [GDPopt/BARON results](../results/gdp_comparison_20260925/analysis/README.md).

Use FMQA Grid on logical CPU 0, GDP comparison on CPU 2, and FMQA process cases
on CPU 4 **only if the topology checks below confirm three different physical cores**.
All retain one-thread settings. Affinity separates these jobs; it does
not reserve the server or exclude other users, shared cache or memory traffic.
For an otherwise idle measurement, run FMQA first and GDP after it finishes.

## Upload the prepared ZIP from the Mac

```bash
scp /Users/albertlee0125/Repos/RBFopt_Test/results/dantzig_review/dantzig_cpu_split_runner_20260925.zip \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

The ZIP contains both Python runners, the frozen FMQA input tables/designs,
this guide and checksums. It contains no shell wrappers, solver license, new
result archives or Python environment. GDP reuses the pinned source checkouts, GAMS 52.2,
MC++ installation and environments from the previous server run.

## Prepare on Dantzig

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
unzip dantzig_cpu_split_runner_20260925.zip

export BENCH_ROOT="$PWD"
export RERUN_ROOT="$BENCH_ROOT/dantzig_cpu_split_runner_20260925"
export FMQA_PY="$BENCH_ROOT/.venv-dantzig-fmqa/bin/python"
export GDP_PY="$BENCH_ROOT/.venv-dantzig-gdp/bin/python"
export RBFOPT_GDP_SOURCES="$BENCH_ROOT/external"
export PYOMO_CONFIG_DIR="$BENCH_ROOT/.pyomo-gdp-comparison"
export GAMS_BIN=/package/gams/52.2/gams
export PYTHONNOUSERSITE=1
export PYTHONUNBUFFERED=1

(cd "$RERUN_ROOT" && sha256sum -c SHA256SUMS)
lscpu -e=CPU,CORE,SOCKET,ONLINE
taskset -pc $$
pgrep -af 'fmqa_.*(runner|benchmark).*run|gdp_compare.py.*run|run_gdp_comparison_dantzig'
```

The last command lists any existing runs; no output is normal if none are
running. Wait for any old job using the selected cores to finish before
starting. Do not launch the same rerun block twice. To inspect one existing
process's allowed CPUs, use `taskset -pc PID` with its numeric process ID.

## Launch

The block checks both Python environments and GAMS, then verifies the CPUs
are allowed and on separate physical cores. If it fails, no job is launched.
Change `GDP_CPU=2` to a different allowed physical core if requested by the
check. CPU IDs are zero-based logical processor IDs.

```bash
FMQA_CPU=0
GDP_CPU=2
FMQA_CASE_CPU=4
if test -x "$FMQA_PY" && test -x "$GDP_PY" && test -x "$GAMS_BIN" && \
   (cd "$RERUN_ROOT" && sha256sum --quiet -c SHA256SUMS) && \
   "$FMQA_PY" "$RERUN_ROOT/fmqa_grid_runner/cpu_affinity.py" --check-pair "$FMQA_CPU" "$GDP_CPU" && \
   "$FMQA_PY" "$RERUN_ROOT/fmqa_grid_runner/cpu_affinity.py" --check-pair "$FMQA_CPU" "$FMQA_CASE_CPU" && \
   "$FMQA_PY" "$RERUN_ROOT/fmqa_grid_runner/cpu_affinity.py" --check-pair "$GDP_CPU" "$FMQA_CASE_CPU"
then
  nohup "$FMQA_PY" "$RERUN_ROOT/fmqa_grid_runner/fmqa_grid_benchmark.py" run \
    --cpu "$FMQA_CPU" --output-root "$BENCH_ROOT/results/cpu_split_20260925" \
    > "$RERUN_ROOT/fmqa_grid.log" 2>&1 &
  echo $! > "$RERUN_ROOT/fmqa_grid.pid"

  nohup "$GDP_PY" "$RERUN_ROOT/gdp_comparison_runner/gdp_compare.py" run \
    --cpu "$GDP_CPU" --time-limit 1800 \
    --output-root "$BENCH_ROOT/results/cpu_split_20260925" \
    > "$RERUN_ROOT/gdp_comparison.log" 2>&1 &
  echo $! > "$RERUN_ROOT/gdp_comparison.pid"

  nohup "$FMQA_PY" "$RERUN_ROOT/fmqa_grid_runner/fmqa_benchmark_runner.py" run \
    --dataset case --cpu "$FMQA_CASE_CPU" \
    --output-root "$BENCH_ROOT/results/cpu_split_20260925" \
    > "$RERUN_ROOT/fmqa_cases_cpu4.log" 2>&1 &
  echo $! > "$RERUN_ROOT/fmqa_cases_cpu4.pid"
else
  echo 'Not started: check environments, ZIP integrity and CPU selection above.'
fi
```

- **FMQA Grid:** 21 functions × 10 seeds × 5 budgets = 1,050 runs; the original
  three ordered initial points, FM training settings and SA settings are
  unchanged. No new DSDA/RBFOpt/BAM run or NLP timing batch is launched.
- **GDP comparison:** CSTR 5/10/15/20/25/30, Column, Dynamic and Small Batch ×
  RIC/GLOA/Big-M/Hull = 36 sequential jobs. Each job has a 1,800-second worker
  wall-time cap; shared preparation is separate. Up to six seconds are allowed
  for process cleanup. GDPopt uses IPOPT; reformulations use BARON through
  GAMS 52.2. Dynamic is discretized once, then cloned for each method.
- **FMQA process cases:** 139 original conditions on CPU 4, with the frozen
  three-point designs and original evaluation budgets; lookup objectives.

Each runner pins its parent process; workers and solver subprocesses inherit
that affinity. The console's `CPU_AFFINITY` line and the new `run.json` record
the effective allowed CPU, socket/core IDs and sibling thread IDs. An invalid
CPU raises an error; it never silently falls back to CPU 0. Resuming a new
FMQA run requires the same CPU as well as the same original experiment options.

## Track and download

```bash
tail -f "$RERUN_ROOT/fmqa_grid.log" "$RERUN_ROOT/gdp_comparison.log" "$RERUN_ROOT/fmqa_cases_cpu4.log"
```

`Ctrl+C` stops viewing the logs, not the jobs. In another terminal, or after
exiting `tail`, verify the parent affinities:

```bash
taskset -pc "$(cat "$RERUN_ROOT/fmqa_grid.pid")"
taskset -pc "$(cat "$RERUN_ROOT/gdp_comparison.pid")"
taskset -pc "$(cat "$RERUN_ROOT/fmqa_cases_cpu4.pid")"
```

At completion the logs print `RESULT_ZIP`. Both runners automatically create
timestamped result directories, ZIP files and matching `.zip.sha256` files
under:

```text
/local/scratch/a/lee4382/repository/RBFopt_Test/results/cpu_split_20260925/
```

After **all three jobs finish**, run on the Mac to download this rerun's ZIPs and
checksums to Downloads:

```bash
scp 'lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/cpu_split_20260925/*.zip' ~/Downloads/
scp 'lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/cpu_split_20260925/*.zip.sha256' ~/Downloads/
```

The uploaded September 25 FMQA archives confirm Grid on CPU 0 and process
cases on CPU 4. See the [current data and figure index](../results/fmqa_20260925/README.md).
