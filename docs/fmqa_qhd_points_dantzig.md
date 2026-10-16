# Complete the QHD logical-rejection point timings

This package measures exactly 96 coordinates: 95 CSTR coordinates outside the
logical triangular domain and Column `(12, 9)`. The original model is freshly
prepared for every measurement. All points must return
`preprocessing_infeasible` before solver invocation; an unexpected solver call
fails the job. No FMQA search is repeated.

It reuses `.venv-dantzig-nlp-overnight` and the pinned `external/dsda-gdp` checkout
already used for the original point measurements. One logical CPU and one
numerical thread are used. Model/source checks run before the per-point timer.
Each point runs in an isolated Python process, writes its result and completion
hash, and retains its log. The selected cost is the original evaluator's
`total_wall_s`. Worker startup and preflight time remain outside this cost.

From the Mac:

```bash
scp /private/tmp/fmqa_qhd_points_dantzig_20261012.zip \
    /private/tmp/fmqa_qhd_points_dantzig_20261012.zip.sha256 \
    lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

On Dantzig:

```bash
(
set -e
cd /local/scratch/a/lee4382/repository/RBFopt_Test
sha256sum -c fmqa_qhd_points_dantzig_20261012.zip.sha256
unzip fmqa_qhd_points_dantzig_20261012.zip
cd fmqa_qhd_points_runner
export POINT_ENV=/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-nlp-overnight
export PYTHONNOUSERSITE=1
"$POINT_ENV/bin/python" -m pip install --no-user -r requirements-gdp.txt \
  "sympy==1.14.0" "networkx==3.6.1"
POINT_CPU=6 bash run_fmqa_qhd_points_dantzig.sh check
POINT_CPU=6 nohup bash run_fmqa_qhd_points_dantzig.sh run \
  > ../fmqa_qhd_points.log 2>&1 &
tail -f ../fmqa_qhd_points.log
)
```

The final output prints `planned_points: 96`, `completed_points: 96`,
`all_completed: true`, `solver_calls: 0`, and the actual `RESULT_ZIP` path.
Use that exact path to download the result with `scp`.

Completed jobs are preserved on interruption. Resume with the printed `RUN_DIR`:

```bash
bash run_fmqa_qhd_points_dantzig.sh resume --run-dir /absolute/RUN_DIR
```

After downloading the result to the Mac, from the repository root:

```bash
python scripts/import_fmqa_qhd_points.py /absolute/path/to/RESULT_ZIP
```

The importer requires all 96 sealed Dantzig measurements, one-thread runtime,
unchanged original GDP/initialization sources and no solver invocation. It
stores the raw ZIP, fills only missing coordinates, rebuilds the cost ledger,
and regenerates process PNG/PDF figures. Existing point observations, lookup
objectives and recorded optimizer paths are unchanged.
