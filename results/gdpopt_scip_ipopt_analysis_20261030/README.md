# GDPopt SCIP–IPOPT returns, 30 October 2026

All 90 jobs have terminal records. The new campaign uses SCIP 9.2.4 for MIP and IPOPT 3.14.19 for NLP; the primary historical Process cohort uses SCIP for both. These are separate solver configurations, not a correction that invalidates every previous SCIP result.

| Scope | Method | Feasible | Target hits | Time limits | Optimal but misses | Worker seconds | SCIP / IPOPT calls |
|---|---|---:|---:|---:|---:|---:|---:|
| grid | LOA | 21/21 | 14/21 | 8 | 2 | 28992.215 | 24697 / 0 |
| grid | RIC | 21/21 | 15/21 | 7 | 2 | 30178.340 | 24839 / 0 |
| grid | GLOA | 21/21 | 15/21 | 10 | 0 | 30402.749 | 24577 / 0 |
| process | LOA | 9/9 | 5/9 | 2 | 2 | 5691.430 | 1048 / 1038 |
| process | RIC | 9/9 | 5/9 | 1 | 3 | 4166.837 | 1282 / 1267 |
| process | GLOA | 9/9 | 1/9 | 0 | 8 | 326.292 | 70 / 68 |

## Historical comparison

Every primary pair uses the exact historical result hash selected before launching the new experiment. Grid history is the unchanged descriptive mixture of retained first attempts and recoveries, not a fresh equal-budget cohort. Process history is the October 26 SCIP/SCIP cohort. Supplementary Process pairs retain the selected HiGHS/BARON and earlier HiGHS/SCIP cohorts.

| Scope | Previous configuration | Method | Previous hits | New hits | Previous seconds | New seconds | New / old |
|---|---|---|---:|---:|---:|---:|---:|
| grid | previous_scip_scip | all | 51/63 | 44/63 | 78376.881 | 89573.304 | 1.143 |
| grid | previous_scip_scip | loa | 18/21 | 14/21 | 25896.385 | 28992.215 | 1.120 |
| grid | previous_scip_scip | ric | 16/21 | 15/21 | 26745.370 | 30178.340 | 1.128 |
| grid | previous_scip_scip | gloa | 17/21 | 15/21 | 25735.125 | 30402.749 | 1.181 |
| process | previous_baron | all | 7/27 | 11/27 | 26556.535 | 10175.253 | 0.383 |
| process | previous_baron | loa | 3/9 | 5/9 | 11060.151 | 5687.647 | 0.514 |
| process | previous_baron | ric | 3/9 | 5/9 | 11040.892 | 4163.898 | 0.377 |
| process | previous_baron | gloa | 1/9 | 1/9 | 4455.492 | 323.708 | 0.073 |
| process | previous_highs_scip | all | 13/27 | 11/27 | 19403.483 | 10175.253 | 0.524 |
| process | previous_highs_scip | loa | 6/9 | 5/9 | 7843.607 | 5687.647 | 0.725 |
| process | previous_highs_scip | ric | 6/9 | 5/9 | 7927.560 | 4163.898 | 0.525 |
| process | previous_highs_scip | gloa | 1/9 | 1/9 | 3632.315 | 323.708 | 0.089 |
| process | previous_scip_scip | all | 13/27 | 11/27 | 20474.882 | 10175.253 | 0.497 |
| process | previous_scip_scip | loa | 6/9 | 5/9 | 8705.002 | 5687.647 | 0.653 |
| process | previous_scip_scip | ric | 6/9 | 5/9 | 8121.969 | 4163.898 | 0.513 |
| process | previous_scip_scip | gloa | 1/9 | 1/9 | 3647.911 | 323.708 | 0.089 |

Grid timing compares worker wall seconds. Process timing compares method completion plus preparation, using worker wall time for hard watchdog cases to avoid double-counting preparation. These are completion costs, not time to first target. Sums across concurrent packages are not elapsed duration. One run per problem, changed tracing/adapter overhead and nonexclusive cores do not establish causal solver speed or statistical superiority.

## Interpretation

- Process LOA/RIC gain the Dynamic target and lose the CSTR10 and CSTR25 targets relative to SCIP/SCIP. Column objectives improve but still miss the unchanged reference. The IPOPT change is not uniformly better.
- All 63 Grid jobs make zero actual IPOPT calls. Their fixed subproblems take the linear SCIP path. Grid timing/target differences cannot be attributed to changing the NLP solver to IPOPT.
- holder_table, michalewicz and shubert remain target misses for all three methods. The previously diagnosed preprocessing issue is not repaired by this experiment. Optimal termination strings are not independently valid global certificates.
- IPOPT is a local NLP solver. A feasible returned vector, target hit and global certificate are distinct claims. This report grants no new global certificate, including for GLOA or RIC.
- Targets and acceptance tolerance remain abs(objective-reference) <= 1e-5*max(1,abs(reference)). Separate minimization attainment is retained. No objective, reference, initialization, bound or returned result is replaced.
- CSTR30 retains constructor initialization; CSTR5–25 retain the algebraic saved initialization. The separate DFO mass_balance_zero_recycle protocol is not substituted. Direct Big-M/Hull methods were not rerun.

## Audit and limitations

All 90 saved vectors pass an independent original-GDP check without an optimizer. 4 hard-watchdog Grid returns had a saved vector but only an unavailable server validation marker; local verification fills that analytical gap without rewriting the source record or changing any hit outcome.

The measured parallel campaign span was 5.1466 hours, from launch through the last run end timestamp, excluding final ZIP packaging. Reported execution errors: 0. Time-limited runs: 28. Completed does not mean globally solved.

Each original ZIP outer SHA256 and every internally listed member was verified at import. Compact evidence retains all non-call files byte-for-byte, including complete run logs, solver journals, trajectories, solution vectors, preflights, exact executed source ZIP and the original full member inventory. Only the large /calls/ scratch and nested per-call ZIPs are omitted from Git; unchanged originals remain with the user. IMPORT.json records original hashes and the explicit retained-file inventory. Solver execution banners in complete logs independently match the journal counts. All 90 jobs keep their denominator, including watchdogs and target misses.

## Per-job primary comparisons

| Job | Previous target | New target | Previous objective | New objective | Termination |
|---|---|---|---:|---:|---|
| grid__ackley__gloa | True | True | 0.0 | -3.117085571445524e-17 | optimal |
| grid__ackley__loa | True | True | 0.0 | -3.117085571445524e-17 | optimal |
| grid__ackley__ric | True | True | 0.0 | -3.117085571445524e-17 | optimal |
| grid__alpine1__gloa | True | True | 0.0 | 0.0 | optimal |
| grid__alpine1__loa | True | True | 0.0 | 0.0 | optimal |
| grid__alpine1__ric | True | True | 0.0 | 0.0 | optimal |
| grid__alpine2__gloa | True | False | 0.0 | 0.06723263291103136 | maxTimeLimit |
| grid__alpine2__loa | True | False | 0.0 | 0.06723263291103136 | maxTimeLimit |
| grid__alpine2__ric | False | True | 0.06723263291103136 | 0.0 | optimal |
| grid__bohachevsky2__gloa | True | True | 0.0 | 0.0 | optimal |
| grid__bohachevsky2__loa | True | True | 0.0 | 0.0 | optimal |
| grid__bohachevsky2__ric | True | True | 0.0 | 0.0 | optimal |
| grid__camel3__gloa | True | True | 0.0 | 0.0 | maxTimeLimit |
| grid__camel3__loa | True | True | 0.0 | 0.0 | maxTimeLimit |
| grid__camel3__ric | True | True | 0.0 | 0.0 | maxTimeLimit |
| grid__csendes__gloa | True | True | 1.9808350653109343e-08 | 1.9808350653109343e-08 | optimal |
| grid__csendes__loa | True | True | 1.9808350653109343e-08 | 1.9808350653109343e-08 | optimal |
| grid__csendes__ric | True | True | 1.9808350653109343e-08 | 1.9808350653109343e-08 | optimal |
| grid__deflected_corrugated_spring__gloa | True | True | 0.0 | 0.0 | optimal |
| grid__deflected_corrugated_spring__loa | True | True | 0.0 | 0.0 | optimal |
| grid__deflected_corrugated_spring__ric | True | True | 0.0 | 0.0 | optimal |
| grid__dropwave__gloa | True | True | 0.0 | 0.0 | optimal |
| grid__dropwave__loa | True | True | 0.0 | 0.0 | optimal |
| grid__dropwave__ric | True | True | 0.0 | 0.0 | optimal |
| grid__easom__gloa | True | False | 0.0 | 0.8722866131855062 | maxTimeLimit |
| grid__easom__loa | True | False | 0.0 | 0.8722866131855062 | maxTimeLimit |
| grid__easom__ric | False | True | 0.8722866131855062 | 0.0 | optimal |
| grid__griewank__gloa | True | True | 0.0 | 0.0 | optimal |
| grid__griewank__loa | True | True | 0.0 | 0.0 | optimal |
| grid__griewank__ric | True | True | 0.0 | 0.0 | optimal |
| grid__holder_table__gloa | False | False | 0.14516723995340786 | 0.14516723995340786 | maxTimeLimit |
| grid__holder_table__loa | False | False | 0.14516723995340786 | 0.14516723995340786 | optimal |
| grid__holder_table__ric | False | False | 0.14516723995340786 | 0.14516723995340786 | maxTimeLimit |
| grid__hosaki__gloa | True | True | 0.0 | 0.0 | maxTimeLimit |
| grid__hosaki__loa | True | True | 0.0 | 0.0 | maxTimeLimit |
| grid__hosaki__ric | True | True | 0.0 | 0.0 | maxTimeLimit |
| grid__levy13__gloa | False | False | 0.002619219653179194 | 0.0026192196531791938 | maxTimeLimit |
| grid__levy13__loa | True | False | 0.0 | 0.0026192196531791938 | maxTimeLimit |
| grid__levy13__ric | True | False | 0.0 | 0.0026192196531791938 | maxTimeLimit |
| grid__levy__gloa | True | True | 0.0 | -1.4566988880917495e-19 | maxTimeLimit |
| grid__levy__loa | True | False | 0.0 | 0.0012209612060090794 | maxTimeLimit |
| grid__levy__ric | True | False | 0.0 | 0.0012209612060090794 | maxTimeLimit |
| grid__michalewicz__gloa | False | False | 0.08649170482029742 | 0.08649170482029742 | maxTimeLimit |
| grid__michalewicz__loa | False | False | 0.08649170482029742 | 0.08649170482029742 | maxTimeLimit |
| grid__michalewicz__ric | False | False | 0.08649170482029742 | 0.08649170482029742 | optimal |
| grid__rastrigin__gloa | True | True | 0.0 | 0.0 | optimal |
| grid__rastrigin__loa | True | True | 0.0 | 0.0 | optimal |
| grid__rastrigin__ric | True | False | 0.0 | 0.014927003374186948 | maxTimeLimit |
| grid__rosenbrock__gloa | True | True | 0.0 | 0.0 | optimal |
| grid__rosenbrock__loa | True | True | 0.0 | 0.0 | optimal |
| grid__rosenbrock__ric | True | True | 0.0 | 0.0 | optimal |
| grid__shubert__gloa | False | False | 0.08242781075119937 | 0.08242781075119937 | maxTimeLimit |
| grid__shubert__loa | False | False | 0.08242781075119937 | 0.08242781075119937 | optimal |
| grid__shubert__ric | False | False | 0.08242781075119937 | 0.08242781075119937 | optimal |
| grid__styblinski_tang__gloa | True | True | 0.0 | 0.0 | maxTimeLimit |
| grid__styblinski_tang__loa | True | True | 0.0 | 0.0 | maxTimeLimit |
| grid__styblinski_tang__ric | True | True | 0.0 | 0.0 | maxTimeLimit |
| grid__sum_of_squares__gloa | True | True | 0.0 | 0.0 | optimal |
| grid__sum_of_squares__loa | True | True | 0.0 | 0.0 | optimal |
| grid__sum_of_squares__ric | True | True | 0.0 | 0.0 | optimal |
| grid__xin_she_yang3__gloa | True | True | 0.0 | 0.0 | optimal |
| grid__xin_she_yang3__loa | True | True | 0.0 | 0.0 | optimal |
| grid__xin_she_yang3__ric | True | True | 0.0 | 0.0 | optimal |
| process__column__gloa | False | False | 22271.549001229178 | 20355.058459180233 | optimal |
| process__column__loa | False | False | 22271.549001229178 | 19449.851511967317 | optimal |
| process__column__ric | False | False | 22271.549001229178 | 19449.851511967317 | optimal |
| process__cstr_10__gloa | False | False | 3.4479385852262503 | 3.44796403166042 | optimal |
| process__cstr_10__loa | True | False | 2.88953696848347 | 2.9660470721113823 | optimal |
| process__cstr_10__ric | True | False | 2.88953696848347 | 2.9660470721113823 | optimal |
| process__cstr_15__gloa | False | False | 3.561900983846565 | 3.561958649508225 | optimal |
| process__cstr_15__loa | True | True | 2.82939406035249 | 2.829394063285755 | optimal |
| process__cstr_15__ric | True | True | 2.82939406035249 | 2.829394063285755 | optimal |
| process__cstr_20__gloa | False | False | 3.61603130759866 | 3.6161229932806 | optimal |
| process__cstr_20__loa | True | True | 2.7994064179885196 | 2.79940642510782 | optimal |
| process__cstr_20__ric | True | True | 2.7994064179885196 | 2.79940642510782 | optimal |
| process__cstr_25__gloa | False | False | 3.64775274238065 | 3.6478558962091747 | optimal |
| process__cstr_25__loa | True | False | 2.78148259257455 | 2.7912516988900062 | maxTimeLimit |
| process__cstr_25__ric | True | False | 2.78148259257455 | 2.7912516988900062 | optimal |
| process__cstr_30__gloa | False | False | 3.66862246699077 | 3.6687157275306603 | optimal |
| process__cstr_30__loa | False | False | 2.815267336799757 | 2.873140226266926 | maxTimeLimit |
| process__cstr_30__ric | False | False | 2.8093885219416777 | 2.771621404246269 | maxTimeLimit |
| process__cstr_5__gloa | False | False | 3.130189877388595 | 3.130198133115465 | optimal |
| process__cstr_5__loa | True | True | 3.06200967750001 | 3.0620145765749553 | optimal |
| process__cstr_5__ric | True | True | 3.06200967750001 | 3.0620145765749553 | optimal |
| process__dynamic__gloa | False | False | -117.07438303798538 | -197.1401311792058 | optimal |
| process__dynamic__loa | False | True | -117.07438303798538 | -212.00878715666488 | optimal |
| process__dynamic__ric | False | True | -117.07438303798538 | -212.00878715666488 | optimal |
| process__small_batch__gloa | True | True | 167427.65141248275 | 167427.6571147092 | optimal |
| process__small_batch__loa | True | True | 167427.65141248275 | 167427.6571147092 | optimal |
| process__small_batch__ric | True | True | 167427.65141248275 | 167427.6571147092 | optimal |

## Reproduce without a solver

```bash
python scripts/analyze_gdpopt_scip_ipopt_return.py --output /tmp/gdpopt-scip-ipopt-analysis
python -m pytest tests/test_gdpopt_scip_ipopt_return.py -q
```

To verify the original downloaded archives again, add --archives /path/to/original-zips and use a fresh output directory. Pyomo 6.10.0 is required for saved-vector evaluation. Analysis never launches a benchmark. Existing reports and manuscript files are unchanged.
