# Issue #28: implementation extraction

## Current main integration (2026-10-19)

The branch now includes upstream/main `b4935b3210c421862714d2c9d522f4bcac95f0bf`, including PR #37's final Process/BAM artifacts and the size-specific CSTR inputs. The extraction/dependency notes below are historical; those retained inputs are now on main. The builders still reject missing/invalid inputs instead of substituting another model size.

The merge retains the reviewed watchdog cleanup, input/archive verification, initial-design snapshots and main's FMQA compatibility CI. IPOPT integration tests are namespaced, and their optional-input collection hook is limited to that package so it cannot intercept main's retained tests with the same filenames. Result ZIPs, tables and execution revisions are unchanged; no new production experiment was run.

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

## Current integration and packaging (2026-10-16)

The extraction/dependency notes and test totals above describe the original
standalone draft. Main `4da1aa0be141362bdcf5bc662292f9def3e0371b` now supplies
the shared CPU, GDP, tracing and reviewed FMQA code. The two extracted
initial-design snapshots remain the source of ordered starts and budgets;
this update does not replace them with historical objective or timing data.

Both builders now use `result_archives.archived_directory()` to verify and
read the committed original GAMS/IPOPT ZIP. They record its path, SHA256 and
member paths rather than an ignored local extraction or temporary directory.
The catalog entry is identical to the one in #32/#37, and the archive bytes
are unchanged. Builders do not import executable process models or solve
NLPs. The standalone packages contain frozen evaluation inputs and textual
model evidence; they do not require the repository archive helper at runtime.

The non-CSTR inputs and CSTR N=30 inputs are available from that ZIP. Later
N=5/10/15/20/25 archives remain part of final-result integration in #37. If
absent or invalid, the CSTR builder explicitly marks only those sizes
`not_ready`, preserves all 240 planned slots and does not substitute N=30
values. No directory-presence skip hides the original-archive checks. Only
tests that actually need the later size-specific inputs remain conditional.

The reviewed watchdog cleanup is unchanged. Both current runners and builders
are now included in CI lint. Unused runtime imports were removed; intentional
importability probes remain explicit and still reject broken imports even
when distribution metadata reports the expected version. Summary generation
continues to require readable run metadata.

Validation commands (no production campaign or process NLP solve):

```bash
python -m pytest tests/ipopt_dfo tests/test_ipopt_fmqa_settings.py tests/test_result_archives.py -q -ra
python -m ruff check ipopt_dfo_cstr.py ipopt_dfo_non_cstr.py build_ipopt_dfo_cstr.py build_ipopt_dfo_non_cstr.py tests/ipopt_dfo
```

The suite checks verified frozen-input loading, record/objective/time joins,
shared starts, callback budgets, failure handling, process cleanup, and
packaging. Worker import guards are isolated between in-process tests; the
production worker's prohibition on process-model imports is unchanged.
Historical runner ZIPs, result records and algorithms are not rewritten.
