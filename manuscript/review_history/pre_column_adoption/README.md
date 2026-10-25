# Current manuscript snapshot — CSTR30 initialization adoption

Overleaf remains the source of truth for the manuscript and its review comments.
The 25 October 2026 sources were edited directly in the existing Overleaf documents and then exported to this repository.
No manuscript source was uploaded to replace an Overleaf document, and David's comments and existing tracked changes were retained.
The current main PDF includes the supplementary material for review.
The supplementary PDF is an extraction of pages 25–35 from that combined PDF, retaining its original pagination; the standalone supplementary source is also provided.

The [publication analysis](../results/cstr30_publication_20261025/README.md) adopts all 50 completed CSTR30 searches after extending the existing mass-balance/zero-recycle initialization to N=30.
It first preserves the finite-1e6 CSTR D-SDA/RBFOpt comparison, then replaces CSTR30 for all five methods using the new evaluation table.
The other 650 primary Process runs and all Grid runs remain unchanged relative to that finite-penalty comparison.
Original targets, ten seeds per condition, evaluation budgets and failure-response policies remain unchanged.

RBFOpt reaches 45/60 CSTR targets, D-SDA 14/60, BAM 18/60, FMQA-SA 9/60 and uniform sampling 11/60.
The Process inventory contains 1,266 accepted configurations, including 464 CSTR30 configurations.
The 700 primary Process runs use 16,206 charged callbacks and visit 2,040 distinct model/size/coordinate keys.
These totals are descriptive aggregates across the stated conditions.
CSTR30 objectives, acceptance and evaluation costs come from the same retained first attempts.
Its point costs include initialization and artifact recording; old-to-new timing differences do not isolate the causal effect of initialization.
The unchanged CSTR30 reference is 2.7695697198995095.

The four affected Process figure PDFs and PNGs are regenerated from completed records and retain the existing presentation style.
The main text currently displays the Process evaluation and completion profiles; the other two updated Process figures remain available without restoring their commented figure blocks.
The active numerical tables, abstract, methods, results, discussion, conclusion and supplementary data links agree with this adopted comparison.
The reconstructed historical FMQA weight diagnostics retain their original scope.

## Files and reproduction

- [Main source](main.tex), [combined review PDF](main.pdf), [supplementary source](supplementary.tex) and [supplementary PDF](supplementary.pdf).
- [Bibliography](reference.bib), [figure files](figures/) and [source distribution](manuscript_sources.zip).
- [Current numerical tables and coverage](../results/cstr30_publication_20261025/tables/) and [input/source/output manifest](../results/cstr30_publication_20261025/manifest.json).
- [Analysis verification](../results/cstr30_publication_20261025/verification.json) and [manuscript synchronization verification](cstr30_revision_verification.json).

```bash
python -m review_comparison.cstr30_publication --output /tmp/cstr30-publication-new
python -m pytest tests/test_cstr30_publication.py tests/test_review_comparison_manuscript.py -q
```

This publication update executes no optimizer, NLP solver, model fitting or annealing, and requests no CI run.
The original experimental archives, provider revisions and audit files remain unchanged.
The [preceding README](review_history/pre_cstr30_initialization_adoption/README.md) and earlier verification records describe their historical snapshots rather than this current manuscript.
PR #49 was already merged; these changes are a follow-up on its original review/cstr15-dantzig-results branch.
