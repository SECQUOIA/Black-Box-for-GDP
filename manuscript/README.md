# Current manuscript snapshot - Grid figure and cost quartiles

Overleaf remains the source of truth for the manuscript and its review comments.
This 29 October 2026 snapshot was exported after in-place edits to the Grid figure caption and cost table.
It also includes the author and reviewer changes made in Overleaf since the preceding repository export.
No manuscript source was uploaded to replace an Overleaf document.
David's comments and the current tracked edits remain in Overleaf, and Albert replies follow the addressed inline comments.
Source exports contain inline comments but do not replace Overleaf's review history.

The combined review PDF has 31 pages, with references starting on page 19 and the supplement on pages 23-31.
The supplementary PDF extracts those nine pages with their original pagination.
Links to main-text pages may not survive extraction.
Overleaf reported zero errors and zero warnings.

The [Grid presentation update](../results/grid_presentation_20261029/README.md) clarifies the evaluation-count figure and adds Q25/Q50/Q75 to the B=100 cost table.
The figure preserves all 30 curve coordinate arrays and the table preserves all target-hit counts and medians.
The input is the [completed D-SDA publication analysis](../results/dsda_publication_20261028/README.md), which remains unchanged.
No searches, NLP solves, or server experiments were run for this update.
Sections 4.4 and the conclusions were not revised in this update.

- [Main source](main.tex), [combined review PDF](main.pdf), [supplementary source](supplementary.tex), and [supplementary PDF](supplementary.pdf).
- [Bibliography](reference.bib), [figure files](figures/), and [source distribution](manuscript_sources.zip).
- [Presentation code](../review_comparison/grid_presentation.py), [quartile data](tables/grid_cost_quartiles.csv), and [validation](../docs/grid_presentation_update_20261029.md).
- [Snapshot manifest](publication_manifest.json) and [verification](grid_revision_verification.json).

```sh
python -m review_comparison.grid_presentation --output /tmp/grid-presentation-new
python -m pytest tests/test_grid_presentation.py tests/test_dsda_publication.py -q
```

The 14 relevant tests pass, and two fresh presentation runs produce seven byte-identical outputs.
Original execution archives, provider revisions, numerical analysis outputs, and historical audit files remain unchanged.
The preceding [snapshot README and manifest](review_history/pre_grid_presentation/) describe the earlier export.
The unchanged analysis_manifest_current.json and dsda_revision_verification.json describe the underlying D-SDA adoption, while the new presentation manifest is linked above.
Inactive legacy figures remain historical companions and were not restored to the paper.
