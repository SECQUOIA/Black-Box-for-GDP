# QHDOpt Grid-only FMQA-SA benchmark

Use `fmqa_grid_benchmark.py` or `run_fmqa_grid_dantzig.sh` to run only the
QHDOpt-derived grids in `benchmark_grids/`. No Column, CSTR, Small Batch or
Dynamic jobs are included. This evaluates FMQA-SA on the same sampled surfaces
as the existing DSDA/RBFOpt/BAM experiments; it does not run the QHDOpt solver.

The separate execution ZIP is `fmqa_grid_runner.zip`. It extracts into
`fmqa_grid_runner/`, so the existing process benchmark's `fmqa_runner/` can
remain in place. The two entry points share the same optimizer implementation.
The original process-only ZIP already sent to Dantzig remains valid.

Shell wrappers are optional local files and are not committed. From a fresh
checkout, install `requirements-fmqa.txt`, then use
`python fmqa_grid_benchmark.py check` and
`python fmqa_grid_benchmark.py run --output-root results`.
The shell examples below apply to older local bundles that included wrappers;
inside a newly generated bundle use the Python entry point with
`--output-root ../results` instead.

## Fixed experiment

- 21 normalized 31 x 31 objective tables; integer coordinates `0..30` in both axes.
- 10 seeds (`0..9`), three shared initial points, and five total evaluation
  budgets (`10,30,50,70,100`) including initialization: **1,050 FMQA-SA runs**.
- The exact 210 ordered designs are loaded from the archived BAM 5.0.0
  `comparison_audit.json`, never regenerated. For example, seed 0 uses
  `(4,7), (30,30), (12,11)`.
- All 21 table files were checked byte-for-byte against original commit
  `eeb560059c7001ad82c13b9249168531af073f95`; packaged checksums are enforced.
- Baseline CSV hashes, all 4,200 archived rows (three original methods plus
  the BAM 5.0.0 rerun), and initial incumbent prefixes are validated.

The original Grid run did not have the process dataset's per-design coordinate
hash manifest. Coordinate evidence here comes from the server BAM rerun audit,
which checked the original sampling versions/source and initial objective
prefixes. Prefix agreement alone does not uniquely identify every coordinate;
the saved coordinates plus the audit's source/version checks are the evidence.
New FMQA runs record ordered-coordinate hashes and every actual evaluation.

Learning and sampling settings are identical to the process runner:
rank-8 FM, NumPy port of the original MXNet backend, 1,000 Adam epochs per
iteration, learning rate 0.01, 100 SA reads, 1,000 sweeps, seeded randomness,
one thread/one allowed Linux CPU and a 30-minute safety cap per run.
Training uses observed points only. If SA yields no in-bounds unseen candidate,
a uniform unseen point is evaluated and the fallback is logged. Inspect this
fraction when interpreting FMQA-SA performance.
See [algorithm and implementation details](fmqa_benchmark.md#relationship-to-bbo_via_fmqa).

The input `z_norm` tables are already normalized, as in the historical Grid
benchmark. This preprocessing is shared by all methods; the FM's additional
training-target scaling uses observed evaluations only.

## Upload and execute

On the Mac:

```bash
scp /Users/albertlee0125/Repos/RBFopt_Test/results/dantzig_review/fmqa_grid_runner.zip \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

On Dantzig, after the current benchmark finishes:

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
unzip fmqa_grid_runner.zip
cd fmqa_grid_runner
sha256sum -c RUNNER_SHA256SUMS
bash run_fmqa_grid_dantzig.sh check
nohup bash run_fmqa_grid_dantzig.sh run > ../fmqa_grid_dantzig.log 2>&1 &
```

`check` reuses the existing `.venv-dantzig-fmqa`. On a new installation use
`bash run_fmqa_grid_dantzig.sh setup` once before `check`.
No QCI/quantum token, GAMS or BAM license is required.

```bash
tail -f /local/scratch/a/lee4382/repository/RBFopt_Test/fmqa_grid_dantzig.log
```

`Ctrl+C` exits `tail` without stopping the benchmark. Results have a distinct
prefix: `results/dantzig_fmqa_grid_TIMESTAMP_ID/`, plus `.zip` and `.zip.sha256`.
The completed aggregate is **`benchmark.csv`**, with its audit manifest,
per-evaluation coordinates and timings, SA proposal logs and source snapshots.
Source snapshots contain both shared entry points for provenance; the Grid
run plan and result CSV contain Grid jobs only.

Examples for local verification or selecting a subset:

```bash
python fmqa_grid_benchmark.py plan
python fmqa_grid_benchmark.py run --grids ackley,alpine1 --seeds 0 --grid-budgets 10
bash run_fmqa_grid_dantzig.sh run --resume ../results/dantzig_fmqa_grid_TIMESTAMP_ID
```

Resume uses the original selection/options and does not rerun completed jobs.
Earlier interrupted attempts are preserved. After a forced termination:

```bash
bash run_fmqa_grid_dantzig.sh pack --run-dir ../results/dantzig_fmqa_grid_TIMESTAMP_ID
```

## Download and compare

On the Mac, use the filename printed as `RESULT_ZIP`:

```bash
scp lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/dantzig_fmqa_grid_TIMESTAMP_ID.zip ~/Downloads/
```

On Dantzig, from `fmqa_grid_runner/`, compare with the archived DSDA/RBFOpt and
BAM 5.0.0 results:

```bash
bash run_fmqa_grid_dantzig.sh compare \
  --fmqa-results ../results/dantzig_fmqa_grid_TIMESTAMP_ID.zip \
  --output-dir ../results/fmqa_grid_comparison_TIMESTAMP_ID \
  --time-profiles
```

Equivalent local command:

```bash
python fmqa_compare.py --dataset grid \
  --fmqa-results ~/Downloads/dantzig_fmqa_grid_TIMESTAMP_ID.zip \
  --output-dir results/fmqa_grid_comparison_TIMESTAMP_ID --time-profiles
```

Full results pair to **4,200 rows across four methods**, with 210 paired
instances per budget. Outputs include `benchmark.csv`, `solved_fraction_summary.csv`,
evaluation performance profiles, convergence curves and, with `--time-profiles`,
completed-run time profiles and supporting tables under `timing/`.
These times cover lookup optimization overhead (including FM training/SA and
logging), not GDP/NLP subproblem solves. Historical completion times are not
first-hit times. Keep load and hardware comparable when interpreting runtimes.

To rebuild a distinct Grid-only execution ZIP:

```bash
python fmqa_grid_benchmark.py bundle --output /tmp/fmqa_grid_runner.zip
```
