Feasibility and bound consistency of the algebraic results

Repository snapshot of main: cb70771b2037301bb6d0e38a2362d49b53fcda7d (accessed October 19, 2026).

The 45 selected runs are in table8_bound_audit.csv; nine saved feasible comparison solutions are in feasible_witnesses.csv. Join on witness_id. The files provide unrounded reported and reevaluated objectives, reported lower bounds, original-model maximum violations, comparator objectives and violations, tolerance, discrepancy, normalized discrepancy, and bound-consistency classification. Missing lower bounds are blank.

Rule: tau = 1e-5 * max(1,abs(witness_recorded_objective)); rho = (reported_lower_bound - witness_recorded_objective)/tau; conflict iff rho > 1. All methods use the same rule. Eleven runs satisfy the conflict criterion. The check concerns consistency with a saved numerically feasible solution, not a proof of exact feasibility or global optimality.

Each row supplies original archive/member paths, local paths and SHA-256 hashes for the saved result and solution. raw/ contains 63 archived result objects and 63 solution vectors. solution_rechecks.json gives their evaluations in the original GDP: active constraints, variable bounds, integrality, selected disjunctions, and logical validity. The largest unscaled violation is 8.947372728933256e-7; all pass the 1e-5 feasibility threshold.

repository_comparison.csv contains the selected-run results from the cited snapshot; repository_validation.json contains validation metadata. Solver-reported certification is retained separately from the consistency-filtered eligibility field. Neither field is an independent mathematical proof.

Reproduction: initialize the pinned submodules, install the repository requirements, and run:
  python gdp_current_analysis.py --output /path/to/new-validation-directory
This checks saved vectors without running an optimizer. Original execution revisions and archive hashes are specified in the manifests. SHA256SUMS covers this directory except itself.
