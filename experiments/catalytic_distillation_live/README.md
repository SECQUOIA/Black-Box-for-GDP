# Live DFO runs on the catalytic distillation column

Seven methods search the configurations of the corrected catalytic distillation model (`gdp_models/catalytic_distillation/distillation_model_corrected.gms`; see `REVIEW.md` there).
Every evaluation solves the NLP of the requested configuration. Nothing is enumerated in advance, unlike the published process cases, which used stored lookup tables.

## Black box

- Each admissible configuration is solved with CONOPT from `init.gdx`, one thread, with a 300 s limit.
- A configuration is accepted when CONOPT reports normal completion with a locally optimal solution. Its value is `zobj`, the negative annual profit in $/yr.
- Every response is a deterministic function of the configuration, so it is solved at most once per campaign and stored in `cache.sqlite`, which all runs share. The cache records the model, initialization, and solver hashes and refuses a mismatch.
- A repeated request is still charged to the budget and to the point cost, as in the published accounting.

## Search space

The six external variables are the ethanol feed stage f1, the catalytic stages c1 < c2 < c3, the butenes feed stage f2, and the boil-up stage b, with 2 <= f1 <= c1 < c2 < c3 <= f2 <= b <= 21.
All methods search the gaps

    g = (f1 - 2, c1 - f1, c2 - c1 - 1, c3 - c2 - 1, f2 - c3, b - f2),   0 <= g_i <= 6.

Of the 117,649 points in this box, 54,159 satisfy sum(g) <= 17 and are admissible; they include every good design found in the pilots.
An inadmissible point is charged to the budget and returned as infeasible without an NLP solve, as the logical rejections of the CSTR and Dynamic cases were.

## Protocol

- Seeds 0–9, each with seven shared starts (d + 1 = 7), drawn uniformly from the admissible points and spanning the space. The starts are the first seven evaluations of every method.
- Budgets B = 25, 50, and 100 evaluations, including the starts. The full plan is 7 methods × 10 seeds × 3 budgets = 210 runs.
- Methods:
  - D-SDA from the best accepted start, with the Separable neighborhood (one-coordinate moves, the neighborhood the original D-SDA used for this column) and improvement tolerance 1e-5.
  - RBFOpt 4.3 MSRSM with genetic global search.
  - BAM with the starts as its predetermined design.
  - FMQA-SA, with a time limit of 7,200 s because objective time counts toward it.
  - Uniform sampling without replacement over the box.
  - NOMAD 4.6 and MISO (soogo CPTV) through the adapters of `experiments/mixed_integer_dfo`.
- Unaccepted values follow the published methods: 1e6, NaN for BAM, and +inf for FMQA.
- Completion time is search overhead plus the measured solve time of every evaluated point, as in the published runs.
- NOMAD and MISO run in a forked child. A native crash is rerun once and kept only if the rerun repeats the search path.
- No global optimum is known, so a hit is a value within 1e-5 relative of the best accepted value found by any run or by the 202-configuration pilot of the same protocol. That value is reported as best-known in `best_known.json`.

## Cost

In a local pilot (seed 0, B = 25), D-SDA, RBFOpt, uniform sampling, NOMAD, and MISO each took 80–130 s, about 4–5 s per evaluation.
The full plan has 12,250 evaluations. At that rate it needs about 15 CPU-hours before cache reuse and FMQA training, so about 1 h on 32 cores.

## Running on Dantzig

    GAMS_EXE=/path/to/gams experiments/catalytic_distillation_live/run_dantzig.sh test
    GAMS_EXE=/path/to/gams CPUS=0-31 experiments/catalytic_distillation_live/run_dantzig.sh run
    GAMS_EXE=/path/to/gams experiments/catalytic_distillation_live/run_dantzig.sh summarize

- The launcher uses these interpreters, which can be overridden:
  - `.venv-dantzig-nlp-overnight` for D-SDA, RBFOpt, and BAM.
  - `.venv-dantzig-fmqa-qhd` for FMQA-SA.
  - `.venv-mi-dfo` for NOMAD and MISO.
- It also uses the Bonmin and IPOPT executables of `.venv-dantzig` and the BAM license file.
- Each job runs pinned to one CPU of `CPUS`, and GAMS inherits the pinning.
- `run` skips jobs that already have a `result.json`, so it can resume.

Outputs in `results/catalytic_distillation_live` (override with `CATDIST_OUTPUT`):

- `plan.json`, `cache.sqlite`, and `controller.log`.
- `runs/<job>/`: `spec.json`, `callbacks.jsonl`, `result.json`, and `worker.log`.
- After `summarize`: `best_known.json`, `runs.csv`, and `conditions.csv`.
