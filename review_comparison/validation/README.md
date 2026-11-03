# Local preparation validation (not Dantzig experiment completion)

`report.json` is the machine-readable validation summary.

- New regression tests: 16 passed in the existing Python 3.12 analysis environment.
- Related original tests: 61 passed, two skipped because that environment has no
  RBFOpt. Both skipped initialization tests passed separately in the existing
  local RBFOpt 4.3.0 environment: 63 related tests passed in total.
- Ruff and `bash -n run_review_comparison_dantzig.sh` passed.
- An actual local RBFOpt 4.3.0 genetic Ackley B10/seed0 search completed with ten
  callbacks. `local_smoke.zip` retains the original log, actual settings,
  callbacks, source snapshots, and local Python/library/solver-path provenance.
  This diagnostic uses Mac solver binaries and different Python/NumPy versions;
  it is not a formal Dantzig result and must not enter comparative timings.
- `historical_analysis.zip` contains completed-data analysis only: all 4,760
  retained runs, conditional alpha scenarios, paired historical comparisons,
  Grid exclusion analyses, and a draft Process attainment figure. All 3,430 new
  slots remain explicitly `not_run`. The code that generated this ZIP is hashed
  in `report.json`.
- The full 20,181-point Grid and 2,455-point Process inventories have no missing
  costs. The original Process selection remains 560 runs, 291 hits, 268 misses
  and one execution failure; corrected BAM supplies 140 runs / 3,430 callbacks.

Commands executed from the source checkout:

```bash
python -m pytest tests/test_review_comparison.py -q
python -m pytest tests/test_grid_trace_runner.py tests/test_final_process_artifacts.py tests/test_ipopt_dfo_cstr.py tests/test_ipopt_dfo_non_cstr.py -q
python -m pytest tests/test_ipopt_dfo_cstr.py::test_actual_rbfopt_initial_callbacks_no_auxiliary_solve tests/test_ipopt_dfo_non_cstr.py::test_actual_rbfopt_initial_callbacks_no_auxiliary_solve -q
python -m ruff check review_comparison tests/test_review_comparison.py
bash -n run_review_comparison_dantzig.sh
```

On an extracted package, `python -m pytest tests/test_review_comparison.py -q`
reuses the included frozen inputs instead of rebuilding from repository ZIPs.
The tests run ordinary sampling callbacks and mocks; they do not run licensed
optimizers. No original process NLP, enumeration, FMQA or BAM rerun occurred.
Dantzig preflight, pilot and elapsed-time estimates remain pending operator
execution; no SSH connection or remote batch was started during preparation.
