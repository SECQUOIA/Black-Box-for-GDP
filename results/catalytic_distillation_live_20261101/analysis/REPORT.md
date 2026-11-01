# Independent data audit of the Dantzig Column return

The execution produced a complete, structurally consistent set of 210 completed search runs.
All numerical results below are recomputed from individual result files and callbacks, while the original CSV files remain unchanged.

## Performance at B = 100

| Method | Hits | Median gap ($/yr) | Gap Q1–Q3 ($/yr) | Median charged completion (s) |
| --- | ---: | ---: | ---: | ---: |
| D-SDA | 3/10 | 1.286 | 0.322–549.186 | 522.3 |
| RBFOpt | 1/10 | 417.238 | 187.077–479.613 | 544.4 |
| BAM | 0/10 | 1172.778 | 1082.896–1172.778 | 571.1 |
| FMQA-SA | 0/10 | 1019.978 | 789.129–1660.797 | 608.5 |
| Uniform | 0/10 | 1118.969 | 740.751–1239.982 | 495.2 |
| NOMAD | 0/10 | 30.428 | 1.286–290.345 | 682.7 |
| MISO | 3/10 | 34.468 | 2.341–350.136 | 627.3 |

D-SDA and MISO each reached the best-known target in 3/10 seeds at B=100, while RBFOpt reached it in 1/10 seeds.
D-SDA has the smallest conventional median objective gap at this budget, while NOMAD has a slightly smaller median gap than MISO but no exact target hits under the fixed tolerance.
MISO and RBFOpt each reached the target in one seed at B=50; no method reached it at B=25.
Each method-budget condition contains ten paired seeds, and these descriptive comparisons do not establish a universal or statistically proven ranking.

## Timing and cache reuse

The campaign ran for 2.792393 h on three assigned physical cores.
The sum of worker wall times was 8.322686 worker-hours, compared with 20.221722 h of charged completion time.
Recorded point costs sum to 19.659591 h across callbacks, while the distinct cache rows contain 7.691884 h of solve wall time.
This difference supports cache reuse as a major reason the campaign finished sooner than an uncached linear forecast.
These totals are recorded wall times or accounting costs, not measured CPU time.
The observed worker-slot occupancy from wall-time sums is 99.35%; this is not an operating-system CPU-utilization measurement.
The original 12,250-evaluation maximum is reduced to 12,015 charged evaluations because eight D-SDA runs terminate before their caps.
All other methods used their full budgets.
All 12,015 evaluated points are distinct within their own runs, but designs recur across seeds, methods, and budgets.
Of 9,226 admissible callbacks, 5,727 are requests beyond the first occurrence of their configuration in the campaign.
Actual cache-hit counts are not logged uniformly across methods and cannot be equated to 5,727.
The same configuration may be solved concurrently before the first cache insertion, and non-forked worker counters can omit a losing concurrent solve.
The 3,500 recorded solve counters and 3,499 unique cache rows therefore do not establish an exact total of actual NLP calls.

## Outcome and provenance qualifications

The original acceptance rule depends on modelstat in {1,2} and solvestat=1; it does not require GAMS process returncode=0.
Two cache records have GAMS returncode=7: gaps (5,1,4,2,0,4) are accepted at objective 25273.891950 with modelstat=2/solvestat=1, while gaps (2,0,1,6,1,3) have missing statuses and are unaccepted.
The original policy is retained, and the return does not provide the individual private GAMS logs needed to establish the reasons for those two return codes.
The accepted returncode-7 objective is not the best-known objective or a target hit.
The 847 unaccepted unique NLP responses generated 2,305 unaccepted callbacks because cached responses were reused.
All 60 NOMAD/MISO runs completed on their first native attempt with exit code zero.
NOMAD records four rejected requests beyond the budget cap per run, for 120 total, due to the inherited adapter budget convention with seven shared starts.
The existing cap guard returns a penalty before evaluating those requests; admitted evaluations remain at the original cap.
The initial seven points were reconstructed independently from the pinned seed stream and agree for every condition.
The combined cache-plus-pilot accepted set contains 2,716 configurations, while the campaign cache alone contains 2,652 accepted configurations.
The best-known value is reconstructed from that same combined set and remains an observed benchmark target, not a certificate of global optimality.

## Original summaries

Every original runs.csv field and all 21 original conditions.csv rows agree with individual records under the original definitions.
The original median labels correspond to sorted(values)[n//2], which selects the sixth value for ten seeds.
The added conventional median averages the fifth and sixth sorted values, and its quartiles use NumPy linear interpolation.
This additional descriptive analysis does not change target hits, acceptance, termination statuses, or any original evidence.

## Evidence limits

The returned wrapper records the execution revision, GAMS/CONOPT versions, CPU topology, preflight outcomes, startup checks, and controller exit code.
The raw preflight test log and private GAMS version-probe logs are not included in the supplied return, so their reported contents cannot be independently re-read from this ZIP.
The cache model, initialization, and solve-script hashes and recorded preflight test-source hash were checked against Git objects at the recorded execution revision.
No optimizer, NLP solver, preflight, or new experiment was executed for this analysis.
