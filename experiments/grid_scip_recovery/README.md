# Grid SCIP error-only recovery, 2026-10-25

These three packages rerun exactly the 46 error jobs in the returned October 25 split experiments.
The selection is RIC 12, LOA 19 and GLOA 15 jobs, with CPUs 12, 14 and 16 respectively.
The five time-limited jobs and all twelve jobs reporting optimal termination are excluded.
The original 63-job combined experiment on CPU 6 is independent and must remain running.
The launcher checks distinct allowed physical cores against CPUs 6, 8, 10, 12, 14 and 16, but does not reserve cores against other users.
Each method has a separate output root and launcher lock.

The analytic model, original constraints, variable bounds, CSV references, objective normalization and solver interface source are byte-identical to the original split packages.
The worker retains GAMS 52.2, Pyomo 6.10.0, SCIP MIP/NLP routing, one thread, relative gap 1e-5, disabled SCIP warm starts and a shared 1,800-second job deadline.
The existing pyomo610-grid-v1 corrections remain unchanged.
The added policy grid-scip-network-and-bohachevsky2-v1 is explicit in the package, run and worker records.

For bohachevsky2, a worker-local correction restores the exact interval of a fixed exponent before Pyomo propagates power bounds.
This extends the already diagnosed fixed-exponent correction to this grid without changing its mathematical formulation.
Validation reproduces the original failure at index [1, 11] and checks all 961 fixed grid configurations without calling a solver.
Variable fractional-exponent domain errors still propagate.
The dispatch function is restored after the worker exits, including exceptional exits.

For a logged GAMS network-session start or close failure containing the observed empty-response Curl message, the same interface call may be retried twice after delays of 5 and 15 seconds.
Every attempt stays in solver_calls.jsonl, and network_recovery.jsonl records its group, log-byte evidence, decision and original deadline.
The model values, bounds and fixed flags must remain unchanged after the failed call, or retry is refused.
No unrelated solver error is retried.
Retries and delays consume the original worker budget, and insufficient remaining budget prevents another retry.
No job is automatically restarted, no successful result is selected from multiple complete attempts, and the supplied wrapper deliberately omits resume.
Preflight remains unchanged and must pass before benchmarks start.
These measures cannot guarantee that the Dantzig network or license service is healthy.

Each package binds its selected jobs to the original archive and result-record SHA-256 hashes in RECOVERY_SELECTION.json.
RECOVERY_PROVENANCE.json identifies every preserved and changed source file.
The inherited SPLIT_PROVENANCE.json describes the historical input package, while RECOVERY_PROVENANCE.json describes this package.
The controller additionally retains leftover GAMS scratch files after a watchdog stop, so terminal seals can be audited completely.
The original run omitted two such sealed temporary files from holder_table/GLOA; that original archive remains unchanged.

Run `bash run_method.sh plan` to inspect the frozen method and error selection without solving.
Run `bash run_method.sh run` on Dantzig to perform the existing environment and solver preflight followed by the selected jobs.
The launcher prints CPU_SEPARATION, METHOD, RUN_DIR, PREFLIGHT, START, DONE and RESULT_ZIP records.
Inspect the launcher run.log, each benchmark's run.log and network_recovery.jsonl for progress and recovery evidence.
The run writes raw logs, trajectories, full solution vectors, source hashes and timing to its own results/grid_gdpopt_scip_recovery_METHOD directory.
The result_zip.txt pointer in that directory is created after packaging finishes.

The first-attempt report remains the record of all original 63 jobs, including failures.
Recovery results must be reported as a separate intervention with pairing by grid and method, not silently substituted into first-attempt success rates.
The Shubert/GLOA optimal-termination mismatch is documented separately and is not included in this user-selected error-only rerun.
No remote solver run was performed while building or validating these packages.
