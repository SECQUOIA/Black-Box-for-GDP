# Professor review disposition — manuscript revision

## Current publication update - Column logical domain, 25 October 2026

The [Column publication analysis](../results/column_publication_20261025/README.md) adopts all 50 completed logical-domain/B13 runs and preserves the other 650 primary Process runs.
Column now uses 64 logically admissible configurations and budget 13, with ten paired seeds for each method.
Target counts are D-SDA 5/10, RBFOpt 4/10, BAM 1/10, FMQA-SA 4/10 and uniform sampling 1/10.
Median reconstructed completion costs are 35.43 s for D-SDA and 54.60 s for RBFOpt.
The current 700-run comparison has 315 target hits, 385 misses, no execution failures, 16,067 callbacks and 2,024 distinct visited configuration keys.
The inventory contains 2,438 configurations and 1,266 accepted responses.
The existing CSTR conclusion remains 45/60 for RBFOpt versus 14/60 for D-SDA.
The [current manuscript](../manuscript/README.md), four Process figures and affected tables and prose are synchronized with Overleaf.
David's 34 comment lines are preserved, and manuscript source files were not re-uploaded to Overleaf.
The new analysis runs no optimizer or NLP solver and requests no CI run.
PR #49 was already merged; this is a follow-up on its original review/cstr15-dantzig-results branch.
The following sections describe earlier snapshots and retain their original numerical totals and review history.

## Previous publication update - CSTR30 initialization, 25 October 2026

The [CSTR30 publication analysis](../results/cstr30_publication_20261025/README.md) adopts the completed initialization follow-up for all five methods while preserving the finite-penalty baseline and all other primary cases.
The current manuscript uses mass-balance/zero-recycle initialization for CSTR5–30, with 464 accepted CSTR30 configurations and an unchanged reference target.
CSTR target counts are 45/60 for RBFOpt and 14/60 for D-SDA.
The current 700-run Process comparison contains 314 target hits, 385 misses and one retained execution failure, with 16,206 callbacks visiting 2,040 distinct keys.
Four affected Process figures and the related active manuscript tables and prose are updated.
The [publication manifest](../results/cstr30_publication_20261025/manifest.json) identifies the retained execution sources separately from this analysis.
CSTR30 completion estimates use the new same-attempt point costs, including initialization and artifact recording.
The historical FMQA weight diagnostics remain limited to their reconstructed models.
No new experiment or CI run was initiated during this publication update.
PR #49 remains merged, and this work is a subsequent commit on review/cstr15-dantzig-results.
The dated sections below preserve earlier review history; their numerical totals describe the earlier cohorts.

The two major experimental comparisons have been incorporated in the [manuscript and supplementary material](../manuscript/README.md).
The primary comparison uses RBFOpt and sampling controls, while the solver variant is retained in Supplementary Section S10.
The 3,430 additional runs and the 4,760 historical runs are preserved unchanged.
The current manuscript synchronizes the latest Overleaf sources and PDFs using completed records, with no new optimizer, NLP, fitting or annealing execution.
The execution provider remains `38d917ef75ef6767c2a9f238d88be19bf0b89160`; the input analysis snapshot is `6e083eb49b497ce4fea90131e18cc0459db682e8`.
See the [original results and limitations](../results/review_comparison_20261020/README.md) and [publication analysis provenance](../manuscript/analysis_manifest_current.json).

| Review item | Status | Evidence / remaining action |
|---|---|---|
| Major: matched MSRSM genetic comparison | incorporated | Primary tables and figures use RBFOpt; S10 retains solver results, paired comparisons, other auxiliary solver calls, and timing-environment limitations |
| Major: uniform and BAM-prefix controls | incorporated | Uniform in both suites; Grid prefix control; first-hit and completion profiles; B10 equality and higher-budget differences discussed |
| Minor 1: timing endpoint and terminal solutions | incorporated | Main timing definition and figure captions exclude final extraction/export; historical terminal audit preserved with solver labels; additional terminal observations linked in S10 |
| Minor 2: alpha cost scenarios | incorporated | S10 scenarios rescale point costs on retained paths; all existing scenario results remain unchanged |
| Minor 3: paired design and uncertainty | incorporated | S10 grouped Grid bootstrap and condition-specific Process analysis; empirical TTS qualification and four-restart illustration |
| FMQA-SA versus uniform paired comparison | incorporated | [1,190 pairs and 19 summaries](../results/review_comparison_20261020/fmqa_uniform/README.md); publication analysis independently agrees |
| Minor 4: suite exclusions | incorporated | S10 excludes Yang3 and Bohachevsky2; lattice effect discussed; no shifted-grid rerun |
| Minor 5: FMQA implementation and energy diagnostic | limited diagnostic incorporated | [Seven reconstructed fits and 3,328 binary strings](../results/review_diagnostics_20261020/README.md) summarized in S10; historical fitted weights remain unavailable; no prevalence or causal claim |
| Minor 6: numerical feasibility and tightened check | CSTR15 check completed and synchronized in main text and S9 | [One-call identity-preprocessed follow-up](../results/review_feasibility_tautology_20261020/README.md), retained in `854a1a7fc5a20a5489d82ef7991a16aaf89025f3`, passed the original-GDP 1e-8 residual test; the recorded A12 lower-bound discrepancy persists; all three earlier failed calls preserved; numerical evidence for this case only |
| Additional CSTR15 check in the Dantzig GAMS environment | completed; manuscript update pending | [Returned result and local comparison](../results/review_cstr15_dantzig_20261021/README.md); one GAMS/IPOPT call passed the original-GDP 1e-8 test; GLOA discrepancy persists and Hull is within tolerance; raw archive and execution revision preserved |
| Minor 7: starred execution profile | incorporated; optional display deferred | Table 5 notes explain replacement of previously failing cases, preserved expressions/settings and corrected preparation; unsuccessful times remain archived |
| Minor 8: figure annotations / variant labels | incorporated | Seven figures regenerated; BAM prefix shaded; RBFOpt and controls labeled; Figure 6 uses mean cost shares |
| Minor 9: 63-object partition | preserved | S9 retains 45 selected plus 18 earlier records; nine witnesses form a subset |
| Minor 10: availability wording | incorporated | Private status and planned post-submission release stated; administrator action still required |
| Minor 11: GDP/process bibliography | preserved | No substantive correction requested; publication years unchanged |
| Minor 12: Nannicini configuration context | incorporated | S10 explains the MSRSM candidate-search comparison and cited implementation context |
| Minor 13: statistical references / TTS meaning | incorporated | Clopper–Pearson issue 4 retained; TTS remains an empirical estimate, not a guarantee |
| Minor 14: metadata / pinned documentation | incorporated with source distinction | Pyomo 6.10.0 documentation and bam-solver 5.0.0 interface documentation are version-pinned; the latter is not claimed to be an archived full engine manual |
| Minor 15: commit-content provenance | partial | Repository URLs updated; historical provider revisions preserved; logged-out public commit-content verification awaits release |
| Typos and terminology | incorporated where verified | ALAMO/NLP/CSTR wording and S6/S9 wording corrected; historical branch capitalization retained from archived source |

The limited FMQA diagnostic was added separately at commit `15663134704b7bb1d4804c94c70edabaffbf8ecd` and has now been summarized without rerunning it.
Historical fitted weights remain unavailable.
The [earlier CSTR15 follow-up](../results/review_feasibility_followup_20261020/README.md) stopped after its no-solution degrees-of-freedom error and remains preserved unchanged.
A separate authorized check proved three fixed-Boolean equalities to be exact identities and omitted only those rows from the computational clone, retaining 156 free variables and reducing equalities from 158 to 155.
Its single new local NLP call returned a point numerically feasible under the original-GDP 1e-8 residual test, including the omitted conditions, with the A12 discrepancy still present.
The [saved summary](../results/review_feasibility_tautology_20261020/summary.json) records objective `2.8293940632857546`, maximum unscaled violation `3.3306690738754696e-16`, and an A12 bound-minus-objective difference of `0.6931579445174396`.
This is numerical evidence for the retained point, not a proof of exact mathematical feasibility, global optimality or a solver defect.
The option-error report in `results/review_diagnostics_20261020/` and the `TOO_FEW_DOF` report in `results/review_feasibility_followup_20261020/` describe earlier unsuccessful allocations and remain unchanged.
The original execution provider and comparison input snapshot above are distinct from the CSTR15 completion commit and remain unchanged.
The earlier status-only correction excluded manuscript files.
The subsequent author-authorized revision now synchronizes the Overleaf manuscript, bibliography, PDFs and figures, including the successful CSTR15 result.
Original result archives, manifests and execution-provider revisions remain unchanged.
The repository visibility has not been changed, and no Slack message has been sent.

## Nannicini source check

Nannicini (2021), *On the implementation of a global optimization method for mixed-variable problems*, appears in Open Journal of Mathematical Optimization 2, article 1, 25 pages ([publisher](https://ojmo.centre-mersenne.org/articles/10.5802/ojmo.3/)).
Sections 4.2.3 and 5.2 of the [publisher PDF](https://ojmo.centre-mersenne.org/item/10.5802/ojmo.3.pdf) describe genetic, sampling and mathematical-solver candidate search and explain omission of MSRSM with mathematical solvers from the principal plots.
Those experiments use more intensive genetic settings than the defaults, and other surrogate-minimization operations retain Ipopt/Bonmin regardless of candidate-search strategy.
These observations motivate the present matched comparison without establishing its outcome or invalidating the preserved solver-option records.
The new performance runs keep the recorded default GA parameters.

## Latest minor review and naming revision

The primary method name is RBFOpt in all current prose, table headings and plot labels.
Its default candidate-search option is stated once in the main methodology; implementation identifiers in historical records remain unchanged.
The main text contains one pointer to the RBFOpt (solver) comparison in Supplementary Section S10.
Method names replace the former single-letter plot labels and RBFOpt setting abbreviations.

| Latest review item | Current disposition |
|---|---|
| 1: population size | Base parameter 400 and 20 generations distinguished from effective populations 408 and 412 |
| 2: Bonmin events | S10 classifies all 154 recorded exceptions, explains candidate recovery, and retains uncertainty about underlying solver causes |
| 3: CSTR15 counts | S5/S9 explain 290 - 135 + 151 = 306 constraints and 60 + 15 = 75 discrete values |
| 4: displayed Process pairs | S18 includes Dynamic B12 RBFOpt versus DSDA and Small Batch FMQA-SA versus Uniform, retaining paired outcomes and exploratory intervals |
| 5: fixed-path costs | Section 4.4 reports the RBFOpt/BAM median-order reversal at tenfold point cost without claiming a live adaptive crossover |
| 6: readable cost ticks | Dynamic B30/B37 numerical logarithmic ticks are present in Figures 7 and 8 |
| 7: exclusions | Main text and S10 include DSDA 44.21% and FMQA-SA 57.89% in the two-function exclusion summary |
| 8-10: references | Accepted references and publication years retained |
| 11: pinned documentation | Pyomo 6.10.0 and bam-solver 5.0.0 interface documentation replace moving links; external cited-commit access still awaits administrator release |
| Small corrections | CSTR expansion, source-verified QHD_Data capitalization, Hamiltonian/FMQA/Boolean capitalization and S9 pagination checked |

The main performance tables, callback records and paired numerical results retain their values.
Seven data figures are regenerated solely from the retained records with the current labels.
The seven reconstructed FMQA fits still do not certify unsaved historical weights.

## Additional Dantzig CSTR15 result

The [2026-10-21 Dantzig check](../results/review_cstr15_dantzig_20261021/README.md) used GAMS 52.2.0, IPOPT 3.14.19 and MUMPS 5.8.1 in one server NLP call from the original W03 start.
It returned objective `2.8293940632857595` and maximum unscaled original-GDP violation `1.1102230246251565e-16`, passing the `1e-8` numerical criterion.
The objective differs from the retained macOS AMPL/IPOPT result by `4.884981308350689e-15`, with the same discrete configuration.
The GLOA A12 discrepancy persists, whereas the Hull A15 difference is within the existing audit tolerance.
The server used execution revision `70bf17ca95e5ee1b98069e494c22fcafd6398960`; the original comparison execution-provider revision remains unchanged.
The local analysis reran no solver and preserved the returned ZIP, server verification and all earlier success/failure records.
The original strict full-summary verifier's cross-platform derived-ratio mismatch is retained in the [verification report](../results/review_cstr15_dantzig_20261021/verification.json).
A separate analysis checks every named residual and the unchanged feasibility criterion, and verifies ratios and near-zero residual rankings exactly against their respective recorded data.
This additional result is now synchronized into the main manuscript and Supplementary Section S9 in Overleaf; the earlier local result remains explicitly identified.

## Minor clarification review — 21 October 2026

The latest review requests clarification and final presentation changes rather than another benchmarking campaign.
The following updates are synchronized with Overleaf and recorded in the [minor-clarification verification](../manuscript/minor_clarification_verification.json).

| Review item | Disposition | Manuscript location |
|---|---|---|
| Minor 1: tightened CSTR15 versus Hull | Added the witness-sensitive contrast while preserving W03 and all eleven historical flags | Main Section 4.3.3 and Supplementary Section S9 |
| Minor 2: visited-key collection | Resolved by the current 700-run coverage audit: 2,050 distinct keys, with the included methods and union rule explicit | Main Table 1 and Section 4.3.2 |
| Minor 3: median-cost label | Caption explicitly states median reconstructed search-completion costs over all ten seeds | Table S17 |
| Minor 4: abstract scope | Added “On the analytical grids” to the budget-100 result | Abstract |
| CSTR terminology | Standardized to “continuous stirred-tank reactor (CSTR)” | Section 2.1 |
| MILP abbreviation | Expanded to “mixed-integer linear programming (MILP)” at first use | Section 2.2 |
| Supplementary pagination | Local paragraph spacing and page allowance retain the S9 introduction on page 22 and the full tightened check on page 25 | Supplementary Section S9 |

For the tighter objective `2.8293940632857546`, the printed Hull bound `2.829394077848967` gives a difference of `1.45632124e-8` and a tolerance ratio of approximately `5.14711e-4`, below the flagging threshold of one.
The historical Hull comparison against W03 has a ratio of approximately `1.536` and remains unchanged.
The GLOA discrepancy remains approximately `24,498` times the tolerance.
This sensitivity comparison does not classify W03 as infeasible, certify the Hull bound, or establish the cause of either bound report.
All performance-table bodies, equations, figure blocks, numerical datasets, source snapshots and prior verification records remain unchanged.
No optimizer, NLP, fitting, annealing or benchmark analysis was rerun.
Both documents compiled in Overleaf with zero errors and warnings; the main manuscript has 33 pages and the supplement has 30 pages.
The prose retains one sentence per source line.
PR #48 was already merged before this follow-up; these changes are subsequent work on `review/additional-comparisons`, not part of that merged PR.
The repository visibility and historical execution-provider revisions are unchanged.

## Resolution of visited-key scope — 21 October 2026

Minor review comment 2 is resolved in Table 1 and Section 4.3.2.
The [coverage audit and reviewer response](../results/review_process_coverage_20261021/README.md) report 2,050 distinct model/size/coordinate keys from 16,252 charged callbacks in the current 700-run primary Process comparison.
The union covers DSDA, RBFOpt, BAM, FMQA-SA and uniform sampling over 14 model--budget conditions and ten seeds per condition, excluding RBFOpt (solver).
The historical count of 1,790 is preserved in its own 560-run context and reconciles as 1,790 - 51 + 311 = 2,050.
All 2,455 measured keys and all 700 run memberships are exposed in auditable ledgers; failed and rejected evaluations remain included.
No experiment was rerun, and the existing performance tables, figures, historical manifests and supplementary stopping-audit scope remain unchanged.

## Submission revision — Dantzig result and reproducibility links

The main manuscript and S9 now report the completed Dantzig validation, with the original W03 configuration and starting values preserved.
The numerical result passes `1e-8`, retains the GLOA discrepancy and places the tightened Hull comparison within the existing audit tolerance.
The original benchmark performance tables, figures, callback data, manifests and execution revisions are unchanged.
Data availability and S8 link the current publication analysis and 2,050-key coverage audit at fixed revision `3c60f4707b454a9d3e4330466ec5f9372b418f54`.
The Dantzig evidence is separately cited at revision `5c124ffdfb2fc0b54673ae784d368f4b2afce973`.
Section 4.4 removes two Dynamic timing sentences already covered in Section 4.3.3 and retains the callback-count explanation.
The section structure is unchanged, and all edited prose uses one sentence per source line.
The environment statement applies to the benchmark performance runs; S10.4 explicitly identifies the reconstructed FMQA fits as local diagnostics.
The seven reconstructed FMQA fits still cannot verify unsaved historical weights.
The [submission verification](../manuscript/submission_revision_verification.json) records 81 passing local tests, source/PDF synchronization, numerical preservation and checks of the final rendered pages.
No optimizer, NLP, fitting, annealing or server experiment was rerun during this manuscript revision, and no CI workflow was requested.
The follow-up branch is `review/cstr15-dantzig-results`; PR #48 remains merged and unchanged.
Repository visibility and unauthenticated external access to the cited commits remain administrator-controlled release items.

## D-SDA tolerance adoption, 28 October 2026

The [publication analysis](../results/dsda_publication_20261028/README.md) adopts the completed Grid common-target stopping run and the Process absolute-improvement rerun.
Grid D-SDA uses the common target predicate at its existing post-descent checkpoint, and both scopes require strict absolute objective improvement greater than 1e-5.
Only D-SDA records change; all other method records, original archives, and provider revisions are preserved.
The primary Process cohort retains 315/700 target hits and 2,024 distinct visited configurations, with 16,041 charged callbacks.
These changes address the numerical criteria in David comments 4 and 5 without equating objective improvement, reference-target proximity, and primal feasibility.
