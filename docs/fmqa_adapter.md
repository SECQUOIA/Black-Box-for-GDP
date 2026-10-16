# FMQA-SA benchmark adapter

This repository reuses the FM learning and BQM conversion core from
[SECQUOIA/bbo_via_fmqa, QHD_Data](https://github.com/SECQUOIA/bbo_via_fmqa/tree/eb3a20d4b5a3773d17ff31d72a35d51f58e84e56)
at commit `eb3a20d4b5a3773d17ff31d72a35d51f58e84e56`. The experiment policy is
implemented separately in `fmqa_benchmark/optimizer.py` and exposed through
`fmqa_benchmark.adapter.run_fmqa_sa`.

The upstream Python files are vendored without numerical edits and verified
against SHA-256 and Git blob hashes. This is a pinned source import, not a
floating dependency on upstream main. Only the FM core and training entry point
are loaded; the upstream experiment drivers and candidate-selection helpers
are not imported. `qhd_surrogate.py` imports the vendored FM package and compiles
the unchanged `train_surrogate_model` definition from `ml_surrogate.py`.
The FM library's MIT notice and the public repository's MIT notice are included
with their provenance. The latter was obtained from public commit `e92ac6c`.

## Responsibility boundary

| Layer | Responsibility |
|---|---|
| Unmodified upstream core | PyTorch factorization machine, MSE loss, Adam training, coefficient scaling and BQM conversion |
| Training adapter | Source validation, deterministic CPU/float32 execution and training seed |
| Benchmark adapter | Ordered starts, objective-call budget, observed-only normalization, failed evaluations, encoding, SA and fallback, trace hooks |
| Experiment controller | CSV provenance/acceptance rules, durable attempted-callback logging, reporting targets, NLP timing and result storage |

The optimizer only receives an objective callback and declared bounds. It is
not given the evaluation table or a target value. The caller supplies the same
initial points used by other methods; the adapter never resamples them based on
feasibility. Supplied starts must be distinct, integer and in bounds. Every
completed initial or adaptive callback consumes the budget, including failed
responses. Adaptive proposals exclude already visited coordinates without a
callback; these internal exclusions do not consume the objective budget.

Finite observed responses are scaled to [0,1] using only observations so far;
non-finite responses receive training target 2. The reporting penalty is 1e6,
while `raw_value` and `lookup_feasible` preserve unsuccessful responses. A finite
objective at or above 1e6 is explicitly rejected by the historical adapter.
Do not infer mathematical infeasibility from a non-finite response.

SA uses `dwave.samplers.SimulatedAnnealingSampler` with a geometric beta schedule.
It chooses the lowest-energy sampled candidate that is in bounds and unseen.
If none qualifies, it samples uniformly from unseen points in the entire box,
without consulting feasibility. The three random streams independently control
FM initialization, annealing and fallback. A soft wall-time limit is checked
between phases; it is not a hard timeout for the PyTorch training call.

## Explicit differences from the public driver

This is an adapted benchmark method, not an unchanged execution of upstream
main. Comparison below is pinned to public commit `e92ac6c9840f74c54fbc8031c5df8bbb1a7f3f3e`.

| Choice | This benchmark adapter | Public main driver at e92ac6c |
|---|---|---|
| Starts | Caller-provided common design (three in our campaigns) | One start from the finite-value grid |
| Normalization | Observations only | Whole-table min/max |
| Candidate feasibility | No full-table screening | Filters using full-table finite values |
| Training epochs | 1000 by default | 300 in the training wrapper |
| SA | D-Wave CPU sampler, 100 reads, 1000 sweeps | dimod sampler, 50 reads |
| No eligible SA sample | Uniform unseen box point | Minimum surrogate energy over remaining finite-value grid |
| Stopping | Callback budget and soft wall limit | Cycle/stagnation limits |

The first three choices implement the common comparison protocol. Epoch count,
sampler settings and fallback are additional algorithm choices and must be
reported explicitly. Reusing the FM core does not establish equivalent full
search paths to the public driver. The historical QHD `predict()` helper has an
unused MXNet reference; this adapter uses BQM energies and does not call it.
No claim of fixing that upstream API is made here.

## Installation and use

```bash
python -m pip install ".[fmqa,test]"
python -m pytest tests/test_fmqa_adapter.py -q
```

For Linux CPU-only environments, install `torch==2.8.0` from the official
PyTorch CPU index before the command above. The wheel includes the pinned source
and license resources; no model submodules or historical result archives are
needed for this adapter.

```python
from fmqa_benchmark.adapter import run_fmqa_sa

evaluations, proposals = [], []
result = run_fmqa_sa(
    objective=lambda point: sum(v * v for v in point),
    lower=[1, 1], upper=[3, 3],
    starts=[(1, 3), (2, 2), (3, 1)], budget=8, seed=0,
    config={"epochs": 1000, "learning_rate": 0.01,
            "num_reads": 100, "num_sweeps": 1000, "time_limit": 1800},
    on_evaluation=lambda event, state: evaluations.append(event),
    on_proposal=proposals.append,
)
```

Each completed evaluation exposes its coordinate, order, phase, raw/reporting
value, acceptance flag, incumbent, and elapsed times. Each proposal exposes
training responses, random seeds, sampled candidates, rejection reasons and
selected point. Hook consumers decide how to persist these records. Objective
exceptions propagate; the experiment controller must log attempted callbacks
at objective entry if it needs failure/terminal-exception records (as the
IPOPT CSV runners in #28 do). DFO elapsed time includes training, sampling and
callback overhead; it is not historical process NLP time.

Returned adapter metadata records the pinned upstream commit and effective
settings. The underlying optimizer and vendored numerical core retain the
Benchmark implementation; this PR does not switch old runs to public defaults.

## Provenance, results and review scope

This is the implementation for [Issue #34](https://github.com/SECQUOIA/RBFopt_Test/issues/34),
extracted from `Benchmark` commit `ade67082ad2b09583a8f5594b827c97417e0ea99`.
Only implementation, tests, provenance and documentation are included.

**Existing Dantzig benchmark results, logs and experiment artifacts remain on
the [Benchmark branch](https://github.com/AlbertLee125/RBFopt_Test/tree/Benchmark).
They are excluded from this PR and intended for a separate results merge from
that branch.** No campaign is rerun or reclassified by this change. Small
synthetic tests establish source/numerical and adapter consistency, not equality
of the public driver's full trajectories. Historical coordinator/bundle
integration under #28 remains separate; its old source inventory needs to be
reconciled with this minimal package before deployment.
