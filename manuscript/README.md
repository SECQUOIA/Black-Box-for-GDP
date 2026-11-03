# Current manuscript snapshot - November 3, 2026

The current [main source](main.tex), [supplementary source](supplementary.tex),
[bibliography](reference.bib), [combined PDF](main.pdf), and
[supplementary PDF](supplementary.pdf) include the seven-method comparison,
Lomustine simulation, catalytic distillation results, and the D-SDA
separable-neighborhood comparison.

The retained records and analysis commands are documented in:

- [Seven-method Grid and process results](../results/seven_method_comparison_20261031/README.md).
- [Lomustine simulation results](../results/lomustine_simulation_20261031/README.md).
- [Catalytic distillation live campaign](../results/catalytic_distillation_live_20261101/README.md).
- [Catalytic distillation MINLP comparison on Dantzig](../results/catalytic_distillation_minlp_dantzig_20261101/README.md)
  and [the Dantzig check outside the search box](../results/catalytic_distillation_outside_box_dantzig_20261103/README.md).
- [D-SDA separable-neighborhood comparison](../results/dsda_separable_20261101/README.md).

The manuscript cites publication snapshot `ea65c5339486b576008df68645ea68d22f7c7213`.
Public access remains to be verified; see [publication readiness](../docs/publication_readiness.md).
The [frozen reproduction companion](../reproduction/README.md) validates the
October 19 baseline and does not cover all later manuscript revisions.

The earlier snapshot notes below are historical. In particular,
`publication_manifest.json`, `manuscript_sources.zip`, and `joint_comparison.pdf`
describe earlier snapshots and do not verify or package the current manuscript.

# Historical snapshot - simulation-based case of October 31, 2026

This branch (PR #57) adds to the PR #56 manuscript a formulation for subproblems defined by a process simulator (Problem Sim) and the `Lomustine` benchmark, a pharmaceutical flowsheet simulated in PharmaPy (SECQUOIA/pd_ising PR 28).
The seven methods run on its 36 configurations with stored simulation-based optimizations ([case](../experiments/lomustine_simulation/README.md), [results](../results/lomustine_simulation_20261031/README.md)); the catalytic distillation column results are still pending.

# Historical snapshot - seven-method revision of October 31, 2026

NOMAD and MISO are now primary methods, from the audited [Dantzig return of PR #56](../results/pr56_dantzig_return_20261031/README.md).
The abstract, contributions, methods, process and Grid results, Discussion, Conclusions, and supplement report all seven DFO methods; NOMAD's 21 crashed Grid runs stay explicit, and the 70 exploratory paired tests have their own supplementary table.
Tables and figures are generated without solver calls by [seven_methods.py](../review_comparison/seven_methods.py), the [joint_process_*.py](../review_comparison/joint_process_main.py) scripts, and [revision_diagnostics.py](../review_comparison/revision_diagnostics.py) ([outputs](../results/seven_method_comparison_20261031/README.md)).
D-SDA never evaluates a configuration twice, as in the original D-SDA and LD-SDA; every D-SDA number, table, and figure comes from Albert's audited rerun (`results/dsda_no_revisit_20261031`), which matches the local rerun run for run.
The combined PDF compiles with zero errors, warnings, or undefined references; the main text ends on page 21.

# Historical snapshot - review revision of October 30, 2026

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

# Historical snapshot - joint process comparison

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

- The main/supplementary sources, PDFs, and bibliography linked above have since been updated.
- [Historical S9 review excerpt](joint_comparison.pdf) and [historical source distribution](manuscript_sources.zip).
- [Historical snapshot manifest](publication_manifest.json) and [historical verification](joint_revision_verification.json).
- [Preceding snapshot metadata](review_history/pre_joint_comparison/).
