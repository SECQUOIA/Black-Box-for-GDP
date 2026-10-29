# Four Process SCIP returns and paired BARON comparison

All 45 planned jobs have terminal records, with 43 independently verified returned solution vectors, 16 time-limited runs and 0 execution errors.
This is one run per method and instance, so percentages across instances are coverage rates rather than repeated-seed success probabilities.
The direct Big-M/Hull jobs actually call SCIP MINLP, while all three GDPopt methods actually call SCIP for both MIP and NLP.
The selected BARON baseline is the unchanged current comparison selection: September 25 Big-M/Hull and October 1 GDPopt.
The BARON GDPopt baseline uses HiGHS MIP and BARON NLP with CLP/IPOPT subsolvers, while direct BARON uses CPLEX/IPOPT subsolvers.
The older October 25 intermediate cohort uses HiGHS MIP plus SCIP NLP and is reported separately.

## Method-level comparison

| Method | BARON absolute hits | SCIP absolute hits | BARON at-or-below | SCIP at-or-below | SCIP feasible | BARON completion s | SCIP completion s | SCIP/BARON time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bigm | 6/9 | 3/9 | 7/9 | 5/9 | 7/9 | 9157.96 | 11577.67 | 1.264 |
| hull | 6/9 | 4/9 | 6/9 | 7/9 | 9/9 | 9738.65 | 7731.20 | 0.794 |
| gloa | 1/9 | 1/9 | 1/9 | 1/9 | 9/9 | 4455.49 | 3647.91 | 0.819 |
| loa | 3/9 | 6/9 | 4/9 | 6/9 | 9/9 | 11060.15 | 8705.00 | 0.787 |
| ric | 3/9 | 6/9 | 3/9 | 6/9 | 9/9 | 11040.89 | 8121.97 | 0.736 |

Absolute-reference hits change from 19/45 to 20/45, while minimization attainment changes from 21/45 to 25/45.
The summed completion-plus-preparation cost changes from 45453.145 to 39783.752 seconds, a decrease of 12.47%.
Completion costs are not time-to-first-target, and the sum across parallel packages is not their end-to-end elapsed duration.
The source, solver adapter, solver options, CPU allocation and tracing differ across historical cohorts, so these observed costs are not a controlled causal estimate of solver speed.
CPU affinity is provenance rather than a claimed explanation of performance.

## Fixed targets and objective quality

The primary rule remains abs(objective-reference) <= 1e-5*max(1,abs(reference)); the separate minimization rule accepts values at or below reference plus that tolerance.
No target, feasibility tolerance, historical selection, original model or initialization is changed.
SCIP Big-M CSTR5/CSTR10 and Hull CSTR15/CSTR20/CSTR25 return lower accepted objectives outside the absolute reference band.
Their absolute misses must not be described as worse objective values or silently converted into absolute hits.
These small CSTR objective differences coexist with residuals near 1e-6 and are numerical accepted-vector differences, not demonstrated improvements of the exact physical optimum.
BARON already has a corresponding better-than-reference absolute miss at Big-M CSTR10 and LOA CSTR15.
LOA CSTR15 changes from a lower BARON objective to a reference-matching SCIP objective, so that additional absolute hit is not an objective improvement.

## Instance results

An asterisk denotes an absolute-reference hit, T denotes time-limit termination, and B denotes a lower-bound conflict with a verified feasible vector from these new returns.
Each cell contains the verified original-GDP objective and measured method/watchdog completion seconds, excluding template preparation.

| Instance | Big-M | Hull | GLOA | LOA | RIC |
|---|---|---|---|---|---|
| cstr_5 | 3.061975221; 53.15 | 3.062008702; 14.89 * B | 3.130189877; 5.15 B | 3.062009678; 25.12 * B | 3.062009678; 25.21 * B |
| cstr_10 | 2.889412738; 771.21 | 2.889514987; 71.48 * B | 3.447938585; 6.26 B | 2.889536968; 234.35 * B | 2.889536968; 214.95 * B |
| cstr_15 | no accepted vector; 1790.78 T | 2.829357302; 284.46 | 3.561900984; 6.97 B | 2.82939406; 545.04 * B | 2.82939406; 325.88 * B |
| cstr_20 | 2.804132601; 1792.22 T | 2.799359556; 1150.45 | 3.616031308; 9.00 B | 2.799406418; 1018.10 * B | 2.799406418; 766.80 * B |
| cstr_25 | 2.78770978; 1792.06 T | 2.781434669; 1701.48 | 3.647752742; 11.01 B | 2.781482593; 1460.44 * B | 2.781482593; 1391.45 * B |
| cstr_30 | 2.769569663; 1791.77 * T | 2.76956972; 1792.51 * T | 3.668622467; 14.40 B | 2.815267337; 1789.79 T | 2.809388522; 1800.01 T |
| column | no accepted vector; 1792.45 T | 22271.549; 1792.38 T | 22271.549; 1791.27 T | 22271.549; 1791.41 T | 22271.549; 1791.27 T |
| small_batch | 167427.6516; 0.47 * | 167427.6516; 0.46 * | 167427.6514; 10.89 * | 167427.6514; 47.73 * | 167427.6514; 13.30 * |
| dynamic | -212.0087909; 1791.36 * T | -196.9311868; 920.89 B | -117.074383; 1791.13 T | -117.074383; 1791.12 T | -117.074383; 1791.23 T |

## Findings requiring care

CSTR15 Big-M returns a solver candidate objective 2.8222510013618556, but the archived original-GDP check rejects its 0.0009636850434195932 violation against the unchanged 1e-5 acceptance criterion.
That candidate is not a returned accepted solution and is not counted as a target hit; its complete variable vector was not saved, so the aggregate rejection is reported from the original incumbent record rather than reconstructed.
Column Big-M reaches its time limit with GAMS MODELSTAT=14 and no SCIP solution, so neither the original initialization nor a solver bound is substituted for a returned vector.
Both cases retain their full denominator and measured cost.
Direct SCIP Hull reaches at-or-below targets for all six CSTR sizes and improves the old CSTR30 Hull result, while direct Big-M loses accepted/reference-quality outcomes on CSTR15, CSTR20 and CSTR25.
Direct SCIP Big-M reaches the Dynamic target at approximately -212.008790892, compared with the old BARON Big-M value -207.626116094.
Dynamic Hull returns a feasible value -196.931186772 and reports optimal with lower bound -196.931186782, but that lower bound exceeds the independently validated Big-M feasible value by about 15.077604.
The Dynamic Hull bound therefore cannot certify the original GDP globally; the exact solver, transformation or numerical cause is not established by these saved artifacts.
All six CSTR GLOA runs again report optimal after two NLP attempts while their lower bounds exceed independently checked feasible objectives.
Their short completion times are not evidence of correct global solution of those CSTRs.
The unchanged tolerance-based bound screen flags 19 comparisons in total: six CSTR GLOA cases, Dynamic Hull, and twelve additional CSTR Hull/LOA/RIC discrepancies between approximately 3.35e-5 and 1.24e-4.
The twelve small discrepancies concern tolerance-accepted numerical vectors and must not be assigned the same structural cause as the much larger GLOA and Dynamic Hull conflicts.
For both GDPopt LOA and RIC, CSTR15/CSTR20/CSTR25 newly match the fixed reference relative to the selected BARON runs.
CSTR30 LOA and RIC do not match the reference; RIC reaches the hard watchdog with a saved feasible incumbent and one unfinished journal return.
CSTR30 uses the original constructor initialization, not the separate material-balance/zero-recycle publication experiment.
All three GDPopt Column/Dynamic runs spend their budget on the first SCIP NLP and return suboptimal feasible incumbents before continued exploration.
No extra solve or automatic replacement is justified merely by a time-limit result; CSTR15 Big-M acceptance loss and the Dynamic Hull/CSTR GLOA bound conflicts warrant targeted diagnosis before treating them as certified performance results.

## Intermediate HiGHS/SCIP cohort

| Method | Previous HiGHS/SCIP hits | New SCIP/SCIP hits | Previous completion s | New completion s |
|---|---:|---:|---:|---:|
| gloa | 1/9 | 1/9 | 3632.32 | 3647.91 |
| loa | 6/9 | 6/9 | 7843.61 | 8705.00 |
| ric | 6/9 | 6/9 | 7927.56 | 8121.97 |

The previous and new GDPopt cohorts each have 13/27 absolute-reference hits, so changing the MIP master to SCIP does not increase the aggregate target count in this observation.
The observed GDPopt completion sum increases by 5.52% relative to that intermediate cohort; transport retries and the earlier CSTR20 RIC error make this an uncontrolled comparison.
RIC gains CSTR20 relative to the earlier network-error run and loses the earlier CSTR30 target hit; the other method hit sets are unchanged.
The new Column RIC vector is saved and independently feasible, whereas the earlier cohort had no saved vector for that job.
The three Dynamic GDPopt objectives worsen from approximately -119.383102745 to -117.074383038, while still missing the reference in both cohorts.

## Solver calls, environment and integrity

The benchmark has 4520 interface attempts and 4517 confirmed solver invocations: {'scip/minlp': 18, 'scip/mip': 2263, 'scip/nlp': 2236}.
Two failed network-start attempts never reach the SCIP execution banner, and the final CSTR30 RIC NLP interface attempt is interrupted before any new SCIP banner or terminal journal record appears.
Five transient network errors are recovered inside their existing deadlines, with 25 seconds of recorded backoff and no whole-job retries.
Preflight adds 7 separate tiny SCIP solves and 18 compile-only calls; these are excluded from benchmark counts and costs.
The benchmark calls are confirmed from actual SCIP execution banners as well as journals, with no external BARON, HiGHS or IPOPT benchmark invocation.
SCIP may internally link Ipopt; that is not a GDPopt nlp_solver=ipopt configuration.
The unused minlp_solver=baron default displayed in the RIC configuration is not an actual BARON call because force_subproblem_nlp=True and both active solver argument blocks specify SCIP.
Actual GDPopt configuration records retain subproblem_presolve=True, mip_presolve=True, set_covering initialization, and the original NLP export.
The special Grid presolve-disabled/DNLP diagnostic is not applied to these Process runs.
All returns record Dantzig, GAMS 52.2.0, SCIP 9.2.4, Python 3.11.16, Pyomo 6.10.0 and single-thread settings, matching the environment gate.
The four CPUs are 18, 20, 22 and 24 on separate physical cores, without an exclusive whole-server reservation.
The original model source, saved initialization, initialization label and template bound tightening match the corresponding BARON records for all 45 pairs.
All original ZIP members, package hashes and all 45 terminal seals are verified, including interrupted GAMS scratch files previously omitted by the old packer.
The independent local audit validates 43 new vectors and all 45 selected BARON vectors, with maximum new original-GDP violation 9.992239457801144e-07.
The local audit uses Python 3.13.12 and Pyomo 6.10.0 solely to evaluate saved vectors and guards against optimizer construction.
Machine-precision differences between Linux and macOS objective/residual evaluation are recorded in solution_checks.json; all saved-vector checks retain their existing acceptance criteria.
The original archives, historical reports, manuscript, Overleaf material and figures are preserved.
No installed Pyomo code, solver option, model constraint or returned execution record is modified by this analysis.
The report does not automatically replace manuscript representative results or claim new global certificates.

## Reproduction

```bash
python scripts/analyze_process_scip_four_return.py --output /tmp/process-scip-four-reproduced
python -m pytest tests/test_process_scip_four_return.py tests/test_process_scip_return.py -q
```

The four unchanged returned ZIPs and locally computed sidecars are stored under results/archives/process_scip_METHOD_20261026_result.zip, with METHOD=minlp, ric, loa or gloa.
[jobs.csv](jobs.csv) retains every new job, including both missing vectors and all time limits.
[paired_baron_scip.csv](paired_baron_scip.csv) contains all 45 BARON pairs and [paired_highs_scip.csv](paired_highs_scip.csv) contains the 27 intermediate-cohort pairs.
[solution_checks.json](solution_checks.json), [issues.json](issues.json) and [solver_calls.csv](solver_calls.csv) preserve independent validation, failure/bound evidence and actual call accounting.
[manifest.json](manifest.json) records input hashes, exact execution source hashes, environment, options, source revisions and the missing execution commit identity explicitly.
Full selected-variable trajectories remain in each unchanged archive, with their per-job event counts and SHA256 links in jobs.csv.
[tests.log](tests.log) records the solver-free tests, [preservation.json](preservation.json) records protected-file hashes, and [artifact_checksums.json](artifact_checksums.json) seals the new code, archives and outputs.
The report is a follow-up on review/cstr15-dantzig-results, the branch associated with already-merged PR 49; pushing it does not automatically update main.
