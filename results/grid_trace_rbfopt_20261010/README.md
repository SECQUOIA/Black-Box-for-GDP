# Complete RBFOpt Grid trajectories, October 10, 2026

All **1,050 runs** have complete ordered trajectories: **21 grids × 10 seeds
× five budgets (10, 30, 50, 70, 100)**. The records contain **54,600 actual
objective callbacks**, including **3,150 initial** and **51,450 adaptive**
evaluations. There are **7,514 unique (grid, coordinate) pairs**. No cases,
callback sequence numbers or completed traces are missing.

## Saved paths

- [Original ZIP](../archives/grid_trace_rbfopt_20261008_190603_og2app39.zip)
  and [SHA-256](../archives/grid_trace_rbfopt_20261008_190603_og2app39.zip.sha256)
  retain all original results, logs, source snapshots and solver artifacts.
- All 1,050 individual JSONL trajectories are stored in the original ZIP,
  with their original headers, ordered evaluations and completion records.
  For example, `grid_ackley_B100_seed0_rbfopt` can be located using the index.
  The optional `trajectories/` copies can be restored with `--extract` below.
- [Trajectory index](trajectory_index.csv) maps every run to its optional local JSONL,
  original archive member, SHA-256, callback count and measured search time.
- [Combined evaluation table](raw/evaluations.csv) contains all 54,600 callback
  rows in run/evaluation order. Its `trace_path` column preserves the original
  archive member path; use the index for the optional extracted JSONL filename.
- [Benchmark results](raw/benchmark.csv), [unique visited points](raw/visited_points.json),
  [frozen run plan](raw/run.json), [summary](raw/summary.json) and
  [final progress](raw/progress.json) preserve the original exported bytes.
- [Verification](verification.json) records coverage and integrity checks;
  [parser observations](parser_roundoff.json) retain last-bit differences seen
  when independently reading the reference CSVs on the publishing Mac.

Every callback records requested and evaluated coordinates, its evaluation
index, initial/adaptive phase, objective, best objective so far, repeated-point
flag and elapsed timings. Coordinates are **integer grid indices 0 through 30**,
not physical function coordinates. Points shared between separate runs remain
in every trajectory. There were zero within-run repeated callbacks in this
particular RBFOpt archive; no deduplication was performed.

## Verification and reproduction

```bash
python results/grid_trace_rbfopt_20261010/verify_archive.py
# Optional: restore all individual JSONLs locally (ignored by Git).
python results/grid_trace_rbfopt_20261010/verify_archive.py --extract
shasum -a 256 -c results/archives/grid_trace_rbfopt_20261008_190603_og2app39.zip.sha256
```

The verifier requires pandas, as used by the original grid CSV loader. It
does not run RBFOpt or any archived Python code. The default verifies all ZIP
trajectories and retained tables without extracting individual JSONLs.
`--extract` recreates their byte-preserved copies and refuses to overwrite
different data. Historical verification and parser observations remain intact;
the verifier reports the current platform's parser observations separately.
The historical `saved_trajectory_files` count describes the 1,050 indexed
traces, whether or not their optional local copies are present.

Checks cover ZIP CRCs and all **5,546 internal file hashes**, all **41 source
hashes**, the frozen initial designs and ordered run matrix, result/trace seals,
headers and completion records, exact budgets and native evaluation counts,
all coordinate bounds, objective values, running incumbents, final best points,
repeated-point flags and monotonic callback clocks. The combined CSV is checked
against every field of every individual callback. Each grid has 50 runs and
2,600 callbacks.

The publishing Mac's pandas 2.3.3 parser differs from the recorded server
values for 154 callbacks by at most two binary64 ULPs (maximum absolute
difference 6.776263578034403e-21). These cases are also within two ULPs of direct
decimal conversion. The original values are preserved. Trace-to-export,
incumbent, final-objective and cross-run-value checks are exact; the tolerance
applies only to the independent reference-parser comparison. A subsequent
verification may observe different parser differences on a different platform.

## Use with IPOPT point costs

These are the **new October 8–10 rerun trajectories**, not reconstructions of
the earlier benchmark's missing paths. The archive used RBFOpt 4.3.0 on Dantzig,
logical CPU 0, one thread, the three frozen starting points, MSRSM, automatic
RBF selection and solver-based global search. Runtime details are in `run.json`.

The trace measures CSV lookups, not GDP/NLP solves. Internal optimizer
candidates or cache accesses that never call the objective are outside its
scope. To reconstruct elapsed time using the existing
[20,181 IPOPT point measurements](../grid_gdp_20261009/raw/point_timings.csv),
join the function name and integer coordinate, preserving callback order:

```text
reconstructed_elapsed(k) = completed_elapsed_s(k)
                          - sum(objective_wall_s for callbacks 1..k)
                          + sum(point_wall_s for their grid coordinates)
```

For a full run use the index's `search_wall_s` instead of the last callback
clock. The source search clock includes setup and trace writes but excludes CSV
loading, final validation and worker startup. This publication stores the
trajectories; it does not replace their measured lookup times with estimates.
