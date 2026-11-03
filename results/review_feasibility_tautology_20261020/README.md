# CSTR15 fixed-Boolean identity preprocessing and tightened feasibility

One new local IPOPT invocation returned a point that passes the independent original-GDP residual target of `1e-8`.
The recorded A12 lower bound still exceeds that point's objective by more than the unchanged audit tolerance.
Only the fixed CSTR15 W03 case was solved, and no benchmark, RBFOpt, BAM, FMQA, sampling or annealing run was repeated.
No Dantzig connection, manuscript or Overleaf edit, figure regeneration or repository-visibility change occurred.

## Result and scope of the conclusion

| Quantity | Original W03 | Returned point |
|---|---:|---:|
| Original objective | 2.82935061823614 | 2.8293940632857546 |
| Maximum unscaled violation | 5.634494497502862e-7 | 3.3306690738754696e-16 |
| Meets original `1e-5` residual test | Yes | Yes |
| Meets the new `1e-8` residual target | No | Yes |
| Recorded A12 lower bound | 3.522552007803194 | 3.522552007803194 |
| Lower bound minus objective | 0.6932013895670543 | 0.6931579445174396 |
| Audit tolerance | 2.8293506182361402e-5 | 2.829394063285755e-5 |

The independent returned-point check sets `tightened_feasibility_passed=True` and `bound_discrepancy_persists=True`.
The largest residual is on `YP_is_cstr[12].YPD_rate_calc`.
The bounds, integrality and disjunction checks have zero maximum violation, all 32 original logical checks pass, and the complete 75-variable discrete configuration equals W03's configuration.
The independent check covers all 306 applicable original algebraic constraints, including the three identities omitted only from the computational clone.
Their individual residuals are zero.
Inactive-disjunct algebraic constraints are not incorrectly activated during validation.

The difference is compared with `1e-5 * max(1, abs(checked_original_objective))`, giving a gap-to-tolerance ratio of about `24498.459`.
The slightly higher returned objective does not replace W03 or any frozen objective/cost table.
The point is numerically feasible under the stated residual test, and the discrepancy persists for this fixed CSTR15 comparison at the tighter threshold.
This is not a proof of exact mathematical feasibility, global optimality or mathematical invalidity of the reported solver bound.
The successful local check does not identify the cause of GLOA's reported bound and does not establish a result for any other case.

## Why the three omissions preserve the fixed-configuration feasible set

The reference GDP is preserved, and `prepare_fixed_nlp` is reused without modification to construct a separate computational clone.
Only the following rows are deactivated on that clone after all three pass the exact identity checks.

| Row | Fixed expression | Exact substituted result |
|---|---|---|
| `logic_to_linear.transformed_constraints[16]` | Sum of the 15 feed Boolean binaries | `1=1` |
| `logic_to_linear.transformed_constraints[17]` | Sum of the 15 recycle-disjunct Boolean binaries | `1=1` |
| `logic_to_linear.transformed_constraints[18]` | First CSTR-disjunct Boolean binary | `1=1` |

For every related binary, the diagnostic checks its binary domain, exact value of zero or one, fixed state, associated Boolean, Boolean fixed state and consistent Boolean value.
The arithmetic is evaluated with exact rational constants, so a small nonzero constant is rejected even if floating-point addition would round it away.
An equality with a free or continuous variable, an undefined or fractional value, inconsistent Boolean metadata, or a false or merely tolerance-satisfied constant is rejected.
All candidates are verified before any row is deactivated.
Each accepted row is true for every continuous vector under this fixed discrete assignment and therefore imposes no additional restriction on the fixed-configuration feasible set.
The diagnostic does not apply a general trivial-constraint deletion routine.

[preprocessing.json](preprocessing.json) retains every constraint's name, expression and active state before and after preprocessing, all variable values, bounds and fixed states, Boolean states, objectives, and the per-variable identity proofs.
Its comparison confirms that only the three active flags change, while all remaining constraints, the objective, bounds, discrete assignment and continuous starting values are identical.
The original GDP remains unchanged and keeps the omitted conditions active for independent checking.
The metadata explicitly records that the computational active constraint sets are different.

| Representation | Free continuous variables | Active algebraic constraints | Equalities |
|---|---:|---:|---:|
| Original fixed NLP before identity removal | 156 | 306 | 158 |
| Computational NLP after identity removal | 156 | 303 | 155 |
| Actual NL file passed to IPOPT | 156 | 303 | 155 |

Both the model counts and the serialized NL counts are checked before the solver call.
NL row mappings differ by exactly the three verified names, and column mappings are identical.
The actual solver input is passed as the already-verified NL file, with its hash recorded immediately before invocation.
No hidden second model serialization or general writer presolve changes the submitted problem.
The counts alone do not establish independence of the remaining equalities or guarantee convergence.

## Single-call execution

This separately authorized allocation used exactly one new NLP invocation, distinct from the two earlier option failures and the later degrees-of-freedom failure.
The worker has a 300-second external limit that terminates the entire worker/solver process group, and there is no retry loop.
The invocation marker is created exclusively immediately before the call, and an existing marker or output directory prevents reuse.
The solver reported `status=ok`, `termination=optimal`, and 28 iterations.
That termination report is kept separate from the independent feasibility decision.
The worker wall time was `0.9313570831436664` seconds, and solver invocation plus loading and independent checking took `0.19768908293917775` seconds.
These are new diagnostic times and are not added to any historical performance comparison.
No timeout occurred.

The native [ipopt.opt](ipopt.opt) is byte-identical to the previous invocation's file.
It sets `tol=1e-10`, `constr_viol_tol=1e-10`, `acceptable_iter=0`, `bound_relax_factor=0`, `honor_original_bounds=yes`, `nlp_scaling_method=none`, `max_cpu_time=290`, and `max_iter=3000`.
The AMPL driver receives only its absolute `option_file_name`.
The internal solver tolerances do not substitute for the independent original-GDP `1e-8` check.

The saved `.sol` vector is loaded through the symbol map of the prewritten NL file only when all expected variable entries are present and finite.
Only a successfully loaded returned vector is saved as [solution.json](solution.json).
It is then restored on a freshly built original GDP, which independently reevaluates the objective, constraints, bounds, integrality, Boolean logic, disjunctions and configuration.
The computational NLP's own residual or the solver's success label cannot produce a passing assessment by itself.

## Provenance and files

The baseline repository revision is `89082bdb7102dbe9db3f78d6ce105b29f6190675`, and the pinned dsda-gdp revision remains `3e469dbeea8931670b8cd6752014ab7a767d3af5`.
The historical execution provider remains `38d917ef75ef6767c2a9f238d88be19bf0b89160`.
The already-existing Python environment is `/private/tmp/issue44-reader-env/bin/python`, with Python 3.12.13, Pyomo 6.10.0, NumPy 2.2.6 and SciPy 1.15.3.
The pinned model imports also use the existing NetworkX 3.4.2 and Matplotlib 3.10.3 installations.
The unchanged local binary is `/Users/albertlee0125/Solvers/ampl.macos64/ipopt`, reporting IPOPT 3.12.13 and ASL 20211109.
Its SHA256 is `40a19ebcfe47d646e8f5696102ffd7363559b2698c10b270bb8e6f981a30e145`.
No packages or solver versions were installed or replaced.

- [selection.json](selection.json): fixed input IDs, source hashes, criteria, limits, environment and baseline revision.
- [before_solution.json](before_solution.json) and [before_residuals.json](before_residuals.json): original W03 restoration and independent check.
- [preprocessing.json](preprocessing.json), [structural_summary.json](structural_summary.json), and [nl_comparison.json](nl_comparison.json): exact proofs and before/after inventories.
- [nl_before](nl_before/), [nl_after](nl_after/), and [solver_input](solver_input/): NL/row/column files and the actual returned `.sol` file.
- [worker.log](worker.log), [ipopt.log](ipopt.log), [worker_result.json](worker_result.json), [execution.json](execution.json), and [solver_call.json](solver_call.json): complete logs, raw status, timing and the one-call ledger.
- [solution.json](solution.json) and [residuals.json](residuals.json): the actual new vector and original-GDP validation.
- [before_after.csv](before_after.csv) and [summary.json](summary.json): comparison and distinct feasibility/discrepancy flags.
- [execution_sources](execution_sources/) and [manifest.json](manifest.json): executed source snapshots and input/source/output SHA256 records.
- [validation](validation/): solver-free tests, rechecks, prior-audit replay and preservation evidence.

The executed source snapshot remains unchanged after the call.
The final verification code additionally supports relocating the prior input directory through `--input` and cross-checks summary fields and the saved original vector.
These replay-only changes are separately hashed in the manifest and did not change any executed preprocessing, solver options, candidate, or validation calculation.
All earlier result directories and their source snapshots, including the failed calls, remain unchanged.

## Validation outcomes

The related solver-free test selection passed all 84 tests, with 14 existing Matplotlib/Pyparsing deprecation warnings.
The tests cover exact Boolean identity recognition, false and tolerance-only rows, unchanged original models, incomplete returned vectors, original-GDP checking of omitted conditions, metadata disagreement, one-call limits and overwrite refusal.
Ruff passed for the new module and tests.
The previous feasibility-follow-up verifier passed unchanged.
The existing review-comparison audit validated 3,430 retained runs and 170,660 callbacks and reproduced all eight checked analysis outputs byte for byte.
All 1,821 pre-existing tracked files other than the intentionally updated status document retain their baseline SHA256 values.
The original sources fixed by earlier verifiers, historical data, failed diagnostic records, manuscript files and figures are included in that preservation check.
No validation test or audit invoked a real NLP solver, trained an FM, or ran annealing.

## Recheck saved results without optimization

Use an existing compatible Python environment with the pinned GDP submodule present.
The following command checks hashes and reconstructs original-GDP residuals without constructing or invoking a solver.
Its output path must be new.
The optional `--input` supplies the prior result directory when the repository is in another filesystem location.

```bash
GDP_PYTHON=/private/tmp/issue44-reader-env/bin/python
export MPLCONFIGDIR=/private/tmp/review-comparison-mpl
"$GDP_PYTHON" -m review_diagnostics.feasibility_tautology verify \
  --input results/review_feasibility_followup_20261020 \
  --directory results/review_feasibility_tautology_20261020 \
  --output /tmp/cstr15_tautology_recheck.json
"$GDP_PYTHON" -m pytest -q \
  tests/test_review_feasibility_tautology.py \
  tests/test_review_feasibility_followup.py \
  tests/test_review_diagnostics_feasibility.py
```

The exact compute command for the retained single-call allocation was the following.
The existing output directory is deliberately refused, and the consumed allocation does not authorize another automatic solve.
Independent reproduction would require a new output directory and a separately authorized call.

```bash
MPLCONFIGDIR=/private/tmp/review-comparison-mpl \
/private/tmp/issue44-reader-env/bin/python \
  -m review_diagnostics.feasibility_tautology run \
  --input results/review_feasibility_followup_20261020 \
  --directory results/review_feasibility_tautology_20261020 \
  --ipopt /Users/albertlee0125/Solvers/ampl.macos64/ipopt
```
