# Dantzig D-SDA rerun without re-evaluating explored configurations

The corrected D-SDA completed all 1,470 planned results on Dantzig using stored configuration responses, with no new GDP or NLP solves.
Grid target hits increased from 374/1,050 to 384/1,050, and Process single-descent hits increased from 74/140 to 79/140.
Both Process restart variants reached 80/140, compared with 74/140 in the previous Dantzig return.
No previous target hit was lost and no final best objective became worse in any same-variant comparison.
The run used the existing no-revisit implementation without modifying the algorithm, model, experiment settings, or manuscript.

## Results compared with the previous implementation

| Cohort | Runs | Previous target hits | New target hits | Change |
| --- | ---: | ---: | ---: | ---: |
| Grid B=10 | 210 | 13 | 13 | +0 |
| Grid B=30 | 210 | 74 | 78 | +4 |
| Grid B=50 | 210 | 88 | 91 | +3 |
| Grid B=70 | 210 | 98 | 101 | +3 |
| Grid B=100 | 210 | 101 | 101 | +0 |
| Grid total | 1050 | 374 | 384 | +10 |
| Process single | 140 | 74 | 79 | +5 |
| Process ranked | 140 | 74 | 80 | +6 |
| Process ranked_random | 140 | 74 | 80 | +6 |

All supplied local cross-check counts match the Dantzig output.
The comparison uses the published target-stop Grid archive and the corresponding Process variants from the previous Dantzig restart run.
The primary Process single-descent comparator also matches the published baseline.
Under the corrected rule, restarts add one target hit beyond single descent, on CSTR30/B43/seed4.
Ranked and ranked_random each improve the objective on 14 Process jobs relative to corrected single descent.
Random restarts use 194 more callbacks than ranked restarts without another target hit in this sample.
The earlier observation that restarts add no target hits applies to the previous repeated-evaluation implementation.

| Cohort | Previous evaluations | New evaluations | Reduction |
| --- | ---: | ---: | ---: |
| Grid total | 37,253 | 31,805 | 14.6% |
| Process single | 2,441 | 2,151 | 11.9% |
| Process ranked | 3,371 | 3,206 | 4.9% |
| Process ranked_random | 3,400 | 3,400 | 0.0% |

Summed evaluation costs reconstructed from the stored point timings decrease by 17.6% for Grid and 10.9% for Process single descent.
These reconstructed costs are separate from the elapsed time of this lookup-only experiment and are not new live-NLP timing measurements.
Conditions reuse functions and seeds across budgets, and these descriptive comparisons do not establish statistical significance or universal superiority.

## Execution

Execution SHA: `c186408728c6f95ac33a5465edd53035d85c5620`.
Host: `dantzig.ecn.purdue.edu`.
Logical CPU: 47; socket: 0; physical core: 61; SMT sibling: 95.
All numerical libraries used one thread, and every result reports effective affinity `[47]`.
Interpreter: `/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig/bin/python`.
Python: 3.11.16; NumPy: 2.4.6; pandas: 2.3.3; SciPy: 1.17.1.
Experiment start: `2026-10-31T23:08:29.688498+00:00`; finish: `2026-10-31T23:08:47.809257+00:00` (UTC).
The local Indiana interval was 19:08:29–19:08:47 EDT on October 31, 2026.
The experiment took 18.120759 seconds, and the launcher through packaging took 18.919380 seconds and exited zero.
The output was `/local/scratch/a/lee4382/repository/dsda_no_revisit_output_20261031_230829`.
The saved results comprise 1,050 Grid jobs and 140 Process jobs for each of single, ranked, and ranked_random.
The original runner additionally performed 1,190 historical-mode validation searches, which are controls rather than additional primary results.

## Validation and preserved evidence

All 1,470 original checks pass, with 1,158 `completed` and 312 `budget_completed` execution statuses and no execution failures.
Budget completion is a termination status and does not itself mean that the target was reached.
The independent audit checks all 40,562 callback responses against the stored input tables, shared initial-point order, seeds, coordinates, uniqueness, evaluation budgets, objective values, target scoring, point costs, and timing arithmetic.
It reconstructs all 1,470 run-summary rows and 47 condition summaries from individual records.
All 1,190 primary paths preserve the historical path with duplicate evaluations removed, and all 280 restarted paths preserve the corrected single-descent prefix.
The 1,190 historical-mode replay checks are reported as passed by the server.
The original runner removes its temporary historical-mode traces, so the return does not independently retain those replay traces; this audit verifies the check flags and the archived-prefix and outcome comparisons without rerunning the algorithm.
ZIP CRCs, 13,791 historical output-member hashes, 263 sealed input-member hashes, and the pinned execution-source and input hashes pass.
The original return, inner experiment ZIP, checksums, logs, and summary tables are preserved unchanged.

| Archive | Bytes | SHA256 |
| --- | ---: | --- |
| `evidence/RETURN_A.zip` | 2,861,359 | `aac54f826a19ebd81b5dfd376e792badcb79586161ce3c622fdd24e4b61ad88f` |
| `evidence/dsda_no_revisit_output_20261031_230829.zip` | 4,512,917 | `6ef180d61c02259fd36f9334221a201aa0b8dff39f79c0082e3fdb8e0dab4b9d` |

The original returned README is also preserved as `evidence/README.returned.md` and inside `RETURN_A.zip`.
The analysis tables and full interpretation are in [analysis/REPORT.md](analysis/REPORT.md).
The actual deployment scripts, package provenance, and original invocation are in [execution/README.md](execution/README.md).

## Reproduction

Run the independent data-only audit from the repository root:

```bash
python3 results/dsda_no_revisit_20261031/analysis/analyze.py
```

The audit reads historical inputs and source bytes from their pinned Git objects and performs no network fetch, optimizer execution, or NLP solve.
It reproduces the comparison tables, validation JSON, and detailed analysis report.
The publication file hashes are listed in `FILE_SHA256.json`.
For a new Dantzig experiment, use the unchanged `experiments/dsda_no_revisit/run_dantzig.sh` at the recorded execution SHA, the existing `DSDA_PYTHON`, a new output directory, and an allowed idle CPU as described in execution/README.md.
