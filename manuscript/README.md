# Current manuscript snapshot - review revision of October 30, 2026

This snapshot starts from the Overleaf export of October 30, 2026 and applies David's review comments and the revised story.
`main.tex`, `supplementary.tex`, `reference.bib`, and the figures here supersede the copies in Overleaf and should be uploaded there.
The combined PDF compiles with zero errors and zero undefined references; the main text ends on page 19.
`joint_comparison.pdf` and `manuscript_sources.zip` below are earlier excerpts and were not regenerated.

- The story is framed around NLP subproblems solved: new main Figure 3 ([generator](../review_comparison/joint_process_nlp.py), [outputs](../results/joint_process_nlp_20261030/README.md)) compares DFO runs, GDPopt, and full enumeration.
- Full enumeration is a reference baseline, with costs in the supplementary completion-cost table and NLP counts in Figure 3.
- Claims rest on exact paired McNemar tests (supplementary paired-test table); Column and Small Batch differences are described as comparable.
- Grid-GDP is a short controlled-behavior section after the process results; its cost table and the first-hit process profiles moved to the supplement.
- Seed spread, tolerance sensitivity, search overhead, GDPopt enumeration counts, and paired tests come from [revision_diagnostics.py](../review_comparison/revision_diagnostics.py) ([outputs](../results/revision_diagnostics_20261030/)).
- Figures use the Okabe-Ito palette ([outputs](../results/colorblind_figures_20261030/README.md)); time-limited conventional runs are shown as 1800+.
- The process D-SDA restart check ([experiment](../experiments/dsda_process_multistart/README.md)) and the NOMAD/MISO comparison ([experiment](../experiments/mixed_integer_dfo/README.md)) have Dantzig launchers for Albert.
- Teal `\claude{}` notes mark text that awaits the Dantzig returns.

# Previous snapshot - joint process comparison

The [updated S9 figures and workload table](../results/joint_process_scip_ipopt_20261030/README.md) now use the SCIP-master/IPOPT-subproblem GDPopt campaign.
Those two figure PDFs and their captions were applied in place to live Overleaf on October 30, 2026.
The source/PDF bundle below remains the earlier snapshot; the current S9 assets and reproduction instructions are in the linked analysis directory.

Overleaf remains the source of truth for the manuscript and review history.
This snapshot contains Supplementary Section S9, Table S8, and Figures S1 and S2 for an exploratory joint DFO and algebraic comparison.
The new section occupies pages 32--34 of the 34-page combined PDF.
References start on page 19 and the supplement starts on page 23.
The supplementary PDF extracts pages 23--34; the joint-comparison PDF extracts pages 32--34.
Links outside an extracted PDF may not resolve.

The live main source was not changed during this task.
The export captures the previously completed Overleaf story revisions since the earlier repository snapshot.
Existing supplement text, comments, and tracked edits were preserved through in-place editing.
Only the two new figure PDFs were uploaded; no TeX document was uploaded to replace an Overleaf file.
The final combined compile reports zero errors and zero warnings.

The [joint comparison](../results/joint_process_comparison_20261029/README.md) contains 700 primary DFO runs and 45 algebraic executions.
It retains all fourteen DFO conditions, the different sample sizes, original target rules, reconstructed versus measured timing, and bound-conflict flags.
The [validation note](../docs/joint_process_comparison_20261029.md) documents callback accounting and reproducibility.
No searches, NLP evaluations, or server experiments were run.

The earlier [Grid presentation update](../results/grid_presentation_20261029/README.md) remains part of this branch.
The underlying [DFO publication analysis](../results/dsda_publication_20261028/README.md) and [SCIP analysis](../results/process_scip_four_analysis_20261026/README.md) are unchanged.
The old Grid and D-SDA verification files describe those earlier steps and are retained as historical records.

- [Combined review PDF](main.pdf), [supplementary PDF](supplementary.pdf), and [S9 review excerpt](joint_comparison.pdf).
- [Main source](main.tex), [supplementary source](supplementary.tex), [bibliography](reference.bib), and [source distribution](manuscript_sources.zip).
- [Snapshot manifest](publication_manifest.json) and [new verification](joint_revision_verification.json).
- [Preceding snapshot metadata](review_history/pre_joint_comparison/).
