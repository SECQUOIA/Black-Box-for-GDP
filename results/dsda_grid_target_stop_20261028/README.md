# Grid D-SDA target stopping aligned with common success

This Grid-only follow-up changes the target stopping predicate of the [second absolute-improvement 1e-5 experiment](../dsda_abs1e5_rerun_20261028/README.md) to the unchanged common success rule.
All 1,050 Grid runs completed with no failed or missing pairs, and all 374 successful seeds remain exactly the same.
Callbacks decrease from 38,516 to 37,253, a reduction of 1,263 or approximately 3.28 percent.
All 36 runs with fewer callbacks belong to Csendes, while the other 20 functions retain their callback sequences and final objective values.
The original Process runs, other methods, manuscript, Overleaf material, and existing representative figures and tables remain unchanged.
These results are preserved separately and are not automatically adopted as manuscript representative results.

## Budget-level results

Each budget contains 21 functions and seeds 0 through 9, giving exactly 210 pairs.
The direct baseline already uses strict absolute improvement `old_value - new_value > 1e-5`, so this comparison isolates the target stopping change.

| Budget | Previous hits | New hits | Previous callbacks | New callbacks | Callback change | Runs ending earlier | Failures / missing |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 13/210 | 13/210 | 2,094 | 2,094 | 0 | 0 | 0 / 0 |
| 30 | 74/210 | 74/210 | 5,970 | 5,925 | -45 | 6 | 0 / 0 |
| 50 | 88/210 | 88/210 | 8,892 | 8,667 | -225 | 10 | 0 / 0 |
| 70 | 98/210 | 98/210 | 10,424 | 10,006 | -418 | 10 | 0 / 0 |
| 100 | 101/210 | 101/210 | 11,136 | 10,561 | -575 | 10 | 0 / 0 |
| Descriptive total | 374/1,050 | 374/1,050 | 38,516 | 37,253 | -1,263 | 36 | 0 / 0 |

The [paired table](paired_runs.csv) includes all 1,050 pairs rather than excluding failures or selecting favorable seeds.
It preserves both success categories, observed minima, callback counts, first-hit callbacks, actual termination callbacks, termination reasons, and measured search times.
The [budget summary](grid_budget_summary.csv), [function summary](function_summary.csv), and [earlier-termination index](earlier_termination_runs.csv) provide complementary views of the same complete cohort.
The expected baseline hit counts supplied with the task were cross-checks only and are not hardcoded into analysis or success classification.

## What changed in the search

Csendes callbacks decrease from 2,443 to 1,180 across its 50 runs, accounting for the entire reduction.
For Csendes B100 seed 3, the first successful observation remains callback 21 while actual termination moves from callback 100 to callback 30.
The final observed minimum for this example remains `9.904175326554672e-9`.
All 36 shortened runs stop after their first successful callback rather than immediately at that callback.
The new callback sequences exactly equal the old sequences or a prefix ending at a successful, completed-descent target checkpoint.
The corresponding descent paths and recorded algorithm states match exactly before stopping after excluding measured durations.
No unexplained callback or movement-path changes were found.

Final observed minima are exactly equal in 1,041 pairs and are less improved in nine pairs because later restarts are skipped.
All nine remain successful, and the maximum objective increase is `3.0218232929537542e-6`.
There are no newly successful or newly unsuccessful pairs, and every first-hit callback index is unchanged.
Consequently, comparisons based on target-hit counts against the unchanged other methods retain their prior interpretation.
Callback reductions are an evaluation-count result, and wall-time differences between separate executions are not used as evidence of a speedup.
Historical configuration evaluation-cost estimates are not reused or combined with the new wall times.

The [termination summary](termination_summary.csv) distinguishes reason labels from actual callback reductions.
In particular, 267 `target_value` labels become `target_common_success`, which by itself is not evidence of fewer evaluations.

## Predicate, incumbent, and checkpoint

The new optional `target_stop` predicate receives the existing `TrackedObjective.incumbent` and the unchanged per-job target.
Execution passes the retained `adopted_analysis.hit` function, which evaluates `abs(best_observed_objective - target) <= 1e-5 * max(1, abs(target))` on unrounded values.
The tracker includes every accepted objective response, including evaluations that were not accepted as moves.
This observed minimum is separate from threshold-filtered `best_seen`, the selected movement point, the final location, and multistart `best_run` selection.
It affects only the target predicate and corresponding final target flag, without changing neighbor choice, start ranking, or movement acceptance.

The checkpoint remains after a descent returns, after the pre-existing budget-exhaustion branch, and before the next ranked start.
No callback-level immediate termination is introduced.
If a descent has no improving neighbor but its observed minimum does not satisfy the target rule, the next ranked start is tried when budget remains.
A descent stopped by the budget exits before this target checkpoint, preserving the existing precedence.
The three initial evaluations retain their order and budget charge, selected start values remain cached, and repeated evaluations remain charged.
The neighbor and direction acceptance test remains strictly `old_value - new_value > 1e-5`, while tie handling and other internal numerical settings remain `tol=1e-12`.
Calls omitting `target_stop` preserve the old target predicate and comparison arithmetic.
The [source diff](../../experiments/dsda_grid_target_stop/source_change.diff) identifies the complete change against the algorithm actually used by the direct baseline.

## Provenance and execution scope

The [original return ZIP](../archives/dsda_grid_target_stop_20261028_032943_2346732.zip) is preserved byte-for-byte with SHA256 `3611ba036df02ef8b155e32be7557c4bf7b88dfa1a5aff6e91c6d82fe7fb135a`.
The direct baseline ZIP remains unchanged with SHA256 `e58982f7179b73c65d83134dcbe0b25854002685812b2511b24523e861c9929e`.
The starting PR revision is `fb4b630983b41111289f1216c5902c30d7932a84` on `review/cstr15-dantzig-results`, and work was prepared in a separate detached worktree.
The local main checkout remained `2d1e2e49158d924f1fe589a55f7d7f210bf5f28b`.
Dantzig's repository checkout was `7f110f9122298a4f492d8ad464e782b2435b167b`, while execution used separately sealed source and input files derived from the verified baseline return.
The 15 published execution source files match the files actually executed on Dantzig byte-for-byte.
The extracted baseline input, source, and raw result evidence match 2,124 members of the independently hashed direct baseline archive byte-for-byte.
Targets, starts, domains, seeds, budgets, and watchdog policy also match the original job specifications.

The server completed 1,050 cohort jobs and three separately recorded Grid smoke jobs, with zero Process jobs, other-method jobs, NLP calls, or other solver calls.
Thirteen Grid-only semantic and negative-control tests passed on Dantzig before the full cohort.
The unchanged solver/model import and child-process guards were active in the lookup workers, and no blocked attempts were recorded.
Incomplete or duplicate cohorts and missing lookup responses are rejected rather than repaired with a solver call or seed substitution.

Execution ran from 23:29:46 to 23:35:14 on October 27, 2026 in America/Indianapolis.
The original UTC timestamps are `2026-10-28T03:29:46.285160+00:00` and `2026-10-28T03:35:14.077728+00:00`, and the artifact names retain that UTC date.
The environment was Python 3.11.16, NumPy 2.4.6, SciPy 1.17.1, and pandas 2.3.3.
The selector observed CPU 46 at `[0, 0, 0]` percent utilization and its SMT sibling 94 at `[1, 1, 0]` percent across three one-second intervals.
Execution was pinned to logical CPU 46, all returned workers confirm that affinity, numerical-library thread limits remained one, and Grid retained its original absence of a watchdog.
The allocation is explicitly an idle-core observation rather than exclusive reservation.
Repository state, existing-process metadata, CPU measurements, commands, source hashes, input hashes, and raw outputs remain in the ZIP and [execution manifest](returned/execution_manifest.json).

## Verification and reproduction

The [independent audit](audit.json) checks 7,413 output hashes, 2,141 input/source hashes, all 1,050 pairings and callback prefixes, all descent prefixes, initial order, budgets, first-hit and termination indices, common success classification, CPU records, and summary tables.
It additionally anchors the copied baseline evidence to the original baseline ZIP and the published execution source to the returned sealed snapshot.
The data-only audit reconstructs every published derived summary without running a search, solver, subprocess, or archived source code.

Run the full publication audit from the repository root with Python 3.10 or later and the standard library.

```bash
python results/dsda_grid_target_stop_20261028/verify_publication.py
```

The raw return can also be verified independently of the extracted publication tables.

```bash
python experiments/dsda_grid_target_stop/verify.py \
  --archive results/archives/dsda_grid_target_stop_20261028_032943_2346732.zip
```

To reproduce the derived publication outputs into a new directory without overwriting retained evidence, use the following command with an unused output path.

```bash
python results/dsda_grid_target_stop_20261028/verify_publication.py \
  --write-new /tmp/dsda_grid_target_stop_publication_replay
```

The [permanent Grid-only workflow](../../experiments/dsda_grid_target_stop/README.md) documents preparation, tests, smoke, full execution, and explicit resume.
The exact one-file installer used for this run is retained in `installer/`.
On the already-installed Dantzig repository, another explicitly requested experiment can be launched with the following command.

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
.venv-dantzig/bin/python experiments/dsda_grid_target_stop/launch.py
```

Completed runs are reused only after validating their source seal, output hashes, process completion, and callback and descent prefixes.
Incomplete attempts are preserved separately, and ambiguous completed records are not automatically executed twice.
Publication of this completed return does not start another full experiment or change any prior execution archive.

The redundant local transfer packages and validation directories were archived in `~/Downloads/dsda_grid_target_stop_local_preparation_20261028.zip` before cleanup.
The [preservation receipt](local_preparation_preservation.json) records their file count, original directory names, and verified backup SHA256.
