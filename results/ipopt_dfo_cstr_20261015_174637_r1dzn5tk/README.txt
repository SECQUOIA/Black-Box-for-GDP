Verified CSTR-only IPOPT DFO return, 2026-10-15

240 slots returned: 97 target_reached, 124 target_not_reached, 19 execution_failed, 0 not_run.
IMPORTANT: All 19 execution failures are BAM budget-control failures.
N20: seeds2,6; N25: all ten seeds; N30: seeds0,2,3,4,5,7,9.
Each has one recorded B+1 callback after callback B raised BudgetStop.
The B+1 request is retained as a protocol error; its CSV row was not read
and no value was delivered. These failures are separate from IPOPT rejections.
Do not use them as evidence that IPOPT objectives degraded BAM performance.
The original returned classification and ten-seed denominators are unchanged.
This return is not a fully budget-compliant 240-run benchmark. Further BAM
experiments require reviewing the runner/backend stop interaction first.

Counts per ten seeds (hit / miss / execution failure / not run):
  cstr_5 B=8 rbfopt: 10 / 0 / 0 / 0
  cstr_5 B=8 bam: 10 / 0 / 0 / 0
  cstr_5 B=8 dsda: 2 / 8 / 0 / 0
  cstr_5 B=8 fmqa_sa: 3 / 7 / 0 / 0
  cstr_10 B=15 rbfopt: 10 / 0 / 0 / 0
  cstr_10 B=15 bam: 1 / 9 / 0 / 0
  cstr_10 B=15 dsda: 2 / 8 / 0 / 0
  cstr_10 B=15 fmqa_sa: 2 / 8 / 0 / 0
  cstr_15 B=22 rbfopt: 10 / 0 / 0 / 0
  cstr_15 B=22 bam: 1 / 9 / 0 / 0
  cstr_15 B=22 dsda: 2 / 8 / 0 / 0
  cstr_15 B=22 fmqa_sa: 1 / 9 / 0 / 0
  cstr_20 B=29 rbfopt: 9 / 1 / 0 / 0
  cstr_20 B=29 bam: 2 / 6 / 2 / 0
  cstr_20 B=29 dsda: 3 / 7 / 0 / 0
  cstr_20 B=29 fmqa_sa: 1 / 9 / 0 / 0
  cstr_25 B=36 rbfopt: 10 / 0 / 0 / 0
  cstr_25 B=36 bam: 0 / 0 / 10 / 0
  cstr_25 B=36 dsda: 3 / 7 / 0 / 0
  cstr_25 B=36 fmqa_sa: 1 / 9 / 0 / 0
  cstr_30 B=43 rbfopt: 10 / 0 / 0 / 0
  cstr_30 B=43 bam: 0 / 3 / 7 / 0
  cstr_30 B=43 dsda: 3 / 7 / 0 / 0
  cstr_30 B=43 fmqa_sa: 1 / 9 / 0 / 0

Input/source integrity: return ZIP CRC passed; all reproduction files exactly
match the submitted package (including all frozen IPOPT records and sources).
All callbacks were checked against the exact size/coordinate/attempt row.
Six returned aggregate/report files were reproduced byte for byte.
5783 callback attempts are preserved: 5764 within budget and 19 overruns.
N5..25 use mass_balance_zero_recycle; N30 uses constructor defaults.
N10 [10,1] and seven original N30 solver rejections remain unchanged.
CSTR ran on CPU1 (physical sibling49), excluding non-CSTR CPUs0/48.

Timing: DFO clocks are measured server method time, including learning and
candidate/auxiliary solves. Historical NLP time comes from the same CSV row.
N30 unmeasured logical exclusions and protocol-error callbacks have unknown
NLP cost. No missing cost was zero-filled or borrowed from another model.
Callback B is in the ledger but raises BudgetStop without returning a value.
Final best/target observation uses the ledger, as in the supplied protocol.
RBFOpt auxiliary exceptions remain in raw logs; they are not process NLP failures.

Files: runs.csv (240 slots), summary.csv/json (24 groups), inputs_report.csv/json,
callbacks.csv.gz (lossless original aggregate), job_metadata.json (all specs,
actual settings, runtimes, start clocks and results), inputs/ (original CSVs
and provenance), budget_control_failures.csv/json, audit.json and hash inventories.
All original per-job callback paths, solver logs, FMQA proposals, per-point
IPOPT JSON records and executable snapshots remain in the full archive:
  results/archives/ipopt_dfo_cstr_20261015_174637_r1dzn5tk.zip
  SHA256 b91afb707229766adcdcfb1ee67406377d1d2ef44839b062ec9e0539893bfefa
The inputs/ provenance inventories include raw records retained in that archive.
Existing publication results and non-CSTR files were not replaced.
No local optimizer, process NLP solve or enumeration was executed during import.

Reproduce the verification/import into a new directory:
  python3 scripts/import_ipopt_dfo_cstr.py results/archives/ipopt_dfo_cstr_20261015_174637_r1dzn5tk.zip --output /tmp/cstr_dfo_verified_import

The submitted CSTR runner/package is preserved exactly as executed, including
the known BAM stop-handling issue. No post-hoc solver/code repair is applied.
