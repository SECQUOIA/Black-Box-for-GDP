# Lomustine flowsheet: seven DFO methods on simulation-based configuration responses

Run on 31 October 2026 on a local workstation from `experiments/lomustine_simulation` (see its README).
Each of the 36 configurations is evaluated by a stored PyNomad optimization of the PharmaPy simulation (SECQUOIA/pd_ising PR 28, commit `633cf923f07abba88970fa1fa816c4d06769751e`); no simulation was run here.
7 methods x budgets 10, 15, 20 x seeds 0-9 = 210 runs, all completed.

| Folder | Content |
|---|---|
| `runs_summary/` | `plan.json`, the harness `runs.csv`, `conditions.csv`, `best_known.json`, and `controller.log` |
| `evidence/lomustine_runs.zip` | the complete run directory (specs, callbacks, results, worker logs, response cache) and its SHA-256 |
| `analysis/` | output of `analyze.py`: target hits, first hits, and completion times per method and budget, the LaTeX table, and `facts.json` |
| `variants/<name>/` | the same 210 runs with another option order (`reversed`, `backmixing`, `random1`-`random3`) or with the capital-cost objective (`capex`): `analysis/` and `evidence/runs.zip` |
| `variants/comparison/` | output of `compare_variants.py`: hits per order and the capital-cost table |

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

## Option order and objective

The external variables index categorical choices, so their order is a convention.
Each campaign below repeats the 210 runs with another order (see `variants/comparison/orders_table.tex`).
Target hits out of 10 in the source order, with the range over the six orders:

| Method | B = 10 | B = 15 | B = 20 |
|---|---|---|---|
| D-SDA | 1 [1, 6] | 4 [3, 8] | 4 [3, 8] |
| NOMAD | 6 [5, 6] | 6 [5, 9] | 6 [5, 9] |
| RBFOpt | 8 [2, 8] | 9 [7, 10] | 10 [9, 10] |
| MISO | 7 [4, 7] | 10 [5, 10] | 10 [6, 10] |
| BAM | 0 [0, 2] | 4 [0, 10] | 6 [0, 10] |
| FMQA-SA | 2 [2, 7] | 3 [3, 10] | 7 [7, 10] |
| Uniform | 2 [0, 4] | 4 [2, 4] | 5 [4, 7] |

With the capital-cost objective (Turton bare-module cost of each flowsheet at its optimized operation), the best configuration is the all-batch flowsheet; see `variants/comparison/capex_table.tex`.
NOMAD 4.6.0 crashed after identical evaluations on both attempts in 12 runs over the variants; as in PR #56, they are scored on the evaluations completed before the crash (`crashed_identical_runs` in each `facts.json`).
