# Dantzig D-SDA no-revisit result analysis

All 1,470 returned results pass the independent data audit, with no missing jobs, duplicate jobs, repeated configurations within a run, budget violations, or target-scoring discrepancies.
This report independently audits the Dantzig return using saved data only; no optimizer or NLP solver is rerun.

## Target attainment and comparison

The Grid comparator is the archived target-stop D-SDA run, and each Process comparator is the corresponding variant from the previous Dantzig restart return.
All initial points, seeds, targets, budgets, and method settings match the sealed plan.

| Cohort | Runs | Previous hits | New hits | Gained | Lost |
| --- | ---: | ---: | ---: | ---: | ---: |
| Grid B=10 | 210 | 13 | 13 | 0 | 0 |
| Grid B=30 | 210 | 74 | 78 | 4 | 0 |
| Grid B=50 | 210 | 88 | 91 | 3 | 0 |
| Grid B=70 | 210 | 98 | 101 | 3 | 0 |
| Grid B=100 | 210 | 101 | 101 | 0 | 0 |
| Grid total | 1050 | 374 | 384 | 10 | 0 |
| Process single | 140 | 74 | 79 | 5 | 0 |
| Process ranked | 140 | 74 | 80 | 6 | 0 |
| Process ranked_random | 140 | 74 | 80 | 6 | 0 |

All supplied local cross-check counts match the Dantzig output.
No previous target hit is lost, and no best objective becomes worse in any same-variant comparison.
Objective-improvement counts in the CSV tables use a change greater than 1e-5; target attainment retains the original relative tolerance of 1e-5 times max(1, absolute target).
Grid gains ten target hits across the budget-seed conditions, while Process single gains five.
The five Process single gains are CSTR10/B15/seed8, CSTR30/B43/seed3, Dynamic/B15/seed9, and Dynamic/B20/seeds7 and 8.
These are outcomes over the tested conditions, with reused functions and seeds across budgets; no new independence or statistical-significance claim is made.

## Incremental effect of restarts

Under the new no-revisit rule, ranked and ranked_random each add one target hit relative to the new single-descent result.
The added hit is CSTR30/B43/seed4, whose best objective changes from 3.1301981330254702 to 2.7695697198995095.
Both restart variants improve the best objective in 14 of the 140 Process jobs relative to new single descent.
Ranked uses 1,055 additional callbacks and ranked_random uses 1,249 additional callbacks relative to new single descent.
Random restarts therefore use 194 more callbacks than ranked restarts without additional target hits in this sample.
The earlier statement that Process restarts add no target hits needs qualification: it describes the previous repeated-evaluation implementation, not this no-revisit result.

## Evaluation cost and runtime

| Cohort | Previous callbacks | Previous repeat callbacks | New callbacks | Previous point cost (s) | New point cost (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Grid total | 37253 | 7274 | 31805 | 26844.960609 | 22115.608390 |
| Process single | 2441 | 349 | 2151 | 3555.537579 | 3167.324375 |
| Process ranked | 3371 | 558 | 3206 | 4733.708158 | 4403.545039 |
| Process ranked_random | 3400 | 566 | 3400 | 4756.396688 | 4524.513536 |

Removing repeated evaluations can both free budget for new configurations and end searches earlier; the change in total callbacks is not necessarily equal to the number of historical repeats.
Point costs are reconstructed from stored per-configuration timings, and completion time adds the measured search overhead and the original preparation cost.
These are not newly measured online NLP runtimes.
The recorded experiment elapsed time is 18.120759 s, and the launcher including packaging took 18.919380 s.
The short runtime is consistent with searching stored responses without new GDP/NLP solves.
The 1,470 published result records are accompanied by 1,190 historical-mode validation searches inside the original runner, for 2,660 search invocations in total.
Historical-mode searches are validation controls rather than extra primary benchmark results.

## Provenance and verification

Execution revision: `c186408728c6f95ac33a5465edd53035d85c5620`.
Host: `dantzig.ecn.purdue.edu`; logical CPU 47; socket 0; physical core 61; SMT sibling 95.
Numerical libraries used one thread, and every returned run reports effective affinity [47].
Started: `2026-10-31T23:08:29.688498+00:00`; finished: `2026-10-31T23:08:47.809257+00:00` (UTC).
Local Indiana time: `2026-10-31T19:08:29.688498-04:00` to `2026-10-31T19:08:47.809257-04:00`.
Python: `3.11.16`; packages: `{"numpy": "2.4.6", "pandas": "2.3.3", "scipy": "1.17.1"}`.
The original launcher exited zero; 1,158 records have completed status and 312 have budget_completed status.
Budget completion is an execution termination status and does not itself indicate target attainment.
Outer return SHA256: `aac54f826a19ebd81b5dfd376e792badcb79586161ce3c622fdd24e4b61ad88f`.
Original inner ZIP: `dsda_no_revisit_output_20261031_230829.zip`; 4512917 bytes; SHA256 `6ef180d61c02259fd36f9334221a201aa0b8dff39f79c0082e3fdb8e0dab4b9d`.
ZIP CRCs, 13,791 reference output member hashes, 263 sealed input hashes, and the execution source/input provenance checks pass.
The audit reconstructs all 40,562 callback responses and point costs from the stored tables, all 1,470 run summaries, and all 47 condition summaries directly from the individual records.
All 1,190 new primary paths preserve the distinct historical prefix, and all 280 restarted paths preserve their new single-descent prefix.
The server records 1,190 successful historical-mode replay checks.
The runner deletes temporary historical-mode traces, so those replay paths cannot be independently reconstructed from this return without executing the algorithm again.
This analysis verifies the reported replay-check flags and independently verifies the retained historical prefix, objectives, and target outcomes; it does not rerun any optimizer or solver locally.

## Files and reproduction

The original RETURN_A.zip and its checksum are preserved byte-for-byte in evidence/.
The audit reads historical reference archives and the Grid cost table from pinned Git objects already present in this repository.
PROVENANCE.json identifies their source revisions, archive members, and hashes.
The pinned source files are read as bytes for provenance checks and are never imported or executed.
analysis/cohorts.csv contains the overall comparisons, analysis/conditions.csv contains every function/model-budget comparison, and analysis/paired_runs.csv retains the paired individual records.
analysis/new_target_hits.csv identifies each new target hit, and analysis/restart_incremental.csv compares each restart with new single descent.
analysis/validation.json records the audit results and evidence limitations.
Reproduce the data-only audit and tables from this directory:

```bash
python3 analysis/analyze.py
```
