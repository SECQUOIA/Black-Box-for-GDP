Column and Dynamic full-box IPOPT return, October 15, 2026

Verified against the returned ZIP, its 153 per-coordinate JSON records, the
submitted execution ZIP and the frozen historical CSV/manifest pairs.
No process solve, DFO search, retry or acceptance-rule change was performed
during import. audit.json and import_files_sha256.json record the checks.

Case     All points  Accepted  Logical exclusion  Preprocessing failure  IPOPT failure
Column          81        29                 17                     28              7
Dynamic         72        37                 35                      0              0

No missing/duplicate coordinates or missing total_wall_s values.
All 29 Column and 37 Dynamic accepted coordinates are unchanged, and their
objectives match the prior CSVs exactly at the stored numeric precision.
Column's best accepted point: [13,4], objective 19346.124801006445.
Dynamic's best accepted point: [1,4], objective -212.00878715666533.
These are table best values, not claims of global GDP optimality.

Measured total_wall_s by outcome (seconds)
Case     Status                     Count       Sum       Minimum       Maximum
Column   accepted                      29   39.493950     1.275008      1.700023
Column   logical_infeasible             17    6.371567     0.358513      0.495221
Column   preprocessing_infeasible       28   11.197053     0.372767      0.485237
Column   ipopt_failed                    7   10.281251     1.369011      1.764566
Dynamic  accepted                      37   46.333338     1.138428      1.915211
Dynamic  logical_infeasible             35    3.007893     0.078794      0.157834

The exact values and status groups are in audit.json; CSV/JSON source times
are preserved without rounding. Total coordinate times are 67.34382153360639
seconds for Column and 49.34123130014632 seconds for Dynamic. Dynamic's common
template preparation took 0.06644518999382854 seconds, recorded separately in
dynamic/preparation.json and excluded from coordinate totals.

total_wall_s covers model preparation/cloning, initialization, logic/fixing,
preprocessing, any actual solver call and validation. Rejected points traverse
the original evaluator and have measured times. A zero solve_wall_s means the
solver was not called; it does not make the coordinate's total cost zero.
Stage times can be blank when not reached. logic_wall_s is a subset of setup;
do not add it to setup again. Shared preparation and checkpoint/CSV writing
are outside coordinate totals. Full definitions are in
reproduction/docs/column_dynamic_box_ipopt.txt.

IPOPT failure is retained separately from logical/preprocessing rejection.
Raw solver status, termination, candidate objective and validation are kept.
Column's completed_with_errors summary means all 81 points were processed,
including 7 IPOPT failures; it does not mean 7 coordinates are missing.

Runtime: Dantzig, CPU0, Python3.11.16, Pyomo6.10.0, GAMS52.2,
IPOPT3.14.19/MUMPS5.8.1. Process time limit60 seconds, unchanged acceptance
and initialization. Executed code commit686a5cdec3a8fa8ee94da8624e62ff54ca34dae4.
Column: 17 trays, saved column_17 initialization, dsda-gdp commit3e469dbe.
Dynamic: 9 stages, constructor defaults, nfe30/ncp3 LAGRANGE-RADAU,
LD-SDA-Dynamic commit482e14eb. Full identities and options are in manifests.

Recheck the original archive without solving or changing files:
python3 scripts/import_column_dynamic_box_ipopt.py \
  results/archives/dantzig_column_dynamic_ipopt_20261015_205822_gG8bXK.zip --check-only

Reproduce the import into a new directory:
python3 scripts/import_column_dynamic_box_ipopt.py \
  results/archives/dantzig_column_dynamic_ipopt_20261015_205822_gG8bXK.zip \
  --output /new/output/directory

Prior DFO experiments and frozen inputs remain unchanged. Their old CSV loader
requires64/37 rows; this81/72-row table needs a separately reviewed loader
update. New times have not been silently attached to historical DFO records.
