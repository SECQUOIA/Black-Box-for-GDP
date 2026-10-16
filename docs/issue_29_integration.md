# Issue #29: implementation extraction

This branch extracts implementation, tests, and documentation from
`AlbertLee125/RBFopt_Test:Benchmark` at `ade67082ad2b09583a8f5594b827c97417e0ea99`.
The extraction added no experiment outputs or result archives. Existing results remain
on [Benchmark](https://github.com/AlbertLee125/RBFopt_Test/tree/ade67082ad2b09583a8f5594b827c97417e0ea99)
and are intended for a separate result merge from that branch.

This is a reviewable implementation draft, not a claim that every acceptance
criterion or production experiment has been completed on main. Historical
launch guides preserve their original paths. Column/Dynamic reference inputs now
load from the verified original ZIP already on main; later CSTR DFO overlays
still require their separate frozen archives. Do not substitute other
model sizes, evaluation procedures, or objective tables for absent inputs.

## Dependencies and review boundaries

Depends on #27 for process models and domain/batch helpers. Legacy publication adapters also require the separate FMQA protocol module; imports are deferred so callback instrumentation remains usable without it. Historical archive tests are explicitly skipped when the immutable inputs are absent. Existing tests are grouped under tests/trace_timing to avoid conflicting with other PR prerequisites. Grid trace runner and additional publication analysis integration remain follow-up work under #29.

## Validation of this extraction

- Full standalone suite: 214 passed, 51 explicitly skipped for absent #27 code or archives.
- With the extracted #27 package on PYTHONPATH, cost-ledger and process-enumeration
  tests: 21 passed, 4 historical-reference tests skipped.
- Ruff passed for modified shared runtime, trace/cost modules and tests.
- No production enumeration, process NLP solver, or DFO search was run.

Historical reference bytes and source pins remain enforced. Restoring arbitrary
replacement tables does not satisfy archive replay prerequisites. Skipped tests
are not evidence that archive replay succeeded. Reconcile the package-list
addition with the other independent implementation PRs before merge.

## Integration with main after #23

Main at `a4db6d6` now includes the historical result archives and shared GDP,
FMQA and tracing infrastructure through #23. The original extraction notes
above describe the standalone draft before that merge. This branch retains
the reviewed selected-attempt identity/objective checks and process-group
cleanup. Its enumeration test double now exposes the effective executable
required by the integrated GAMS adapter. The trace test package is namespaced
to avoid colliding with main's existing test module names.


## Current source-preflight integration (2026-10-16)

Main `4da1aa0be141362bdcf5bc662292f9def3e0371b` supplies the shared GDP,
tracing and reviewed FMQA implementations. The sections above retain the
original extraction history rather than describing missing current code.

The Column/Dynamic enumerator explicitly accepts the exact `evaluation.py` and
`solvers.py` hashes introduced by the reviewed effective-GAMS-executable fix
`5a9e704`. That change routes availability, version and solve to the same
configured executable and reports it consistently. It does not change the
pinned process models, initialization, options or acceptance rule. The original
adapter profile remains accepted; unknown changes still fail. No hashes are
automatically approved from the working tree. Future adapter edits (including
#30's rejection-phase metadata) require a separate compatibility review.

When no bundle/local reference directory exists, `reference_files()` uses
`result_archives.verified_zip()` and the `original-ipopt-evaluations` catalog
entry. The original archive was already committed on main; this PR adds only
its catalog metadata, not a new archive or result. Outer/internal hashes and
the four frozen CSV/manifest hashes are checked. An existing changed or
incomplete reference directory fails rather than falling back silently.

The builder validates the exact captured adapter bytes before writing a ZIP,
records the accepted differences, and embeds those same bytes and verified
references. Building now requires the GDP Python dependencies and initialized
pinned submodules. It constructs no models and invokes no solvers. Standalone
bundles read their own `reference/` files and do not require the repository's
archive helper or an unpacked historical result directory.

Solver-free regression checks:

```bash
python -m pytest tests/trace_timing/test_enumerate_process_ipopt.py -q
python -m pytest tests/trace_timing tests/test_nlp_cost_join.py tests/test_result_archives.py tests/test_gdp_solvers.py -q -ra
python -m ruff check enumerate_process_ipopt.py enumerate_column_ipopt.py enumerate_dynamic_ipopt.py build_column_dynamic_ipopt.py measure_cstr30_structural_rejections.py tests/trace_timing
```

The source/bundle checks no longer skip when the ignored extracted input
folder is absent. They cover archive-backed loading, changed-reference
rejection, unreviewed captured adapter rejection, and real bundled preflight
in a separate interpreter. The separate CSTR structural-overlay replay tests
remain explicit skips when their later DFO archive is unavailable.
