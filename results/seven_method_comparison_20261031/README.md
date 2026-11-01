# Seven-method comparison for the manuscript

Presentation of existing records only; no optimizer or NLP solver is run.
RBFOpt, BAM, FMQA-SA, uniform sampling, NOMAD, MISO, and the BAM-prefix control come from the audited Dantzig return of PR #56 (`results/pr56_dantzig_return_20261031/analysis`, verified against its `REPRODUCTION.json`), and D-SDA from the rerun in which no configuration is evaluated twice (`results/dsda_no_revisit_20261031`, verified against its `FILE_SHA256.json`); the GDPopt and direct GDP runs come from `results/joint_process_scip_ipopt_20261030`.
NOMAD's 21 Grid B = 100 runs that crashed identically on every attempt are scored on the evaluations completed before the crash (16 reach the target), as in the return.

| Folder | Content | Command |
|---|---|---|
| `grid_and_tables` | Grid and process evaluation profiles, the Grid-hit and process-target tables, the process completion-cost table, and the Grid cost rows at B = 100 (NOMAD over its 189 timed runs) | `python -m review_comparison.seven_methods --output DIR` |
| `revision_diagnostics` | Seed spread and tolerance sensitivity, search time per evaluation, paired exact tests, and GDPopt enumeration counts | `python -m review_comparison.revision_diagnostics --output DIR` |
| `process_nlp` | NLP subproblems solved per run (`process_nlp_solves`) | `python -m review_comparison.joint_process_nlp --output DIR` |
| `process_completion` | Full-run completion times (`process_joint_completion`) | `python -m review_comparison.joint_process_main --output DIR` |
| `process_completion_supplement` | Completion times for the remaining eight process conditions (`joint_remaining_completion`) | `python -m review_comparison.joint_process_supplement --output DIR` |
