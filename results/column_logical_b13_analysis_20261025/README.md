# Column logical-domain/B13 follow-up versus historical B16

All 50 new jobs completed without execution failure, with 648 charged callbacks and no original process NLP calculation.
Total target hits change from 14/50 to 15/50, which is a small aggregate difference rather than broad evidence of improved search.
The comparison is between the historical 81-coordinate/B16 cohort and the 64-coordinate/B13 cohort, with newly generated shared initial points.
The domain, budget and common initial designs changed together, so this comparison does not isolate any one factor.
Every method retains ten seeds in the denominator, and the historical D-SDA execution failure remains in all primary counts and timing summaries.

| Method | B16 hits / 10 | B13 hits / 10 | B16 median reconstructed completion (s) | B13 median reconstructed completion (s) | Change |
| --- | ---: | ---: | ---: | ---: | ---: |
| D-SDA | 5 | 5 | 37.909 | 35.434 | -6.5% |
| RBFOpt | 5 | 4 | 33.541 | 54.603 | +62.8% |
| BAM | 0 | 1 | 37.974 | 27.500 | -27.6% |
| FMQA-SA | 4 | 4 | 29.725 | 41.818 | +40.7% |
| Uniform | 0 | 1 | 26.287 | 21.689 | -17.5% |

## Earlier target observations

The new evaluation profiles reach their final success levels within thirteen callbacks, whereas several historical successes occur at callbacks fourteen through sixteen.
Reading the first thirteen callbacks of the archived B16 paths gives the descriptive counts below.
These prefixes are not new B13 runs and do not isolate the budget effect, because the actual algorithms used B16 settings, the old domain and the old initial designs.

| Method | Historical B16 paths by callback 13 | New B13 runs |
| --- | ---: | ---: |
| D-SDA | 3/10 | 5/10 |
| RBFOpt | 2/10 | 4/10 |
| BAM | 0/10 | 1/10 |
| FMQA-SA | 0/10 | 4/10 |
| Uniform | 0/10 | 1/10 |

## Initial-design effect

The new seed-6 design is [(11,3), (9,7), (13,4)], so every method observes the reference target on its third initial callback.
Neither historical initial designs nor any other new seed starts at the target.
The sole new successes for BAM and uniform sampling both occur at seed 6 and therefore do not establish an improvement in their adaptive search.
Targets first reached after initialization change from 14 runs to 10 runs; this is an observation-stage breakdown, not a replacement success denominator.
D-SDA seed 0 previously failed after three unaccepted initial points and now completes with an accepted initial observation, but it still misses the target.
D-SDA seed 6 terminates naturally after eleven callbacks, while the other 49 new jobs consume thirteen callbacks.

## Paired target outcomes

| Method | Both succeed | New only | Old only | Neither succeeds |
| --- | ---: | ---: | ---: | ---: |
| D-SDA | 3 | 2 | 2 | 3 |
| RBFOpt | 3 | 1 | 2 | 4 |
| BAM | 0 | 1 | 0 | 9 |
| FMQA-SA | 2 | 2 | 2 | 4 |
| Uniform | 0 | 1 | 0 | 9 |

All fifty paired seed records, including unchanged and worsened outcomes, are retained in final_comparison/paired_runs.csv.
Ten seeds per method provide descriptive evidence and do not establish a general algorithm ranking.

## Timing interpretation

Reconstructed completion equals recorded search wall time minus measured table-lookup time plus historical same-attempt point costs charged on every callback.
These times are not online optimizer-NLP measurements and do not measure new process solves.
The reported time median includes all ten runs for each method, including the one historical D-SDA failure.
Medians of individual timing components need not add to the median of reconstructed completion.
RBFOpt median measured search overhead decreases from 0.337729 s to 0.226033 s, while median charged point cost rises from 33.221 s to 54.369 s.
RBFOpt visits the unaccepted coordinate (15,8), whose historical cost is 40.191319 s, 0 times before and 6 times after, adding 241.148 s across its ten runs.
This is a deterministic accounting explanation using unchanged point costs, not a newly measured solver slowdown.
FMQA-SA likewise has lower median search overhead but a larger median charged point cost in the new coordinate paths.
The controller takes 151.773 s from creation to completion before final analysis and ZIP packaging, including 132.129 s in the sequential job phase.
The sum of measured new search wall times is 71.659 s; these execution durations are distinct from reconstructed per-run completion costs.
The auxiliary journal contains 10 Bonmin calls for RBFOpt surrogate models, totaling 0.873 s and already included in search overhead.
BAM internal surrogate work remains inside search overhead and is not independently counted as process NLP work.

## Domain, target and verification

The input retains 29 accepted and 35 unaccepted coordinates, with the seventeen excluded historical coordinates all outside the logical domain.
The accepted fraction of the candidate set rises from 29/81 to 29/64, while the nominal budget fraction changes from 16/81 to 13/64.
The reference remains (13,4), objective 19346.124801006445, and the final-best absolute tolerance remains 0.193461248010.
No objective, acceptance record, target, archived provider revision, manuscript, Overleaf file or representative figure is changed.
All 50 runtime, settings, CPU-2 affinity, single-thread and disabled-GPU records match the frozen plan, and worker intervals are sequential.
All 1,202 returned member hashes pass, the 638 reproduction files match the delivered v3 package, and ten data/report outputs reproduce byte-for-byte.
The local scientific figures are rendered from the verified profile coordinates and are separate follow-up artifacts.
No original process NLP or optimizer is invoked by this analysis.
The input archive, full callbacks, environments, paired comparison, coordinate cost attribution and replay sources are retained alongside this report.

## Artifacts and cleanup

The full paired table is [paired_runs.csv](final_comparison/paired_runs.csv), and the method-level accounting is [methods.csv](final_comparison/methods.csv).
The scientific figures are the [evaluation profile](replayed/profile_evaluations.png) and the [reconstructed completion profile](replayed/profile_reconstructed_completion_s.png).
The return ZIP is preserved under source/, and the unmodified extracted run is under returned/.
All 95 related tests pass against the returned package inputs, and all sixteen comparison outputs reproduce byte-for-byte in an independent replay.
The original 2,501 workspace files and 2,128 tracked baseline files retain their hashes.
The user clarified that cleanup concerns uncommitted Column v1/v2 files rather than Git commits.
The two obsolete local execution directories and their two temporary source directories were removed after verifying their contents.
Only their original ZIPs and checksum sidecars remain under provenance/retired_launch_packages/ for traceability.
The v3 package remains in its original location, and no Git history was rewritten or pushed.
Cleanup details and retained archive hashes are in cleanup_verification.json.

## Replay without optimization

The following commands use retained v3 analysis code and create fresh output directories without invoking any optimizer or process NLP solver.
Choose new output names if the example replay directories already exist.

```bash
cd /Users/albertlee0125/Repos/RBFopt_Test
COLUMN_PYTHON=.venv-trace-bam5/bin/python
COLUMN_PACKAGE=results/runners/column_logical_b13_20261025_v3/column_logical_b13_dantzig_20261025_v3
COLUMN_ANALYSIS=results/column_logical_b13_analysis_20261025
"$COLUMN_PYTHON" "$COLUMN_PACKAGE/analyze.py" --run-dir "$COLUMN_ANALYSIS/returned" --output "$COLUMN_ANALYSIS/replayed_again"
"$COLUMN_PYTHON" "$COLUMN_ANALYSIS/compare.py" --run "$COLUMN_ANALYSIS/returned" --package "$COLUMN_PACKAGE" --replay "$COLUMN_ANALYSIS/replayed_again" --output "$COLUMN_ANALYSIS/comparison_again"
```
