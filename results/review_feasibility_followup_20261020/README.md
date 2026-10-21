# CSTR15 tightened-feasibility follow-up

The follow-up is incomplete because the single new IPOPT invocation returned no solution.
Native option-file delivery now works, but IPOPT 3.12.13 stopped with `TOO_FEW_DOF` before optimization iterations.
The controller stopped immediately and did not use the second permitted call.
No Dantzig connection, installation, solver replacement, benchmark rerun, FMQA fit or annealing call occurred.
The manuscript and Overleaf were not modified.

## Fixed target and preservation

The target remains CSTR15 GLOA audit A12 and the original LOA witness W03.
[selection.json](selection.json) freezes the target, input hashes, execution-source hashes, residual targets and new two-call allocation before either solver invocation or candidate generation.
The baseline repository revision is `6c0228e81b73a0a7bd78edc1b4068b7957889af0`.
The pinned dsda-gdp model revision is `3e469dbeea8931670b8cd6752014ab7a767d3af5`.
The model, initialization and serializer hashes match the original execution archive.
The historical execution provider remains `38d917ef75ef6767c2a9f238d88be19bf0b89160`.
The repository commit publishing this follow-up is distinct from all historical execution revisions.
The [previous two option-rejected calls](../review_diagnostics_20261020/feasibility/interpretation.json) remain unchanged and do not count toward this separate allocation.

## Results

| Record | Returned point | Objective | Maximum unscaled violation | Residual criterion | Result |
|---|---|---:|---:|---:|---|
| Original W03 | Original saved witness | 2.82935061823614 | 5.634494497502862e-7 | 1e-5 | Passes original independent check |
| Follow-up attempt 1 | No | Not available | Not available | 1e-8 | IPOPT `TOO_FEW_DOF` |
| Follow-up attempt 2 | Not run | Not available | Not available | 1e-10, conditional | No returned point from attempt 1, so retry prohibited |

The original W03 objective, residual, variable bounds, integrality, disjunction and logical conditions were independently reproduced before the new invocation.
W03 is numerically feasible under the stated residual test of `1e-5`, but its retained violation exceeds `1e-8`.
The original A12 lower bound remains `3.522552007803194`.
Its difference from W03 is `0.6932013895670543`, compared with the unchanged audit threshold `1e-5 * max(1, abs(objective)) = 2.8293506182361402e-5`.
No new point exists for evaluating that comparison at the tighter residual threshold.
Accordingly, `tightened_feasibility_passed` is false and `bound_discrepancy_persists` is null, meaning unestablished for a new tightly checked point rather than a resolved discrepancy.
The failure does not establish mathematical infeasibility, global optimality or mathematical invalidity of the reported bound.

## Option delivery and structural obstruction

The [actual options file](feasibility/attempt_1/ipopt.opt) contains solver `tol` and `constr_viol_tol` of `1e-10`, `acceptable_iter 0`, `bound_relax_factor 0`, `honor_original_bounds yes`, `nlp_scaling_method none`, `max_cpu_time 290` and `max_iter 3000`.
Only its absolute `option_file_name` was passed through the AMPL command line.
The [IPOPT log](feasibility/attempt_1/ipopt.log) confirms that the file was read and contains no unsupported-option rejection.
The solver's internal tolerances are separate from the independently checked original-GDP target of `1e-8`.
The actual solver-call wall time was about `0.045300` seconds, and the worker wall time was about `0.673010` seconds.
The external watchdog limited the worker and its entire process group to 300 seconds; no timeout occurred.

The [model equivalence check](model_equivalence.json) confirms unchanged objective, variable bounds, continuous starting values and fixing, and the complete 306-row active algebraic constraint set.
Only the 75 discrete variables were fixed, leaving 156 continuous variables free.
The independently serialized [NL header](structure/fixed_nlp.nl) contains 156 variables and 158 equalities, consistent with the solver's degrees-of-freedom failure.
Three equalities, `logic_to_linear.transformed_constraints[16]`, `[17]` and `[18]`, contain only fixed Boolean values and evaluate to `1=1`.
The remaining 155 equalities contain free variables.
These satisfied logical rows were retained because the requested procedure preserves the full active constraint set.
No constraint was removed, no bound was relaxed, and the objective was not changed to bypass the error.
The count diagnoses the interface obstruction but does not prove that the remaining equations are independent or that a revised serialization would converge.
Any follow-up should first review an equivalent treatment of satisfied fixed-logic rows during serialization while retaining all original-GDP checks, then obtain separate authorization for a new solver call.

## Environment and artifacts

The requested repository `.venv` is Python 3.13.12 with Pyomo 6.10.0 but lacks the pinned model's `networkx` import.
Its solver-free preflight produced two passed tests and four setup errors, before any NLP invocation.
The already-existing `/private/tmp/issue44-reader-env/bin/python` environment was therefore used without installing packages.
It contains Python 3.12.13, Pyomo 6.10.0, NetworkX 3.4.2, NumPy 2.2.6, SciPy 1.15.3 and Matplotlib 3.10.3.
The unchanged solver is `/Users/albertlee0125/Solvers/ampl.macos64/ipopt`, reporting IPOPT 3.12.13 and ASL 20211109.
Its binary SHA256 is recorded in selection.json and the solver-call ledger.

- [before_after.csv](before_after.csv): original witness and new-attempt assessment, with missing returned quantities left empty.
- [before_solution.json](before_solution.json) and [before_residuals.json](before_residuals.json): the restored original vector and independent GDP checks.
- [summary.json](summary.json) and [interpretation.json](interpretation.json): distinct feasibility and discrepancy conclusions, allocation usage and failure explanation.
- [attempt_1](feasibility/attempt_1/): actual options, full worker and solver logs, solver return metadata, timing and call ledger.
- [unreturned_state.json](feasibility/attempt_1/unreturned_state.json): unchanged W03 state after the failed call, explicitly not a polished solution.
- [structure](structure/): equality inventory and solver-free NL serialization explaining the count mismatch.
- [execution_sources](execution_sources/): exact source snapshots used for the follow-up.
- [manifest.json](manifest.json): output SHA256 inventory and replay command.
- [reviewer_reply.md](reviewer_reply.md) and [manuscript_wording.md](manuscript_wording.md): proposed English text, not applied to the manuscript.

The worker's raw result.json and residuals.json describe the unchanged in-memory W03 state when `solution_loaded` is false.
The follow-up comparison deliberately reports no returned objective or returned residual in that situation.

## Validation outcomes

The solver-free related test selection passed all 65 tests, including option-file transport, independent residual gating, discrete configuration preservation, stop-after-success/error behavior and the two-call maximum.
The 14 reported warnings are existing Matplotlib/Pyparsing deprecations.
Ruff passed for the new driver, tests and structural replay script.
The existing review-comparison audit replay validated 3,430 runs and 170,660 callbacks and reproduced its eight checked analysis outputs byte for byte.
All 1,776 pre-existing tracked files other than the intentionally updated status document retain their baseline SHA256 values, including the previous failed diagnostics, FMQA-uniform analysis and manuscript files.
The structural replay produced byte-identical counts, equation inventory and NL/row/column files without invoking a solver.
The saved-result verifier rebuilt the original GDP and rechecked W03 without fitting, annealing or optimization.
Detailed test logs, the existing audit result and the preservation inventory are retained in [validation](validation/).

## Recheck without optimization

Use an existing Python environment with the versions above and initialized pinned GDP submodules.
The commands below rebuild the model and read saved data but never invoke an NLP solver.
Output paths must not already exist.

```bash
GDP_PYTHON=/private/tmp/issue44-reader-env/bin/python
export MPLCONFIGDIR=/private/tmp/review-comparison-mpl
"$GDP_PYTHON" -m review_diagnostics.feasibility_followup verify \
  --directory results/review_feasibility_followup_20261020 \
  --output /tmp/cstr15_followup_recheck.json
PYTHONPATH="$PWD" "$GDP_PYTHON" \
  results/review_feasibility_followup_20261020/structure/reproduce.py \
  --directory results/review_feasibility_followup_20261020 \
  --output /tmp/cstr15_followup_structure
"$GDP_PYTHON" -m pytest -q \
  tests/test_review_feasibility_followup.py \
  tests/test_review_diagnostics_feasibility.py
```

The recorded compute command was the following, with a new directory and this task's separate authorization.
Do not repeat it automatically after the no-solution stop condition.

```bash
MPLCONFIGDIR=/private/tmp/review-comparison-mpl \
/private/tmp/issue44-reader-env/bin/python \
  -m review_diagnostics.feasibility_followup run \
  --directory results/review_feasibility_followup_20261020 \
  --ipopt /Users/albertlee0125/Solvers/ampl.macos64/ipopt
```

The retained directory is intentionally refused by a repeated compute command, protecting the recorded attempt from overwrite or duplicate invocation.
