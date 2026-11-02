# Dantzig catalytic distillation Column results

This directory archives the completed Dantzig live-NLP catalytic distillation Column campaign and a data-only audit of its returned results.
The directory date follows the recorded UTC execution date, 2026-11-01.
Execution revision recorded in the return: `5580a7eacdc8b4098ba5c239822de2300e667a1c`.
Publication base revision: `8612336dc67733d1cf2162572cab1677fb529588` on `feature/catalytic-distillation-pilot`.
The later optional case-selection support and lomustine additions do not change the provenance of this earlier Column run.
No experiment, NLP solve, preflight, or failed job was rerun while preparing this publication.

## Execution

Host: `dantzig.ecn.purdue.edu`.
Actual allocation was three single-thread workers on socket 0: CPU 17 / core 21, CPU 38 / core 50, and CPU 43 / core 57.
Their SMT siblings were 65, 86, and 91, respectively, and were not assigned as separate workers.
Start: `2026-11-01 00:13:21.828690 UTC`; finish: `2026-11-01 03:00:54.444394 UTC`.
In Indiana, these timestamps are `2026-10-31 20:13:21.828690 EDT` and `2026-10-31 23:00:54.444394 EDT`.
Elapsed campaign wall time was 10,052.615704 s, or approximately 2 h 47 min 33 s; controller exit code was 0.
GAMS was `54.3.1` at `/package/gams/54.3/gams`, and the recorded CONOPT backend version was `4.39.1`.
All three Python interpreters were `3.11.16`; exact paths and distribution locations are retained in `wrapper_execution.json`.

| Environment | Main recorded packages |
| --- | --- |
| DFO | RBFOpt 4.3.0; bam-solver 5.0.0; NumPy 2.4.6; pandas 3.0.5 |
| FMQA | torch 2.8.0+cpu; dimod 0.12.21; dwave-samplers 1.6.0; NumPy 2.2.6 |
| MI-DFO | PyNomadBBO 4.6.0; soogo 2.1.0; NumPy 2.4.6; pandas 2.3.3; SciPy 1.17.1 |

## Results

The plan and individual records cover exactly 210 runs: seven methods, budgets 25/50/100, and seeds 0–9 for each condition.
All 210 runs have `completed` status, with 9 target hits and 201 target misses; there are no missing or duplicate runs, run failures, worker timeouts, native crashes, or native reruns.
Each condition retains its original denominator of ten seeds.

| Method | B = 25 | B = 50 | B = 100 |
| --- | ---: | ---: | ---: |
| D-SDA | 0/10 | 0/10 | 3/10 |
| RBFOpt | 0/10 | 1/10 | 1/10 |
| BAM | 0/10 | 0/10 | 0/10 |
| FMQA-SA | 0/10 | 0/10 | 0/10 |
| Uniform | 0/10 | 0/10 | 0/10 |
| NOMAD | 0/10 | 0/10 | 0/10 |
| MISO | 0/10 | 1/10 | 3/10 |

The best accepted observed design is `(f1, c1, c2, c3, f2, b) = (8, 8, 12, 17, 17, 21)`, with gaps `(6, 0, 3, 4, 0, 4)` and minimized objective `zobj = 24895.552861 $/yr`.
It improves on the same-protocol pilot best of `25271.327689 $/yr` by `375.774828 $/yr`.
This is a best-known observed value, not a certified global optimum or lower bound.
The unchanged hit rule is `abs(run_best - best_known) <= 1e-5 * max(1, abs(best_known))`, giving an absolute tolerance of `0.24895552861`.
The design was reached by D-SDA at B=100/seeds 2,8,9; MISO at B=50/seed 6 and B=100/seeds 3,5,6; and RBFOpt at B=50/seed 6 and B=100/seed 6.

## Accounting and limitations

There were 12,015 charged evaluations: 6,921 accepted responses, 2,789 logical rejections without NLP solves, and 2,305 unaccepted NLP responses.
No admitted evaluation exceeded its budget or box bounds, all runs preserved the seven shared starts in order, and no run evaluated the same point twice.
Eight D-SDA runs stopped below budget under the unchanged termination rules.
NOMAD made 120 additional requests after the cap across 30 runs; the existing guard rejected them before response lookup or NLP evaluation.
The 9,226 admissible requests reference 3,499 distinct cache entries, so 5,727 requests repeat configurations across runs.
This repeated-request count is not an exact cache-hit or NLP-call count because concurrent initial misses can race.
The recorded solve counters sum to 3,500, while the cache contains 3,499 configurations; the exact total of actual NLP calls cannot be recovered from these records.
The cache has 2,652 accepted responses and 847 unaccepted responses: 842 `model5_solve1`, four `model7_solve4`, and one `modelNone_solveNone`.
Two cached GAMS calls have return code 7; one is accepted under the original modelstat/solvestat-only rule, and one has no reported model or solver status and is unaccepted.
These evaluation-level outcomes are preserved and are separate from the 210 completed search runs.
The unchanged original summary files use the sixth sorted observation as their median for ten seeds; `analysis/conditions_recomputed.csv` additionally reports the conventional middle-pair median and linear-interpolated quartiles.
Charged completion time equals search overhead plus the recorded solve time charged to each evaluated point, including cached responses; it is not elapsed campaign time.
The returned wrapper records all ten required preflight tests passing across the designated environments, including the live GAMS test; the raw preflight and private GAMS logs remain on Dantzig and are not included in this return.

## Evidence and verification

Uploaded original: `evidence/RETURN_B.zip`; `1,544,410` bytes; SHA256 `9518bf6ab26faed2d2b2b5e9834280c40a98c0c760679170d480e48112e78dab`.
Original nested collect archive: `evidence/catalytic_distillation_live_dantzig_20261101_030054.zip`; `1,808,154` bytes; SHA256 `1ff96f101b3e30cbb0c47663af13d5d8fc680eb1466c425868e1e25825718e26`.
Both original ZIPs are preserved byte-for-byte, pass CRC checks, and are below the 90 MB limit.
The audit verifies model/initialization/solve-script hashes against the execution revision, regenerates only the initial designs, and checks all 210 results, 12,015 callbacks, 21 condition rows, controller exit records, and the SQLite cache.
Original result summaries and logs are unchanged; the returned README is retained as `evidence/README.returned.md`.
Further statistics and qualifications are in `analysis/REPORT.md`, and machine-readable checks are in `analysis/validation.json`.

From a checkout containing the recorded execution commit, the following commands verify and analyze existing data without invoking a solver.

```bash
(cd results/catalytic_distillation_live_20261101/evidence && shasum -a 256 -c RETURN_B.zip.sha256)
python results/catalytic_distillation_live_20261101/analysis/analyze.py \
  --result-dir results/catalytic_distillation_live_20261101 \
  --repository . --output /tmp/pr57_column_data_audit
```

The audit uses Python 3.11 or later and NumPy; it was run with NumPy 2.4.6.
