# D-SDA with the separable neighborhood

Every stored-response D-SDA run of the manuscript repeated with the separable neighborhood (one external variable changed by ±1, 2d neighbors) in place of the unit L∞ neighborhood (3^d − 1 neighbors), with every other setting unchanged.
The catalytic distillation column, whose L∞ neighborhood has 728 configurations, already uses the separable neighborhood.
Responses and point costs come from stored tables; no NLP solver, process model, or simulator was run, so the runs took seconds on a workstation.

| Folder | Content |
|---|---|
| `grid_process/` | `experiments/dsda_separable/run.py`: the 1,050 Grid runs and the 140 single-descent process runs, through the harness of `experiments/dsda_no_revisit` (`runs.csv`, `condition_summary.csv`, `checks.json`, `manifest.json`), each paired with its L∞ run of `results/dsda_no_revisit_20261031` (`paired_runs.csv`, `comparison.csv`); `evidence/` holds every run's records |
| `lomustine/<order>/` | the 30 D-SDA runs of each of the six option orders of `results/lomustine_simulation_20261031`, through `experiments/catalytic_distillation_live/run.py` with the case `experiments/dsda_separable/lomustine_case.py` (the Lomustine case with the separable neighborhood) and `LOMUSTINE_ORDER`; `evidence/` holds the full campaigns |
| `analysis/` | `experiments/dsda_separable/analyze.py`: paired comparison per condition (`conditions.csv`), pooled counts with exact McNemar tests (`facts.json`), and the supplementary table |

## Results

Target hits, L∞ against separable, with the discordant runs (separable only / L∞ only) and the exact McNemar p-value:

| Runs | L∞ | Separable | Discordant | p |
|---|---:|---:|---:|---:|
| Grid, B = 10 (210) | 13 | 22 | 9 / 0 | 0.004 |
| Grid, B = 30 (210) | 78 | 79 | 14 / 13 | 1 |
| Grid, B = 50 (210) | 91 | 87 | 10 / 14 | 0.54 |
| Grid, B = 70 and 100 (210 each) | 101 | 88 | 5 / 18 | 0.011 |
| CSTR5 to CSTR30 (60) | 16 | 7 | 0 / 9 | 0.004 |
| Dynamic, B = 12 and 15 (20) | 10 | 16 | 6 / 0 | 0.031 |
| All process conditions (140) | 79 | 78 | 11 / 12 | 1 |
| Lomustine, six orders, all budgets (180) | 90 | 99 | 11 / 2 | 0.022 |

The separable neighborhood fits small budgets: with two or three external variables it evaluates four or six neighbors in place of eight or 26, so it completes more descents within 10 to 15 evaluations.
Without diagonal moves, its descents stop earlier, after a median of 25 Grid evaluations in place of 37, and on CSTR they miss the corner target that diagonal moves reach.

## Reproduction

```bash
python experiments/dsda_separable/run.py --output OUT/grid_process
export LIVE_DFO_CASE=$PWD/experiments/dsda_separable/lomustine_case.py
export LOMUSTINE_ORDER=...   # unset for the source order; see lomustine/<order>/plan.json, case_options
cd experiments/catalytic_distillation_live
python run.py plan --output OUT/lomustine/ORDER --methods dsda
python run.py run --output OUT/lomustine/ORDER --gams none --cpus 0 --methods dsda
python run.py summarize --output OUT/lomustine/ORDER
cd ../..
python experiments/dsda_separable/analyze.py --results OUT
```
