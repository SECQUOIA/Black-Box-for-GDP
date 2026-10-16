# Dantzig: original GDP point measurements

Use the Python entry point from a repository checkout. Server `.sh` wrappers
are local convenience files and are not required or included in this change.
The published dataset retains **CSTR30 only**, alongside Column, Small Batch
and Dynamic. Historical lookup benchmarks remain unchanged.

## Setup

On Dantzig:

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
git submodule update --init -- external/dsda-gdp external/ld-sda-dynamic
.venv-dantzig/bin/python -m venv .venv-dantzig-gdp
.venv-dantzig-gdp/bin/python -m pip install -r requirements-gdp.txt
```

If `.venv-dantzig-gdp` is already prepared, reuse it. The Python dependencies
do not install native solvers or licenses. The original source revisions are
pinned in Git. For a standalone runner without submodules,
`python -m gdp_models.dantzig setup` obtains the same pinned sources.

## GAMS 52.2 IPOPT, IPOPTH and CONOPT comparison

Set the same thread limits used for the recorded experiments:

```bash
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 GOTO_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 NUMEXPR_MAX_THREADS=1 OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
export MPLBACKEND=Agg PYTHONNOUSERSITE=1
```

Check dependencies, original model transformations and actual solver execution:

```bash
.venv-dantzig-gdp/bin/python -m gdp_models.dantzig check \
  --solvers gams_ipopt,ipopth,conopt --cstr-sizes 30 \
  --executable /package/gams/52.2/gams --expected-gams-version 52.2
```

Run the same matrix:

```bash
nohup .venv-dantzig-gdp/bin/python -m gdp_models.dantzig run \
  --solvers gams_ipopt,ipopth,conopt --cstr-sizes 30 \
  --executable /package/gams/52.2/gams --expected-gams-version 52.2 \
  > gdp_gams_run.log 2>&1 &
tail -f gdp_gams_run.log
```

The first allowed Linux CPU is selected by default. Solvers run sequentially
with a 60-second limit per point. IPOPT uses MUMPS, IPOPTH uses MA27, and CONOPT
uses GAMS' installed CONOPT solver. Native IPOPT remains available as
`--solver ipopt --executable /path/to/ipopt`; its records must remain separate
from GAMS IPOPT measurements.

| Case | Logical candidate points per solver |
|---|---:|
| Column 17 | 64 |
| CSTR30 | 465 |
| Small Batch | 27 |
| Dynamic | 37 |
| Total | 593 |

Three solvers produce 1,779 measurements. Logical candidates are not claims
of continuous feasibility. Rejections and solver errors are retained, and
there is no automatic cross-solver fallback. `complete` means all candidates
were attempted, not that all solves succeeded. CSTR30 normally uses constructor
initialization because its upstream saved-start file does not exist.
The [seven-point retry](cstr30_retry.md) uses a separately recorded feasible start.

## Dynamic preparation and point costs

Dynamic builds and discretizes one unsolved Pyomo DAE template per Python
process (`nfe=30`, `ncp=3`, Radau), then independently clones/fixes/solves each
integer point. No solution is reused as the next point's start.
`dynamic/preparation.json` stores that one-time construction/discretization cost;
point records reference its `preparation_id`. A shared preparation ID copied
into multiple solver folders is the same preparation, not multiple costs.

`solve_wall_s` measures the solver interface call including file/process
handling. `total_wall_s` includes model preparation and validation, excluding
Dynamic's one-time template preparation. These timers overlap. Failed points
also incur recorded costs; a missing time is never zero. Neither summed point
costs nor legacy lookup timings establish a measured end-to-end DFO runtime.

## Results, restart and download

The command prints `RESULT_DIR` and `RESULT_ZIP` under the repository's
`results/` directory. Each case/solver folder contains `evaluations.csv`, full
per-point JSON checkpoints, a manifest, summary and log. The ZIP includes source
snapshots and file checksums; an adjacent `.zip.sha256` checks the archive.

```bash
.venv-dantzig-gdp/bin/python -m gdp_models.dantzig resume --run-dir /absolute/path/to/RESULT_DIR
.venv-dantzig-gdp/bin/python -m gdp_models.dantzig pack --run-dir /absolute/path/to/RESULT_DIR
```

Resume requires the original runner/environment and skips all saved attempts,
including failures. Changed settings or a new retry need a new result folder.
Ctrl+C packages completed work; `pack` recovers already saved records after a
forced termination. `--max-points 3` limits new evaluations per case for a short
pipeline check, and `--cases cstr --cstr-sizes 30` restricts the run to CSTR30.

Download from a **Mac terminal**, replacing the result name:

```bash
scp lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/results/RESULT_NAME.zip \
  ~/Downloads/
```

## Published measurements

[The merged timing dataset](../results/gdp_point_timings_20260922/README.md)
contains the GAMS measurements from September 22 and seven returned CSTR30
IPOPT retries. It excludes CSTR5–25 and the earlier missing-SymPy run. Original
attempts and retry costs remain separate from selected per-coordinate results.
The published merge is reproducible from the two extracted result archives
using `scripts/merge_gdp_timings.py`; see the dataset README.
