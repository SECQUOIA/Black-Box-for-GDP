# LOA subproblem presolve disabled: returned diagnostic

This is a selective three-problem diagnostic, not a new 21-grid benchmark.
This follow-up combines subproblem_presolve=False with an explicit SCIP/DNLP subproblem export.
It is separate from the earlier single-option diagnostic, which stopped at GAMS compilation.
The option also bypasses fixed-variable and trivial-constraint preprocessing, so solver routing and measured time may differ.
Known feasible reference objectives and the 1e-5 acceptance/target tolerance remain unchanged.
The table uses independently evaluated original-GDP objectives from the same returned variable vectors as the residual checks.
An optimal termination string does not certify the original nonconvex GDP, and inconsistent lower bounds are retained in comparison.json.

| Grid | Prior objective | Prior termination | Prior max violation | Prior seconds | Prior reference evaluations | New objective | New termination/status | New max violation | New worker seconds | New reference evaluations | New target |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
| holder_table | 0.145167239953 | optimal | 0.0 | 1623.761 | 0 | -1.9587104186792927e-16 | maxTimeLimit | 1.7763568394002505e-15 | 1800.0292075679172 | 4 | True |
| michalewicz | 0.0864917048203 | optimal | 0.0 | 1490.761 | 0 | 0.0 | maxTimeLimit | 4.440892098500626e-16 | 1790.398833095096 | 1 | True |
| shubert | 0.0824278107512 | optimal | 0.0 | 1278.446 | 0 | 0.0 | maxTimeLimit | 0.0 | 1793.2569180449937 | 1 | True |

Fixed call attempts: 6; confirmed SCIP invocations: 6; full LOA solve entries: 0.
Fixed gates passed: 6/6; run status: completed.
The reference_paths.json file distinguishes discrete selection, bypassed presolve, evaluation entry, evaluation return and target incumbents for all six diagnostic coordinates.
Missing new values mean that the corresponding stage did not produce a result.
No solver is invoked by this analysis.
