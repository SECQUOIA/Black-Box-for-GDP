# NOMAD and MISO on the stored responses

## Why

Ploskas and Sahinidis (2022, J. Glob. Optim. 82:433-462) found NOMAD and MISO to be the strongest mixed-integer DFO solvers in their comparison, and the manuscript now cites that review.
This experiment runs both on the same 1,050 Grid and 140 process jobs as the published methods, so a reviewer cannot ask why they were left out.

| Method | Implementation | Start |
|---|---|---|
| `nomad` | NOMAD 4 (MADS) through `PyNomadBBO` 4.6.0, all variables integer (`BB_INPUT_TYPE`) | Best of the three shared initial configurations; its stored value is replayed without charge |
| `miso` | MISO's CPTV algorithm as implemented by `soogo.cptv` 2.1.0 (NREL), RBF model with integer indices and median low-pass filter | RBF model updated with the three shared initial configurations and their values |
| `uniform` | Solver-free harness check: uniform sampling without replacement | Three shared initial configurations |

Every run evaluates the three shared initial configurations in their shared order first, so they are charged exactly as for the published methods.
Every later request, including a repeated configuration, consumes budget, and the harness never charges more than B evaluations.
Unaccepted configurations return the finite penalty `1e6`, as for D-SDA and RBFOpt.
No method receives the reference target.

### Solver-specific adaptations

- **MISO.** soogo 2.1.0 rejects pure-integer problems in the dynamically dimensioned search (DDS) sampler of its coordinate-perturbation step, and every configuration space here is pure-integer.
  The adapter supplies an integer DDS sampler written for this runner (same algorithm on the integer lattice, following soogo's convention for integer coordinates) and disables the continuous local-search phase, which has no coordinates to act on.
  The CPTV loop, target-value step, and RBF model are soogo's.
  On small domains the acquisition can run out of unevaluated candidates, and CPTV then alternates its steps without evaluating; the adapter stops such a run after ten consecutive iterations without a new evaluation (`stop_reason` `no_new_candidates`).
- **NOMAD.** For integer variables NOMAD 4.6.0 caps total evaluations, including cache hits, at 900 and stops when its mesh reaches the integer resolution, so it can end before the budget, like D-SDA.
  In local tests NOMAD 4.6.0 sometimes crashed with a segmentation fault (for example `grid_ackley_B30_seed9`), always after its last blackbox evaluation, while cycling through cached points toward that cap.
  Every run therefore executes in a forked worker.
  After a NOMAD crash, the job is rerun with `MAX_EVAL 5000` and then `MAX_EVAL 20000`; a rerun is accepted only if it completes and evaluates exactly the same configurations in the same order as the crashed run (`completed_after_verified_rerun`, with every attempt recorded in `result.json`).
  Otherwise, and for any crash of another method or a run exceeding `--timeout` (default 2,100 s), the run is an execution failure under the published failure rule.
  In the checks, a larger cap never changed the evaluated path of a run that completed with the default cap.

## Inputs

Responses come from the sealed package in `results/archives/dsda_abs1e5_rerun_20261028_020753_2004611.zip`, verified by its SHA256 and its internal `SHA256SUMS.json`.
Point costs come from `results/grid_gdp_20261009/raw/point_timings.csv` (Grid) and the `total_wall_s` of each process lookup row, the tables used for the published completion times; the tests check that archived D-SDA paths priced this way reproduce the published point costs.
NLP solves use the configuration status in `results/dsda_publication_20261028/tables/configuration_coverage.csv`.

## Run on Dantzig

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
git fetch origin && git checkout <branch with this directory>
bash experiments/mixed_integer_dfo/run_dantzig.sh
```

On first use, the launcher creates `.venv-mi-dfo` from `.venv-dantzig/bin/python` and installs `requirements-mi-dfo.txt`; set `MIDFO_BASE_PYTHON` to use another Python 3.10 or 3.11.
It runs `tests/test_mixed_integer_dfo.py` as a preflight, then starts the full run in the background on an observed idle core (override with `MIDFO_CPU=<n>`).
The log ends with `CHECKS PASSED` and `RETURN_ARCHIVE`; please send back that ZIP and the log.
To run one method or scope, append for example `--methods nomad --scopes process`.

## Outputs

- `runs/<job>__<method>/`: `result.json`, `callbacks.jsonl`, and `search.log` (including native NOMAD output).
- `runs.csv`, `condition_summary.csv`: hits, evaluations, NLP solves, search time, and completion-time quartiles.
- `comparison_hits.csv`: target hits of NOMAD and MISO next to the five published methods for every condition.
- `checks.json`, `manifest.json`: failures, budget overruns, shared-start order, environment, and package versions.

## Local check

```bash
python experiments/mixed_integer_dfo/run.py --cpu none --no-zip --methods uniform --output /tmp/midfo_check
python -m pytest -q tests/test_mixed_integer_dfo.py
```
