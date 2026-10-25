# Column logical-domain/B13 adoption for publication

This analysis replaces all fifty primary Column runs with the completed 64-configuration/B13 follow-up.
The other 650 primary Process runs, every Grid run, and historical solver-option results are unchanged.
The original experimental archives, targets, acceptance records and execution revisions are preserved.
The Column candidate rectangle is exactly the original model's logical domain; algebraic feasibility remains determined by the retained evaluation records.
All methods share three ordered initial configurations and retain ten seeds in their denominator.
The new domain, budget and regenerated initial designs differ together from the historical cohort, so their separate effects are not identified.

| Method | Column hits / 10 | Median reconstructed completion (s) |
| --- | ---: | ---: |
| D-SDA | 5 | 35.43 |
| RBFOpt | 4 | 54.60 |
| BAM | 1 | 27.50 |
| FMQA-SA | 4 | 41.82 |
| Uniform | 1 | 21.69 |

Seed 6 includes the reference target as its third shared initial point, accounting for the only BAM and uniform successes.
RBFOpt does not improve target-hit frequency over D-SDA on this condition; a one-seed difference does not establish a general ranking.
RBFOpt's larger reconstructed cost is associated with expensive unaccepted configurations, while its median search overhead decreases relative to the historical run.
Completion costs combine measured search overhead and unchanged same-attempt point costs charged on every callback, including repeats and unsuccessful evaluations.
They are not measured online optimizer-NLP runtimes.
The adopted 700-run cohort has 16,067 callbacks and 2,024 distinct visited configuration keys.
Its candidate inventory contains 2,438 configurations, including 1,266 accepted responses.
Paired percentile intervals resample ten paired seeds within each condition with seed 20261020 and 2,000 replications.
They are descriptive, can degenerate, and are not equivalence tests or multiplicity-adjusted evidence of superiority.
The FMQA-SA proposal counts replace the ten Column traces and retain every other recorded proposal source.
This analysis runs no optimizer, fitting, annealing or NLP solver.

Reproduce in a new directory:

```bash
python -m review_comparison.column_publication --output /tmp/column-publication-new
python -m pytest tests/test_column_publication.py -q
```
