Non-CSTR IPOPT DFO return audit, 2026-10-15

Original report: 320 slots; 190 target_reached, 129 target_not_reached, 1 execution_failed, 0 not_run.
Separate protocol audit: 184 target_reached, 127 target_not_reached, 9 execution_failed, 0 not_run.
Column B16 seed0 DSDA failed after three unaccepted starts: [8,3], [15,9], [10,4].
It was retained; seed0 was not replaced with seed10.

IMPORTANT: Eight Dynamic BAM runs requested a callback after B:
B30 seeds1,4,7,9; B37 seed7; B50 seeds4,6,8.
The older non-CSTR guard raised before recording these calls. The worker
then labeled them budget_completed. Six had already observed the table
minimum within B. Their original records remain unchanged, while separate
audit categories flag protocol failure. No new objective was read/returned
for the blocked calls. Their coordinates and exact count are unknown.
7058 callbacks are logged; at least 7066 were requested. This is not a
fully documented, budget-compliant 320-run benchmark. IPOPT rejection
and the BAM runner/backend exception interaction are distinct issues.

Counts per ten seeds (original hits/misses/failures -> audit hits/misses/failures):
  column B=16 rbfopt: 4/6/0 -> 4/6/0
  column B=16 bam: 0/10/0 -> 0/10/0
  column B=16 dsda: 5/4/1 -> 5/4/1
  column B=16 fmqa_sa: 4/6/0 -> 4/6/0
  dynamic B=12 rbfopt: 9/1/0 -> 9/1/0
  dynamic B=12 bam: 0/10/0 -> 0/10/0
  dynamic B=12 dsda: 4/6/0 -> 4/6/0
  dynamic B=12 fmqa_sa: 2/8/0 -> 2/8/0
  dynamic B=15 rbfopt: 10/0/0 -> 10/0/0
  dynamic B=15 bam: 3/7/0 -> 3/7/0
  dynamic B=15 dsda: 5/5/0 -> 5/5/0
  dynamic B=15 fmqa_sa: 3/7/0 -> 3/7/0
  dynamic B=20 rbfopt: 10/0/0 -> 10/0/0
  dynamic B=20 bam: 3/7/0 -> 3/7/0
  dynamic B=20 dsda: 8/2/0 -> 8/2/0
  dynamic B=20 fmqa_sa: 3/7/0 -> 3/7/0
  dynamic B=30 rbfopt: 10/0/0 -> 10/0/0
  dynamic B=30 bam: 4/6/0 -> 1/5/4
  dynamic B=30 dsda: 10/0/0 -> 10/0/0
  dynamic B=30 fmqa_sa: 4/6/0 -> 4/6/0
  dynamic B=37 rbfopt: 10/0/0 -> 10/0/0
  dynamic B=37 bam: 7/3/0 -> 7/2/1
  dynamic B=37 dsda: 10/0/0 -> 10/0/0
  dynamic B=37 fmqa_sa: 5/5/0 -> 5/5/0
  dynamic B=50 rbfopt: 10/0/0 -> 10/0/0
  dynamic B=50 bam: 10/0/0 -> 7/0/3
  dynamic B=50 dsda: 10/0/0 -> 10/0/0
  dynamic B=50 fmqa_sa: 6/4/0 -> 6/4/0
  small_batch B=10 rbfopt: 5/5/0 -> 5/5/0
  small_batch B=10 bam: 2/8/0 -> 2/8/0
  small_batch B=10 dsda: 8/2/0 -> 8/2/0
  small_batch B=10 fmqa_sa: 6/4/0 -> 6/4/0

Input IPOPT table minima (reporting targets, not GDP global optima):
  column: 19346.124801 at [[13, 4]]; 29/64 accepted; statuses {'rejected': 7, 'preprocessing_infeasible': 28, 'accepted': 29}; 17 unmeasured logical exclusions in the search box.
  dynamic: -212.008787157 at [[1, 4]]; 37/37 accepted; statuses {'accepted': 37}; 35 unmeasured logical exclusions in the search box.
  small_batch: 167427.657115 at [[2, 2, 1]]; 12/27 accepted; statuses {'preprocessing_infeasible': 15, 'accepted': 12}; 0 unmeasured logical exclusions in the search box.

RBFOpt reaches the Dynamic target in 9/10 runs at B12 and 10/10 at B15+
and DSDA in 10/10 at B30+. Small Batch favors DSDA (8/10) in this return.
Column has lower hit rates (RBFOpt4, BAM0, DSDA5, FMQA4 out of10).
These observations alone do not isolate the effect of changing BARON to IPOPT.

Input provenance: Column and Small Batch use SECQUOIA/dsda-gdp at
3e469dbeea8931670b8cd6752014ab7a767d3af5 and the upstream saved initializations.
Dynamic uses SECQUOIA/LD-SDA-Dynamic at 482e14ebf9caabbd35d959986942cb028778a1d7
with constructor defaults, 9 stages, nfe30/ncp3 LAGRANGE-RADAU.
All logical candidates are processed; no missing candidate became infeasible.
Column retains 7 rejected rows, 28 preprocessing_infeasible rows and 29 accepted rows.
Raw candidate objectives, termination, solver statuses and reasons remain in source_row.
Penalties: RBFOpt/DSDA 1e6; BAM NaN; FMQA callback +inf (reporting penalty1e6).
Rejected is an unaccepted evaluation, not a proof of global infeasibility.

Recorded NLP cost is complete for 9/40 Column runs, 2/240 Dynamic runs,
and all40 Small Batch runs. The missing costs are unmeasured logical
exclusions, not zero-duration NLP solves. Total cost for affected runs is
unavailable. Preprocessing-only records may lack setup/preprocess split
despite having measured total time. Dynamic one-time preparation cost
(0.1090063113s) is preserved separately. No missing times are zero-filled.
DFO wall time includes surrogate/candidate work and is separate from NLP
historical cost and CSV lookup time. Every input has one selected attempt.
Callback B is recorded but raises BudgetStop without delivering its value.
Reported best is the best accepted ledger observation, including callback B.
Target rule: abs(best-table_min) <= 1e-5*max(1,abs(table_min)); reporting only.

Verification: ZIP CRC; exact submitted/reproduced package and input hashes;
CSV versus raw attempt records; every logged callback and same-attempt
cost; original LHC design; seeds0..9; actual settings and environment;
four server reports reproduced byte-for-byte. CPU0/sibling48 was used.
RBFOpt auxiliary exceptions are retained and are not process NLP failures.
No optimizer/process solver/enumeration was run locally during this import.

Original files: runs.csv, summary.csv/json, callbacks.csv.gz (lossless).
Audit: audited_runs.csv, analysis_groups.csv/json, budget_control_issues.csv/json,
inputs_report.csv/json, audit.json. Job specs/settings/runtime/results are
in job_metadata.json; frozen inputs and per-attempt records are in inputs/.
All original per-job paths, logs, proposals, evidence and executable
snapshots remain in the full return archive:
  results/archives/ipopt_dfo_non_cstr_20261015_172428_o671edu_.zip
  SHA256 ed7eaa2c20031b58f5a9c02c0bc89699cf170c7e256a65c92664ac4b1875cc6e
Archive and compact-export SHA256 inventories are included.

Reproduce into a new directory (no optimizer calls):
  .venv/bin/python scripts/import_ipopt_dfo_non_cstr.py results/archives/ipopt_dfo_non_cstr_20261015_172428_o671edu_.zip --output /tmp/non_cstr_dfo_verified_import

Before a clean BAM comparison, review the callback stop/exception handling
and rerun affected slots under the same input/settings/seeds if authorized.
The submitted runner remains exactly as executed; no repair/rerun is applied.
Existing CSTR and publication results are unchanged.
