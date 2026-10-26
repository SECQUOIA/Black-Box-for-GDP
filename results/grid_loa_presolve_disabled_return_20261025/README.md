# Presolve-disabled LOA diagnostic: stopped before SCIP execution

The v2 return stopped on holder_table [3,1] during GAMS compilation.
The official subproblem_presolve=False option was applied and the before_subproblem event was recorded.
The retained GAMS mtype=nlp route rejected the ABS function in equation c3_hi with errors 61 and 256 before SCIP started.
The initial preprocessing rejection in run.log belongs to the separate default-presolve probe, not to the disabled-presolve call.
This result confirms entry past the known preprocessing rejection but does not establish successful solution of the subproblem or any full LOA improvement.

There was one solver-interface attempt and one GAMS job, zero confirmed SCIP invocations, zero returned solutions and zero full LOA runs.
The remaining five fixed configurations were not attempted after the first gate failed.
The runner field actual_fixed_solver_calls counts interface attempts, so its value of one must not be described as one completed SCIP solve.
The first delivery's serialization failure is also preserved inside the returned ZIP and made zero interface calls.
The v2 GAMS interface call took 0.373931 seconds and its fixed worker took 0.621599 seconds.

| Problem | Prior objective | Prior termination | Prior maximum violation | Prior worker seconds | New full LOA |
| --- | ---: | --- | ---: | ---: | --- |
| holder_table | 0.145167239953 | optimal | 0.0 | 1623.761 | Not run |
| michalewicz | 0.0864917048203 | optimal | 0.0 | 1490.761 | Not run |
| shubert | 0.0824278107512 | optimal | 0.0 | 1278.446 | Not run |

New objectives, residuals, target outcomes and full-run timings are unavailable and are not replaced by reference-witness values or zeros.
The baseline optimal strings do not certify original-GDP global optimality, and their known target misses remain preserved.
This is a stopped selective diagnostic, not a three-problem performance result or a replacement of the 21-problem benchmark.

The server host, Python, Pyomo 6.10.0, GAMS 52.2.0 executable hash, CPU 14 affinity and single-thread settings match the recorded baseline.
The installed Pyomo module hashes remained unchanged.
SCIP 9.2.4 is the historical version, but this failed call produced no fresh SCIP banner and cannot verify its runtime version.
The actual effective options and original GDP witness are retained under evidence without treating the witness as a returned solver solution.

The earlier 42-test validation covered mocked solver boundaries and did not test whether GAMS could compile this ABS-containing model as NLP.
That validation gap was missed during package preparation and is the reason the corrected package still failed immediately on the server.
The earlier ConfigDict serialization error and the current compilation error are distinct failures.
The GAMS diagnostic suggests DNLP, but changing mtype would be a second solver-option change beyond the requested single-option experiment and is not validated here.
No DNLP change, additional patch, retry, new execution package or optimization run is performed in this audit.
The requested stop-on-first-fixed-failure rule remains in force.

The original ZIPs, historical results, source packages and publication material remain unchanged.
The analysis uses archive bytes only and can be reproduced without any optimization solver.

```bash
python scripts/analyze_grid_loa_presolve_disabled_return.py --output /tmp/grid_loa_return_fresh
```
