# D-SDA 절대 개선 허용오차 변경 실험

This independent D-SDA absolute-improvement-tolerance experiment changes the minimization acceptance condition to `old_value - new_value > 1e-5`.
Grid target hits decrease from 382/1,050 to 374/1,050, while Process target hits remain 74/140 with identical successful seeds in every condition.
All 1,190 runs completed with zero failures, missing runs, or additional NLP calls.
These sensitivity results are retained separately and are not adopted as the manuscript's representative results.
This experiment does not claim to reproduce the complete original LD-SDA implementation.

## Grid results

Each budget contains 21 functions and seeds 0 through 9, giving 210 paired runs.

| Budget | Existing hits | New hits | Existing only | New only | Existing callbacks | New callbacks |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 13 | 13 | 0 | 0 | 2,094 | 2,094 |
| 30 | 75 | 74 | 2 | 1 | 5,988 | 5,970 |
| 50 | 89 | 88 | 2 | 1 | 8,871 | 8,892 |
| 70 | 101 | 98 | 3 | 0 | 10,255 | 10,424 |
| 100 | 104 | 101 | 3 | 0 | 10,825 | 11,136 |
| Total | 382 | 374 | 10 | 2 | 38,033 | 38,516 |

The aggregate target-hit fraction changes from 36.38% to 35.62%, a decrease of about 0.76 percentage points.
Callback paths change in 91 runs, callback counts change in 67 runs, and final observed objectives change in 71 runs.
Sixteen of the 21 functions retain exactly the same callback paths for all budgets and seeds.
The functions with changed paths are Camel3, Csendes, Easom, Michalewicz, and Rosenbrock.
The net target-hit changes are Easom −6, Michalewicz −3, and Rosenbrock +1.
The discordant pairs include the same function and seed at multiple budgets, so they are not independent replications.

Although the aggregate change is small, individual objective losses can be large.
At budget 100, Easom seed 5 changes from normalized objective 0 to 0.9906354089254488, and Michalewicz seed 3 changes from 0 to 0.3295049350714533.
Their returned paths reject small improving steps of approximately 2.65e-6 and 1.70e-6, respectively, that the original search accepted before reaching a better region.
Csendes contributes 855 additional callbacks while its target-hit count is unchanged.
The larger movement tolerance can stop an individual search before the unchanged 1e-12 Grid target termination condition is met, causing the multistart wrapper to continue from additional starting points.
Thus a larger improvement tolerance does not necessarily reduce total callback counts.

## Process results

Each model–budget condition contains the same ten seeds as its adopted baseline.

| Case | Budget | Existing hits | New hits | Existing callbacks | New callbacks |
|---|---:|---:|---:|---:|---:|
| Column | 13 | 5 | 5 | 128 | 128 |
| CSTR5 | 8 | 2 | 2 | 76 | 76 |
| CSTR10 | 15 | 2 | 2 | 133 | 125 |
| CSTR15 | 22 | 2 | 2 | 175 | 173 |
| CSTR20 | 29 | 3 | 3 | 208 | 203 |
| CSTR25 | 36 | 3 | 3 | 264 | 259 |
| CSTR30 | 43 | 2 | 2 | 272 | 266 |
| Dynamic | 12 | 4 | 4 | 120 | 120 |
| Dynamic | 15 | 5 | 5 | 150 | 150 |
| Dynamic | 20 | 8 | 8 | 182 | 182 |
| Dynamic | 30 | 10 | 10 | 217 | 217 |
| Dynamic | 37 | 10 | 10 | 221 | 221 |
| Dynamic | 50 | 10 | 10 | 221 | 221 |
| Small Batch | 10 | 8 | 8 | 100 | 100 |
| Total | — | 74 | 74 | 2,467 | 2,441 |

All 14 conditions retain the same successful seeds and first-hit callback indices.
Final observed objectives are exactly equal in 138 runs, and the remaining two differ by only approximately 8e-11.
Only six CSTR paths change, and all six miss the target under both settings.
These are CSTR10 seeds 5 and 6, CSTR15 seed 4, and CSTR20, CSTR25, and CSTR30 seed 8.
They stop without following very small improvements around objective 3.130198133, saving 26 callbacks in total.
The descriptive CSTR subtotal remains 14/60 hits with callbacks decreasing from 1,128 to 1,102.

Existing RBFOpt, BAM, FMQA-SA, and uniform results are retained without rerunning them.
The target-hit ordering between D-SDA and each unchanged comparator is unchanged in every Grid budget and Process condition.
This is a descriptive comparison and is not a statistical equivalence claim.

## Protocol and provenance

The adopted baseline is `results/column_publication_20261025/tables/run_records.csv` at PR #52 head `5e94df72b472a5039c35518b685de6080cf8d67f` on `review/cstr15-dantzig-results`.
The initial local checkout revision was `2d1e2e49158d924f1fe589a55f7d7f210bf5f28b`, and preparation took place in a separate detached worktree at the PR head.
The Dantzig repository checkout was `7f110f9122298a4f492d8ad464e782b2435b167b`, while execution used the separate frozen input/source package based on `5e94df72b472a5039c35518b685de6080cf8d67f` plus uncommitted additions identified by file SHA256 hashes.
The run started at 19:43:49 and ended at 20:04:33 on October 27, 2026 in America/Indiana/Indianapolis; the original UTC timestamps remain unchanged in the execution manifest.
The environment was Dantzig Python 3.11.16, NumPy 2.4.6, SciPy 1.17.1, and pandas 2.3.3.
Execution was sequential on shared logical CPU 2 with all numerical-library thread limits set to one.
Search wall times retain concurrent-load and tracing costs, so no speed comparison or speedup claim is made against the historical runs.

The latest CSTR30 initialization results and Column logical domain `[8..15] × [1..8]` with budget 13 are preserved.
Initial configurations and their order, seeds, candidate domains, budgets, finite Process rejection penalty 1e6, repeated-evaluation charging, cached initial values, and starting-point selection are unchanged.
Process retains its 2,100-second watchdog and terminal-callback `BudgetStop` behavior, and Grid retains its original absence of a watchdog limit.
Only D-SDA is executed, and every response comes from saved configuration objectives and statuses.
Missing stored responses abort execution rather than invoking a solver.
The worker blocks solver/model imports and child-process creation, and no such attempts are recorded.

The new optional `improvement_abs_tol` controls neighbor acceptance, line-search acceptance, the existing connected `best_seen` updates, and multistart `best_run` updates.
The observed incumbent used for reporting remains the best value over all callbacks without tolerance filtering.
No relative improvement criterion is added, and calls that omit the new setting keep the original comparison arithmetic.
Tie handling and Grid target termination keep `tol=1e-12`.
The existing common outcome rule remains `abs(best_objective - target) <= 1e-5 * max(1, abs(target))` for all methods.

## Retained evidence and independent verification

The [original return ZIP](../archives/dsda_abs1e5_sharedcpu_v2_return.zip) is preserved byte-for-byte with SHA256 `555445b52d2fb40c58cc6e4a4a5321592dd6f2bd5cb48ead6ca31fc8174a8964`.
It contains all 1,190 new result files, callback logs, movement paths or partial paths, baseline records, exact inputs and source files, tests, commands, environments, and repair diagnostics.
The `returned/` directory contains byte-identical copies of the server's paired comparison, summary tables, execution manifest, CPU allocation record, and unit-test log.
The paired table preserves original outcome categories and separately identifies termination information recovered by baseline verification when it was not explicitly archived.

Run the independent verification from the repository root with the Python standard library alone.

```bash
python results/dsda_abs1e5_20261027/verify.py
```

The verifier reads archived data without importing or executing archived experiment code and without running an optimizer, solver, or subprocess.
It verifies 6,363 archived output hashes, 248 execution input/source hashes, exact pairing, original categories, callback order and counts, initial configurations, budgets, best objectives, first-hit indices, finite penalties, watchdog outcomes, all summary tables, and unchanged comparator hit orderings.
The server records 11 protocol tests plus five repository-identity tests and four CPU-allocation tests.
The independently reproduced report is retained in `audit.json`, and `manifest.json` hashes the published files.
This addition does not modify prior execution records, lookup tables, success rules, manuscript sources, Overleaf material, or existing figures.
