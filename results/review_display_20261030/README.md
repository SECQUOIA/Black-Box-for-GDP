# Review presentation follow-up

This update addresses the Grid hit-table, Figure 1 distinction, and process search-time comments using completed DFO records only.
No optimizer, NLP solver, training, or server experiment is run.
The archived input manifest and data remain unchanged.

The input is `results/dsda_publication_20261028/tables/run_records.csv`.
Input SHA256 is checked against its archived manifest before use.
All 6,300 primary Grid runs and all 30 archived curves are checked before selecting the six B=100 curves for Figure 1.
The separate five-budget Grid table retains its original percentages and highlights all row maxima, including ties.
Figure 1 has no internal title and preserves every B=100 curve coordinate.
BAM uses a thicker green solid line and filled triangles; its prefix control uses a thinner black dash-dot line and open downward triangles.
The overlap is not displaced, and staggered markers help reveal both methods where their curves coincide.

The process table uses exactly 700 current DFO runs: 14 case-budget conditions, five methods, and seeds 0--9 in every group.
Historical RBFOpt solver-mode records are excluded.
Missing, duplicate, unexpected, nonfinite, or negative-time records cause an error.
Each table cell reports target hits, Q50 search time, and [Q25, Q75] in seconds.
All ten seeds remain in each summary, including target misses or execution failures if present.
Search time is the stored `search_s`, which excludes lookup processing and configuration-evaluation costs.
It retains candidate-selection overhead, including surrogate subsolver calls where applicable.
Quartiles use inclusive linear interpolation at rank (n-1)p and are descriptive seed variability, not confidence intervals.
Conditions are summarized separately, including the six Dynamic budgets.
Displayed times use three significant digits; the CSV retains full precision.
Only target-hit maxima are bold, and ties are retained.

Reproduce from the repository root:

```sh
python -m review_comparison.review_display --output /tmp/review-display-replay
```

Overleaf remains the manuscript source of truth.
The TeX outputs are table-row fragments for localized edits, not replacement manuscript files.
