Verified CSTR30 structural-rejection timing supplement

435/435 x2>x1 points measured, with finite positive total_wall_s and integer
elapsed_ns. Status preprocessing_infeasible; termination not_solved; objective
blank; accepted=False; solve_wall_s=0 because no solver was called.
Original465 objectives, statuses and times are unchanged in the combined900
unique-point table. No rows are missing, duplicated or replaced by retries.

Measured rejection time (seconds):
  Minimum 0.195096984; median 0.197789882; maximum 0.922110536.
  Sum across435 unique points: 95.46080097400004.
  Separate common preparation: 0.909763244.
The interval includes the original fresh-model construction, initialization,
external fixing and GDP logic checks until rejection returns. Source preloading,
CSV reads/writes, progress output and common preparation are excluded.

508 callback costs for228 visited structural coordinates are filled, charging
each repeated visit. Missing times decrease from515 to7. All40 run outcomes
and all1,615 original callback fields remain unchanged, including objectives,
penalties, visit order, counts, DFO runtime and lookup runtime.
The remaining7 gaps are BAM B+1 protocol errors (seeds0,2,3,4,5,7,9), whose
process CSV rows were never read. These remain execution_failed with unknown
cost, not zero cost; all33 other runs have complete reconstructed process sums.

Use reconstructed_process_wall_s in callbacks_with_timing_supplement.csv.gz.
The original timing fields remain historical evidence. Per-run before/after
counts and process cost sums are in cstr30_run_time_comparison.csv. These are
reconstructed costs from separate measurements, not measured online DFO times.
Original DFO datasets, search results and success classifications are untouched.

Raw archive retained locally, excluded from the published result:
results/dantzig_review/cstr30_structural_returns/dantzig_cstr30_structural_20261015_214202_pgve882p.zip
All1,133 archive members, including435 individual records, original465.csv,
the full JSONL ledger and frozen execution sources, remain in that unchanged ZIP.
The curated CSV/JSON files are exact copies; the callback CSV is losslessly
gzip-compressed. audit.json and file-hash inventories document the checks.
Historical inputs/execution sources are not duplicated as loose files here.

Executed code commit: 366b001e920a435f696fdcfc14499663a7f018b6
Runtime: Dantzig CPU0, Python3.11.16, Pyomo6.10.0. Model/source identities,
all input hashes and the nanosecond clock are retained in manifest.json.
No local model construction, solver calls, DFO search or timing measurement
was performed during import. Reports were regenerated in a temporary folder
and checked byte-for-byte against the returned reports.

Recheck without writing repository files:
python3 scripts/import_cstr30_structural_rejections.py \
  /path/to/dantzig_cstr30_structural_20261015_214202_pgve882p.zip --check-only
Import into another new directory using --output /new/path.
