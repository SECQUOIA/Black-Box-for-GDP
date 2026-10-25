CSTR30 initialization follow-up

This experiment changes only the initialization used for CSTR30.
The primary comparison retains the manuscript final-best absolute target rule and the original reference.
The finite-penalty D-SDA and genetic RBFOpt records replace their older manuscript search records in the explicitly identified baseline.
Any-hit results are reported separately because the historical finite-penalty report used that definition.
Actual coordinate NLP calls: 465; separate preflight NLP calls: 1; process NLP calls during lookup search: 0.
Accepted coordinates: 458 -> 464 out of 900.
Reference coordinate [30, 30]: 2.7695697198995095 -> 2.7695697198995095.
The new table minimum is 2.7695697198995095 at [30, 30].
The difference from the fixed reference is 0.0.

Method | Old hits | New hits | Both | New only | Old only | Neither | New any-hit
--- | --- | --- | --- | --- | --- | --- | ---
dsda | 3/10 | 2/10 | 2 | 0 | 1 | 7 | 2/10
rbfopt | 9/10 | 9/10 | 8 | 1 | 1 | 0 | 9/10
bam | 2/10 | 2/10 | 2 | 0 | 0 | 8 | 2/10
fmqa_sa | 1/10 | 1/10 | 1 | 0 | 0 | 9 | 1/10
uniform_without_replacement | 1/10 | 1/10 | 1 | 0 | 0 | 9 | 1/10

All six CSTR sizes retain every old record for N=5, 10, 15, 20 and 25.
dsda: 15/60 -> 14/60.
rbfopt: 45/60 -> 45/60.
bam: 18/60 -> 18/60.
fmqa_sa: 9/60 -> 9/60.
uniform_without_replacement: 11/60 -> 11/60.

The new measured point-evaluation cost sums to 1719.000150 seconds.
Measured search time sums to 328.056496 seconds.
Completion estimates subtract lookup time from measured search time and add the new per-callback evaluation costs, including repeats.
Timing also includes recorded initialization and artifact-retention overhead and is not a pure solver-time comparison.
Baseline residual records contain only the combined maximum, so separate old constraint and bound residuals remain unavailable.
Better-than-reference objectives that miss the absolute target rule are explicitly flagged in paired_runs.csv.
No raw baseline record, historical manifest, manuscript, Overleaf file or figure was modified.
Whether to adopt this experiment as a representative manuscript result remains a later decision.
