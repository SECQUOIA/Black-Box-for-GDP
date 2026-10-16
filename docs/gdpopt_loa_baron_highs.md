# Dantzig LOA-only run on CPU 6: BARON + HiGHS

All nine Dantzig LOA jobs have completed. The final archive, checksums and
saved-vector validation are published with the [LOA results](../results/gdp_comparison_loa_20261001/README.md).
The [current comparison](../results/gdp_comparison_current/analysis/README.md)
includes all 27 new GDPopt jobs and the 18 September 25 Big-M/Hull baselines.

This bundle runs **LOA only, nine jobs**: CSTR5/10/15/20/25/30, Column 17,
nine-stage Dynamic and Small Batch. NLP subproblems use GAMS BARON; the
MILP master and initialization use GAMS HiGHS. BARON's internal LP/MIP
solver is CLP/CBC (`LPSol 8`) and its local NLP component is IPOPT (`NLPSol 9`).
The models, initialization, bounds, feasibility checks and subproblem budget
guard match the RIC/GLOA BARON/HiGHS runner.

Each job has one shared 1,800-second deadline, with one thread on CPU 6.
Nine jobs can use up to about 4.5 hours plus preparation and cleanup.
The wrapper verifies that CPUs 2 and 6 are allowed and are different physical
cores before running alongside the existing CPU 2 RIC/GLOA experiment.
It does not start or stop any RIC/GLOA job. `GDP_CPU` can override the default;
the separate 15-job follow-up wrapper explicitly retains CPU 2 for both phases.
LOA needs no MC++ relaxations; the existing `.venv-dantzig-gdp`, GAMS 52.2
and pinned `external` model checkouts are reused.

## Upload from the Mac

```bash
scp /Users/albertlee0125/Repos/RBFopt_Test/results/dantzig_review/gdpopt_loa_cpu6_runner.zip \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

## Run on Dantzig

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
LOA_RUNNER_DIR=$(mktemp -d "$PWD/gdpopt_loa_cpu6_runner_XXXXXX")
unzip -q gdpopt_loa_cpu6_runner.zip -d "$LOA_RUNNER_DIR"
cd "$LOA_RUNNER_DIR/gdp_comparison_runner"
sha256sum -c COMPARISON_RUNNER_SHA256SUMS
GDP_CPU=6 nohup bash run_gdpopt_loa_baron_highs_dantzig.sh run > console.log 2>&1 &
echo "PID=$! LOG=$PWD/console.log"
tail -f console.log
```

Ctrl+C stops viewing the log. `run` automatically solves the BARON NLP and
HiGHS MIP preflight tests before launching the nine jobs. An optional standalone
check is `bash run_gdpopt_loa_baron_highs_dantzig.sh check`.
Each job records solver call statuses, bounds, elapsed times, incumbent events,
the solution vector and an original-GDP feasibility check. The result archive
retains run configuration, source snapshots and file checksums.

The CPU affinity applies to the Python worker and its GAMS/solver subprocesses.
The run records the selected CPU and physical-core topology; affinity does not
reserve a whole server or eliminate shared-resource contention.

Results go to `results/gdpopt_loa_baron_highs_cpu6/`. Wait for `RESULT_ZIP` in the
log; a copied directory while a solver is running is only a partial snapshot.
Download completed archives and their checksums from a Mac terminal:

```bash
scp 'lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/gdpopt_loa_baron_highs_cpu6/*.zip' ~/Downloads/
scp 'lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/gdpopt_loa_baron_highs_cpu6/*.zip.sha256' ~/Downloads/
```

LOA's outer-approximation bounds on nonconvex models are not global
certificates, even with globally solved BARON NLP subproblems. The runner
therefore records `global_bound_valid=false` and
`global_optimality_certified=false`. See the
[Pyomo LOA documentation](https://pyomo.readthedocs.io/en/6.9.3/api/pyomo.contrib.gdpopt.loa.GDP_LOA_Solver.html).
