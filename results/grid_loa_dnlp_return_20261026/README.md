# Selective SCIP/DNLP LOA follow-up: returned Dantzig results

All six fixed configurations return SCIP solutions that pass independent checks against the unchanged original GDP and the existing 1e-5 target criterion.
All three full LOA runs also return feasible target solutions, changing the paired target count from 0/3 to 3/3.
There are three new-only target hits and no both-hit, old-only-hit or both-miss pair.
This is evidence of recovered target configurations, not improved termination time or a global optimality certificate.
This follow-up combines subproblem_presolve=False and nlp_solver_args.mtype=dnlp with solver=scip.
The preceding single-option experiment failed at GAMS NLP compilation and remains preserved separately.
The effect cannot be attributed to the presolve flag alone independently of the export-type change.

| Problem | Prior objective | New objective | First target seconds | Prior worker seconds | New worker seconds | New maximum original violation | New wrapper / termination |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| holder_table | 0.145167239953 | -1.95871041868e-16 | 168.270 | 1623.761 | 1800.029 | 1.78e-15 | hard_time_limit / maxTimeLimit |
| michalewicz | 0.0864917048203 | 0 | 1478.579 | 1490.761 | 1790.399 | 4.44e-16 | finished / maxTimeLimit |
| shubert | 0.0824278107512 | 0 | 986.809 | 1278.446 | 1793.257 | 0 | finished / maxTimeLimit |

The prior three runs all reported optimal but missed the known feasible reference objective of zero.
Their lower bounds exceeded that reference and remain recorded as inconsistent bounds for the original GDP.
The new three runs all reach their time limits; finished for Michalewicz and Shubert means normal worker completion with GDPopt maxTimeLimit, not optimal termination.
Holder table is stopped by the parent watchdog, so its maxTimeLimit is a parent classification and no final GDPopt bound pair was returned.
Its last discrete lower bound is kept separately and is not substituted into a missing final bound field.
The new total worker time is 5383.685 seconds (89.728 minutes), versus 4392.968 seconds previously.
This is an increase of 990.717 seconds (22.55%), with different successful versus unsuccessful outcomes.
First-target times are measured from the method start using feasible-subproblem events, not from the final incumbent timestamp or the end of the worker.
Holder table first reaches the tolerance at [3,29] before replacing it with a numerically smaller value at [3,1].
Worker timing includes slightly more setup than the event clock, so time-after-target differences are descriptive rather than a separate solver timing measurement.

The default-presolve probes reject all six original-feasible reference configurations without solver calls.
With the recorded bypass, all six reference configurations are selected once, enter subproblem evaluation once and return target solutions once in the full runs.
All six fixed SCIP calls and all three full jobs are recorded in the launch ledger in the intended order.
The returned initial templates match fresh original constructor values and model structure, including objectives, constraints, bounds and logic.
No fixed diagnostic solution is used to warm-start a full run.
The original midpoint values are [0,0], [pi/2,pi/2] and [5,5] for holder_table, michalewicz and shubert respectively.

| Problem | Completed SCIP MIP | Completed SCIP DNLP | Failed interface attempts | Interrupted interface attempts | Confirmed SCIP starts | Last discrete lower bound |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| holder_table | 868 | 867 | 0 | 1 | 1735 | -0.828637340494 |
| michalewicz | 821 | 820 | 0 | 0 | 1641 | -0.110450831302 |
| shubert | 749 | 749 | 1 | 0 | 1498 | -0.0442217473692 |

The full runs start 4876 solver-interface attempts, with 4874 confirmed SCIP invocations.
The difference consists of one Shubert network-session start failure and one Holder table interface attempt interrupted before a SCIP banner was recorded.
The interrupted Holder table attempt is not counted as a confirmed SCIP solve, and its unrecorded duration is not fabricated.
Shubert retries the failed interface call once under the preserved network policy after a five-second backoff within the original shared deadline.
That recovery is not a second full LOA job or a replacement of a failed benchmark run.
Adding the six fixed solves gives 4880 confirmed SCIP invocations in this new experiment.
The six GAMS action=c checks use no optimization solver and take 2.045 seconds in total.
The six fixed workers take 4.272 seconds in total.

Every completed SCIP call logs that GAMS received no marginals, and each problem's discrete lower bound remains unchanged throughout the recorded run.
The exported MIP equation count increases by one per iteration, consistent with exclusion cuts rather than stronger objective bounds.
Pyomo 6.10.0 LOA skips an OA linearization when its subproblem constraint has no dual value, which is a plausible explanation for this observed lack of bound progress.
This is a source-and-log inference; the archive does not directly snapshot the internal dual suffix or OA-cut collection.
It is not a controlled test of an alternative solver or cut policy, and no such change is made here.
This was inspected in the installed Pyomo 6.10.0 source and agrees with the [official LOA source documentation](https://pyomo.readthedocs.io/en/stable/_modules/pyomo/contrib/gdpopt/loa.html), whose current page identifies version 6.10.1.
The option also bypasses fixed-variable and trivial-constraint preprocessing, so solver routing and cost differ from the default run.

The original run.json incorrectly reports actual_full_loa_runs=0 and actual_option_verified=false for each full job.
The custom capture handler was removed while GDPopt configured tee logging, leaving the expected sidecar files absent.
The behavior is reproduced in a solver-free test of the installed Pyomo 6.10.0 logging context and is also visible in the [official logging utility source](https://pyomo.readthedocs.io/en/stable/_modules/pyomo/contrib/gdpopt/util.html).
The counter incorrectly used those missing files as evidence that no solve entered.
The actual effective configurations remain in all three run.log files and show subproblem_presolve=false, mip_presolve=true and SCIP/DNLP subproblems.
The launch ledger, LOA headers, call journals, SCIP banners, trajectory events and returned variables independently establish three actual full runs.
The audit corrects the derived count and option verification without editing any returned file or historical manifest.
The original erroneous summary and report are retained under returned_evidence, while the complete original logs remain in the immutable return ZIP.
No rerun or new package is required to recover this information.

The server matches the recorded Python 3.11.16, Pyomo 6.10.0, GAMS 52.2.0 executable hash and SCIP 9.2.4 (a94f778ac8).
CPU affinity is [14] and all recorded thread settings are one, as in the prior LOA experiment.
Affinity is not an exclusive reservation, so these single-run wall times should not be treated as replicated speed estimates.
The recorded Pyomo module hashes stay unchanged during execution.
The original 1800-second job limit, set-covering initialization, bound tolerance and network recovery policy remain in place.
The actual GDPopt time_limit is 1789 seconds because the original wrapper reserves time within the shared 1800-second worker budget.
The stable effective configuration fields differ from the original logged configuration only in subproblem_presolve and nlp_solver_args.mtype.

This selected three-problem diagnostic does not replace the original 21-grid experiment or recompute its ranking.
RIC, GLOA, direct MINLP, process GDPs and DFO experiments are not rerun.
Manuscript, Overleaf, representative figures and historical performance tables remain unchanged.
Adopting this result as a paper's representative experiment remains a separate review decision.
The archive, source package, input hashes, effective options, original-model checks, reference paths and output hashes are recorded in manifest.json and the accompanying JSON files.
The result archive is ../archives/grid_loa_dnlp_20261025_result.zip.
The analysis invokes no optimization solver and can be reproduced with the following command in a fresh output directory.

```bash
python scripts/analyze_grid_loa_dnlp_return.py --output /tmp/grid_loa_dnlp_audit_fresh
```
