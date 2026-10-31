# Dantzig D-SDA without re-evaluation

Execution revision: `c186408728c6f95ac33a5465edd53035d85c5620`.
Host: `dantzig.ecn.purdue.edu`; CPU: `{'mode': 'pinned', 'cpu': 47, 'effective_cpus': [47], 'selection': None, 'exclusive_reservation': False}`.
Started: `2026-10-31T23:08:29.622772+00:00`; finished: `2026-10-31T23:08:48.542152+00:00` (UTC).
Python: `3.11.16`; packages: `{"numpy": "2.4.6", "pandas": "2.3.3", "scipy": "1.17.1"}`.
All numerical libraries used one thread.
The experiment used stored configuration responses and performed no new GDP or NLP solves.
All 1,470 planned jobs passed the original checks and the wrapper audit, with no missing or duplicate results.

| Cohort | Target hits | Published target hits |
| --- | ---: | ---: |
| ranked | 80/140 | 74 |
| ranked_random | 80/140 | 74 |
| single | 79/140 | 74 |
| grid_B100 | 101/210 | 101 |
| grid_B10 | 13/210 | 13 |
| grid_B30 | 78/210 | 74 |
| grid_B50 | 91/210 | 88 |
| grid_B70 | 101/210 | 98 |

The published primary Process baseline used a single descent with 74/140 hits; both previous restart diagnostics also had 74/140 hits.
The checks preserve no repeats, historical replay, the distinct published prefix, non-worsening objectives, retained historical hits, and matching first descents.
Original return: `evidence/dsda_no_revisit_output_20261031_230829.zip` (4512917 bytes).
SHA256: `6ef180d61c02259fd36f9334221a201aa0b8dff39f79c0082e3fdb8e0dab4b9d`; ZIP CRC validation passed.

Reproduce on Dantzig from the pinned worktree:

```bash
export DSDA_PYTHON=/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig/bin/python
bash experiments/dsda_no_revisit/run_dantzig.sh
```

The original ZIP, checksum, log, and summary files are preserved without modification.
No manuscript, model, optimizer, or previous result was changed.
