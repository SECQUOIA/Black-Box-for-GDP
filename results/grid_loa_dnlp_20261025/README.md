# Prepared SCIP/DNLP follow-up after the stopped single-option diagnostic

The user requested continuation after the original NLP export failed at GAMS compilation.
This delivery adds nlp_solver_args.mtype=dnlp while retaining solver=scip and subproblem_presolve=False.
The two-option follow-up is recorded separately from the failed single-option diagnostic.
The original equations, bounds, initialization, targets, tolerances, single-thread policy and solver time limits are retained.

The actual local GAMS 53.3 compiler reproduced error 61 for the old holder_table NLP export and accepted the same equations exported as DNLP.
All six fixed configurations then passed actual compilation-only checks using GAMS action=c, with zero optimization solver invocations.
The compiler evidence, generated models and logs are preserved under local_compile_only_53_3 and compiler_regression.
This local environment differs from Dantzig and is not represented as GAMS 52.2 or SCIP 9.2.4 execution validation.
The server launcher must first match the original Dantzig environment and pass all six compile-only checks with the existing GAMS 52.2 executable.
GAMS [documents action=c as compilation only](https://www.gams.com/52/docs/UG_GamsCall.html#GAMSAOaction).

After compilation passes, the launcher performs one SCIP/DNLP solve per fixed configuration with a 60-second limit and validates the returned variables against the original GDP.
The sequence is holder_table [3,1], [3,29], [27,1], [27,29], michalewicz [21,15] and shubert [17,22].
Only when all six gates pass are holder_table, michalewicz and shubert run with LOA once each, using the original 1,800-second limits and fresh original midpoint initialization.
No diagnostic solution is used as a full-run warm start.
The new fixed-solver cap is six and the new full-LOA cap is three.
Including the already recorded v2 GAMS compilation failure, the aggregate interface-attempt cap is seven and the aggregate fixed SCIP-invocation cap is six.
The prior failed result remains in place and is included in the new return ZIP by exact hash.

The new tests check both solver arguments at the actual GDPopt call, the unchanged ordinary NLP route, all six fixed-worker return/validation paths using synthetic solver returns, effective-configuration rejection, and compile-gate stopping before any optimization worker starts.
Synthetic test returns are not represented as actual SCIP results.
The original launcher tests continue to verify the six-fixed-plus-three-LOA scope and stop-on-first-fixed-failure behavior.
No Pyomo installation file or FBBT implementation is changed.
No earlier result, package, manuscript, Overleaf material or representative figure is overwritten.

Dantzig rejected noninteractive SSH authentication, so the assistant has not launched the new optimization experiment.
The user can run the delivered ZIP with DANTZIG_COMMANDS.txt, which includes upload, launch, tail and download commands.
New actual fixed SCIP solves and full LOA runs are both zero at preparation time.
Actual feasibility, target attainment and full LOA performance remain pending the returned server archive.
