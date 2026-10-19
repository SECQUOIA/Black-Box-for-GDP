# Uniform bound-consistency audit

The replay based on main revision `44b8a8b21a00f95f25683d5f71ec98a95adf877f`
applies the existing strict comparison to every method with a reported lower
bound and an available feasible witness for the same instance:

```text
reported_lower_bound > best_saved_feasible_objective
                       + 1e-5 * max(1, abs(best_saved_feasible_objective))
```

Missing bounds or witnesses remain non-conflicts. This does not establish that
a missing bound is valid. The current replay independently checks the saved
vectors in the original GDP models without invoking a solver.

## Changes and preserved evidence

- CSTR 5, 10, 15, 20, 25 and 30 GLOA conflict flags change from False to True.
- The existing five Big-M/Hull conflicts remain unchanged: 11 conflicts total.
- `solver_reported_global_optimality_certified` preserves the raw report.
  The analysis field `global_optimality_certified` excludes conflicting bounds.
  Both fields were already False for the six GLOA records, so their actual
  certification values do not change.
- The comparison and baseline CSVs, audit conflict list, report/figure markers,
  source-level reports and combined GDP/DFO performance summary are refreshed.
  The combined summary's six GLOA `bound_conflicts` counts change from 0 to 1.
- All other comparison fields are unchanged, including objective, completion
  time, target match/attainment, solver termination, reported bounds and row
  order. Selection and all original archives are unchanged.
- All 45 selected jobs and 63 saved vectors are retained. The maximum rechecked
  primal violation is 8.947372728933256e-7. Target attainment counts remain
  RIC=3, GLOA=1, LOA=4, Big-M=7, Hull=6.

[Machine-readable verification](bound_consistency_verification.json) records
field differences and preserved archive hashes. Of 1,003 previously tracked
result files, 991 are byte-identical; the 12 changed files are derived reports,
figures and manifests. The official replay also retains source-level audits in
`analysis/sources/`. Historical `validation.json`, execution revisions, raw
solutions and logs remain unchanged. Updated analysis code hashes identify the
replay implementation, not a new experimental run.

## Reproduce without optimization

Use the repository's existing analysis environment and pinned model submodules:

```bash
python gdp_current_analysis.py
python -m scripts.plot_dantzig_performance --gdp-only
python -m pytest tests/test_nlp_cost_analysis.py tests/test_gdp_current_analysis.py tests/test_dantzig_performance.py -q
```

The GDP-only refresh verifies the existing performance artifacts first, updates
only the two GDP-derived tables and their combined figure, and records scoped
producer hashes. Unrelated DFO figures and historical producer hashes are
preserved. The integration test prohibits solver calls while replaying saved
vectors. Validation: **86 tests passed**; Ruff and `git diff --check` passed.
No optimization/NLP experiment or manuscript edit was performed.
