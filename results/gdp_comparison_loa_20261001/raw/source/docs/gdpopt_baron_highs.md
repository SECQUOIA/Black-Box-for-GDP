# GDPopt rerun on Dantzig: BARON + HiGHS

The received October 1 snapshot has 12 completed CSTR jobs and six pending
final records; see the [current audit](../results/gdp_comparison_current/analysis/README.md).
Use the [15-job follow-up](gdpopt_followup.md) for the missing Column/Dynamic/
Small Batch RIC/GLOA jobs plus LOA on all nine models.

This rerun covers all nine existing instances: CSTR5/10/15/20/25/30,
Column 17, nine-stage Dynamic, and Small Batch. Each runs RIC and GLOA,
for **18 sequential jobs at 1,800 seconds each** (up to about nine hours,
plus preflight/model construction/cleanup). It uses the same models,
initialization, bounds, feasibility checks and CPU/thread policy as the
[original comparison](gdp_comparison.md).

| Role | New setting |
|---|---|
| GDPopt NLP subproblem | GAMS BARON |
| GDPopt MILP master / initialization | GAMS HiGHS |
| BARON internal LP/MIP solver | CLP/CBC (`LPSol 8`) |
| BARON internal local NLP search | IPOPT (`NLPSol 9`) |
| Runtime | GAMS 52.2, Pyomo 6.10.0, existing MC++ build |
| CPU | Logical CPU 2, one thread; override with `GDP_CPU` or `--cpu` |

HiGHS is the GDPopt master solver. BARON does not expose HiGHS as an
internal `LPSol` choice in GAMS 52; CLP/CBC removes the internal CPLEX
dependency. IPOPT inside BARON is a local search component of BARON's global
algorithm, not the GDPopt NLP solver. No `highspy` package is needed.
The runner registers HiGHS's supported linear model types in Pyomo 6.10's
older GAMS writer allowlist; actual availability is verified by solving a MIP.

## Upload and run the bundle

On the Mac, from the repository:

```bash
scp results/dantzig_review/gdpopt_baron_highs_runner.zip \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

On Dantzig:

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
RERUN_DIR=$(mktemp -d "$PWD/gdpopt_baron_highs_runner_XXXXXX")
unzip -q gdpopt_baron_highs_runner.zip -d "$RERUN_DIR"
cd "$RERUN_DIR/gdp_comparison_runner"
sha256sum -c COMPARISON_RUNNER_SHA256SUMS
nohup bash run_gdpopt_baron_highs_dantzig.sh run > console.log 2>&1 &
echo "PID=$! LOG=$PWD/console.log"
tail -f console.log
```

`run` automatically performs preflight before any benchmark jobs. It checks
the GAMS version, MC++, a nonconvex continuous BARON NLP, and a HiGHS MIP.
Missing solvers/licenses/dependencies stop the run. It reuses the server's
existing `.venv-dantzig-gdp`, `.pyomo-gdp-comparison` and pinned `external`
source checkouts. If the runtime has not been prepared, run
`bash run_gdpopt_baron_highs_dantzig.sh setup` first; this installs the pinned
Python requirements and builds MC++ (network and a C++17 compiler required).
Ctrl+C stops `tail`, not the background benchmark.

Results go to new unique directories under `results/gdpopt_baron_highs/`.
The log prints `RESULT_DIR` and `RESULT_ZIP`; each run saves its configuration,
source snapshot, solver call records, independently checked incumbents and
SHA256-checked result ZIP. The September 25 results are not replaced.
Download the printed archive with `scp`, as for the previous runs.

## Optional checks and selections

From either the extracted bundle or the repository:

```bash
bash run_gdpopt_baron_highs_dantzig.sh check
bash run_gdpopt_baron_highs_dantzig.sh run --cases cstr --cstr-sizes 5 --time-limit 60
```

The default wrapper always selects all 18 jobs. Later CLI flags can select
models/methods, a different time budget or an available CPU. A busy CPU does
not become exclusively reserved through affinity. Each worker and solver
inherits the one-thread limits and a shared deadline, including every BARON
subproblem. No subproblem receives a fresh 1,800 seconds.

The equivalent direct Python flags are:

```bash
.venv-dantzig-gdp/bin/python gdp_compare.py run \
  --methods ric,gloa --nlp-solver baron --mip-solver highs --baron-lp-solver clp \
  --cpu 2 --output-root results/gdpopt_baron_highs
```

The general Python runner retains IPOPT/CPLEX as its defaults for reproducing
the original experiment; the new wrapper explicitly selects BARON/HiGHS.

## Incomplete solves and certificates

The BARON profile stops a job if a subproblem has an unproven outcome, rather
than letting GDPopt exclude a discrete configuration based on a local optimum,
local infeasibility, solver failure or a time-limited solution. A returned
BARON incumbent is independently checked and saved before stopping when
available. Previously saved incumbents survive the watchdog's hard deadline.
GAMS may label a BARON NLP `locallyOptimal` even when its global bound has
closed to `optcr`; that case is accepted only after checking normal termination
and the raw incumbent/bound gap. The status label alone is insufficient.

The runner conservatively keeps GDPopt `global_optimality_certified=false`
and `global_bound_valid=false`, including for BARON. A global solver selection
or GDPopt `optimal` string alone does not replace a separate audit of bounds,
raw statuses, numerical consistency and original-model feasibility. Raw
bounds and every subproblem's GAMS statuses remain available for that audit.

## Local validation, October 1

The 47 comparison regression tests, Ruff checks and shell syntax check pass.
On macOS with **GAMS 53.3** and Pyomo 6.10.0, actual BARON NLP and HiGHS MIP
smoke solves pass. Short 60-second-per-job integration runs finish with
independently feasible incumbents for both CSTR5 and Small Batch:

| Model | RIC + BARON/HiGHS | GLOA + BARON/HiGHS |
|---|---:|---:|
| CSTR5 | 3.061983957 | 3.130198133 |
| Small Batch | 167427.657004 | 167427.657004 |

These are local wiring checks, not Dantzig benchmark results. In particular,
CSTR5 GLOA still returns a worse solution than RIC despite an `optimal` label;
changing the subsolvers has not resolved every GDPopt bound/termination issue.
Do not treat that label as a global certificate. The returned October 1
Dantzig snapshot passed its GAMS 52.2 preflight and contains 12 completed
CSTR jobs; six final records are still pending. See the current audit above.

Sources: [GAMS 52 HiGHS](https://www.gams.com/52/docs/S_HIGHS.html),
[GAMS 52 BARON](https://www.gams.com/52/docs/S_BARON.html),
[GDPopt](https://pyomo.readthedocs.io/en/stable/explanation/solvers/gdpopt.html).
