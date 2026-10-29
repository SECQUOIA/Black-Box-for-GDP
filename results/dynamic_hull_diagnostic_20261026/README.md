# Dynamic Hull lower-bound diagnostic

The better saved Big-M point passes the original GDP, reconstructed Hull, and archived Hull GAMS algebra checks at the unchanged absolute feasibility tolerance of `1e-5`.
The Hull lower bound exceeds that accepted point's objective by `15.077604109427995`, so the recorded `optimal` termination is not accepted as a global optimality certificate for the original GDP.
This audit identifies a bound inconsistency but does not establish its internal numerical or software cause.

## Scope and preservation

The remote `review/cstr15-dantzig-results` head was checked as `ed40a19c33725e0ee8c5403e66768eb6b27072b2`, matching the requested review revision.
The main workspace was on `main` and contained the existing untracked `results/runners/process_scip_four_20261026/` directory.
To preserve that workspace, this diagnostic uses the clean detached worktree `/private/tmp/process-scip-four-20261026` at the review revision.
Only this new diagnostic directory is written, and all 2,493 pre-existing tracked files retain their before/after SHA256 hashes.
The diagnostic and its reproductions make zero solver or GAMS calls, including compilation, and install or upgrade no dependencies.
The subsequent user-authorized publication includes this diagnostic in PR #52 without merging main or manually requesting CI.
Other process cases, GDPopt methods, manuscript sources, Overleaf material, figures, and existing result tables are unchanged.

## Model identity and original checks

Both jobs preserve the same source revision `482e14ebf9caabbd35d959986942cb028778a1d7` of `SECQUOIA/LD-SDA-Dynamic` and the same SHA256 for `models/nine_stage_dynamic_model_switching_nonlinear.py`.
Both use `build_model(mode_transfer=False)`, constructor-default initialization, and the same unsolved template preparation identifier `4d0d08747be049369a3ea71ce132cb98`.
The frozen preparation applies Radau collocation with `nfe=30` and `ncp=3`, reconstructs the disjunct constraints on that mesh, and sets derivative bounds to `[-300,300]`.
The original state bounds are `[0,10]`, control bounds are `[-4,4]`, and the objective minimizes the negative sum of the nine discretized squared-state integrals.
The globally active FBBT pass changes 267 variable bounds identically in both jobs, and the diagnostic reproduces the complete recorded before/after bound map exactly.
The frozen execution clones the unsolved template separately for each method and applies `core.logical_to_linear` followed by `gdp.bigm` or `gdp.hull` without keyword overrides.
The original objective expression, direction, original-variable bounds, domains, fixed flags, and initialization values remain identical after either transformation.
The network wrapper only retries transport failures within the existing deadline and installs no Grid or FBBT patch in these Process jobs.
Each Dynamic job records one returned SCIP MINLP call and no transport retry.

| Saved vector | Recomputed original objective | Maximum bound violation | Maximum active algebraic violation | Integrality / fixed values / XOR violations | Result |
|---|---:|---:|---:|---:|---|
| Big-M | -212.00879089175004 | 9.999544481331668e-8 | 9.691267788269897e-9 | 0 / 0 / 0 | Pass |
| Hull | -196.93118677234045 | 9.999944516891901e-8 | 2.916639152417133e-12 | 0 / 0 / 0 | Pass |

For each vector, all 1,674 original variables, 27 integer variables, 1,725 active algebraic constraints, 31 logical constraints, and nine disjunctions are checked with no missing values.
The worst original bound is `x9[9]` for both vectors.
The worst Big-M active constraint is `stage_mode[9,3].mode3_dynamic_constraint[8.988165]`.
The worst Hull active constraint is `stage_mode[1,1].mode1_dynamic_constraint[0.605168]`.
The selected modes for stages 1 through 9 are `[1,2,2,2,3,3,3,3,3]` for Big-M and `[1,2,2,2,2,2,3,3,3]` for Hull, and both satisfy all original logic.
Repeating the original-GDP checks with the recorded tightened execution bounds gives the same acceptance conclusions.
The local Hull objective differs from the stored `-196.93118677234048` by only `2.842170943040401e-14` from floating-point evaluation.

## Big-M witness in Hull

Pyomo 6.10.0's default Hull options are `perspective function=FurmanSawayaGrossmann`, `EPS=0.0001`, and `assume_fixed_vars_permanent=False`.
The diagnostic constructs every disaggregated value using the transformation's source/copy maps and the selected indicators, with a branch copy equal to `y_d*x`.
The implementation also handles shared complementary copies by summing the indicators mapped to that copy, although this Dynamic instance has no such complementary copies.
All 4,941 auxiliary variables are assigned from their definitions, with no missing auxiliaries, clipping, or optimization.
The resulting Big-M witness satisfies all 12,447 active Pyomo Hull constraints and all variable bounds and integrality requirements at `1e-5`.
Its maximum Hull constraint violation is `9.999544481331668e-8` at `_pyomo_gdp_hull_reformulation.relaxedDisjuncts[26].'x9[9]_bounds'[ub]`.
The same lift applied to the saved Hull vector is a positive control and also passes.

The regenerated unsolved Hull GAMS export is byte-identical to the archived server preflight file, with SHA256 `bdb5cedb6e4b8753db1dab3828af4afb84655670dc0455c6243bed337cac58b6`.
A separate arithmetic parser evaluates the archived GAMS text directly, including its 12,448 equations, 6,613 declared variables, 24 binary variables, and 9,901 bound assignments.
The Big-M witness passes this check with maximum equation and bound violations of `9.999544481331668e-8`, and its exported objective-defining equation has zero residual.
These equation and variable counts agree with the actual Hull solve's GAMS statistics.
The extra GAMS equation and variable define the objective, while three fixed original indicators are substituted out of the export.
The regenerated Big-M export differs from its archived preflight in exactly three computed M literals, each by `5.684341886080802e-14`, and the differing lines are retained in `diagnostic.json`.
The Hull export and all recorded template bound tightenings match exactly, so the Big-M export rounding differences do not affect the saved-vector Hull check.

## Log evidence and remaining uncertainty

| Actual SCIP log | Big-M | Hull |
|---|---:|---:|
| Termination | time limit reached | optimal solution found |
| Primal bound | -212.008790901637 | -196.931186782322 |
| Dual bound | -795.447866072757 | -196.931186782322 |
| Reported gap | 275.20% | 0.00% |
| GAMS MODELSTAT / SOLVESTAT | 8 / 3 | 1 / 1 |

The Hull journal preserves lower bound `-196.93118678232204` and upper bound `-196.93118677234048` from the same invocation.
The tiny approximately `1e-8` primal-bound versus recomputed-objective differences are preserved and do not explain the `15.077604109427995` cross-method inconsistency.
The GAMS export explicitly minimizes the same negative objective without normalization, additional scaling, or offset, and contains no explicit `.scale` or `.scaleopt` assignment.
Both execution logs and the extracted results agree on the lower bounds, excluding a simple sign, scale, or report-copying error as an explanation of this discrepancy.
Hull reports 5,839 bound tightenings during presolve, but the log does not identify the affected variable bounds or their reasons.
At the sole processed root node, the reported dual bound moves from about `-783.6048` at 917 seconds to the incumbent `-196.9312` at 918 seconds, after which SCIP reports optimality.
This locates the reported certificate closure in the solver log but does not prove that presolve, a cut, numerical tolerance, or SCIP itself is the root cause.

The archived GAMS file is the preflight export generated from the same template and transformation path, rather than the deleted solve-time temporary file.
The solve wrapper adds the recorded time, thread, gap, option-file, and result-output settings, with `warmstart=False` and `gams/mipstart=0`.
The preserved solve counts and bound ranges agree with that export, but the exact compiled solve-time model, complete transformed returned vector, presolved bounds, cut pool, and reasons for root closure are unavailable.
Therefore the archived evidence supports a feasible Hull witness and an inconsistent reported certificate, while it cannot conclusively separate GAMS translation/interface effects from internal solver or numerical effects.
No additional solver execution is necessary for the present decision to withhold the global certificate, and none is performed.

## Reproduction and artifacts

Run from a repository checkout containing the baseline revision and this diagnostic with the already-installed local Python environment.
The script accepts a descendant of the baseline revision and checks the same 2,493 baseline files before and after evaluation, so committing the diagnostic does not invalidate reproduction.

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/albertlee0125/Repos/RBFopt_Test/.venv-trace-bam5/bin/python results/dynamic_hull_diagnostic_20261026/diagnose.py
```

The existing `frozen_models`, `verify_solution`, and archive integrity routines are reused, with optimizer construction and external subprocess creation blocked during model evaluation.
The actual solve environment was Dantzig with GAMS 52.2.0, SCIP 9.2.4, Python 3.11.16, Pyomo 6.10.0, and the recorded single-thread settings.
This diagnostic uses local Python 3.13.12 and Pyomo 6.10.0 only for symbolic transformation and arithmetic evaluation, without claiming to reproduce the solver environment.
`diagnostic.json` contains detailed residuals, selected disjuncts, preserved log excerpts with line numbers, model checks, and export comparisons.
`bigm_hull_auxiliary_values.csv` records every auxiliary assignment and the indicator/source rule used to construct it.
`manifest.json` records input and output hashes, frozen source and package hashes, environments, transformation defaults, and reproduction commands.
`preserved_files.json` records the verified unchanged pre-existing tracked files.

## Manuscript-safe wording

A saved Big-M point with objective -212.008790892 satisfies the original Dynamic GDP and reconstructed Hull formulation at the 1e-5 feasibility tolerance, despite lying below the Hull run's reported lower bound of -196.931186782.
We therefore do not treat the Hull run's reported optimal termination as a global optimality certificate; the cause of the inconsistent bound remains unresolved.
