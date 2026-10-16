# Process DSDA domain and callback-budget fairness

The process DSDA adapters previously passed dictionaries of feasible lookup
outcomes as domain membership. An in-bounds unsuccessful coordinate could then
be skipped without an objective callback and, in line search, be reported as
out of bounds. This changed the information and budget available to DSDA.

The adapters now construct dummy membership keys from declared integer bounds,
independently of objective outcomes. All initial points are evaluated in order;
only charged, finite non-penalty responses are eligible for starting-point
selection. If all starts are unsuccessful, initialization raises after charging
each supplied point, without selecting a replacement.

| Case | Declared integer box |
|---|---|
| Column | `{7,...,15} × {1,...,9}` |
| CSTR N | `{1,...,N}²` |
| Dynamic | `{1,...,9} × {2,...,9}` |
| Small Batch legacy adapter | `{1,2,3}³` |

`starting_points=` accepts an ordered frozen design. Length, bounds, and the
initial evaluation budget are validated before callbacks. Repeated supplied
points still incur callbacks. Remaining search budget subtracts all initial
calls; the selected starting value is reused without another callback.

The shared `grid_dsda.py` engine is unchanged, including neighborhood order,
first tie-breaking, improvement tolerance, penalties and line-search behavior.
Its existing caps stop mid-neighborhood and mid-line-search. An in-bounds
unsuccessful trial is evaluated and rejected; only a coordinate outside the
explicit box is classified as out of bounds.

## Validation

Run `python -m pytest tests/test_process_dsda_domain.py tests/test_*dsda_case.py -q`.
The source-only tests exercise membership without dictionary-value access,
failed and repeated callback accounting, frozen initialization, 2D/3D domains,
and budget stops during initialization, neighborhoods and line search.

## Issue scope and archived evidence

This PR addresses the adapter/model-domain portion of
[Issue #24](https://github.com/SECQUOIA/RBFopt_Test/issues/24). It is extracted
from `Benchmark` at `ade67082ad2b09583a8f5594b827c97417e0ea99`; the relevant
original implementation commit is `5cb69db`.

**The actual Dantzig revalidation results, original failed trace, single-job
recovery, audits and publication-selection records are stored on the
[Benchmark branch](https://github.com/AlbertLee125/RBFopt_Test/tree/Benchmark),
not in this implementation PR.** Results are intended for a separate results
merge from that branch. See
[`results/process_dsda_fairness_20261014/`](https://github.com/AlbertLee125/RBFopt_Test/tree/ade67082ad2b09583a8f5594b827c97417e0ea99/results/process_dsda_fairness_20261014)
and the source/result indexes on that branch.

The historical 140-run matrix, tolerance-aware returned-incumbent validator,
recovery launcher, cost coverage and selection audits are not re-executed or
certified by these adapter tests. The issue remains open for those integration
and evidence-review criteria. No recorded results are reclassified here.

Small Batch's selected full-domain publication runs already used all 27 keys;
this change to its legacy adapter is not evidence those selected runs were
incorrect and does not replace them. Historical Column seeds 1–10 in #24 are
also distinct from the later IPOPT CSV experiment's seeds 0–9.
