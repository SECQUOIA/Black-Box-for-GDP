# Professor review disposition — manuscript revision

The two major experimental comparisons have been incorporated in the [manuscript and supplementary material](../manuscript/README.md).
The primary comparison uses RBFOpt genetic and sampling controls, while the solver variant is retained in Supplementary Section S10.
The 3,430 additional runs and the 4,760 historical runs are preserved unchanged.
The manuscript revision at `6c0228e8` used completed records and ran no optimizer or NLP experiment.
The execution provider remains `38d917ef75ef6767c2a9f238d88be19bf0b89160`; the input analysis snapshot is `6e083eb49b497ce4fea90131e18cc0459db682e8`.
See the [original results and limitations](../results/review_comparison_20261020/README.md) and [publication analysis provenance](../manuscript/analysis_manifest.json).

| Review item | Status | Evidence / remaining action |
|---|---|---|
| Major: matched MSRSM genetic comparison | incorporated | Primary tables and figures use genetic; S10 retains solver results, paired comparisons, other auxiliary solver calls, and timing-environment limitations |
| Major: uniform and BAM-prefix controls | incorporated | Uniform in both suites; Grid prefix control; first-hit and completion profiles; B10 equality and higher-budget differences discussed |
| Minor 1: timing endpoint and terminal solutions | incorporated | Main timing definition and figure captions exclude final extraction/export; historical terminal audit preserved with solver labels; additional terminal observations linked in S10 |
| Minor 2: alpha cost scenarios | incorporated | S10 scenarios rescale point costs on retained paths; all existing scenario results remain unchanged |
| Minor 3: paired design and uncertainty | incorporated | S10 grouped Grid bootstrap and condition-specific Process analysis; empirical TTS qualification and four-restart illustration |
| FMQA-SA versus uniform paired comparison | incorporated | [1,190 pairs and 19 summaries](../results/review_comparison_20261020/fmqa_uniform/README.md); publication analysis independently agrees |
| Minor 4: suite exclusions | incorporated | S10 excludes Yang3 and Bohachevsky2; lattice effect discussed; no shifted-grid rerun |
| Minor 5: FMQA implementation and energy diagnostic | limited diagnostic incorporated | [Seven reconstructed fits and 3,328 binary strings](../results/review_diagnostics_20261020/README.md) summarized in S10; historical fitted weights remain unavailable; no prevalence or causal claim |
| Minor 6: numerical feasibility and tightened check | CSTR15 check completed; manuscript synchronization outside this correction | [One-call identity-preprocessed follow-up](../results/review_feasibility_tautology_20261020/README.md), retained in `854a1a7fc5a20a5489d82ef7991a16aaf89025f3`, passed the original-GDP 1e-8 residual test; the recorded A12 lower-bound discrepancy persists; all three earlier failed calls preserved; numerical evidence for this case only |
| Minor 7: starred execution profile | incorporated; optional display deferred | Table 5 notes explain replacement of previously failing cases, preserved expressions/settings and corrected preparation; unsuccessful times remain archived |
| Minor 8: figure annotations / variant labels | incorporated | Seven figures regenerated; BAM prefix shaded; genetic and controls labeled; Figure 6 uses mean cost shares |
| Minor 9: 63-object partition | preserved | S9 retains 45 selected plus 18 earlier records; nine witnesses form a subset |
| Minor 10: availability wording | incorporated | Private status and planned post-submission release stated; administrator action still required |
| Minor 11: GDP/process bibliography | preserved | No substantive correction requested; publication years unchanged |
| Minor 12: Nannicini configuration context | incorporated | Section 3.3.3 explains MSRSM candidate-search context without assuming the new result |
| Minor 13: statistical references / TTS meaning | incorporated | Clopper–Pearson issue 4 retained; TTS remains an empirical estimate, not a guarantee |
| Minor 14: metadata / pinned manuals | partial | Three DOIs and D-Wave 1.6.0 release link added; exact build-specific BAM/Pyomo documentation still requires verification |
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
This correction updates current repository status descriptions only; manuscript sources, bibliography, PDFs, figures and distribution ZIPs remain unchanged, and Overleaf was not accessed.
Obsolete incomplete-status wording in the manuscript copies is outside this correction, and no manuscript synchronization is claimed.
Other incomplete review items retain their previous status.
The repository visibility has not been changed, and no Slack message has been sent.

## Nannicini source check

Nannicini (2021), *On the implementation of a global optimization method for mixed-variable problems*, appears in Open Journal of Mathematical Optimization 2, article 1, 25 pages ([publisher](https://ojmo.centre-mersenne.org/articles/10.5802/ojmo.3/)).
Sections 4.2.3 and 5.2 of the [publisher PDF](https://ojmo.centre-mersenne.org/item/10.5802/ojmo.3.pdf) describe genetic, sampling and mathematical-solver candidate search and explain omission of MSRSM with mathematical solvers from the principal plots.
Those experiments use more intensive genetic settings than the defaults, and other surrogate-minimization operations retain Ipopt/Bonmin regardless of candidate-search strategy.
These observations motivate the present matched comparison without establishing its outcome or invalidating the preserved solver-option records.
The new performance runs keep the recorded default GA parameters.
