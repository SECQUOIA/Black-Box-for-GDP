# Maintained D-SDA protocol (issue #53)

This change promotes the D-SDA criteria verified in PR #52 into maintained code and public execution paths.
It is a code-equivalence change, not a new performance experiment or a replacement of publication results.
The follow-up PR is a draft stacked on `review/cstr15-dantzig-results` and must not merge before #52.
After #52 merges, retarget the follow-up PR to `main` and review its remaining diff.
The starting revision is `ef2365e420244de858c3b97f67a3cc53ea1769e1`.

## Defaults and distinct criteria

`grid_dsda.dsda_from_csv` and its multistart wrapper default to `improvement_abs_tol=1e-5`.
Minimization accepts a move only when the actual floating-point subtraction `old_value - new_value > improvement_abs_tol` is true.
Maximization uses `new_value - old_value > improvement_abs_tol`.
There is no relative improvement term or `isclose` boundary relaxation.
The same predicate controls neighbor acceptance, direction search, and the existing connected threshold-filtered `best_seen` and `best_run` updates.
Numerical ties retain the independent `tol=1e-12` with zero relative tolerance.
Tolerances must be finite and nonnegative, and invalid settings fail before objective callbacks.
In the adopted mode, nonfinite responses never become moves or observed incumbents, and a finite response can recover a nonfinite start.
Per-descent incumbent trajectories also exclude nonfinite responses and declared failure penalties, including a cached invalid start, while legacy trajectories retain their original arithmetic.

Grid defaults to `target_stop=dsda_protocol.common_target_reached`.
The predicate is `abs(observed_best - target) <= 1e-5 * max(1.0, abs(target))` on finite, unrounded values.
Targets remain caller inputs, including the existing per-case targets in the saved job specifications.
Tests compare this maintained predicate against the unchanged publication analysis predicate, including nonzero targets and representable boundary neighbors.
Objective improvement, target proximity, and configuration feasibility are different criteria.
Feasibility remains determined by the existing accepted lookup response policy; this change does not alter a model, feasibility tolerance, penalty, domain, or initialization.
Target proximity does not certify global optimality or reproduce the complete original LD-SDA implementation.

## Observation, checkpoints, and reporting

The D-SDA-specific `ObservedObjective` counts every returned callback but tracks only finite accepted values, excluding each Process wrapper's existing finite failure penalty where applicable.
This reporting incumbent includes evaluations rejected as moves and is independent of the selected endpoint and threshold-filtered best fields.
The shared instrumentation used by other methods retains its original behavior.
`best_value` and `best_point` retain their historical path-selected meanings, while `observed_best_value` reports the accepted observed extremum and `target_reached` reports common target proximity.
Grid's default `found_optimum` is a compatibility alias for its common target flag, and `benchmark.py` no longer overwrites it using an absolute `1e-12` check.
The Process wrappers retain `found_optimum` as the historical conjunction of known-coordinate equality and value equality within absolute `1e-12`, alongside the independent common `target_reached` field.
CSV output includes the two new reporting columns when supplied, while other-method-only CSV schemas remain unchanged.
The CSV header and paired manifest describe the same ordered fields, and resume and trace validation restore the optional numeric value and boolean flag without discarding them.
In mixed-method files, empty reporting cells for methods without a report remain missing rather than becoming a false success flag.
A D-SDA report with no accepted observation retains `observed_best_value=None` and `target_reached=False`.
The Process analysis loader preserves both optional columns with nullable numeric and boolean types; historical summaries based on `found_optimum` retain their existing meaning.

Grid checks the target only after a descent returns, after the existing interrupted-descent budget branch, and before another ranked initial start.
An improving terminal callback that interrupts a descent therefore retains the budget reason even if it also reaches the target.
A naturally completed descent may end exactly at callback B without setting the interruption flag, retaining the original target or natural-completion reason.
The saved Grid reference contains 12 such boundary completions, including two with the target reason, and all reason labels are preserved exactly.
No additional callback-level stopping or post-descent budget checkpoint has been introduced.
If no improving neighbor exists and the target has not been reached, Grid proceeds to the next ranked initial start when budget remains.
Process still selects the single best accepted observation among the three ordered initial configurations and never adds Grid target stopping or multistart behavior.
All three initial callbacks remain charged, the chosen initial value remains cached, repeated configurations consume callbacks again, and failed responses consume their existing budget charge.

## Public paths and explicit legacy calls

`benchmark.py` and the CSTR, Column, small-batch, and dynamic D-SDA wrappers explicitly pass the adopted improvement setting.
The Grid benchmark also explicitly passes the common target predicate.
Existing command-line entry points inherit those maintained defaults.
The packaged Process cases retain their existing domains and defaults, while the regression replay reads the adopted experiment's exact domains and budgets from its archive.
For example, replay uses the saved CSTR30 initialization and Column `[8..15] × [1..8]` domain with B=13, rather than substituting packaged case defaults.

Use explicit `None` settings to reproduce historical movement arithmetic and Grid target checks.

```python
from grid_dsda import dsda_from_csv, run_dsda_from_best_starting_points
from case_studies.cstr_dsda import run_cstr_dsda

legacy_descent = dsda_from_csv(
    csv_path, start_point, improvement_abs_tol=None, tol=1e-12,
)
legacy_grid = run_dsda_from_best_starting_points(
    csv_path, starting_points, target_value=target,
    improvement_abs_tol=None, target_stop=None, tol=1e-12,
)
legacy_process = run_cstr_dsda(improvement_abs_tol=None)
```

The Grid benchmark helper likewise accepts `improvement_abs_tol=None, target_stop=None` for legacy calls.
`process_dsda_fairness.py`, `small_batch_full_domain.py`, `ipopt_dfo_cstr.py`, `ipopt_dfo_non_cstr.py`, `process_followup_runner.py`, and `overnight_benchmark/worker.py` are historical campaign drivers and explicitly select legacy movement at their maintained call sites.
Their historical inputs and archived execution sources are not rewritten to use new defaults.
In particular, the Column seed-10 supplement retains its initial `1e6` penalty in the historical incumbent trace and continues to pass the unchanged trace audit.
Maintained standalone bundle builders include `dsda_protocol.py` in their source inventories, and D-SDA benchmark provenance hashes this dependency before accepting a resume.
The sealed copies under `experiments/dsda_grid_target_stop/`, the archived `workflow/` directories, ZIPs, execution-provider revisions, and all existing result trees remain byte-identical.
No maintained production path relies on runtime string replacement, module interception, or an experimental source copy.

## Solver-free regression and preservation

The full local replay compares 1,050 Grid jobs against `dsda_grid_target_stop_20261028` and 140 Process jobs against `dsda_abs1e5_rerun_20261028`.
Pairing uses `(scope, case, budget, seed)`, checks exact seed sets 0–9, and rejects missing jobs, duplicates, wrong scopes, other methods, and missing responses.
Grid response values come from a configuration-indexed table of the saved server callback responses, with repeated values checked for consistency and the full candidate domain taken from the saved CSV.
This preserves the executed binary floating-point responses without depending on different platforms' CSV parsers, and does not feed the search a predetermined callback sequence.
Process reads accepted status and objective values from the saved full lookup and returns the original `1e6` failure penalty.
The Process adapter preserves the campaign's terminal-callback convention: callback B is recorded and raises its budget exception before returning a value to the optimizer.
A read-only exception trace records the interrupted movement state; it does not patch the search function or change responses.
The maintained single-descent engine and initial-ranking helper are replayed, and separate behavioral tests exercise all four public Process wrappers.

All 1,190 pairs match in callback coordinates, objective responses, acceptance, initial order, movement paths, success, first-hit index, termination, and non-timing algorithm state.
Grid checkpoint records also match exactly, and Process terminal response delivery matches the saved oracle convention.
Measured durations and execution-environment metadata are excluded from equivalence comparisons, and no timing speedup is claimed.
Grid successes are 13, 74, 88, 98, and 101 at budgets 10, 30, 50, 70, and 100, with 37,253 callbacks in total.
Process successes are 74/140 with 2,441 callbacks.
These counts are derived from observations and checked against archived per-run records, rather than used to construct outcomes.
Import guards reject solver/model/other-method imports and Python audit hooks prohibit child processes during replay.
The final replay records zero solver calls, zero NLP calls, and zero blocked attempts.
Importing replay validation helpers does not change thread environment variables or import numerical libraries.
The replay command explicitly sets the six numerical-library thread limits to one before loading its numerical dependencies and installing the execution guard.

Run the local equivalence replay with an unused output directory.

```bash
python -m review_comparison.dsda_protocol_replay --output /tmp/dsda_protocol_53_replay
python -m pytest tests/test_dsda_protocol.py tests/test_grid_modules.py tests/test_process_dsda_domain.py tests/test_cstr_dsda_case.py tests/test_column_dsda_case.py tests/test_small_batch_dsda_case.py tests/test_dynamic_dsda_case.py tests/test_instrumentation.py tests/test_process_dsda_fairness.py tests/test_process_dsda_fairness_analysis.py tests/test_benchmark.py tests/test_case_study_benchmark.py tests/test_dsda_publication.py -q
python -m pytest tests/test_dsda_protocol_integration.py tests/test_evaluation_trace.py tests/test_trace_analysis.py tests/test_process_followup_runner.py tests/test_case_study_analysis.py -q
python -m pytest tests/ -q
```

Run the unchanged historical and publication data-only audits separately, using new output paths where shown.

```bash
python -m review_comparison.audit --output /tmp/dsda_protocol_53_audit
python -m review_comparison.dsda_publication --output /tmp/dsda_protocol_53_publication
python results/dsda_grid_target_stop_20261028/verify_publication.py
python results/dsda_abs1e5_rerun_20261028/verify.py --output /tmp/dsda_protocol_53_rerun_audit.json --paired-output /tmp/dsda_protocol_53_rerun_pairs.csv
```

The initial implementation validation included 188 passing tests and two subtests, the full 1,190-job replay, the unchanged 3,430-job historical audit, both source-archive data-only verifiers, and 12 byte-identical regenerated publication tables.
The original [verification receipt](dsda_protocol_53_verification.json) records that revision's input and maintained-source hashes and preservation checks.
The [review follow-up receipt](dsda_protocol_review_verification.json) records the integration fixes, expanded tests, repeated replay and audits, and the remaining platform limitation.
The review follow-up passes 169 targeted tests with one optional-dependency skip, and the broader suite reports 1,432 passes, 33 skips, nine passing subtests, and one pre-existing platform failure.
The remaining failure is `tests/test_cstr30_retry.py::test_timeout_stops_child_and_does_not_block_next_point`, where macOS denies the process-group `os.killpg` call with `PermissionError: [Errno 1] Operation not permitted`.
The same failure was reproduced on the unchanged PR base, and its test and production code have not been modified or bypassed.
All pre-existing result files, manifests, verification files, source evidence, manuscript files, publication figures, CI configuration, and unrelated checkout contents are preserved.
No Dantzig job, new solver run, other-method experiment, manual CI request, manuscript update, or automatic merge is performed.
