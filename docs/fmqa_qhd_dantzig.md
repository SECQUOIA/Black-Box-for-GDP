# QHD_Data PyTorch FMQA-SA on Dantzig

The surrogate is the original PyTorch FMBQM in
[SECQUOIA/bbo_via_fmqa, QHD_Data](https://github.com/SECQUOIA/bbo_via_fmqa/tree/eb3a20d4b5a3773d17ff31d72a35d51f58e84e56),
pinned to `eb3a20d4b5a3773d17ff31d72a35d51f58e84e56`.
The exact source bytes and MIT license are under `fmqa_benchmark/vendor/qhd/`.
Both SHA256 and GitHub blob hashes are recorded. No remote code is fetched when
the benchmark runs. The earlier benchmark used a NumPy port of the MXNet model;
the current publication label is `FMQA-SA`; raw execution records retain `FMQA-SA (PyTorch QHD_Data)`. Previous results are preserved as `FMQA-SA (NumPy legacy)`.

The same **three initial coordinates in the same evaluation order** are reused
for each seed from the existing results. No LHC sampling or seed selection takes
place in this runner. Their frozen hashes are checked. Small Batch uses the new
27-point domain and its latest starting points. Column includes the approved
seed-10 supplement. Grid uses the same saved designs as the existing 1,050-run
FMQA/DFO experiments. Adaptive points may differ because the learned model differs.

| Scope | Jobs | Total objective callbacks if completed |
| --- | ---: | ---: |
| `small_batch` (default) | 10 | 100 |
| `process` | 140 | 3,430 |
| `grid` | 1,050 | 54,600 |
| `all` | 1,190 | 58,030 |

Process budgets: Column 16 (seeds 1-10), CSTR sizes 5/10/15/20/25/30 use
8/15/22/29/36/43, Small Batch 10, and Dynamic 12/15/20/30/37/50.
All remaining process replications use seeds 0-9. Grid uses 21 functions,
budgets 10/30/50/70/100, and seeds 0-9. `--seeds 0` can select a diagnostic subset;
it excludes Column, whose approved seeds begin at 1.

## What is changed and what is controlled

The rank-8 PyTorch model is called through the unchanged upstream
`train_surrogate_model` and `FMBQM.from_data` implementations. This preserves
float32, zero initial bias, native parameter initialization order, MSELoss,
PyTorch Adam, 1,000 epochs, learning rate 0.01, and upstream QUBO normalization.
The previous NumPy backend used float64, a random initial bias, and an MXNet-style
Adam update including batch rescaling. Consequently this is a comparison of the
two implementations, not merely a hardware timing substitution.

The original `QHD_Data/fmqa_simulated.py` demonstration is archived but is not
executed: it uses a 70% initial dataset, full-table scaling, a different SA
implementation, and an `x < y` filter. Those choices would change the benchmark.
Instead the existing budgeted loop, binary encoding, observed-only target
scaling, infeasible penalty, and independent model/SA/fallback random streams are
reused. SA remains `dwave.samplers.SimulatedAnnealingSampler`, with 100 reads,
1,000 sweeps, and geometric beta schedule. There is no hidden feasibility filter.

All three initial evaluations count toward the budget. Every actual callback is
saved and fsynced, including infeasible outcomes; all SA proposals, rejected
bitstrings, selected coordinates and iteration seeds are saved separately.
The budgeted FMQA loop evaluates distinct points and uses the same seeded
uniform-unseen fallback as the existing implementation. Known optima are used
only in reporting. The unused upstream `predict()` still contains legacy MXNet
references; the training-to-BQM-to-SA execution path never invokes that method.

CPU only, float32, deterministic PyTorch operations, one intra-op and inter-op
thread, and one Linux logical CPU. Pinning is not an exclusive CPU reservation.
New setups install the PyTorch version in `requirements-fmqa-qhd.txt` from the
[official CPU wheel index](https://download.pytorch.org/whl/cpu), matching preflight.
Historical runs used `torch==2.8.0`; their frozen bundles and runtime records remain
unchanged. Use a separate run directory for the patched runtime. An existing run
must be resumed with its original extracted runner and environment.
The other six pinned numerical/sampling packages match the earlier FMQA environment.
Every installed package version and the host/CPU/source identity are recorded.
Module imports happen before the method clock; native optimizer initialization
and all fitting, SA and trace/checkpoint writes occur within it. A 1,800-second
limit is checked between fitting/sampling steps; the unchanged upstream fit has
no per-epoch interruption hook. A separate 2,100-second process watchdog bounds
an unresponsive fit. A timeout is retained as incomplete, never converted to success.

## Upload and run

Mac:

```bash
scp /private/tmp/fmqa_qhd_dantzig_20261012.zip \
    /private/tmp/fmqa_qhd_dantzig_20261012.zip.sha256 \
    lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

Dantzig:

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
sha256sum -c fmqa_qhd_dantzig_20261012.zip.sha256
unzip fmqa_qhd_dantzig_20261012.zip
cd fmqa_qhd_runner

# Creates only the separate .venv-dantzig-fmqa-qhd environment.
bash run_fmqa_qhd_dantzig.sh setup

# The latest Small Batch design: 10 seeds, budget 10 each.
FMQA_QHD_CPU=6 nohup bash run_fmqa_qhd_dantzig.sh run --scope small_batch \
  > ../fmqa_qhd_small_batch.log 2>&1 &
tail -f ../fmqa_qhd_small_batch.log
```

To run another scope, replace `--scope small_batch` with `--scope process`,
`--scope grid`, or `--scope all` and use a corresponding log name.
Do not launch these scopes together on the same CPU. A scope includes only the
PyTorch method; existing NumPy benchmarks are not rerun or overwritten.
`FMQA_QHD_BASE_PYTHON` can specify Python 3.11-3.13 for setup (3.11 recommended).
`FMQA_QHD_ENV` can select a dedicated environment; do not point it at the old
FMQA/GDP/DFO environment. GAMS, RBFOpt, BAM, solver licenses and GPUs are not required.

## Outputs and recovery

The log prints `RUN_DIR`, progress `[i/N]`, summary counts, and `RESULT_ZIP`.
Expect `all_completed=true` and `completed_runs` equal to the chosen plan size.
The result ZIP includes raw JSONL callbacks/proposals, checkpoints, worker logs,
runtime and source snapshots, checksums, `runs.csv` and `trajectories.csv`.

`evaluation_costs.csv` attaches existing Dantzig point measurements to callbacks.
`completion_estimates.csv` uses `method time - lookup time + point costs`, plus
the same one-time Dynamic preparation as the current plots. Small Batch and
all 20,181 Grid coordinates have existing measurements. A new process coordinate
may lack a measurement: `missing_point_costs.csv` records it and its run's
completion estimate remains blank. Missing costs are never replaced with zero.
These are fixed-path estimates, not online GDP/NLP executions. Original Dantzig
source tables and their hashes travel in the ZIP.

`pytorch_summary.csv` reports target hits and median costs per case/budget.
TTS99 is emitted only when that group's planned jobs and all point costs are
complete. It uses all-run median time and the observed independent-restart
formula. `tts99_infinite=true` identifies a zero-hit group; JSON-safe CSV export
leaves its numeric infinity blank.

```bash
# Dantzig, from the same extracted runner. Substitute the printed RUN_DIR.
QHD_RUN=/local/scratch/a/lee4382/repository/RBFopt_Test/results/fmqa_qhd/fmqa_qhd_TIMESTAMP_SUFFIX
FMQA_QHD_CPU=6 nohup bash run_fmqa_qhd_dantzig.sh resume \
  --run-dir "$QHD_RUN" --retry-errors >> ../fmqa_qhd_small_batch.log 2>&1 &

# After it stops:
bash run_fmqa_qhd_dantzig.sh pack --run-dir "$QHD_RUN"

# Mac, using the actual RESULT_ZIP basename:
scp lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/fmqa_qhd/fmqa_qhd_TIMESTAMP_SUFFIX.zip \
    ~/Downloads/
```

Resume uses the saved scope/seeds, verifies completed traces and source/runtime
identities, skips valid completions, and restarts an interrupted job from its
original seed. Partial attempts are retained. It does not resume neural-network
state mid-run. Results from altered training settings must remain a separate experiment.

Build the execution ZIP locally:

```bash
python process_followup_runner.py bundle --experiment fmqa_qhd \
  --output /private/tmp/fmqa_qhd_dantzig_20261012.zip
```
