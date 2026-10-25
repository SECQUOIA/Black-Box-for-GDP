# CSTR30 initialization adoption for publication

This follow-up analysis uses completed records and runs no optimizer or NLP solver.
The original 8,190-record analysis is retained, with 120 finite-penalty CSTR D-SDA/RBFOpt records overlaid before replacing all 50 CSTR30 records.
The primary Process comparison contains 700 runs over 14 conditions and ten paired seeds per method.
Relative to the finite-penalty primary cohort, the other 650 Process runs are unchanged.
All Grid runs and historical solver-option contrasts retain their original records.
CSTR30 uses the mass-balance/zero-recycle initializer, the existing reference target, and each new evaluation attempt's own objective, acceptance and measured cost.
The archive retains the one GAMS execution error at [27,10], which none of the 50 new searches visited.

| Method | CSTR30 hits / 10 | All CSTR hits / 60 | CSTR30 median completion (s) |
| --- | ---: | ---: | ---: |
| D-SDA | 2 | 14 | 53.08 |
| RBFOpt | 9 | 45 | 101.96 |
| BAM | 2 | 18 | 115.41 |
| FMQA-SA | 1 | 9 | 101.19 |
| Uniform | 1 | 11 | 65.20 |

The primary cohort visits 2,040 distinct model/size/coordinate keys using 16,206 charged callbacks.
The complete Process inventory contains 1,266 accepted configurations, including 464 of the 900 CSTR30 coordinates.
Completion cost is measured lookup-search time minus measured lookup time plus the new recorded evaluation cost for every callback, including repeats and rejected points.
CSTR30 timing includes its recorded initialization and artifact-retention work, while other cases retain their existing measurement conventions.
These conditional recorded-path estimates do not isolate the causal timing effect of initialization or establish a pure IPOPT slowdown.
Per-condition success intervals use the existing exact binomial convention, and paired differences use 2,000 percentile bootstrap replications with seed 20261020 over paired seeds within each condition.
The paired intervals are descriptive, can degenerate with ten seeds, and are neither equivalence tests nor multiplicity-adjusted superiority claims.
Dynamic budgets and CSTR sizes remain separate conditions, with the all-CSTR success sum used only as a descriptive aggregate.
The four Process figures retain the existing publication colors, labels and panel layout.
Historical solver-versus-genetic comparisons are neither regenerated nor relabeled as comparisons against this adopted initialization.

The FMQA-SA fallback tables count the archived proposal sources for all 140 Process runs, replacing only the ten CSTR30 traces.
These counts describe candidate provenance and do not isolate the causal contribution of model fitting or annealing.

Reproduce in a new directory from the repository root:

```bash
python -m review_comparison.cstr30_publication --output /tmp/cstr30-publication-new
python -m pytest tests/test_cstr30_publication.py -q
```

Input, source and output hashes, retained execution revisions and the generation environment are recorded in manifest.json.
