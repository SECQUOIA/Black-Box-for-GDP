# LOA follow-up with presolve disabled and SCIP/DNLP export

This is a separate follow-up after the user requested continuation of the stopped diagnostic.
It explicitly combines subproblem_presolve=False with nlp_solver_args.mtype=dnlp while retaining solver=scip.
It must not be described as evidence from the earlier single-option experiment.
The previous v2 return made one GAMS interface call, zero SCIP invocations and zero full LOA runs.
That stopped return and its original source remain unchanged.

The new follow-up covers only holder_table, michalewicz and shubert with LOA.
The original equations, bounds, grids, normalization, reference targets, initialization and 1e-5 acceptance/target tolerance remain unchanged.
The additional export-type option is conditional on this separate diagnostic configuration, so ordinary callers still use the original NLP route.
The original mip_presolve=True setting and network retry handling remain unchanged.
No installed Pyomo or FBBT source is patched.

The launcher first verifies the exact v2 stopped archive and the original Dantzig environment.
It then exports all six fixed configurations and invokes the actual GAMS compiler with action=c and a 30-second timeout for each compilation.
GAMS [documents action=c as compilation only](https://www.gams.com/52/docs/UG_GamsCall.html#GAMSAOaction), so these checks do not execute an optimization solver.
The generated GAMS files, compiler logs, return codes, versions and hashes are retained.
A compilation failure stops before any new optimization call.
Local GAMS 53.3 compilation evidence is labeled separately and is not substituted for the server GAMS 52.2 execution environment.

After all compilations pass, the six original fixed configurations are solved once each with SCIP/DNLP and at most 60 seconds per configuration.
The sequence is holder_table [3,1], [3,29], [27,1], [27,29], michalewicz [21,15] and shubert [17,22].
Each configuration starts from a fresh model through the original construction path.
One failed fixed validation stops the sequence without replacing the failed result or retrying the whole job.
Only after all six fixed validations pass are the three full LOA runs started, once each with the original 1,800-second deadlines and fresh midpoint initialization.
The fixed diagnostic solutions are never passed into the full runs.
Both actual GDPopt options and actual solver-call kinds are recorded, and an effective configuration without SCIP/DNLP is rejected.

The new limits are six fixed solver calls and three full LOA runs.
Including the prior compile failure, the aggregate interface-attempt cap is seven and the aggregate confirmed fixed SCIP-call cap is six.
The new output root is results/grid_loa_dnlp_20261025 and the exclusive claim prevents a second invocation.
The previous result directory, execution claim and all historical benchmark records remain intact.
The result archive includes the predecessor return, actual sources, environment, compiler checks, fixed results and full traces.
An optimal termination string alone never certifies global optimality.

```bash
bash execution/run_diagnostic.sh run
```

Local compilation-only inspection in a fresh directory is available without optimization.

```bash
python execution/dnlp_support.py --gams /path/to/gams --output /fresh/compile-output
```
