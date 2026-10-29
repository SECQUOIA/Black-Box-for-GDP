# D-SDA tolerance adoption

This is a data-only publication analysis of completed experiments.
No optimizer, NLP solver, model fitting, or server experiment is invoked.
Only the 1,050 Grid and 140 Process D-SDA records replace the preceding Column publication cohort.
Every other method record is preserved exactly.

D-SDA accepts a move only for a strict absolute objective improvement greater than 1e-5.
Grid target stopping uses the common success predicate on the best observed objective at the existing post-descent checkpoint, after the budget-exhaustion check.
It does not interrupt a descent immediately at the first target observation.
Process retains its single best accepted initial configuration and no target-based stopping.
The objective-improvement threshold, target test, and primal-feasibility threshold have different meanings.

Completion estimates are rebuilt from each new callback path, charging the unchanged same-attempt point cost for every callback, including repeats and rejected evaluations.
Retained search time is the new measured search duration minus its recorded lookup time; unchanged preparation cost is added once.
These are fixed-path reconstructed costs, not measured online optimizer-NLP runtimes or evidence of a cross-run wall-time speedup.
The Grid and Process execution environments and original provider revisions remain in their separate immutable return archives.

Pairing uses scope, case, budget, seed and method, with exactly seeds 0 through 9 in every group.
Grid bootstrap samples intact functions in sorted function order; Process bootstrap samples paired seeds separately within each condition.
The descriptive percentile intervals use seed 20261020 and 2,000 replicates and do not establish equivalence or general superiority.

| Grid budget | D-SDA target hits / 210 | Callbacks |
|---|---:|---:|
| 10 | 13 | 2094 |
| 30 | 74 | 5925 |
| 50 | 88 | 8667 |
| 70 | 98 | 10006 |
| 100 | 101 | 10561 |

The adopted Process cohort retains 315/700 target hits with 16,041 callbacks and 2,024 distinct visited configuration keys.
Process target hits and first-hit indices remain unchanged; CSTR remains 14/60 for D-SDA and 45/60 for RBFOpt.
The separate target-stopping follow-up preserves the preceding improvement-run Grid successes; relative to the previously published cohort the improvement change reduces Grid D-SDA hits from 382 to 374.

Reproduce in a fresh directory:

```bash
python -m review_comparison.dsda_publication --output /tmp/dsda-publication-replay
python -m pytest tests/test_dsda_publication.py -q
```
