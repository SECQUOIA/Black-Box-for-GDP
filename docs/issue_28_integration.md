# Issue #28: implementation extraction

This branch extracts implementation, tests, and documentation from
`AlbertLee125/RBFopt_Test:Benchmark` at `ade67082ad2b09583a8f5594b827c97417e0ea99`.
It contains no experiment outputs or result archives. Existing results remain
on [Benchmark](https://github.com/AlbertLee125/RBFopt_Test/tree/ade67082ad2b09583a8f5594b827c97417e0ea99)
and are intended for a separate result merge from that branch.

This is a reviewable implementation draft, not a claim that every acceptance
criterion or production experiment has been completed on main. Historical
launch guides preserve their original paths; frozen input archives must be
restored separately before replaying those commands. Do not substitute other
model sizes, evaluation procedures, or objective tables for absent inputs.

## Dependencies and review boundaries

Depends on CPU support from #27, trace instrumentation from #29, and separately reviewed FMQA adapter code for the historical all-method bundle. Plan-only snapshots exclude old results and timing records. Archive replay tests are explicitly skipped when the required frozen inputs or source modules are absent; standalone budget and plan tests still run. No FMQA implementation is included.

## Validation of this extraction

- Full suite: 217 passed, 43 explicitly skipped for absent integration sources/archives.
- Standalone DFO plan/budget tests: 22 passed, 43 archive/dependency checks skipped.
- Ruff passed for tests. Original runner formatting is retained.
- No DFO experiment or process NLP solve was executed.

This draft is not independently deployable as the historical all-method bundle:
resolve the documented source dependencies and supply immutable inputs before
bundle replay. Skips do not certify those integration paths. Test prerequisites
are scoped to `tests/ipopt_dfo/` and do not suppress unrelated tests.
