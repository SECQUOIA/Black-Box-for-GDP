# Issue #27: implementation extraction

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
