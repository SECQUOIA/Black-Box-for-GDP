# Lomustine flowsheet: seven DFO methods on simulation-based configuration responses

Run on 31 October 2026 on a local workstation from `experiments/lomustine_simulation` (see its README).
Each of the 36 configurations is evaluated by a stored PyNomad optimization of the PharmaPy simulation (SECQUOIA/pd_ising PR 28, commit `633cf923f07abba88970fa1fa816c4d06769751e`); no simulation was run here.
7 methods x budgets 10, 15, 20 x seeds 0-9 = 210 runs, all completed.

| Folder | Content |
|---|---|
| `runs_summary/` | `plan.json`, the harness `runs.csv`, `conditions.csv`, `best_known.json`, and `controller.log` |
| `evidence/lomustine_runs.zip` | the complete run directory (specs, callbacks, results, worker logs, response cache) and its SHA-256 |
| `analysis/` | output of `analyze.py`: target hits, first hits, and completion times per method and budget, the LaTeX table, and `facts.json` |

Target hits out of 10 (median completion time in hours):

| Method | B = 10 | B = 15 | B = 20 |
|---|---|---|---|
| D-SDA | 1 (1.15) | 4 (1.68) | 4 (1.97) |
| NOMAD | 6 (1.05) | 6 (1.22) | 6 (1.22) |
| RBFOpt | 8 (1.24) | 9 (1.70) | 10 (2.44) |
| MISO | 7 (1.13) | 10 (1.82) | 10 (2.66) |
| BAM | 0 (1.36) | 4 (1.90) | 6 (2.48) |
| FMQA-SA | 2 (1.47) | 3 (2.39) | 7 (3.09) |
| Uniform | 2 (1.48) | 4 (2.11) | 5 (2.91) |

Enumerating all 36 configurations takes 5.3 h. Median search times stay below 13 s, so the recorded inner optimizations make up almost all of the completion time.

Reproduce the analysis from the archive:

```bash
python -m zipfile -e results/lomustine_simulation_20261031/evidence/lomustine_runs.zip /tmp/lomustine
python experiments/lomustine_simulation/analyze.py --runs /tmp/lomustine/lomustine_full --output /tmp/lomustine_analysis
```
