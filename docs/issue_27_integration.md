# Issue #27: implementation extraction

## Current main integration (2026-10-19)

The branch now includes upstream/main `b4935b3210c421862714d2c9d522f4bcac95f0bf`, including PR #37's final Process/BAM artifacts. The original extraction notes below are historical. Main's original ZIPs, result tables and execution revisions are retained unchanged; no new production experiment was run.

The merge preserves logical/preprocessing rejection metadata. The newly integrated Column/Dynamic enumerator explicitly accepts the exact reviewed `models.py` and `evaluation.py` hashes for this metadata-only change. Unknown adapter changes still fail. Original model formulas, initialization, solver settings and acceptance criteria are unchanged; regression tests check both accepted pins and rejection of changed bytes.

PR #43 is also integrated: uniform bound-conflict checks, refreshed reports and preservation validation are retained. No result files differ from this main revision.

## Historical extraction record

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

Requires pinned external model submodules. Grid GDP definitions from PR #26 are separate. No production solver campaign is run by this extraction.

## Validation of this extraction

- `python -m pytest tests/ -q`: 319 passed with pinned model submodules initialized.
- Targeted GDP/CPU tests: 124 passed.
- Ruff passed for the new package, runner, CPU helper and tests.
- No production solver campaign was executed; solver calls in interface tests use test doubles.

PR #26 also introduces `gdp_models/__init__.py` and the GDP optional dependency.
Reconcile those small package/dependency edits when merging the independent PRs;
this branch does not contain the grid model or its benchmark outputs.

## Integration with main after PR #23

The main merge retains the reviewed rejection-phase metadata and the existing
GAMS executable fix. Read-only trace replay verifies the model adapter stored
in the archive and uses its hash to join historical point measurements; it does
not execute that adapter. Live lookup inputs and all archived bytes remain
strictly checked. Future evaluation runs still use the current model adapter's
hash when deciding whether a historical cost is compatible. No archived result
or evaluation time is changed by this separation.
