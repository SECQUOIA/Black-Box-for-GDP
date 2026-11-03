# D-SDA 절대 개선 허용오차 변경 실험 — Dantzig rerun

This independent rerun preserves all 1,190 results produced with the strict absolute improvement condition `old_value - new_value > 1e-5`.
All 1,190 runs completed with zero failures, missing pairs, or additional NLP calls.
Compared with the [first 1e-5 experiment](../dsda_abs1e5_20261027/README.md), every final objective, success category, callback response, callback count, first-hit index, termination, movement path, and recorded algorithm state is identical after excluding measured durations and CPU affinity.
The comparison covers 40,957 callback responses, not only aggregate summaries.
This reproducibility result does not claim statistical equivalence with the original D-SDA or reproduce the complete original LD-SDA implementation.
The original experiment, adopted baseline, manuscript, Overleaf material, existing figures, and representative results remain unchanged.

## Comparison with the adopted D-SDA baseline

The baseline remains `results/column_publication_20261025/tables/run_records.csv` with SHA256 `c4d3cd0c2e46cee976a2684a0b83bf0bb543a75790398aaed293a2b6b7267611`.
The original and new runs pair exactly by `(scope, case, budget, seed)`.

| Scope | Runs | Original hits | Rerun hits | Original only | Rerun only | Original callbacks | Rerun callbacks |
|---|---:|---:|---:|---:|---:|---:|---:|
| Grid | 1,050 | 382 | 374 | 10 | 2 | 38,033 | 38,516 |
| Process | 140 | 74 | 74 | 0 | 0 | 2,467 | 2,441 |
| CSTR, included in Process | 60 | 14 | 14 | 0 | 0 | 1,128 | 1,102 |

Grid target hits change by -8, approximately -0.76 percentage points, while Process retains exactly the same successful seeds in all 14 conditions.
Grid callback paths differ from the original baseline in 91 runs, callback counts differ in 67, and endpoints differ in 69.
Process paths, counts, and endpoints differ in six CSTR runs, all of which miss the target under both tolerance settings.
The larger tolerance can reject a small improving step leading to a better region, and some individual Grid objective losses remain large despite the small aggregate hit-rate change.
Grid callbacks increase by 483, while Process callbacks decrease by 26.
The target-hit ordering against the unchanged RBFOpt, BAM, FMQA-SA, and uniform results is unchanged in every budget or condition.
The [paired baseline comparison](returned/paired_comparison.csv), [Grid budget summary](returned/grid_budget_summary.csv), and [Process condition summary](returned/process_condition_summary.csv) retain the complete details.
The [rerun comparison](rerun_comparison.csv) separately compares this rerun with the first 1e-5 experiment for every seed.

## CPU observation and execution provenance

Immediately before launch, the selector measured all allowed logical CPUs over three one-second intervals and selected logical CPU 10 with SMT sibling 58.
CPU 10 had measured utilization `[0, 0, 0]` percent, and CPU 58 had `[0, 0.9900990099009901, 0]` percent.
Both members of the physical core satisfied the unchanged 5-percent selection threshold in every interval.
The launcher pinned execution to CPU 10 and limited numerical-library threads to one, and all 1,190 returned workers report affinity `[10]`.
This is an observed idle physical core followed by affinity pinning, and the retained record explicitly states `exclusive_reservation=false`.
The observation does not establish exclusive allocation or absence of later competing work, and no speedup claim is made from the measured wall times.
The previous execution provenance is retained without rewriting it.

Execution started at `2026-10-28T02:07:54.260587+00:00` and finished at `2026-10-28T02:16:17.814103+00:00` on Dantzig.
The directory date is the UTC execution date, corresponding to the evening of October 27 in America/Indiana/Indianapolis.
The server checkout was `7f110f9122298a4f492d8ad464e782b2435b167b`, and the frozen scientific source base remained `5e94df72b472a5039c35518b685de6080cf8d67f` plus individually hashed experiment additions.
This publication starts from PR #52 revision `060737ee9b02aabde082ec8a3bb7204d3bd95bfa` in a separate worktree.
The local main checkout remains `2d1e2e49158d924f1fe589a55f7d7f210bf5f28b`.
The server environment was Python 3.11.16, NumPy 2.4.6, SciPy 1.17.1, and pandas 2.3.3.
Exact commands, source hashes, input hashes, environment, CPU observations, and output hashes are retained in the [execution manifest](returned/execution_manifest.json) and original ZIP.

## Preserved protocol and source

The frozen scientific inputs, lookup tables, adopted baseline, algorithm sources, and historical replay records match the first experiment byte-for-byte across 50 files.
Only D-SDA is rerun, using saved configuration objectives and statuses with no solver or model invocation.
Missing lookup responses cause failure rather than triggering an NLP fallback.
The latest CSTR30 initialization and Column domain `[8..15] × [1..8]` with budget 13 remain in the retained inputs.
Initial configurations and their order, seeds, domains, budgets, start selection, cached initial responses, repeated-evaluation charging, finite Process rejection penalty `1e6`, and watchdog settings remain unchanged.
Neighbor acceptance, direction search, and the existing connected `best_seen` and multistart `best_run` updates use the strict absolute improvement threshold.
The observed incumbent used for reporting remains the minimum over accepted callbacks without improvement-threshold filtering.
No relative improvement criterion is added, and calls omitting `improvement_abs_tol` preserve the original comparison arithmetic.
Tie handling and Grid target termination retain `tol=1e-12`, and the common outcome rule remains `abs(best - target) <= 1e-5 * max(1, abs(target))` for every method.

The [return archive](../archives/dsda_abs1e5_rerun_20261028_020753_2004611.zip) is preserved byte-for-byte with SHA256 `e58982f7179b73c65d83134dcbe0b25854002685812b2511b24523e861c9929e`.
Its `reproduction/` directory contains the exact sealed execution package, source, tests, and preparation records, and its `runs/` directory contains every raw callback and search result.
The `returned/` directory contains byte-identical top-level output files for convenient review.
The `workflow/` directory preserves the exact installer and readable workflow sources used to install the permanent Dantzig workflow.
The embedded installer payload matches the archived workflow sources, and the reference data remain in the already-published first return archive.
These retained workflow files are historical execution evidence and are not executed by the independent verifier.

## Verification and reproduction

Run the data-only audit and its negative-control tests from the repository root with Python 3.10 or later and the standard library.

```bash
python results/dsda_abs1e5_rerun_20261028/verify.py
python results/dsda_abs1e5_rerun_20261028/test_verify.py
```

The verifier checks all 6,378 output hashes and 263 sealed input/source hashes, exact baseline pairing, initial order, budgets, objective responses, categories, first-hit callbacks, finite penalties, watchdog records, summary tables, and unchanged comparator ordering.
It also compares every raw result and callback against the first experiment while excluding only specified measured durations and CPU affinity.
The negative controls confirm that changed nested algorithm values, movement paths, callback responses, and missing objective-timing entries are rejected.
The [audit report](audit.json) and repeat comparison CSV are reproducible without an optimizer, solver, subprocess, or execution of archived experiment code.
The server preparation records contain 32 passing tests, and the 11 protocol tests passed again immediately before the full run.

To write new audit outputs without overwriting retained evidence, supply unused output paths.

```bash
python results/dsda_abs1e5_rerun_20261028/verify.py \
  --output /tmp/dsda_rerun_audit_new.json \
  --paired-output /tmp/dsda_rerun_pairs_new.csv
```

The permanent workflow is already installed in the Dantzig repository, and the following command prepares a fresh sealed input, selects an observed idle physical core, and launches a new independent run when another execution is explicitly wanted.

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
.venv-dantzig/bin/python experiments/dsda_abs1e5/launch.py
```

The launcher creates unique result and log paths, retains the selected CPU and SMT observations, and holds a lock against duplicate runs of this workflow.
It does not reserve the CPU against other users' work.
The preserved `workflow/dsda_repository_run.py` is the original one-file installer for that exact server path and requires the retained `results/dsda_abs1e5_input_20261027_2320_sharedcpu_v2` input package.
The recorded server command and all dependencies are also retained inside the return archive for inspection.
No additional full experiment is run during this publication.

## Local preparation cleanup

The two untracked preparation directories contained 1,808 files, including duplicate installation validations and transfer packages.
They were backed up in full to `~/Downloads/dsda_abs1e5_local_preparation_20261028.zip`, with every member verified against its original SHA256 and byte count before removing the redundant working copies.
The [preservation receipt](local_preparation_preservation.json) records the backup hash, original directory names, file count, and published workflow location.
The reusable execution evidence is retained here and in the original return ZIPs, while the redundant local preparation backup is not added to Git.
No unrelated user changes are removed.
