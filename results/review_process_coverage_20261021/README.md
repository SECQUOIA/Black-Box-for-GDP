# Primary Process configuration coverage

This follow-up addresses minor review comment 2 about the scope of the visited-configuration count in Table 1.
The current primary comparison comprises DSDA, RBFOpt with its default genetic candidate search, BAM, FMQA-SA and uniform sampling.
Each method retains all ten seeds for each of 14 model--budget conditions, giving 700 runs.
The retained RBFOpt (solver) runs belong to the supplementary comparison and are excluded from primary coverage.
No optimizer, NLP, training or annealing experiment was rerun.

## Definition and result

A configuration key identifies the model, its size where applicable, and its integer coordinates.
The `case` field encodes CSTR size, so the same coordinate in CSTR5 and CSTR10 is counted separately.
Methods, seeds and budgets are not part of this key.
All six Dynamic budgets share one 72-configuration domain and are unioned rather than counted as separate domains.
All charged callbacks are retained, including initialization, repeated visits, rejected points, terminal callbacks and callbacks from the failed DSDA run.
Deduplication changes the coverage count only; repeated calls continue to incur their saved costs in the performance analysis.
The 16,252 charged calls visit 2,050 of the 2,455 measured configuration keys.

| Model | Measured inventory | Primary runs | Charged calls | Distinct visited keys |
|---|---:|---:|---:|---:|
| Column | 81 | 50 | 787 | 80 |
| CSTR 5 | 25 | 50 | 396 | 25 |
| CSTR 10 | 100 | 50 | 733 | 97 |
| CSTR 15 | 225 | 50 | 1,055 | 208 |
| CSTR 20 | 400 | 50 | 1,368 | 348 |
| CSTR 25 | 625 | 50 | 1,704 | 514 |
| CSTR 30 | 900 | 50 | 2,038 | 679 |
| Small Batch | 27 | 50 | 500 | 27 |
| Dynamic | 72 | 300 | 7,671 | 72 |
| **Total** | **2,455** | **700** | **16,252** | **2,050** |

The model rows represent disjoint keys and therefore sum to the total.
Method-specific coverage overlaps and must not be added to obtain the union.

| Method | Runs | Charged calls | Distinct visited keys |
|---|---:|---:|---:|
| DSDA | 140 | 2,532 | 690 |
| RBFOpt | 140 | 3,430 | 877 |
| BAM | 140 | 3,430 | 726 |
| FMQA-SA | 140 | 3,430 | 1,215 |
| Uniform sampling | 140 | 3,430 | 1,273 |

## Reconciliation with the earlier count

The earlier 1,790 count came from the October 15 campaign of 560 runs and 12,822 callbacks, containing RBFOpt (solver), DSDA, BAM and FMQA-SA.
It was carried into the revised Table 1 footnote after the primary comparison changed.
The current comparison retains the 420 DSDA/BAM/FMQA-SA runs, replaces 140 solver-option runs with 140 RBFOpt runs, and adds 140 uniform-sampling runs.
The two visited sets share 1,739 keys; 51 belong only to the earlier set and 311 only to the current set.
Consequently, 1,790 - 51 + 311 = 2,050.
This is a change in the population being summarized, not a correction to the historical trajectories or their original count.

## Evidence and reproduction

[configuration_coverage.csv](configuration_coverage.csv) lists all 2,455 inventory keys with their acceptance/status records, current method-specific callback counts and historical callback counts.
Counting rows with `primary_callbacks > 0` gives 2,050; counting `historical_callbacks > 0` gives 1,790.
[runs.csv](runs.csv) lists all 700 selected runs, their callback counts, deduplicated coordinate lists, and exact source file or archive-member references with hashes.
An independent union of the run coordinate lists reproduces the configuration ledger.
[case_summary.csv](case_summary.csv), [method_summary.csv](method_summary.csv) and [summary.json](summary.json) expose the aggregates above.
[manifest.json](manifest.json) records input, analysis-source and output hashes and preserves the original execution-provider revision.

```sh
python -m review_comparison.visited_keys --output /tmp/process-coverage-new
python -m pytest tests/test_review_visited_keys.py -q
```

Use a fresh output directory; the command refuses to overwrite existing results.
The analysis verifies the completed-run table and return archive against their retained manifest, historical callbacks against the retained checkout replay, and all nine cost inventories against their original hashes.
It also verifies the exact 700-run selection against the manuscript run table, complete condition/seed membership, sequential callback indices, callback totals, inventory membership and acceptance flags.
Missing, duplicate or inconsistent records raise errors instead of being omitted.
Two fresh temporary reproductions and this retained output agree byte for byte across all six generated files.
Ten coverage tests and the targeted lint check pass.
Original experiment records, previous audit classifications, performance data, figures and prior manifests remain unchanged.

## Response to the reviewer

We corrected the Table 1 footnote to report the union of configurations visited by the current 700-run primary Process comparison.
The five methods and the 14 model--budget conditions with ten seeds per condition are now stated explicitly, and the retained RBFOpt (solver) runs are excluded.
The 16,252 charged callbacks yield 2,050 distinct model/size/coordinate keys after deduplication across methods, budgets and seeds.
Section 4.3.2 now reports the same scope and count.
The earlier 1,790 value described the historical 560-run campaign; the accompanying per-model summary and configuration-level ledger reconcile the two populations without modifying any historical result.
