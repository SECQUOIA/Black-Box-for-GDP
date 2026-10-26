# Four separate Process SCIP packages

The minlp package runs Big-M and Hull on nine Process instances, for eighteen jobs.
The ric, loa and gloa packages each run their single GDPopt method on the same nine instances.
The order is CSTR5, CSTR10, CSTR15, CSTR20, CSTR25, CSTR30, Column, Small Batch and Dynamic.
The MINLP reformulations use SCIP directly, while each GDPopt method uses SCIP for both its MIP master and NLP subproblem.
The GDPopt NLP export is the original Process mtype=nlp, not the separate Grid DNLP diagnostic.
The original subproblem_presolve=True and mip_presolve=True settings remain unchanged.
Every benchmark job retains the original 1800-second worker limit, single-thread policy, relative gap 1e-5, zero absolute gap and disabled warm starts.
Each package has its own directory and immutable execution claim, with no automatic whole-job rerun or resume.
Only explicitly logged network-session transport errors can retry inside the same job deadline, with at most three interface attempts and five/fifteen-second backoffs.
This reuses the previously exercised Grid transport function without installing any Grid, FBBT or GLOA correction.

All original model, initialization, comparison and solver-adapter files are taken byte-for-byte from the returned October 25 Process archive.
The new controller changes the GDPopt MIP solver from HiGHS to SCIP and selects SCIP for direct MINLP jobs.
CSTR30 retains the original constructor initialization in this source cohort, keeping the separate CSTR30 initialization experiment distinct.
Column retains its original GDP formulation; the later DFO logical-domain/budget experiment is not applied to the full GDP model.
Each method starts from an unsolved clone and never receives another method's solution as an initial value.
Original targets are copied from the prior Process SCIP audit and never inferred from newly observed minima.
Acceptance uses the existing 1e-5 original-GDP tolerance and the existing absolute reference-target rule.

The four packages select CPUs 18, 20, 22 and 24 respectively.
The launcher verifies that these are four distinct physical cores, including SMT topology, and pins every solver descendant to its package CPU.
A per-user physical-core lock prevents these packages from sharing a selected core.
No occupancy check rejects a launch merely because a system daemon can execute on the core.
Affinity does not reserve the entire server or exclude other users' computations.
No existing remote job is stopped or overwritten.

The launcher checks the existing Dantzig environment against the prior Python 3.11.16, Pyomo 6.10.0 and GAMS 52.2.0 records.
The GLOA package additionally verifies the original MC++ library hash.
No dependency is automatically installed or upgraded.
Before benchmark execution, the MINLP package performs one tiny SCIP MINLP smoke solve and compiles all eighteen actual reformulations with GAMS action=c.
Each GDPopt package performs one tiny SCIP MIP and one tiny SCIP NLP smoke solve and verifies the SCIP 9.2.4 banner.
Preflight calls and compilation time are recorded separately from benchmark calls and timing.
A preflight failure stops that package and preserves its diagnostic result archive.
Local compilation validation, when supplied, uses GAMS 53.3 and is not claimed to reproduce the server environment or to solve the benchmarks.

Actual GDPopt configuration is captured with a logger filter that survives Pyomo tee handler replacement.
The call journal, raw log, returned variables, independent original-GDP validation and selected Boolean/binary trajectories are saved for each job.
Every completed job retains both worker_result.json and the independently annotated result.json.
Interrupted GAMS output is included instead of omitting all gams-* directories, avoiding the earlier Column return's missing-file problem.
The launch log prints progress and a heartbeat every minute while a job is running.

The known CSTR GLOA inconsistent-bound issue is not fixed by this packaging change.
Reported optimal strings and global bounds remain separate from independently validated feasible returns and target attainment.
The controller records a lower bound exceeding a known feasible reference and leaves global certification false pending review.
Column and Dynamic may still consume their full time limits before GDPopt can continue to another configuration.
These outcomes remain in the returned archive and are never replaced by successful retries of whole jobs.

Run bash run.sh plan to inspect the exact job list without invoking a solver.
Run bash run.sh run once on Dantzig to execute that package.
The result is written to results/process_scip_METHOD_20261026/process_scip_METHOD_20261026_result.zip, where METHOD is minlp, ric, loa or gloa.
Use the accompanying COMMANDS.md for separate upload, launch, monitoring and download commands.
