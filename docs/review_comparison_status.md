# Professor review disposition — additional comparisons returned and audited

All 3,430 planned additional comparisons were returned from Dantzig and audited:
1,558 target hits, 1,872 misses, no failed or missing slots. The 170,660 callbacks
and all recorded costs passed independent checks; eight analysis files replay
byte-for-byte. See the [results and limitations](../results/review_comparison_20261020/README.md).
Original experiments remain unchanged. The execution ZIP retains this document's
original preparation-only version; manuscript revisions and the other review
items below are separate work.

| Review item | Status | Evidence / remaining action |
|---|---|---|
| Major: matched MSRSM genetic comparison | executed and audited; manuscript discussion pending | 1,190 runs; only candidate-search setting changed; comparable aggregate hit counts with lower observed search overhead; no equivalence claim |
| Major: uniform and BAM-prefix controls | executed and audited; manuscript discussion pending | 1,190 uniform + 1,050 prefix-control runs; B10 BAM outcomes reproduced; higher-budget BAM gains retained |
| Minor 1: timing endpoint and terminal solutions | recorded and audited; manuscript explanation pending | search, lookup, extraction/export and worker clocks distinct; Process terminal observation retained; no missing point costs |
| Minor 2: alpha cost scenarios | regenerated for all completed comparisons | `analysis.py`, alpha=.01,.1,1,10,100; recorded-path cost rescaling, not new adaptive runs |
| Minor 3: success uncertainty and grouping | regenerated; manuscript interpretation pending | paired differences, grouped Grid bootstrap, complete ten-seed conditions; descriptive intervals with no equivalence or multiplicity claim |
| Minor 4: Yang3 / Bohachevsky2 exclusions | regenerated for all completed comparisons | `grid_exclusions.csv`; no objective definition changed; main descriptive patterns persist |
| Minor 5: FMQA zero-scale, regularization, exhaustive energy diagnostic | needs additional computation | original QHD converter and wrapper retained in execution snapshots; proposal logs exist, per-iteration fitted weight snapshots have not been established; no reconstructed iteration is claimed historical; no FMQA rerun launched |
| Minor 6: bound discrepancy and tightened feasibility | needs additional computation | original audit and residual checks retained; no restoration/tightened NLP authorized in this base package; proposed representative test must retain raw bound and witness provenance |
| Minor 7: Table 5 starred execution profile | analysis pending | historical `gdp_runs.csv`/grid GDP manifest available in repository; exact selection/profile equivalence explanation remains to be drafted and checked; no solver rerun |
| Minor 8: figure annotations / variant labels | new comparison figures generated; manuscript edits pending | solver/genetic and retained/new labels explicit; Process failure retained; final manuscript Figure2 annotation remains separate |
| Minor 9: 63-vector partition | addressed in supplied latest manuscript | supplementary.tex lines760–761: 45 selected + 18 earlier RIC/GLOA, nine witnesses a subset (seven selected + two earlier RIC); not reverted or edited |
| Minor 10: availability wording | analysis pending | final release/availability wording is separate; no statement of completed public release |
| Minor 11: GDP/process bibliography | addressed by review, no correction requested | publication years not changed |
| Minor 12: Nannicini configuration context | addressed in preparation note; manuscript edit pending | source below, Sections4.2.3 and5.2; no predicted outcome on these benchmarks |
| Minor 13: statistical references/TTS meaning | addressed in analysis documentation; manuscript edit pending | TTS99 remains an empirical restart estimate, not a percentile or guarantee |
| Minor 14: bibliography metadata/pinned manuals | analysis pending | DOI/build-specific documentation edits separate; no solver upgrade |
| Minor 15: commit-content provenance | return manifest and source hashes recorded; release verification pending | execution provider remains `38d917ef`; publication revision is distinct; logged-out release verification remains separate |
| Typos and terminology | analysis pending | do not edit supplied Overleaf sources here; check ALAMO, NLP/CSTR expansions, capitalization, branch case, and S6/S9 wording separately |

## Nannicini source check

G. Nannicini (2021), *On the implementation of a global optimization method for
mixed-variable problems*, Open Journal of Mathematical Optimization 2, article1,
25 pages, [DOI 10.5802/ojmo.3](https://ojmo.centre-mersenne.org/articles/10.5802/ojmo.3/).
[Publisher PDF](https://ojmo.centre-mersenne.org/item/10.5802/ojmo.3.pdf),
Sections4.2.3 (printed p9) and5.2 (printed pp14–15), checked 2026-10-20.
The paper describes genetic, sampling and mathematical-solver candidate search.
Its experiments omit MSRSM with mathematical solvers from the principal plots,
reporting poor performance associated with the nonconvex distance subproblem.
Those experiments use more intensive genetic settings than the defaults.
Other surrogate-minimization operations still use Ipopt/Bonmin regardless of
candidate-search strategy. These observations motivate a matched configuration
comparison here; they do not establish its result or invalidate the original
solver-option records. The new runs keep the recorded default GA parameters.

## Manuscript reference boundary

The supplied review and `cohesion-review-20261020/after/main.tex` and
`supplementary.tex` were read as reference material. They are not copied into the
execution package. `review_comparison_draft.tex` is a new short wording draft,
not an edited or bundled manuscript. Numerical results are now available in
the additional-comparison report; no manuscript or Overleaf source was edited.
