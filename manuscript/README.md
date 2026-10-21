# Revised manuscript — 21 October 2026

The primary method is labeled RBFOpt throughout the manuscript, tables and figures.
Section 3.3.3 states that its candidate-search option is the version 4.3.0 default.
The primary comparison also includes uniform sampling in both suites and the BAM-prefix control on Grid.
The main text refers readers to Supplementary Section S10 for the RBFOpt (solver) setting, results and paired comparisons.
That section preserves all 1,190 matched historical runs, numerical comparisons, auxiliary-solver errors and timing-environment limitations.
The separate diagnostic commit `15663134704b7bb1d4804c94c70edabaffbf8ecd` is summarized in S9/S10 without rerunning it.
That diagnostic verified seven reconstructed FM fits, while historical weights remain unknown, and recorded two option-rejected NLP calls without a new solution.
The later [CSTR15 follow-up](../results/review_feasibility_tautology_20261020/summary.json), retained in commit `854a1a7fc5a20a5489d82ef7991a16aaf89025f3`, passed the `1e-8` numerical feasibility check on the original GDP with objective `2.8293940632857546` and maximum unscaled violation `3.3306690738754696e-16`.
The recorded A12 lower-bound discrepancy persists, with a difference of `0.6931579445174396`.
This is numerical evidence for the retained point, not a proof of exact mathematical feasibility, global optimality or a solver defect.
The current sources, bibliography, PDFs, figures and source distribution ZIP are synchronized with the Chrome Overleaf revision.
The main text and Supplementary Section S9 include the successful CSTR15 follow-up; earlier unsuccessful calls remain historical evidence.
The original manifests and verification record retain their historical hashes.
The [analysis manifest](analysis_manifest_current.json) and [naming-revision verification](revision_verification.json) document the synchronized naming revision.
The subsequent [prose-only revision](prose_trim_verification.json) removes ten repeated sentences from the main text and updates its PDF and source ZIP.
The subsequent [minor-clarification verification](minor_clarification_verification.json) records the Hull contrast, Table S17 median-cost caption, abstract scope, terminology and S9 pagination corrections.
The [Process coverage audit](../results/review_process_coverage_20261021/README.md) resolves review item 2: the 700 primary runs visit 2,050 distinct model/size/coordinate keys through 16,252 charged callbacks.
Table 1 explicitly identifies the five methods and excludes the retained RBFOpt (solver) runs.
The [deletion record](../docs/prose_redundancy_trim.md) identifies each removed sentence and the retained explanation supporting its removal.
The [status correction record](../results/review_comparison_20261020/status_correction.json) still identifies the earlier README correction, whose exact README and status-document bytes are preserved under [review_history/cstr_status_correction](review_history/cstr_status_correction/).
The original analytical and process NLP inventories, logs, ZIP archives, manifests and audit implementation are unchanged.
No new optimization or NLP execution is part of this revision.

## Documents

- [Main source](main.tex) and [main PDF](main.pdf).
- [Supplementary source](supplementary.tex) and [supplementary PDF](supplementary.pdf).
- [Reference database](reference.bib), [figures](figures/) and [generated numerical records](tables/).
- [Review disposition](../docs/review_comparison_status.md) distinguishes completed text changes from outstanding numerical diagnostics and release work.

The sources were based on the current Overleaf project downloaded on 20 October 2026 and checked byte-for-byte against the saved pre-revision source.
The revised sources and figures were uploaded to that same project through Chrome.
The PDFs are downloaded from Overleaf after compilation.
Prose retains one sentence per source line.
Generated table rows are embedded directly in the sources so the manuscript remains editable as three root source files plus the figure directory.
The matching table snippets are retained under `tables/` for review and numerical reproduction.
Historical companion files referenced in S4–S9 are preserved under `reproduction/data/` and the original result archives.

## Numerical scope

At Grid B=100, RBFOpt reaches 171/210 targets (81.4%), BAM 147/210 (70.0%), FMQA-SA 129/210 (61.4%), uniform 45/210 (21.4%), and the BAM-prefix control 124/210 (59.0%).
The RBFOpt median reconstructed search-completion cost is 70.81 s, compared with 64.42 s for BAM, 60.51 s for uniform and 365.74 s for the retained solver variant.
The primary Process comparison retains all 700 runs, including 326 target hits, 373 misses and one DSDA execution failure.
RBFOpt reaches 126/140 Process targets versus 127/140 for RBFOpt (solver); the primary figures include all 16,252 charged callbacks.
Process totals are descriptive across heterogeneous conditions, including six related Dynamic budgets.
Each RBFOpt trajectory uses its own saved search time, every charged point cost and the one-time Dynamic preparation cost.
The cost endpoint excludes final wrapper result extraction/export and does not claim measured online optimizer–NLP runtime.
CPU affinity and kernel differed between historical and additional runs, so the timing comparison is not a simultaneous controlled experiment.

## Reproduction

Run these commands from the repository root with the recorded analysis dependencies, including Matplotlib 3.10.9.

```sh
python -m review_comparison.manuscript --output /tmp/gdp-publication-analysis
python -m pytest tests/test_review_comparison.py tests/test_review_comparison_audit.py tests/test_review_comparison_fmqa_uniform.py tests/test_review_comparison_manuscript.py tests/test_review_minor_presentation.py -q
python -m review_comparison.audit --output /tmp/gdp-original-audit
```

Use fresh output locations for audit reproduction.
The publication module generates tables and seven data figures without importing or invoking an optimizer.
It verifies the original completed-run CSV and return-archive hashes, all condition seed sets, every additional callback cost sum, and first-hit consistency.
The original illustrative Rosenbrock Figure 1 is retained unchanged and is not regenerated by this module.
The publication bootstrap reuses the unchanged `analysis.paired_interval` with seed 20261020 and 2,000 replicates.
Cases are ordered lexicographically and paired seeds numerically from 0 through 9.
Grid resamples intact ten-seed function vectors; Process resamples paired seeds separately within each condition.
Intervals are exploratory descriptive percentile intervals without equivalence, multiplicity-adjustment or general superiority claims.
Ten-seed boundary cases may produce degenerate intervals.

Compile `main.tex` or `supplementary.tex` in Overleaf with pdfLaTeX and BibTeX using the supplied figure directory and bibliography.
[analysis_manifest_current.json](analysis_manifest_current.json) records current input/source/output hashes, bootstrap settings, execution provenance and generation environment.
[revision_verification.json](revision_verification.json) records the naming-revision checks.
[prose_trim_verification.json](prose_trim_verification.json) records the preceding prose revision and its publication hashes.
[minor_clarification_verification.json](minor_clarification_verification.json) records the preceding clarification revision.
[coverage_revision_verification.json](coverage_revision_verification.json) records the subsequent resolution of the visited-key comment and the latest synchronized main source, PDF and source ZIP.
The earlier [verification.json](verification.json), [analysis_manifest.json](analysis_manifest.json) and [publication_manifest.json](publication_manifest.json) document the preceding publication snapshot, not the current display labels or PDFs.
