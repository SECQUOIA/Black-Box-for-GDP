# Supplement panels without main-text duplication

This presentation-only reduction retains the eight process conditions absent from main Figure 3.
The remaining panels are CSTR10 B=15, CSTR15 B=22, CSTR20 B=29, CSTR25 B=36, and Dynamic B=15, B=20, B=37, and B=50.
Together with `results/joint_process_main_20261030`, these panels cover all fourteen conditions exactly once.
No optimizer, NLP solver, or benchmark is rerun.

Every DFO condition retains all ten seeds, including misses, with inclusive quartiles and medians computed over all ten runs.
All underlying values, target rules, statuses, and source references are unchanged.
The 600 plotted marks comprise 560 distinct DFO runs and 25 distinct conventional GDP runs.
NOMAD and MISO come from the audited Dantzig return of PR #56 (`results/pr56_dantzig_return_20261031`), and D-SDA from the rerun without re-evaluated configurations (`results/dsda_no_revisit_20261031`).
The same five conventional Dynamic observations are repeated for context across four budgets, not counted as additional executions.
The figure retains individual outcomes, bound flags, measured-time TL labels, and the different recorded time bases.
The previous full fourteen-condition figures and old DFO-only profile remain archived in their original result directories, but are no longer repeated in the Overleaf supplement.

The Overleaf supplement keeps the detailed conventional objective/time table and the NLP-workload table.
The old DFO-only time profile, its main-text reference, and the unused cumulative completion-time definition are removed.
The configuration-evaluation profile and reconstructed completion-cost equation remain in the main paper.
David comments, tracked changes, and underlying experiment records are preserved.

Reproduce from the repository root into a fresh directory:

```sh
python -m review_comparison.joint_process_supplement --output /tmp/joint-process-supplement
```
