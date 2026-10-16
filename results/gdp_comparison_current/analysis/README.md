# Current full-GDP results — October 1 complete results

**45/45 selected jobs completed**: RIC, GLOA and LOA with BARON/HiGHS on nine original GDP models, plus Big-M/Hull with BARON. All 45 available selected solution vectors pass an independent original-GDP feasibility check at tolerance 1e-5. Completion includes time-limited jobs, not just optimal terminations.

The final October 1 archives replace the earlier partial RIC/GLOA snapshot. Both external ZIP checksums and all internal SHA256SUMS entries were verified; extracted files match the archived bytes. The 12 CSTR records already present in the partial copy are unchanged.

Big-M/Hull retain September 25 results, independently rechecked here. Historical feasible IPOPT vectors remain evidence when checking reported bounds; their times are not substituted. RIC/GLOA and Big-M/Hull record logical CPU 2 (physical core 2, socket 0); LOA records logical CPU 6 (physical core 8, socket 0). RIC/GLOA and LOA overlapped on separate physical cores, with one thread each. CPU affinity does not establish an otherwise idle server or remove shared-resource contention.

Each completed cell is **objective / seconds including template preparation**. TL = time limit; † = BARON bound conflicts with a better saved feasible solution. Preflight, process launch and archiving are excluded. Missing cells are not zero or failures.

| Model | RIC BARON/HiGHS | GLOA BARON/HiGHS | LOA BARON/HiGHS | Big-M BARON (Sep 25) | Hull BARON (Sep 25) |
|---|---:|---:|---:|---:|---:|
| cstr_5 | 3.061984 / 31.27s | 3.1301981 / 3.76s | 3.061984 / 31.82s | 3.0620136 / 9.12s | 3.0620146 / 14.86s † |
| cstr_10 | 2.8895081 / 214.06s | 3.447964 / 4.56s | 2.8895081 / 234.13s | 2.8894835 / 123.74s | 2.8895358 / 126.47s † |
| cstr_15 | 2.9660174 / 1798.83s TL | 3.522552 / 26.19s | 2.8293506 / 1799.38s TL | 2.829394 / 1799.00s TL | 2.8293941 / 940.36s † |
| cstr_20 | 2.9095042 / 1799.04s TL | 3.616123 / 6.79s | 2.8895081 / 1797.72s TL | 2.7994063 / 1798.72s TL | 2.7994064 / 1797.44s TL |
| cstr_25 | 2.859437 / 1797.05s TL | 3.6478181 / 85.20s | 2.7951055 / 1797.46s TL | 2.7814826 / 1797.67s TL | 2.7814826 / 1797.41s TL |
| cstr_30 | 2.8379523 / 1792.52s TL | 3.1543081 / 718.80s | 2.7844377 / 1798.92s TL | 2.7695698 / 1797.31s TL | 2.8093862 / 1466.60s † |
| column | 22271.549 / 1797.54s TL | 22271.549 / 1798.15s TL | 22271.549 / 1797.77s TL | 19853.723 / 34.36s † | 20837.08 / 1797.17s TL |
| dynamic | -119.3831 / 1797.71s TL | -119.3831 / 1797.55s TL | -119.3831 / 1797.84s TL | -207.62612 / 1797.51s TL | -28.596739 / 1797.77s TL |
| small_batch | 167427.66 / 12.86s | 167427.66 / 14.49s | 167427.66 / 5.11s | 167427.66 / 0.55s | 167427.66 / 0.57s |

## Findings

- The new RIC results improve CSTR5–25 relative to the old IPOPT run, but RIC reaches its time limit on CSTR15/20/25/30. All six CSTR GLOA runs report `optimal` while returning worse objectives than the corresponding feasible RIC solutions. The GDPopt global certificate and bound-validity flags remain false.

- LOA returns better feasible objectives than RIC on CSTR15/20/25/30, under the same 30-minute per-job limit. CSTR5/10 and Small Batch agree with RIC within the comparison tolerance.

- Column and Dynamic return the same incumbent for RIC/GLOA/LOA: approximately 22271.54872 and -119.3830994. Each has one initialization MIP and one time-limited BARON NLP; the strict subproblem guard stops without cutting off an unproven configuration. These results do not demonstrate that the three search algorithms converged to the same optimum.

- LOA CSTR15 returns 2.829350618, below the historical lookup target by about 1.53e-5 relatively. It passes the recorded primal-feasibility tolerance, but this is not a new global-optimality proof. Its signed objective gap is retained. A better-than-target solution counts as attainment, even if it falls outside the old symmetric target-match tolerance.

## Target attainment and termination

All models are minimization problems. `target_attained` means objective <= target + 1e-5 × max(1, |target|). The historical `target_hit` column is retained separately and means absolute objective error within that tolerance. The denominator is nine different models, not repeated stochastic trials. These are completion-time records, not first-hit times.

| Method | Completed | At target or better | Absolute target match | Time limit |
|---|---:|---:|---:|---:|
| RIC | 9/9 | 3/9 | 3/9 | 6 |
| GLOA | 9/9 | 1/9 | 1/9 | 2 |
| LOA | 9/9 | 4/9 | 3/9 | 6 |
| BIGM | 9/9 | 7/9 | 6/9 | 5 |
| HULL | 9/9 | 6/9 | 6/9 | 4 |

## Files and reproduction

- `comparison.csv`: completed jobs only, with exact source directory/date and solver policy.
- `method_summary.csv`: target attainment, symmetric matches and time limits by method.
- `pending_jobs.json`: empty for this completed import.
- `audit.json`, `solution_rechecks.json`: hashes, solver statuses and independent feasibility checks.
- `gdp_objectives_and_times.png` / `.pdf`: published comparison figure.

The [September 25 IPOPT comparison](../../gdp_comparison_20260925/analysis/README.md) remains historical. The [RIC/GLOA final archive](../../gdp_comparison_20261001/README.md) and [LOA final archive](../../gdp_comparison_loa_20261001/README.md) document the new sources. The previously prepared six-job follow-up is unnecessary: the original RIC/GLOA run finished.

Reproduce without solving:

```bash
python gdp_current_analysis.py
```
