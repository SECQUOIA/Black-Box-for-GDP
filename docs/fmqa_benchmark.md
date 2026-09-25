# FMQA with simulated annealing on Dantzig

Use the [September 25 results and figure index](../results/fmqa_20260925/README.md)
for current comparisons. The reruns contain 139 process cases on CPU 4 and
1,050 Grid runs on CPU 0, on distinct recorded physical cores. The previous
same-CPU-overlap FMQA result files have been removed.

This runner adds **FMQA-SA** to the existing process-case lookup benchmark.
It uses the same ordered three-point initialization, seeds, integer bounds,
objective tables, and total evaluation budgets as the original September 10
Dantzig experiments. It does not require a quantum computer, QCI token, GAMS,
or BAM license. The default comparison covers the process case-study tables.
For the separate 1,050-run QHDOpt-derived Grid benchmark, use the
[Grid-only runner and ZIP](fmqa_grids.md).

## Run and test from a checkout

Shell wrappers are optional local files and are not committed. The Python entry
points work directly from the repository root:

```bash
python -m pip install -r requirements-fmqa.txt pytest
python fmqa_benchmark_runner.py check
python fmqa_grid_benchmark.py check
python -m pytest tests/test_fmqa_benchmark.py -q
python fmqa_benchmark_runner.py run --output-root results
```

The shell-based deployment examples below refer to older local bundles that
included those optional wrappers. A newly generated bundle can instead use
`python fmqa_benchmark_runner.py run --output-root ../results` directly.

## Fixed experiment protocol

| Case | Total evaluations, including the three initial points | Seeds | Runs |
|---|---:|---|---:|
| Column | 16 | 1–9 | 9 |
| CSTR 5 / 10 / 15 / 20 / 25 / 30 | 8 / 15 / 22 / 29 / 36 / 43 | 0–9 | 60 |
| Small Batch | 10 | 0–9 | 10 |
| Dynamic | 12 / 15 / 20 / 30 / 37 / 50 | 0–9 | 60 |
| **Total** | | | **139** |

The 89 distinct initial designs are in
`fmqa_benchmark/reference/initial_designs.json`. Coordinates were recovered
from the later local evaluation traces, then every ordered design was verified
against the SHA256 recorded in the **original Dantzig manifest**. They are loaded
directly, not regenerated with a potentially different sampling library.
For example, CSTR5 seed 0 starts at `(1, 2), (5, 5), (3, 2)`.
All methods receive the same three evaluations; DSDA subsequently starts its
search from its best feasible initial point. Matching initial designs does not
imply matching subsequent search trajectories.

Each FMQA iteration fits a factorization machine (FM) using only previously
evaluated points, samples the resulting binary quadratic model with CPU
simulated annealing (SA), and evaluates one new integer point. Both feasible
and infeasible calls consume the evaluation budget. There is no early stop on
reaching a known optimum. Known optima are used only in reporting.

Binary encoding concatenates each actual integer's bits, most significant bit
first, in the original coordinate order. Each coordinate gets its own width
`upper_bound.bit_length()`. This handles Small Batch's three coordinates.
SA samples outside the box or already evaluated are rejected without an
objective call. The lowest-energy valid unseen sample is selected. If none
exists, a seeded uniform unseen point from the bounded integer lattice is
evaluated. There is no feasibility-table filtering or look-ahead. Proposals,
rejections and fallbacks are logged separately from true evaluations.

Observed finite objectives are rescaled to `[0, 1]` for training; equal observed
values map to zero, and observed infeasible values map to `2`. Scaling is
recomputed from observed values only. Raw infeasibility is saved as JSON `null`
with `lookup_feasible: false`; the standard result CSV uses the existing
`1e6` report penalty. No infeasibility is presented as a successful solution.

## Relationship to bbo_via_fmqa

Pinned upstream sources and their MIT licenses are included under
`fmqa_benchmark/vendor/`:

- [SECQUOIA/bbo_via_fmqa](https://github.com/SECQUOIA/bbo_via_fmqa/tree/4bd0aa331cd2f996e7a0507e8fc236cf43ad4e63),
  commit `4bd0aa331cd2f996e7a0507e8fc236cf43ad4e63`.
- [tsudalab/fmqa](https://github.com/tsudalab/fmqa/tree/51d827d1f88d602278dd0ab5e827ac4fbf8f0b29),
  commit `51d827d1f88d602278dd0ab5e827ac4fbf8f0b29`.

The original SECQUOIA `train_surrogate_model` function body is executed unchanged
with a compatible `FMBQM.from_data` adapter. The legacy MXNet FM backend is
ported to NumPy CPU in `fmqa_benchmark/surrogate.py`:

- Rank-8 FM, `b + h·x + sum(i<j) (V[:,i]·V[:,j]) x[i] x[j]`.
- Fresh normal initialization with standard deviation `0.01` each iteration.
- Full-batch Adam, 1,000 epochs, learning rate `0.01`, beta values `0.9/0.999`,
  epsilon `1e-8`. Mean-square loss plus the extra batch-size gradient rescaling
  corresponding to the upstream `Trainer.step(batchsize)` call.
  Bias correction multiplies the learning rate by
  `sqrt(1 - beta2**t) / (1 - beta1**t)`, with epsilon added to the square root
  of the uncorrected second moment, matching
  [MXNet 1.8 Adam](https://github.com/apache/mxnet/blob/1.8.0/python/mxnet/optimizer/optimizer.py).
- BQM coefficients and offset normalized by the largest absolute coefficient.

**This is an adapted implementation, not a bit-identical reproduction of the
MXNet backend.** NumPy uses float64 and different random streams. The baseline
upstream script's 70% feasible-table training sample, full-table objective
scaling, CSTR-specific feasibility filter and coordinate swap are not used.
Those choices are incompatible with a three-initial-point black-box comparison.
The original sources remain available for inspection.

Sampling uses `dwave.samplers.SimulatedAnnealingSampler`, 100 reads and 1,000
sweeps per iteration with its geometric beta schedule. FM initialization, SA,
and fallback selection have independent random streams derived from the run
seed. Every iteration's FM/SA seed is saved. The sampler executes locally and
does not call a quantum or cloud service. This benchmark measures the FM + SA
algorithm; it is not evidence of quantum speedup.

Python >=3.10 is required. `requirements-fmqa.txt` pins the runtime dependencies.
The shell creates a separate `.venv-dantzig-fmqa`; it does not install into the
GDP environment. Thread environment variables are set to 1 before NumPy import;
Linux execution is additionally restricted to one available CPU, inherited by
each fresh worker subprocess. Jobs run sequentially, with a 1,800-second safety
limit per run. This cap is not an alternative to the original evaluation budget.

## Upload and run

The prepared execution ZIP includes this code, frozen reference results,
initial designs, lookup tables and licenses. It needs no git submodules and
does not include private solver licenses or credentials.

On the Mac:

```bash
scp /Users/albertlee0125/Repos/RBFopt_Test/results/dantzig_review/fmqa_benchmark_runner.zip \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

On Dantzig:

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
unzip fmqa_benchmark_runner.zip
cd fmqa_runner
sha256sum -c RUNNER_SHA256SUMS
bash run_fmqa_dantzig.sh setup
bash run_fmqa_dantzig.sh plan
nohup bash run_fmqa_dantzig.sh run > ../fmqa_dantzig.log 2>&1 &
```

For completion-time comparisons, run after the current GDP benchmark finishes
and avoid competing CPU workloads. The sequential runner does not wait for an
unrelated GDP process automatically. The original benchmark timers and software
backends differ; keep the environment metadata when interpreting runtime ratios.

Setup uses `.venv-dantzig-gdp/bin/python` as a Python interpreter to create the
new environment, falling back to `python3`. To select another >=3.10 interpreter:

```bash
FMQA_BASE_PYTHON=/path/to/python3.11 bash run_fmqa_dantzig.sh setup
```

Check progress from the repository root:

```bash
tail -f fmqa_dantzig.log
```

A local/smoke subset can use `--cases cstr --cstr-sizes 5 --seeds 0`.
Shorter `--epochs`, `--num-reads` and `--num-sweeps` settings are useful for
testing; they are recorded and must not be mixed with the default experiment.
All reported matrix counts and comparisons reflect the actual selected subset.

## Results, recovery and download

The log prints `RESULT_DIR=` and, on completion/interruption, `RESULT_ZIP=`.
Results are stored under the repository's `results/dantzig_fmqa_<UTC>_<id>/`:

- `run.json`: full configuration, exact initial points, host, package versions,
  CPU affinity and source/data checksums; `source/` contains a source snapshot.
- `jobs/<case_budget_seed>/evaluations.jsonl`: every actual oracle call, ordered
  coordinates, feasibility, raw objective, incumbent and elapsed time.
- `jobs/.../proposals.jsonl`: SA candidate bit strings, decoded coordinates,
  energies, rejection reasons, random seeds and chosen point.
- `jobs/.../result.json`: terminal status, evaluation counts, best point and
  training/annealing/lookup/run timings; `run.log` contains worker diagnostics.
- `process_case_studies.csv` and `.manifest.json`: audited aggregate in the
  existing benchmark schema, with checksums of all job artifacts.
- `summary.json`, internal `SHA256SUMS`, and a ZIP with external `.zip.sha256`.

The current runner updates per-job results and `progress.json` during execution.
It rebuilds the aggregate CSV, audit manifest and summary when packaging at the
end or on interruption. `pack` can also recover these from completed job files.

The default 139-run result pairs with 139 runs per baseline method, producing
**556 rows for four methods**. Reference DSDA/RBFOpt results are from September
10; BAM results are replaced with the September 16 BAM **5.0.0** rerun.

Resume requires the same selection, hyperparameters, source, dependencies and
host. Completed jobs are checked and skipped; timeout/error jobs are retried
in fresh processes and earlier attempts are preserved. Supply the original
options again when resuming a subset or custom configuration:

```bash
bash run_fmqa_dantzig.sh run --resume ../results/dantzig_fmqa_TIMESTAMP_ID
```

The runner packages results even on a normal interrupt. After a machine crash
or forced termination, recover an archive without rerunning:

```bash
bash run_fmqa_dantzig.sh pack --run-dir ../results/dantzig_fmqa_TIMESTAMP_ID
```

Incomplete or invalid runs are marked explicitly. A time-limited run that
finished all three initial calls remains a terminal result and its actual
evaluation count/status is retained. It is not relabeled as budget-complete.
Comparison refuses a missing job or inconsistent trace rather than silently
dropping a failed condition.

Download to the Mac (replace the final filename with `RESULT_ZIP`):

```bash
scp lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/dantzig_fmqa_TIMESTAMP_ID.zip ~/Downloads/
scp lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/dantzig_fmqa_TIMESTAMP_ID.zip.sha256 ~/Downloads/
cd ~/Downloads
shasum -a 256 -c dantzig_fmqa_TIMESTAMP_ID.zip.sha256
```

## Comparison figures

On Dantzig, from `fmqa_runner`:

```bash
bash run_fmqa_dantzig.sh compare \
  --fmqa-results ../results/dantzig_fmqa_TIMESTAMP_ID.zip \
  --output-dir ../results/fmqa_comparison_TIMESTAMP_ID \
  --time-profiles
```

The Python equivalent works on a Mac after installing `requirements-fmqa.txt`:

```bash
python fmqa_compare.py --fmqa-results ~/Downloads/dantzig_fmqa_TIMESTAMP_ID.zip \
  --output-dir results/fmqa_comparison_TIMESTAMP_ID --time-profiles
```

The comparison verifies original initial-design hashes, exact case/seed/budget
pairs, CSV manifests, artifact hashes and objective traces. It produces:

- `process_case_studies.csv` and its provenance manifest for the four methods.
- `case_study_summary.csv`, `evaluation_convergence_summary.csv`,
  `case_study_overview.png`, and `evaluation_convergence.png`.
- With `--time-profiles`: `timing/time_performance_profiles.png`, absolute
  completion-time and work/time plots, and their source tables.

**Timing scope:** these runs query the original objective tables. FMQA's full
run wall time includes surrogate training, SA, selection and logging overhead,
plus lookup calls; it excludes interpreter startup and initial data loading.
`worker_wall_s` additionally captures subprocess overhead. Component timings
cover completed training/SA calls; a timeout may interrupt a component before
its timer is accumulated, so use total wall time for censored runs.
Baseline instrumentation overhead is not identical to the new detailed logger.

No cached or live GDP/NLP solve time is added here. Consequently these figures
compare optimization overhead on the lookup benchmark, **not end-to-end GDP
solution time**. Saved integer coordinates permit a later, explicitly defined
join to the measured NLP timings, including a policy for failures/retries and
Dynamic's one-time discretization. Completion profiles use total recorded run
time, not first-hit time, because the historical baselines lack first-hit
timestamps. Do not use Mac smoke runs to make Dantzig runtime claims.

To rebuild the execution ZIP from the repository:

```bash
python fmqa_benchmark_runner.py bundle --output /tmp/fmqa_benchmark_runner.zip
```
