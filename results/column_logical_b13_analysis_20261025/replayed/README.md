# Column logical-domain follow-up

50 of 50 new jobs are sealed, 0 are execution failures, and 0 remain uncompleted.
No new original GDP NLP calculation is performed; the oracle reuses the 64 original IPOPT records, including all 35 unaccepted coordinates.
The original 81-coordinate/B16 cohort and the new 64-coordinate/B13 cohort are distinct experiments.
The new domain and budget change together, so their difference is not a causal estimate of either factor alone.
The target, acceptance criteria, failure policies, archived algorithms and native stopping rules are preserved.
Every method retains all ten seeds in its denominator, including algorithm failures.
A target first observed at callback 13 is retained even when the callback raises the budget-stop exception.
Reported completion times combine measured new search overhead with old same-attempt point costs and are not online optimizer-NLP measurements.
The time profile uses the full-run reconstructed completion time for successful runs, matching the publication.

| Condition | Method | Sealed | Failed | Hits / 10 | Median estimated completion (s) | Median search overhead (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 81_B16 | dsda | 10 | 1 | 5 | 37.9086 | 0.00817824 |
| 81_B16 | rbfopt | 10 | 0 | 5 | 33.5407 | 0.337729 |
| 81_B16 | bam | 10 | 0 | 0 | 37.9744 | 0.194907 |
| 81_B16 | fmqa_sa | 10 | 0 | 4 | 29.7249 | 8.64072 |
| 81_B16 | uniform_without_replacement | 10 | 0 | 0 | 26.2868 | 0.00834858 |
| 64_B13 | dsda | 10 | 0 | 5 | 35.4339 | 0.00685844 |
| 64_B13 | rbfopt | 10 | 0 | 4 | 54.6034 | 0.226033 |
| 64_B13 | bam | 10 | 0 | 1 | 27.4999 | 0.0176923 |
| 64_B13 | fmqa_sa | 10 | 0 | 4 | 41.8185 | 6.8498 |
| 64_B13 | uniform_without_replacement | 10 | 0 | 1 | 21.6888 | 0.00716491 |

Pending runs are not reported as measured failures or zero-duration results.
Partial-run rates and available-time medians are provisional until all ten jobs for that method are sealed.
All baseline and new per-seed records are in runs.csv, with callback details in callback_ledger.csv.
profiles.csv preserves the plotted coordinates, and verification.json records the checks and job counts.
