# Issue #44 validation and release gate

Baseline: SECQUOIA/RBFopt_Test `cb70771b2037301bb6d0e38a2362d49b53fcda7d`.
Reference: supplied top-level October 19 `main.tex` and `supplementary.tex`,
used only outside the repository. No manuscript sources/Overleaf ZIP added.

## Scope and evidence

- Added missing supporting protocols, model/acceptance/version inventories,
  proposal/fallback counts, all 14 terminal-only recovery records, 4,760 stopping
  diagnostic records, and the complete algebraic audit (63 result/vector pairs).
- Added generators for all eight main figures and all 23 table datasets,
  a path/hash index, locked Python environment, deterministic package builder
  and verification commands. Historical data and original ZIP bytes are intact.
- Numerical replay uses only recorded data. Saved GDP vectors are evaluated
  against constraints; there are no new optimization or NLP solves.
- The figure review uses PDF rasterizations. New layout code is disclosed for
  Figures 1/3/4/5; identical PDF bytes are not a reproducibility claim. Figure 4
  explicitly separates zero-hit counts from the infinite-median strip.

## Checks executed

The machine-readable reports beside this file provide actual commands,
environment, source hashes, output hashes and detailed outcomes. They distinguish
fresh saved-vector checks from merely reading the historical checks.

The initial clean Python 3.12.13 environment reproduced eight figures and 23
CSV/Markdown datasets. Official Process, Grid and algebraic replays matched
retained outputs: 560 Process runs (291 hits, 268 misses, one execution failure),
4,200 Grid runs and 201,833 callbacks, and 140 corrected BAM runs / 3,430 callbacks.
All 476 binomial intervals, Process/Grid medians and TTS99 values, 14 terminal-only
records and eleven bound flags were checked. All 560 protocol dictionaries were
checked against original job metadata (only the two RBFOpt solver paths are
shortened to executable basenames in the supplied protocol).

734 automated comparisons against the latest top-level TeX reference passed,
covering displayed hit counts, completion/target values, medians, intervals,
stopping/model counts, minimizers, domains and algebraic classifications.
Table 2 prose, mathematical notation and final manuscript page layout remain
editorial review, not automatic numerical checks. CSV exports expose the full
original settings rather than pretending to generate the prose table verbatim.

The official GDP replay prints `target_hits_by_method` using **absolute objective
matching** (RIC 3, GLOA 1, LOA 3, Big-M 6, Hull 6). The manuscript audit's
`target_attained` is the distinct minimization rule, at-or-below target within
tolerance (3, 1, 4, 7, 6). Both original columns are preserved; these are different
predicates, not an altered experiment or missing result.

Local targeted regression suite: 101 passed (companion, final Process,
Grid-path, NLP-cost and archive tests). Additional checks and extracted-package
execution are recorded in the accompanying JSON reports. CI results are separate;
local success does not claim that a remote CI run has already completed.

## Manuscript / release follow-up (not performed here)

The nested `manuscript_sources.zip` is stale: both TeX hashes differ from the
top-level reference. Changes include captions, timing explanations, historical
function names and the bound-audit interpretation. Its companion figure renderer
matches the copy inside `supplementary_data.zip`; that renderer covers only
Figures 2/6/7. The supplied Figure 8 data equals the retained Process CSV after
newline normalization; the data and all 36 ten-run medians are unchanged.

The paper should separately update S8/availability to the final immutable package
locator and the complete output index after merge. Refresh nested submission
archives from the then-final top-level sources. No manuscript edits were made.

Public release/tag creation, an immutable download URL and logged-out browser
access checks remain **pending**. The reviewer-observed 404 is retained as an
access observation with unknown cause. The post-merge checklist is in
`reproduction/README.md`; Issue #44 must remain open until satisfied.
