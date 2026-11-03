# Current manuscript snapshot - Column logical-domain adoption

Overleaf remains the source of truth for the manuscript and its review comments.
The 25 October 2026 sources were edited directly in the existing Overleaf documents and then exported to this repository.
No manuscript source was uploaded to replace an Overleaf document, and David's comments and existing tracked changes were retained.
The current main PDF includes the supplementary material for review.
The combined PDF has 34 pages, with references starting on page 19.
The supplementary PDF contains pages 23-34 of that combined PDF, retaining its original pagination.
Links to excluded main-text pages may not survive this extraction.

The [current publication analysis](../results/column_publication_20261025/README.md) replaces all 50 Column runs with the completed logical-domain/B13 comparison.
The 64 candidate configurations satisfy the original model's logical restrictions and reuse the retained IPOPT responses and point costs.
All five methods share three ordered initial configurations and ten seeds.
The domain, budget and regenerated initial designs change together, so their separate effects are not identified.
The other 650 primary Process runs and all Grid runs remain unchanged relative to the preceding CSTR30 publication analysis.

Column target counts are D-SDA 5/10, RBFOpt 4/10, BAM 1/10, FMQA-SA 4/10 and uniform sampling 1/10.
RBFOpt therefore shows no target-hit advantage over D-SDA in this condition.
Median reconstructed completion costs are 35.43 s for D-SDA and 54.60 s for RBFOpt.
These are full-run estimates from recorded search overhead and charged point costs, not online optimizer-NLP timings.
Seed 6 contains the target as its third shared initial point and accounts for the only BAM and uniform successes.
The unchanged CSTR totals remain 45/60 for RBFOpt and 14/60 for D-SDA.
The Process inventory contains 2,438 configurations, including 1,266 accepted responses and 464 accepted CSTR30 configurations.
The 700 primary Process runs contain 315 target hits, 385 misses and no execution failures.
They use 16,067 charged callbacks and visit 2,024 distinct model/size/coordinate keys.
These totals are descriptive aggregates across the stated conditions.

The four affected Process figure PDFs and PNGs are regenerated from completed records and retain the existing presentation style.
The main text currently displays the Process evaluation and completion profiles; the other two updated Process figures remain available without restoring their commented figure blocks.
The affected domain, budget, target-count, cost, coverage and fallback statements agree with this adopted comparison.
The reconstructed historical FMQA weight diagnostics retain their original scope.
All 34 David comment lines are unchanged from the source downloaded before this task.
Overleaf produces the combined PDF with one pre-existing undefined-command error for a retained David comment and no warnings.

## Files and reproduction

- [Main source](main.tex), [combined review PDF](main.pdf), [supplementary source](supplementary.tex) and [supplementary PDF](supplementary.pdf).
- [Bibliography](reference.bib), [figure files](figures/) and [source distribution](manuscript_sources.zip).
- [Current numerical tables and coverage](../results/column_publication_20261025/tables/) and [input/source/output manifest](../results/column_publication_20261025/manifest.json).
- [Analysis verification](../results/column_publication_20261025/verification.json) and [manuscript synchronization verification](column_revision_verification.json).

```bash
python -m review_comparison.column_publication --output /tmp/column-publication-new
python -m pytest tests/test_column_publication.py tests/test_cstr30_publication.py tests/test_review_comparison_manuscript.py -q
```

This publication update executes no optimizer, NLP solver, model fitting or annealing, and requests no CI run.
The original experimental archives, provider revisions and audit files remain unchanged.
The [preceding README](review_history/pre_column_adoption/README.md) and earlier verification records describe their historical snapshots rather than this current manuscript.
The original analysis_manifest.json remains a historical record; analysis_manifest_current.json points to the current analysis.
PR #49 was already merged; these changes are a follow-up on its original review/cstr15-dantzig-results branch.
