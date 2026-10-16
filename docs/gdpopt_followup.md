# Dantzig follow-up: remaining RIC/GLOA and nine LOA jobs

**Historical preparation only; do not use this to reproduce the current dataset.**
The original RIC/GLOA process survived the SSH disconnect and completed all
18 jobs. LOA was run separately on CPU 6. The two final archives are now
verified in the [current comparison](../results/gdp_comparison_current/analysis/README.md).
The six-job restart described below was not needed.

The imported October 1 archive is a partial snapshot: 12 CSTR RIC/GLOA jobs
are complete, Column RIC is `running`, and the remaining final records are absent.
It does not establish whether the server process subsequently stopped or finished.

This bundle executes **15 jobs sequentially on CPU 2, one thread**:

1. Column, nine-stage Dynamic and Small Batch with RIC and GLOA: **6 jobs**.
2. CSTR5/10/15/20/25/30, Column, Dynamic and Small Batch with LOA: **9 jobs**.

All use BARON NLP subproblems and HiGHS MIP masters, with BARON CLP/CBC
(`LPSol 8`) and IPOPT (`NLPSol 9`) internally. Each job has one shared
1,800-second deadline, so the combined limit is 7.5 hours plus preparation
and cleanup. Phase 1 restarts the six missing jobs from their standard initial
models; it does not continue the incomplete Column subproblem. It does not
rerun the completed CSTR RIC/GLOA jobs.

## Upload from the Mac

```bash
scp /Users/albertlee0125/Repos/RBFopt_Test/results/dantzig_review/gdpopt_followup_runner.zip \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

## Run on Dantzig

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
GDP_FOLLOWUP_DIR=$(mktemp -d "$PWD/gdpopt_followup_runner_XXXXXX")
unzip -q gdpopt_followup_runner.zip -d "$GDP_FOLLOWUP_DIR"
cd "$GDP_FOLLOWUP_DIR/gdp_comparison_runner"
sha256sum -c COMPARISON_RUNNER_SHA256SUMS
nohup bash run_gdpopt_followup_dantzig.sh run > console.log 2>&1 &
echo "PID=$! LOG=$PWD/console.log"
tail -f console.log
```

Ctrl+C exits `tail`, leaving the run active. The wrapper checks for another
GDP runner owned by this user on CPU 2 or its physical-core sibling and stops
before starting if one exists. It never kills an existing process. If that
happens, wait for the original run and inspect its final archive before rerunning
the same jobs. The check is not an exclusive server reservation.

The existing `.venv-dantzig-gdp`, GAMS 52.2, MC++ and pinned `external`
source checkouts are reused. Both phases perform their solver/model preflight.
Phase 1 needs MC++ for GLOA; LOA itself does not. Each phase creates its own
unique result directory and SHA256-checked ZIP under `results/gdpopt_followup/`.
After both phases complete, the log prints `FOLLOWUP_FINISHED` and contains
two `RESULT_ZIP` paths. Solver errors that make phase 1 exit nonzero stop the
wrapper before phase 2; completed results remain packaged.

## Download completed results from the Mac

```bash
scp 'lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/gdpopt_followup/*.zip' ~/Downloads/
scp 'lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/gdpopt_followup/*.zip.sha256' ~/Downloads/
```

Use [the LOA-only wrapper](gdpopt_loa_baron_highs.md) if the original six
RIC/GLOA jobs have already finished. Both wrappers are included in this bundle.
GDPopt certificates remain conservative: an `optimal` status does not prove
global optimality of these nonconvex GDPs. In particular, LOA's outer
approximations need not give globally valid bounds even with BARON NLPs.

Local validation uses macOS/GAMS 53.3 and does not replace the Dantzig 52.2
preflight. LOA CSTR5 and Small Batch wiring tests returned independently
feasible objectives 3.061983957 and 167427.657004, respectively.
