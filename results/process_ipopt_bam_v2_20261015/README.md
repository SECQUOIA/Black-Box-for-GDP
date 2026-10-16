# Final IPOPT Process comparison

Use this directory for the final October 15 Process comparison: **560 runs,
291 target hits, 268 target misses and one execution failure**. The failed run
is Column B16, DSDA, seed 0, with three unaccepted initial points. All ten
seeds remain in each denominator. Targets are accepted IPOPT-table minima,
not certificates of the original GDP's global optimum.

All **140 BAM slots** come from the corrected native-budget runs, with **3,430
callbacks**. The remaining 420 runs retain the original CSTR/non-CSTR returns.
There is no best-of-old/new selection. The old BAM records retain their
19 CSTR and eight non-CSTR budget-protocol failures in their historical audits.
The new BAM results have 47 hits, 93 misses and no execution failures.

## Results and evidence

| Result or input | Files and original evidence | Code and configuration |
|---|---|---|
| Final outcomes, completion costs and TTS99 | [run_results.csv](tables/run_results.csv), [group_summary.csv](tables/group_summary.csv), [callbacks.csv](tables/callbacks.csv), [timing_audit.json](timing_audit.json) | [analysis_core.py](../../scripts/process_ipopt/analysis_core.py), [refresh.py](../../scripts/process_ipopt/refresh.py); 56 groups, ten seeds each |
| Four principal figures and two diagnostics | [figures/](figures/), [figure_manifest.json](figure_manifest.json) | [build_figures.py](../../scripts/process_ipopt/build_figures.py); figures use the same final run selection |
| Original CSTR return: 180 selected non-BAM runs; old BAM retained | [compact records](../ipopt_dfo_cstr_20261015_174637_r1dzn5tk/), [original ZIP](../archives/ipopt_dfo_cstr_20261015_174637_r1dzn5tk.zip) | [submitted runner](../runners/ipopt_dfo_cstr_20261015.zip); `reproduction/plan.json`, `build_provenance.json`, `inputs/` and source files inside the ZIP |
| Original non-CSTR return: 240 selected non-BAM runs; old BAM retained | [compact records](../ipopt_dfo_non_cstr_20261015_172428_o671edu_/), [original ZIP](../archives/ipopt_dfo_non_cstr_20261015_172428_o671edu_.zip) | [submitted runner](../runners/ipopt_dfo_non_cstr_20261015.zip); raw categories and separately audited budget violations are both retained |
| Corrected CSTR BAM: all 60 slots | [compact records](../bam_budget_v2/ipopt_dfo_cstr_20261015_223017_ncd_12gx/), [original ZIP](../archives/ipopt_dfo_cstr_20261015_223017_ncd_12gx.zip) | [executed BAM package](../runners/bam_cstr_budget_v2.zip); [pinned importer](../../scripts/import_bam_budget_v2.py) |
| Corrected non-CSTR BAM: all 80 slots | [compact records](../bam_budget_v2/ipopt_dfo_non_cstr_20261015_223138_r3ifrgaq/), [original ZIP](../archives/ipopt_dfo_non_cstr_20261015_223138_r3ifrgaq.zip) | [executed BAM package](../runners/bam_non_cstr_budget_v2.zip); same importer |
| Size-specific CSTR5/10/15 and CSTR20/25 IPOPT tables | [source index](../cstr_box_ipopt/INDEX.txt), [5/10/15 ZIP](../cstr_box_ipopt/dantzig_cstr_box_ipopt_20261015_155116_eqpg0g41.zip), [20/25 ZIP](../archives/dantzig_cstr_box_ipopt_20261015_162507_3bnp0xm3.zip) | `mass_balance_zero_recycle`; submitted packages and source snapshots retain the exact setup |
| Original CSTR30, Column, Dynamic and Small Batch IPOPT inputs | Frozen `inputs/<case>/` in the DFO returns; [original GAMS return](../archives/dantzig_gdp_gams_20260922_050038_p4q8hy54.zip) | N30 constructor defaults; Column 17 trays and saved initialization; Dynamic nine stages, constructor defaults, nfe30/ncp3 LAGRANGE-RADAU; Small Batch saved initialization |
| Column/Dynamic missing structural costs | [full-box source index](../column_dynamic_box_ipopt/INDEX.txt), [153-point original ZIP](../archives/dantzig_column_dynamic_ipopt_20261015_205822_gG8bXK.zip) | [executed package](../runners/column_dynamic_box_ipopt_20261015.zip); only previously unmeasured logical exclusions supply costs |
| CSTR30 missing structural costs | [435-point supplement](../cstr30_structural_rejections/INDEX.txt), [original ZIP](../archives/dantzig_cstr30_structural_20261015_214202_pgve882p.zip) | [executed package](../runners/cstr30_structural_rejections_20261015.zip); no solver calls, original 465 NLP rows unchanged |

Original per-job `callbacks.jsonl`, `run.log`, FMQA `proposals.jsonl` where
recorded, settings, results and runtime records are under `jobs/<job_id>/` in
the four DFO return ZIPs. Their `reproduction/` trees contain the exact submitted
inputs and execution sources. These raw records need not be duplicated as
thousands of ordinary files. Missing or unrecorded historical callbacks are
not fabricated. Compact `job_metadata.json` files expose configurations without
unpacking the logs.

The [integration manifest](integration/manifest.json) supplies archive and
runner hashes, member inventories, source revisions and paths. The retained
[integration verification](integration/verification.json) records the checks
at the merge revision and the exact verifier hash used. The original
[source manifest](source_manifest.json), [replacement verification](replacement_verification.json)
and [BAM delta table](tables/bam_replacement_delta.csv) remain unchanged.

## BAM stopping and timing interpretation

The corrected runner returns callback B to BAM and lets its native
`max_evals=B-3` limit stop after the three supplied starts. It preserves the
guard against B+1 and does not suppress genuine backend errors. All in-budget
coordinates, acceptance flags, objectives and selected point costs match the
earlier BAM paths exactly. Configuration differs only in the explicit
`budget_stop_policy`; DFO wall times are the newly recorded rerun clocks.

Completion cost is the recorded DFO wall time minus recorded lookup time,
plus the sum of historical process costs for **every callback**, plus Dynamic's
separate common preparation cost. Only previously missing structural costs
are supplemented. This gives complete reconstructed costs for all 560 runs
and fills 2,752 callback cost gaps, without zero filling or borrowing across
sizes/attempts. These are retrospective fixed-path reconstructions, not online
optimizer/NLP runtime measurements.

Target attainment uses `abs(best - table_min) <= 1e-5 * max(1, abs(table_min))`.
Empirical TTS99 is the ten-run median completion cost times
`ceil(log(0.01) / log(1-p))`, with one repetition when p=1 and infinity when
p=0. There are 54 finite groups and two infinite groups (BAM Column B16 and
Dynamic B12). The earlier eight conflicting algebraic solver optimality reports
remain unresolved; this integration does not change them or claim new proofs.

## Verification and regeneration without solvers

From the repository root, use a **new output directory**:

```bash
python scripts/verify_final_process.py --output /tmp/final-process-review
# Optional: numpy and matplotlib are needed only for new figure copies.
python scripts/verify_final_process.py --output /tmp/final-process-figures --figures
python result_archives.py verify
shasum -a 256 -c results/archives/PROCESS_SHA256SUMS
python -m pytest tests/test_import_bam_budget_v2.py tests/test_import_ipopt_dfo_cstr.py tests/test_import_ipopt_dfo_non_cstr.py tests/test_bam_budget_stop.py tests/test_result_archives.py tests/test_final_process_artifacts.py -q
```

The verifier checks pre-integration hashes, original ZIPs and member inventories,
the 44 recorded analysis inputs, old/new BAM configurations and callbacks, and
byte-for-byte regenerated tables including completion costs and TTS99. It writes
its report and regenerated tables outside the retained results. It never runs
an optimizer, process NLP or enumeration. Figure bytes can vary with plotting
versions/PDF metadata; the retained six PDFs and six PNGs keep their original
hashes. Generated copies do not replace them.

## Revision history

These artifacts were on **AlbertLee125/RBFopt_Test:Benchmark at `ade67082`**,
not SECQUOIA's similarly named Benchmark used for #23. They were integrated
with SECQUOIA/main `a4db6d6` in merge `4b41cc8`. The earlier BARON-lookup and
DSDA-recovery comparisons remain historical, separately documented datasets.

Recorded package build HEADs are `bb4087e` (original CSTR), `f3dceba` (original
non-CSTR) and `b863b4f` (both corrected BAM packages). Build-time HEAD alone does
not capture uncommitted runner edits: the frozen source inventories are the
authority for the executed bytes. The structural supplement records `366b001`.
The existing analysis records `b863b4f`; those historical revisions were not
replaced with a merge revision. `verification.json` separately reports the
repository revision currently providing the artifacts.

No new optimization experiment or Overleaf edit was performed for this integration.

The merge retains main's reviewed GAMS executable routing. The current
Column/Dynamic provenance gate explicitly recognizes those two exact adapter
hashes from `5a9e704`; unknown changes still fail validation. Frozen executed
packages and their original gates remain unchanged. Tests isolate worker import
guards and model the effective-executable API. The three published analysis
scripts retain their source hashes, with narrow Ruff style/import exceptions;
their complete table replay is covered by the regression suite.
