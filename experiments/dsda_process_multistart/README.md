# Process D-SDA with multistart

## Why

On Grid-GDP, D-SDA descends from each of the three shared initial configurations in order of objective value while budget remains.
The published process D-SDA descends only from the best initial configuration and stops when that descent ends, which leaves budget unused in about half of the process runs.
A reviewer could read this as a handicapped baseline.
This experiment reruns the 140 process D-SDA jobs with the Grid rule and with a variant that keeps restarting until the budget is spent.

| Variant | Protocol |
|---|---|
| `single` | Published protocol: one descent from the best accepted initial configuration. Replay control. |
| `ranked` | Grid rule: descents from all three shared initial configurations, best first, while budget remains. |
| `ranked_random` | `ranked`, then descents from uniformly drawn unvisited configurations until the budget is exhausted. |

All variants use the adopted absolute improvement threshold `1e-5`, the same 14 process conditions, seeds 0-9, shared initial configurations and order, budgets, unaccepted-response handling, and target rule.
No variant receives the reference target as a stopping criterion.
Random restarts are drawn with `numpy.random.default_rng([20261030, seed])` from box configurations not yet evaluated in that run, without feasibility screening, matching the uniform-sampling control.

## Inputs

The runner reads the sealed input package and the archived process runs from `results/archives/dsda_abs1e5_rerun_20261028_020753_2004611.zip` (SHA256 `e58982f7179b73c65d83134dcbe0b25854002685812b2511b24523e861c9929e`).
It verifies the archive hash and every hash in the package's `SHA256SUMS.json`, and imports the sealed `grid_dsda.py` and frozen cohort modules rather than the repository copies.
Responses and point costs come from the stored lookup tables; no NLP solver, process model, or other optimizer is imported.

## Run on Dantzig

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
git fetch origin && git checkout <branch with this directory>
bash experiments/dsda_process_multistart/run_dantzig.sh
```

The launcher uses `.venv-dantzig/bin/python` (override with `DSDA_PYTHON`), waits for an observed idle physical core and pins to one logical CPU (override with `DSDA_CPU=<n>`), and limits numerical libraries to one thread.
The 420 runs take about one minute.
The last lines print `CHECKS PASSED` and the `RETURN_ARCHIVE` path; please send back that ZIP and the `.log` next to it.

## Checks

- `single` must reproduce every archived process run exactly: callback sequence, evaluations, best objective, hit, first hit, and category.
- The first descent of `ranked` and `ranked_random` must match the `single` callback sequence.
- No run may fail.

The process exits with status 1 if any check fails; `checks.json` lists the failures.

## Outputs

- `runs/<job>__<variant>/`: `result.json`, `callbacks.jsonl`, `search.log`, `actual_settings.json`.
- `runs.csv`: one row per job and variant, with hits, evaluations, descents, search time (lookup time removed), summed point cost, preparation, and estimated completion time.
- `condition_summary.csv`: hits, median evaluations, full-budget runs, and search and completion quartiles per condition and variant.
- `checks.json` and `manifest.json`: validation results, environment, CPU selection, Git revision, and hashes.

Search times are measured; point costs are the stored same-attempt costs from the lookup tables, so estimated completion times follow Equation (reconstructed cost) of the manuscript.

## Local check

Outcomes are deterministic, so a local run reproduces every hit and callback; only times differ.

```bash
python experiments/dsda_process_multistart/run.py --cpu none --no-zip --output /tmp/dsda_multistart_check
```
