CSTR30 initialization follow-up: independent return audit, 2026-10-25

Applying the archived CSTR5–25 mass-balance and zero-recycle initializer to CSTR30 increased accepted configurations from 458 to 464, but target attainment decreased from 16/50 to 15/50.
The accepted minimum and fixed reference remained exactly 2.7695697198995095 at coordinate `[30,30]`.
These data support improved evaluator acceptance on this first-attempt table, without an improvement in the best objective or aggregate search success for the tested seeds.
This is a separate follow-up result and does not replace the manuscript's representative results.

The byte-preserved [returned archive](../archives/cstr30_init_20261025_060540_98uz54ol.zip) has SHA256 `0cfec308ee68512f9e46bd2dc78f9839dad987fd5843cc3e829d5d71ee9ccdfb` and contains the exact executed source, baseline inputs, first-attempt records, solver artifacts and search trajectories.
The outer hash was computed locally because no server outer-checksum sidecar was supplied.
All 10,663 internally checksummed files, all 3,211 reproduction inventory entries and all 7,450 manifest output hashes were verified.
The returned reproduction files also match the originally delivered package byte for byte, as recorded in [package_identity.json](package_identity.json).

The comparison baseline is the manuscript's BAM v2, FMQA-SA and uniform runs combined with the requested 2026-10-22 finite-1e6 D-SDA and genetic RBFOpt runs.
Its baseline revision is `44ed72156a03017d7021f3fac6744bae4366dbfb`, and the executed follow-up source revision is `750169cdaa42dc46577b7c267837da54e7b99c35`.
The original constructor-default CSTR30 NLP attempts are used, including their seven rejected configurations, without substituting subsequent retry results.
The earlier manuscript aggregate of 109/300 predates the finite-penalty overlay and is not the starting count for this initialization comparison.
The selected finite-penalty baseline recomputes to 98/300 from its input records.
Infinite-penalty runs and RBFOpt's alternative `solver` candidate-search configuration are not used.

The initializer's only source change extends `SUPPORTED_SIZES` from `(5,10,15,20,25)` to `(5,10,15,20,25,30)`.
The exact patch is retained inside the archive at `reproduction/provenance/initialization.patch`.
The procedure computes values using the N=30 model indices, without copying a smaller model's value array.
Each coordinate starts in a fresh worker with a new model, following constructor defaults, configuration fixing, original constraint snapshot, original preprocessing, and then mass-balance and zero-recycle initialization.
No previous configuration's solution is used as the next initial point.
The archived sources establish the different initialization paths but do not document why CSTR30 was previously excluded.

All 900 external coordinates are present once, with 465 logically allowed configurations and 435 structural rejections.
The original preparation path rejects every structural configuration before the NLP interface is called.
An independent solver-free reconstruction verified all 900 preparation outcomes, all 465 initialized models, unchanged objective/constraint/bound fingerprints, and all 464 accepted saved solution vectors.
The largest recomputed constraint violation among accepted returned vectors is `1.700837470863803e-9`, and the largest bound violation is zero.
The complete per-coordinate checks are in [model_checks.json](model_checks.json), and original logs and vectors remain in the returned archive.

| Evaluation outcome | Original | New |
| --- | ---: | ---: |
| Accepted | 458 | 464 |
| Logically allowed but unaccepted | 7 | 1 |
| Structurally rejected | 435 | 435 |
| Total | 900 | 900 |

There are 457 configurations accepted in both tables, seven newly accepted configurations, one newly unaccepted configuration, and 435 rejected in both.
Acceptance among logically allowed configurations changes from 458/465 (98.49%) to 464/465 (99.78%).
Among the 457 common accepted configurations, the maximum absolute objective change is `6.19647169131099e-8`, with no change exceeding `1e-5`.
The reference configuration's objective changes by exactly zero, while its recorded maximum primal violation changes from `2.7755575615628914e-15` to `1.5543122344752192e-15`.
Separate original constraint and bound violations were not recorded, so only the original combined maximum is compared rather than inventing missing components.

| Coordinate | Original outcome | New accepted objective |
| --- | --- | ---: |
| `[5,1]` | Infeasible termination | 3.1301981330254702 |
| `[5,3]` | Infeasible termination | 3.1301981331092597 |
| `[6,2]` | Infeasible termination | 3.20097659466549 |
| `[6,4]` | Infeasible termination | 3.20097659467698 |
| `[23,2]` | Feasible termination with solver warning | 3.636879987848124 |
| `[26,2]` | Feasible termination with solver warning | 3.6526901767238242 |
| `[29,3]` | Feasible termination with solver warning | 3.6651355318680525 |

The first four original rejections had appreciable primal violations, whereas the last three had small residuals but GAMS MODELSTAT 7 and SOLVESTAT 4 and did not satisfy the original acceptance rule.
All seven new attempts satisfy the unchanged acceptance rule.
The newly unaccepted configuration `[27,10]` previously had objective 3.6571553283661897.
Its new attempt fails the GAMS availability/interface check with the message `'gams' command failed to solve a simple model - GAMS shell solver functionality is not available.`
The retained artifact ZIP contains only `ipopt.opt`, with no CSTR GAMS model, results files or IPOPT solver log.
Its saved final state is labeled `last_model_state_no_loaded_candidate` and must not be treated as a returned feasible solution despite its small initialization residuals.
The error consumes 60.0744 seconds inside the interface attempt and 61.1809 seconds in the recorded evaluation.
No retry replaces this first failure, and this coordinate is visited zero times in the 50 new searches.
Thus, it cannot directly explain the observed search-success changes.

The server's `actual_coordinate_nlp_calls=465` field counts entry to the GAMS solve interface.
The audit distinguishes **465 interface attempts from 464 confirmed CSTR30 IPOPT invocations**, plus one separate quadratic IPOPT preflight.
No CSTR NLP is invoked during the 50 lookup searches or during this independent analysis.
RBFOpt's archived auxiliary surrogate solvers are separate from process-model NLP evaluation.
The raw server summary is preserved unchanged, and the corrected interpretation is recorded in [audit_summary.json](audit_summary.json) and [audit_manifest.json](audit_manifest.json).

All 50 planned searches completed with budget 43 and seeds 0–9, retaining ten attempts per method.
The first three coordinates and their order match the original run for every method and seed.
The recorded optimizer settings, seeds, runtime identities, stopping rules and failure-response policies match the selected baseline.
D-SDA and RBFOpt retain the unaccepted response of `1e6`, and RBFOpt retains genetic global candidate search.
The primary target test remains `abs(final_best - reference) <= 1e-5 * max(1, abs(reference))`, with reference `2.7695697198995095`.
Any-hit attainment is retained as an auxiliary measure and agrees with the primary result in all 50 new runs.
No new best value lies below the reference far enough to become an absolute-target miss, and the reference was not updated.

| Method | Original hits | New hits | Both hit | New only | Original only | Neither |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| D-SDA | 3/10 (30%) | 2/10 (20%) | 2 | 0 | 1 | 7 |
| RBFOpt | 9/10 (90%) | 9/10 (90%) | 8 | 1 | 1 | 0 |
| BAM | 2/10 (20%) | 2/10 (20%) | 2 | 0 | 0 | 8 |
| FMQA-SA | 1/10 (10%) | 1/10 (10%) | 1 | 0 | 0 | 9 |
| Uniform sampling | 1/10 (10%) | 1/10 (10%) | 1 | 0 | 0 | 9 |
| Total | 16/50 (32%) | 15/50 (30%) | 14 | 1 | 2 | 33 |

D-SDA seed 6 changes from a target hit to best objective 3.1301981330254702 at `[5,1]`, with 43 original callbacks and 30 new callbacks.
Its first coordinate divergence occurs at callback 12, from original `[13,9]` to new `[13,5]`, before any acceptance changes in the shared prefix.
Small objective changes occur in that prefix, so the first divergence cannot be attributed specifically to the newly accepted `[5,1]` configuration.
RBFOpt seed 4 changes from a hit to best objective 3.062014576556465 at `[5,5]`, with the first coordinate divergence at callback 15 after newly accepted `[6,4]` at callback 14.
RBFOpt seed 7 changes from a miss with best objective 2.791251697823334 to a hit, with the first coordinate divergence at callback 17 after newly accepted `[5,1]` at callback 16.
These are observed trajectory differences rather than a controlled causal decomposition of all numerical and optimizer effects.
All 50 paired traces are summarized in [paired_search_audit.csv](paired_search_audit.csv), and all 430 new RBFOpt callback coordinates are retained in [returned/rbfopt_coordinates.csv](returned/rbfopt_coordinates.csv).

The six-size aggregate retains all 250 original CSTR5–25 runs and replaces only the 50 CSTR30 runs.
Both original and new totals below are recomputed from those records.

| Method | Original six-size hits | New six-size hits |
| --- | ---: | ---: |
| D-SDA | 15/60 (25%) | 14/60 (23.33%) |
| RBFOpt | 45/60 (75%) | 45/60 (75%) |
| BAM | 18/60 (30%) | 18/60 (30%) |
| FMQA-SA | 9/60 (15%) | 9/60 (15%) |
| Uniform sampling | 11/60 (18.33%) | 11/60 (18.33%) |
| Total | 98/300 (32.67%) | 97/300 (32.33%) |

The actual Dantzig environment matches GAMS 52.2.0, IPOPT 3.14.19, MUMPS 5.8.1, the historical GAMS executable hash, Python 3.11.16, Pyomo 6.10.0 and the recorded dependency versions.
The GAMS solve limit is 60 seconds, the iteration limit is 3000, and the solver is restricted to one thread with CPU affinity recorded as CPU 10.
IPOPT retains `tol 1e-8`, `bound_relax_factor 0`, `max_iter 3000`, `warm_start_init_point no` and `linear_solver mumps`.
GAMS `warmstart=True` transmits the current initialized primal values and does not reuse a previous configuration's solution.
The maximum accepted primal violation remains `1e-5`, and the worker watchdog remains 180 seconds.
The kernel changed from `5.15.0-323.211.3.4.el9uek` to `5.15.0-325.220.5.el9uek`; both platforms are recorded in the audit manifest.
No alternative local optimizer was substituted for the experiment.

| Recorded timing quantity | Original seconds | New seconds |
| --- | ---: | ---: |
| All 900 evaluations, summed | 922.8565 | 1719.0001 |
| Logically allowed evaluations, summed | 827.3957 | 1317.6050 |
| Structural rejections, summed | 95.4608 | 401.3952 |
| Median evaluation | 1.0742 | 1.8132 |
| Recorded solve-interface wall time, summed | 656.3808 | 803.2726 |
| 50 search completion estimates, summed | 2311.1567 | 4741.2813 |

The new measured lookup-search time is 328.0565 seconds in total.
Completion estimates use the historical formula: measured search time minus lookup time plus new evaluation-table time for every charged callback, including repeats.
These estimates are not actual NLP reruns performed during search.
The new timing includes initialization and durable artifact retention, while the original CSTR30 runner used different process and artifact-recording conventions.
Structural rejection time also increases substantially without any NLP calls, and the new interface sum includes the 60-second GAMS availability failure.
Consequently, these wall-time differences do not establish a pure IPOPT slowdown or a causal CPU-affinity effect.
Per-method completion estimates remain available in [methods.csv](methods.csv).

The independent audit script is [scripts/analyze_cstr30_initialization_return.py](../../scripts/analyze_cstr30_initialization_return.py).
It verifies the archive before executing its frozen report generator, checks the selected baseline job bytes against six historical archives, rebuilds models without optimization, and joins each callback's objective, acceptance and measured cost to the same first-attempt record hash.
The report replay reproduces all selected tables byte for byte, with one floating-point summation difference of `1.1368683772161603e-13` seconds in the JSON summary under local Python 3.13.12 versus server Python 3.11.16.
That replay difference is recorded explicitly and does not change the target or acceptance tolerance.
Eight new audit tests and seven archived protocol tests passed, including mixed-attempt rejection, missing-vector handling, fixed absolute targets, repeat-cost accounting, shared starts and preservation of other-size records.
Ruff passed for the two added Python files.
The solver-free model audit uses Pyomo 6.10.0 and the pinned `external/dsda-gdp` source revision `3e469dbeea8931670b8cd6752014ab7a767d3af5`.
The original server execution commands and exact experiment source are retained inside `reproduction/README.txt` and `reproduction/run_dantzig.sh` in the archive.

To reproduce this audit from the repository root in a Pyomo 6.10.0 environment with the pinned model submodule available:

```bash
python scripts/analyze_cstr30_initialization_return.py \
  --output /tmp/cstr30-return-recheck --sources external
python -m pytest tests/test_cstr30_initialization_return.py -q
python -m ruff check scripts/analyze_cstr30_initialization_return.py \
  tests/test_cstr30_initialization_return.py
```

The `--skip-models` option reproduces record and accounting checks only and explicitly marks model validation incomplete.
The saved [coordinates.csv](coordinates.csv) and [acceptance_changes.csv](acceptance_changes.csv) expose coordinate-level outcomes, objective differences, residuals and measured times.
The `returned/` directory contains byte-preserved copies of the principal returned tables, while the archive retains every raw log, input and original manifest.
[preservation.json](preservation.json) verifies all 1,991 pre-existing tracked files in the target worktree, including historical raw data, manuscript sources and figures, against hashes captured before this audit.
The main working directory and its unfinished user changes were left untouched.
[artifact_checksums.json](artifact_checksums.json) seals the added analysis artifacts, audit source, tests and original return ZIP, excluding the checksum index itself.
Whether to adopt this initialization result in the manuscript remains a subsequent review decision.
