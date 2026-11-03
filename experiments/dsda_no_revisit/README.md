# D-SDA without re-evaluating explored configurations

## Why

The published D-SDA runs evaluated an already explored configuration again when it reappeared as a neighbor or line-search point, and each repeat consumed an evaluation.
This affected 349 of 2,441 process evaluations (14%) and 7,274 of 37,253 Grid evaluations (20%).
The original D-SDA (`global_evaluated` in `dsda-gdp`) and the Pyomo LD-SDA (`explored_point_set` in `pyomo.contrib.gdpopt.ldsda`) never evaluate a configuration twice.
The repository `grid_dsda.py` now follows them: a configuration evaluated earlier in the same search, including the shared initial configurations and earlier descents, reuses its stored value without an objective call, so it consumes no budget.
`reevaluate_explored=True` restores the historical behavior.

In one descent, every explored configuration is at least as bad as the current incumbent, so reusing its value never changes a move.
The new runs therefore follow the published paths without the repeats and continue with the evaluations that the repeats had used.

## Runs

| Variant | Runs | Protocol |
|---|---|---|
| `grid` | 1,050 | Grid: ranked shared starts, L-infinity neighborhood, common target stop after each descent |
| `single` | 140 | Process: one descent from the best accepted shared start (published protocol) |
| `ranked` | 140 | Process: descents from the ranked shared starts while budget remains |
| `ranked_random` | 140 | Process: `ranked`, then descents from uniformly drawn unvisited configurations |

All variants use the adopted improvement threshold `1e-5`, the shared initial configurations, budgets, seeds, unaccepted-response value `1e6`, and target rule of the published runs.

## Inputs

- `results/archives/dsda_abs1e5_rerun_20261028_020753_2004611.zip`: the sealed package with every job, the Grid lookup tables, the process lookup tables and point costs, and the published process runs.
- `results/archives/dsda_grid_target_stop_20261028_032943_2346732.zip`: the published Grid runs.
- `results/grid_gdp_20261009/raw/point_timings.csv`: Grid point costs.

All three are hash-checked. No NLP solver, process model, or other optimizer is imported.

## Checks

For every job:

- `no_repeats`: no configuration is evaluated twice.
- `legacy_reproduces_published` (`grid`, `single`): the same code with `reevaluate_explored=True` reproduces the published callback sequence, best objective, and hit exactly. So the no-revisit rule is the only change.
- `published_distinct_prefix` (`grid`, `single`): the new run starts with the published sequence without its repeats.
- `not_worse` and `hit_kept`: the best objective is never worse, and no published hit is lost.
- `first_descent_matches_single` (`ranked`, `ranked_random`): the first descent equals the `single` run.

The run exits with status 1 if any check fails; `checks.csv` lists every job.

## Run on Dantzig

```bash
bash experiments/dsda_no_revisit/run_dantzig.sh
```

The launcher uses `.venv-dantzig/bin/python` (override with `DSDA_PYTHON`), pins one logical CPU of an observed idle physical core (override with `DSDA_CPU`), and limits numerical libraries to one thread.
The 1,470 runs and their 1,190 replay checks take a few minutes.
The last lines print `CHECKS PASSED` and the `RETURN_ARCHIVE` path.

## Outputs

- `runs/<job>__<variant>/`: `result.json`, `callbacks.jsonl`, and `search.log`.
- `runs.csv`: one row per run with hits, evaluations, search time (lookup time removed), point cost, preparation, and estimated completion time.
- `condition_summary.csv`, `checks.csv`, `checks.json`, and `manifest.json` (environment, CPU, Git revision, and hashes).

Search times are measured; point costs come from the stored tables, so completion times follow the reconstructed-cost equation of the manuscript.

## Local check

Outcomes are deterministic, so a local run reproduces every hit and callback; only times differ.

```bash
python experiments/dsda_no_revisit/run.py --cpu none --no-zip --output /tmp/dsda_no_revisit_check
```
