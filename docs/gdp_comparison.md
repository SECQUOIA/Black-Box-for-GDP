# Full GDP comparison on Dantzig

The [current results and audit](../results/gdp_comparison_current/analysis/README.md)
include 27 completed October 1 BARON/HiGHS GDPopt jobs (RIC, GLOA and LOA)
and 18 September 25 Big-M/Hull jobs. All 45 selected saved solutions pass
original-GDP feasibility checks. Run
`python gdp_current_analysis.py` to recheck these saved solutions without solving.
The [LOA bundle](gdpopt_loa_baron_highs.md) runs nine LOA jobs on CPU 6.
The earlier six-job follow-up is obsolete: the original RIC/GLOA run completed.
The September 25 IPOPT comparison remains historical;
`python gdp_comparison_analysis.py` reproduces its original 36-job audit.

For the 18-job RIC/GLOA rerun with BARON NLP subproblems and HiGHS MILP
masters, use the [Dantzig BARON + HiGHS guide](gdpopt_baron_highs.md) and
`run_gdpopt_baron_highs_dantzig.sh`. The settings below describe the original
IPOPT/CPLEX experiment and remain the general Python runner's defaults.

Nine original model instances (CSTR5/10/15/20/25/30, Column 17, nine-stage
Dynamic, Small Batch) are solved by four methods: GDPopt RIC, GDPopt GLOA,
Big-M + BARON, Hull + BARON.
There are 36 sequential jobs, each limited to 1,800 seconds. GDPopt uses GAMS
IPOPT/MUMPS for every NLP and GAMS CPLEX for its MILP master. All reformulated
MINLPs use GAMS BARON, with internal CPLEX (`LPSol 3`) and IPOPT (`NLPSol 9`)
explicitly selected to avoid automatic subsolver switching. The expected
server version is GAMS 52.2.

The six CSTR sizes match the original Dantzig DSDA/RBFOpt/BAM benchmark.
Each is constructed separately with its own `NT`; a CSTR30 solve does not
replace these smaller full-GDP problems. The earlier CSTR30-only policy applies
to the coordinate-by-coordinate NLP timing dataset, which this runner does not
modify or use to solve the full GDPs.

RIC/GLOA with a local NLP solver are heuristic global searches: an `optimal`
termination from GDPopt is not a global certificate. Their reported bounds
are retained with `global_bound_valid=false`. Only BARON's raw normal/optimal
statuses, together with an independently feasible original GDP solution,
permit `global_optimality_certified=true`.

## Run from a checkout

The committed runner works directly through Python; no shell wrapper is required.
From the repository on Dantzig:

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
git submodule update --init
python3 -m venv .venv-dantzig-gdp
.venv-dantzig-gdp/bin/python -m pip install -r requirements-gdp-comparison.txt
export PYOMO_CONFIG_DIR="$PWD/.pyomo-gdp-comparison"
export GAMS_BIN=/package/gams/52.2/gams
.venv-dantzig-gdp/bin/python gdp_compare.py setup
.venv-dantzig-gdp/bin/python gdp_compare.py check
nohup .venv-dantzig-gdp/bin/python gdp_compare.py run > comparison_console.log 2>&1 &
tail -f comparison_console.log
```

The default is 1,800 seconds per model/method. For a short selected run, use
`gdp_compare.py run --cases small_batch --methods ric,bigm --time-limit 60`.
To package an existing run, use `gdp_compare.py pack --run-dir /path/to/RESULT_DIR`.
Both commands use the same virtual-environment Python as above. Only `setup`
builds MC++; it requires Git, network access and a C++17 compiler.

The regression tests exercise model reformulations, feasibility validation,
the time-limit watchdog and result archives without requiring licensed solvers:

```bash
.venv-dantzig-gdp/bin/python -m pip install pytest
.venv-dantzig-gdp/bin/python -m pytest tests/test_gdp_comparison.py -q
```

## Optional local runner ZIP

The shell-based commands below apply to previously prepared local bundles that
include `run_gdp_comparison_dantzig.sh`. That wrapper is not committed. A bundle
created from a fresh checkout can use `python gdp_compare.py` directly after
installing the requirements and setting `RBFOPT_GDP_SOURCES` to the repository's
`external` directory. Use `--output-root ../results` when running from the
extracted runner directory to keep result archives in the repository's results.

Upload the small runner ZIP from the Mac:

```bash
scp ~/Repos/RBFopt_Test/results/dantzig_review/gdp_comparison_runner.zip \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

On Dantzig:

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
unzip -o gdp_comparison_runner.zip
cd gdp_comparison_runner
sha256sum -c COMPARISON_RUNNER_SHA256SUMS
bash run_gdp_comparison_dantzig.sh setup
bash run_gdp_comparison_dantzig.sh check
nohup bash run_gdp_comparison_dantzig.sh run > comparison_console.log 2>&1 &
tail -f comparison_console.log
```

The original source checkouts and `.venv-dantzig-gdp` are reused. `setup`
installs the comparison requirements and compiles Pyomo's MC++ interface;
it needs Git, a C++17 compiler and network access to the official MC++ source.
Its pinned revision is `c8ae9800d02b09bee0012aed593de92c9cf10fa7`.
It is installed under the repository's `.pyomo-gdp-comparison` directory,
not into the source checkout. `check` verifies MC++ arithmetic, actually solves
small IPOPT/CPLEX/BARON test models, and writes all selected reformulations to
GAMS files. License/dependency failures stop before the full experiment.

Both `check` and `run` perform preflight; the explicit check command is useful
before launching the long background run. `run` may take approximately eighteen
hours if every job reaches its limit. Ctrl+C exits `tail`, not the background run.

Overrides: `GDP_REPOSITORY`, `GDP_PYTHON`, `GAMS_BIN`, `GDP_GAMS_VERSION`,
`RBFOPT_GDP_SOURCES`, `PYOMO_CONFIG_DIR`. Example of a short isolated test:

```bash
bash run_gdp_comparison_dantzig.sh run --cases small_batch --methods ric,bigm --time-limit 60
```

`--cases cstr` runs all six CSTR sizes (24 jobs). To select specific sizes:

```bash
bash run_gdp_comparison_dantzig.sh run --cases cstr --cstr-sizes 5,10,15,20,25,30
bash run_gdp_comparison_dantzig.sh run --cases cstr --cstr-sizes 30
```

`--cstr-grid-sizes` is an alias for `--cstr-sizes`, matching the older benchmark
terminology. Sizes are reactor counts, not evaluation budgets.

The Python command works without a shell wrapper:

```bash
PYOMO_CONFIG_DIR="$PWD/.pyomo-gdp-comparison" \
  .venv-dantzig-gdp/bin/python gdp_compare.py run \
  --executable /package/gams/52.2/gams --expected-gams-version 52.2
```

## Fairness, initialization and timing

All methods receive independent unsolved clones of the same original GDP.
The integer choices are optimized freely, not enumerated or fixed to a known
solution. Saved upstream values are loaded where available (including
size-matched CSTR5/10/15/20/25 initializations); CSTR30
and Dynamic use their constructor defaults. Prior point timing tables and their
optimal objective values are not used by these solves. GDPopt uses its standard
set-covering initialization and subproblem initialization behavior. BARON is
called without transmitting variable levels as a warm start; it constructs its
own starting point. This avoids a reproducible local BARON failure with an
infeasible supplied starting point in the small MINLP preflight test.

Before cloning methods, FBBT uses only globally active constraints to derive
valid bounds. This is applied identically to all methods, and every changed
bound is recorded. It supplies the implied finite bounds for Small Batch's
exponentials, avoiding MC++'s arbitrary missing-bound fallback and overflow.
Constraints inside mutually exclusive disjuncts are not intersected.

Big-M constants are inferred from the original expression bounds. Hull uses
Pyomo's standard perspective reformulation. No arbitrary global M or new
physical bounds are introduced. Transformation errors are explicit outcomes.

For Column/Hull only, BARON uses `LBTTDo 0` to disable linear-feasibility-based
range reduction. With the default `LBTTDo 1`, local GAMS 53.3 testing returned
infeasible immediately even though a feasible original GDP solution also
satisfied the Hull constraints. Disabling this one option removed that early
rejection. This is a recorded numerical workaround, not a change to the model
or a guarantee of finding an incumbent. To test BARON's stock setting on GAMS
52.2, use `--cases column --methods hull --baron-column-hull-lbtt 1` in a separate
run. Report this solver setting when presenting the benchmark.

Dynamic is built and discretized once in the parent process, with the existing
30 finite elements/stage, three Radau points and derivative bounds [-300,300].
Each method receives an independent unsolved clone through an isolated forked
worker. One-time template preparation is recorded separately; add it once to a
standalone method's cost when comparing end-to-end solution workflows.

OpenMP/BLAS thread limits are forced to one before importing numerical libraries.
On Linux, the parent and inherited workers are pinned to `--cpu CPU_ID`, or the
first allowed CPU if omitted. The effective affinity and physical-core topology
are recorded in `run.json`. An unavailable CPU is an error, not a fallback.
For the CPU 0 FMQA / CPU 2 GDP rerun, use the
[upload and execution guide](dantzig_cpu_rerun.md), which verifies these are
different physical cores before launching. Affinity is not an exclusive reservation.
Every GAMS call explicitly receives `threads=1` and the remaining job budget.
The configured GAMS executable is used directly (Pyomo 6.10's default shell
constructor does not honor an `executable=` keyword on its own).

The 1,800-second worker budget includes cloning, reformulation, the optimization
algorithm and validation. Parent template construction and preflight are separate.
Each solver receives slightly less than the remaining worker time so results can
be loaded. A parent watchdog terminates the worker and solver process group at
the deadline, with up to six seconds for cleanup, then starts the next job.
This prevents GDPopt from receiving a fresh 30 minutes for every subproblem.
GAMS uses relative objective gap `1e-5` with zero absolute gap; GDPopt's separate
absolute bound-convergence tolerance is `1e-5`. IPOPT's tolerance is `1e-8`.

GDPopt feasible-subproblem callbacks save independently checked incumbents as
they become available, so they survive a later error/timeout. BARON incumbents
are loaded when GAMS returns within its internal time limit. A forced external
kill cannot guarantee recovery of an unreturned BARON incumbent.

## Results

Each invocation creates `results/dantzig_gdp_compare_DATE_ID/` and a matching
ZIP with SHA256 checksums. It prints `RESULT_DIR` and `RESULT_ZIP`.

- `summary.csv`, `summary.json`: model instance ID, CSTR size, objective, feasibility, termination, bounds,
  certificate status, timings and solver call counts for every attempted job.
- `run.json`: configuration, sources, solver versions, dependency checks,
  thread/CPU policy and shared model preparation.
- `jobs/INSTANCE/METHOD/result.json`: detailed final outcome. CSTR instances
  use separate `cstr_5`, `cstr_10`, ..., `cstr_30` directories, so sizes cannot
  overwrite one another.
- `solution.json`: best independently validated original GDP variable values.
- `incumbents.jsonl`: feasible-subproblem/final checks and elapsed timestamps.
- `solver_calls.jsonl`: each GAMS call's raw statuses, bounds and wall time.
- `run.log`: complete GDPopt/GAMS output; failed calls also keep listing files.
  BARON outcomes without a feasible incumbent also retain diagnostic listings.
- `source/`: exact runner snapshot used for this invocation.

`complete` means all planned jobs returned an outcome, not that all were solved
or certified. The result preserves time-limit incumbents separately from proofs.
Original model constraints, selected disjuncts, logical conditions, bounds and
integrality are checked before an objective is reported as feasible. Timers
overlap; do not sum `solve_wall_s`, `method_wall_s` and `worker_wall_s` together.

To package saved work after a forced interruption:

```bash
bash run_gdp_comparison_dantzig.sh pack --run-dir /absolute/path/to/RESULT_DIR
```

Download the printed ZIP from a Mac terminal:

```bash
scp lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/RESULT_NAME.zip \
  ~/Downloads/
```

Sources: [Pyomo GDPopt](https://pyomo.readthedocs.io/en/stable/explanation/solvers/gdpopt.html),
[GDP reformulations](https://pyomo.readthedocs.io/en/6.4.1/modeling_extensions/gdp/solving.html),
[GAMS BARON options](https://www.gams.com/52/docs/S_BARON.html),
[MC++](https://github.com/omega-icl/mcpp). Runtime is pinned to Pyomo 6.10.0;
the installed implementation is used for callback and solver configuration.
