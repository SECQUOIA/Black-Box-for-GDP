# Current manuscript snapshot - D-SDA tolerance and target-stopping update

Overleaf remains the source of truth for the manuscript and its review comments.
The 28 October 2026 sources were edited directly in the existing Overleaf documents and exported after compilation.
The snapshot includes the intervening author and reviewer edits since the preceding repository export.
No manuscript source was uploaded to replace an Overleaf document, and existing comments and tracked changes were retained.
The current combined review PDF has 35 pages, with references starting on page 19 and supplementary material on pages 23-35.
The supplementary PDF extracts those 13 pages and retains their original pagination.
Links to excluded main-text pages may not survive this extraction.
Overleaf reports zero errors and zero warnings.

The [current publication analysis](../results/dsda_publication_20261028/README.md) adopts 1,050 Grid and 140 Process D-SDA runs from the completed return archives.
Neighborhood and line-search moves require strict absolute objective improvement greater than 1e-5.
Grid D-SDA applies the common reference-target predicate after a completed descent, while budget exhaustion is checked first.
This is not immediate stopping at the first successful callback.
Process D-SDA retains its single best accepted initial start and its existing stopping policy.
Primal feasibility remains a separate constraint-violation test.
Brief Albert replies address David comments 4 and 5, while all David comment text is preserved for review.

Grid D-SDA target counts are 13, 74, 88, 98 and 101 of 210 at budgets 10, 30, 50, 70 and 100, respectively.
At B=100, D-SDA reaches 48.1% and RBFOpt reaches 81.4% of targets.
All Process D-SDA successes remain unchanged at 74/140, including CSTR 14/60 and Column 5/10.
RBFOpt remains at CSTR 45/60 and Column 4/10.
All other methods retain their adopted records.
The 700 primary Process runs contain 315 target hits, 385 misses and no execution failures.
They use 16,041 charged callbacks and visit 2,024 distinct model/size/coordinate keys.
The Process inventory remains 2,438 configurations with 1,266 accepted responses, including 464 accepted CSTR30 configurations.
These totals are descriptive aggregates across the stated conditions.
Completion costs combine the new recorded D-SDA search overhead with the unchanged point costs along each new callback path.
They are reconstructed full-run estimates, not online optimizer-NLP timings or cross-run hardware speedup measurements.

Seven figure PDFs and PNGs were regenerated using the existing presentation style.
The active main-text plots remain the Grid evaluation profile and the Process evaluation and completion profiles.
Regenerated inactive figures are available as companions and are not restored to the paper.
The current tables and analysis manifests are linked below; unused older companions remain explicitly historical.
The reconstructed historical FMQA weight diagnostics retain their original scope.

## Files and reproduction

- [Main source](main.tex), [combined review PDF](main.pdf), [supplementary source](supplementary.tex) and [supplementary PDF](supplementary.pdf).
- [Bibliography](reference.bib), [figure files](figures/) and [source distribution](manuscript_sources.zip).
- [Current numerical tables](../results/dsda_publication_20261028/tables/) and [input/source/output manifest](../results/dsda_publication_20261028/manifest.json).
- [Analysis validation](../docs/dsda_publication_update_20261028.md) and [snapshot verification](dsda_revision_verification.json).

```bash
python -m review_comparison.dsda_publication --output /tmp/dsda-publication-new
python -m pytest tests/test_dsda_publication.py tests/test_column_publication.py tests/test_cstr30_publication.py tests/test_review_comparison_audit.py -q
```

The related test set passes all 35 tests, and two fresh analysis replays produce 30 byte-identical files, including all seven PDFs.
The original comparison audit also reproduces its original outputs unchanged.
This publication update executes no optimizer, NLP solver, model fitting or annealing, and requests no CI run.
Original experimental archives, execution revisions and historical audit files remain unchanged.
The [preceding README and manifests](review_history/pre_dsda_adoption/) and earlier verification records describe their historical snapshots.
The original analysis_manifest.json is historical; analysis_manifest_current.json points to the current analysis.
These changes update PR #52 on review/cstr15-dantzig-results without merging it.
