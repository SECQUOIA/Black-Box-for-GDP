# Full GDP comparison — September 25 CPU 2 rerun

All 36 jobs completed and all 36 saved solutions pass a fresh original-GDP feasibility check. Twenty-seven report `optimal`; nine return at the solver time limit with feasible incumbents. An `optimal` termination string alone is not a global-optimality guarantee.

GDP ran on CPU 2 (physical core 2, sibling 50); FMQA Grid used CPU 0 and FMQA cases CPU 4. The recorded physical cores are distinct, with one-thread settings. CPU affinity is not an exclusive reservation; background server load was not recorded.

Each cell is **objective / completion seconds including one shared template preparation**. TL = solver time limit; † = reported bound conflicts with another saved feasible solution. Worker launch, preflight and final packaging are excluded. Lower objectives are better.

| Model | RIC + IPOPT | GLOA + IPOPT | Big-M + BARON | Hull + BARON |
|---|---:|---:|---:|---:|
| cstr_5 | 9.8947368 / 14.20s | 9.8947368 / 8.82s | 3.0620136 / 9.12s | 3.0620146 / 14.86s |
| cstr_10 | 9.8947368 / 56.12s | 9.8947368 / 15.36s | 2.8894835 / 123.74s | 2.8895358 / 126.47s † |
| cstr_15 | 9.8947368 / 168.85s | 9.8947368 / 11.65s | 2.829394 / 1799.00s TL | 2.8293941 / 940.36s |
| cstr_20 | 9.8947368 / 338.67s | 9.8947368 / 12.95s | 2.7994063 / 1798.72s TL | 2.7994064 / 1797.44s TL |
| cstr_25 | 9.8947368 / 716.51s | 9.8947368 / 39.03s | 2.7814826 / 1797.67s TL | 2.7814826 / 1797.41s TL |
| cstr_30 | 2.7716214 / 1287.64s | 3.6687157 / 6.41s | 2.7695698 / 1797.31s TL | 2.8093862 / 1466.60s † |
| column | 19346.125 / 82.21s | 20916.392 / 9.00s | 19853.723 / 34.36s † | 20837.08 / 1797.17s TL |
| dynamic | -212.00879 / 104.00s | -197.14013 / 147.03s | -207.62612 / 1797.51s TL | -28.596739 / 1797.77s TL |
| small_batch | 167427.66 / 12.84s | 167427.66 / 10.80s | 167427.66 / 0.55s | 167427.66 / 0.57s |

## Findings

- CSTR30 Big-M reaches the lookup target (2.769569795) and returns its solution at the 30-minute cap. Hull returns 2.809386231, about 1.44% above the target, despite an `optimal` flag. Its reported lower bound exceeds the independently checked Big-M feasible objective; the claimed global certificate is excluded from derived tables.
- Column: RIC matches the target at about 82.21 s. The Big-M lower bound still conflicts with this better feasible solution.
- Dynamic: RIC matches the target at about 104.00 s. GLOA, Big-M and Hull retain gaps of about 7.01%, 2.07% and 86.51%.
- Small Batch: all four methods match the target. Big-M/Hull complete in about 0.55/0.57 s including preparation.
- CSTR5–25 GDPopt still returns approximately 9.894737. Recorded IPOPT subproblem failures persist with separate CPUs; they are not evidence that the corresponding original GDP configurations are mathematically infeasible. Initialization and local NLP convergence remain unresolved factors.
- CSTR10 Hull also has a numerical bound conflict: its objective differs from the better Big-M solution by about 1.81e-5 relatively. Both pass the recorded 1e-5 primal-feasibility threshold; this is a tolerance-sensitive comparison.

## Target attainment

Target hits across nine models: RIC + IPOPT: 3/9, GLOA + IPOPT: 1/9, Big-M + BARON: 6/9, Hull + BARON: 6/9. These are nine different GDP instances, not repeated stochastic success probabilities. Success uses the existing lookup target and absolute error <= 1e-5 × max(1, |target|).

## Current outputs

- `comparison.csv`: all 36 objectives, target hits, completion times and bound flags.
- `audit.json`: CPU topology, checksums, NLP statuses and bound conflicts.
- `solution_rechecks.json`: independent evaluations of all saved vectors.
- `gdp_objectives_and_times.png`: slide-ready table (generated locally).

Reproduce without solving:

```bash
python gdp_comparison_analysis.py
```
