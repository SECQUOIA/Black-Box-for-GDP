# CSTR15: Dantzig GAMS/IPOPT versus retained local check

The returned Dantzig point passes the original-GDP 1e-8 numerical feasibility test.
The original ZIP is retained unchanged as [the return archive](../archives/review_cstr15_dantzig_20261021_161412_30959_return_1792599258428957007.zip) with its adjacent SHA256 file.
All raw inputs, logs, listing, solution vectors, preflight files, historical execution sources and the server verification report remain inside that archive.
The single server NLP call used execution revision `70bf17ca95e5ee1b98069e494c22fcafd6398960`; this import and analysis performed zero NLP calls.
The starting point and all 75 discrete values match the retained original W03 configuration.

| Record | Objective | Maximum unscaled violation | Passes 1e-8 | IPOPT iterations |
|---|---:|---:|---|---:|
| original_W03 | 2.82935061823614 | 5.634494497502862e-07 | False | not applicable |
| retained_local_AMPL_IPOPT | 2.8293940632857546 | 3.3306690738754696e-16 | True | 28 |
| Dantzig_GAMS_IPOPT | 2.8293940632857595 | 1.1102230246251565e-16 | True | 8 |

Dantzig minus local objective is `4.884981308350689e-15`.
Across the 231 saved variable values, the largest absolute difference is `2.416775557456674e-09` at `F[B,12]`.
The two objectives differ only at floating-point roundoff scale; the smaller residual is not evidence of a mathematically better solution.

## Retained lower bounds

For GLOA A12, lower bound `3.522552007803194`, delta `0.6931579445174347`, tau `2.8293940632857597e-05` and rho `24498.458999114257` retain the rho > 1 discrepancy.
For Hull A15, lower bound `2.829394077848967`, delta `1.456320752879492e-08`, tau `2.8293940632857597e-05` and rho `0.0005147111785440996` are within the audit tolerance.
Both tightened points yield the same two classifications, while the original W03 point itself does not pass the tighter 1e-8 test.
The full original/local/Dantzig comparisons are generated in [comparison.csv](comparison.csv) and [bound_comparison.csv](bound_comparison.csv).
These records do not establish exact mathematical feasibility, global optimality or the cause of the GLOA lower-bound discrepancy.

## Environment and equation-count differences

Dantzig used GAMS 52.2.0, IPOPT 3.14.19 and MUMPS 5.8.1 with Python 3.11.16 and Pyomo 6.10.0.
The retained macOS run used the AMPL interface and IPOPT 3.12.13 with MUMPS; its log does not identify the MUMPS version.
Both runs use the original W03 start, the same numerical tolerances and the same three proved identity removals.
Dantzig explicitly requests MUMPS and no dual warm start, while the local option file leaves those two options implicit; all raw options are preserved in analysis.json.
The local run uses max_cpu_time=290, while GAMS uses reslim=290; both outer worker limits are 300 seconds.
The computational clone has 156 free continuous variables and 303 constraints, including 155 equalities.
The GAMS input has 304 equation blocks including the objective; its listing reports 156 generated equations including that objective.
All 148 remaining inequalities are satisfied constant expressions after discrete fixing, proved exactly as 1 >= 1 or 2 >= 1 in [constant_inequalities.json](constant_inequalities.json).
Their count exactly accounts for the GAMS equation reduction; IPOPT receives 155 equalities and no inequalities after objective substitution.
The earlier AMPL/NL export retained those 148 inequalities, so it is not the identical solver-level representation even though the fixed original GDP and independently checked constraints agree.
The retained outer worker times are local `0.9313570831436664` seconds and Dantzig `0.7647965078940615` seconds.
The inner timing scopes differ: local solve_and_check includes residual validation, while the GAMS worker timing covers its process launch and completion.
The 28 versus 8 iterations and these diagnostic times do not isolate an effect of the solver version, interface or constant-row treatment.
No diagnostic time is added to existing benchmark cost or performance tables.

## Independent replay and floating-point metadata

The original unmodified full-summary verifier passed in this analysis environment: `False`.
Its recorded error, if any, is `Saved summary disagrees with independent replay`.
The server verification report remains unchanged and records its successful server-side replay.
The separate analysis verifier checks the same archived hashes, execution sources, model proofs and actual vector, then compares every original-GDP residual and configuration field with the existing 1e-12 replay comparator.
Each bound ratio is checked exactly from its own recorded objective, and each largest-residual ranking is checked exactly against its own full residual rows.
The local re-evaluation changes the Dantzig objective by floating-point roundoff; dividing the small Hull gap by tau amplifies that difference in rho, and near-zero residual rankings can also change.
These derived differences and both rankings are exposed in [verification.json](verification.json), rather than replacing the server summary or weakening the original verifier.
The original 1e-8 feasibility criterion and both bound classifications are unchanged.

## Reproduce without a solver

```bash
git submodule update --init external/dsda-gdp
python -m review_diagnostics.cstr15_gams_analysis --output /path/to/new/analysis
```

Use the repository GDP dependencies with Pyomo 6.10.0; neither GAMS nor IPOPT is needed for this command.
The command checks the ZIP and its complete return manifest, extracts into a temporary directory and regenerates the comparisons and verification reports.
Use a new output directory; original outputs and source revisions are never overwritten.

## Draft reviewer wording

An additional single-call CSTR15 check in the archived Dantzig GAMS/IPOPT environment returned objective 2.8293940632857595 with maximum unscaled original-GDP violation 1.1102230246251565e-16, satisfying the 1e-8 numerical test.
The objective differed from the retained local AMPL/IPOPT result by 4.884981308350689e-15, with the same discrete configuration.
The retained GLOA lower-bound discrepancy persisted, whereas the Hull difference was within the audit tolerance.
This is fixed-configuration numerical evidence and does not establish exact feasibility, global optimality or the source of the lower-bound discrepancy.
These sentences are a draft only; this task did not edit the manuscript, Overleaf, figures or historical performance records.

## Validation

See the [validation report](../../docs/validation/cstr15_dantzig_results_20261021.json) for the solver-free tests, deterministic CSV replay and preservation checks.
The targeted test command is `python -m pytest tests/test_cstr15_gams_analysis.py tests/test_cstr15_gams.py tests/test_review_diagnostics_feasibility.py tests/test_review_feasibility_followup.py tests/test_review_feasibility_tautology.py -q`.
