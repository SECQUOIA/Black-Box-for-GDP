# Grid D-SDA common-success target stopping

This follows the second absolute-improvement 1e-5 D-SDA experiment and changes only the Grid target stopping predicate and its observed incumbent.
The checkpoint remains after a completed descent and after the pre-existing budget-stop check, before the next ranked start.
The target is retained from each baseline job and the predicate is the unchanged adopted_analysis.hit function.
Movement acceptance remains old_value - new_value > 1e-5, and ties and internal numerical settings retain tol=1e-12.
No immediate callback-level stopping is added and the first target callback can precede the termination callback.
The cohort has 1050 Grid jobs, 1050 verified completions, 0 failed verifications, and 0 missing runs.
Target hits change from 374 to 374, and callbacks change from 38516 to 37253 among the reported records.
Incomplete rows retain the full cohort denominator and are listed in verification.json.
Only saved Grid responses are evaluated and no NLP, GAMS, SCIP, Process job, or other optimization method is run.
CPU selection observes an idle SMT pair and affinity pins one logical CPU, without exclusive reservation.
Wall times are retained without a speedup claim and historical configuration-cost estimates are not reused.
Process records and existing representative manuscript tables and figures are preserved, and these results are not automatically adopted into the manuscript or Overleaf.
The reproduction directory contains sealed inputs and source, and execution_manifest.json records environment and execution sessions.
Run python reproduction/verify.py --results . from this result directory to verify stored data without a search or solver.
