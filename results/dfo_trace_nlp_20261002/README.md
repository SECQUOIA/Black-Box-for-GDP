# Dantzig DFO trace and NLP timing import — October 2, 2026

Use the [current QHD dataset and figure index](../fmqa_qhd_20261012/README.md). The [October 2 source audit](analysis/README.md) remains historical evidence.

The original [ZIP](../archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip) and [checksum](../archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip.sha256) preserve all 7,968 checksummed evidence files, including ordered callback traces, point results, job completion records and the executed source snapshot. They are immutable evidence. Current English runner instructions are in [the runner guide](../../docs/dfo_trace_nlp_dantzig.md).

The archive was extracted locally under `results/dantzig_review/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p/`. The extracted copy is ignored by Git to avoid duplicating thousands of archived files. Reproduction verifies and extracts the archive automatically into a temporary directory; it never runs an optimizer or NLP solver.

```bash
python dfo_trace_analysis.py
```

The [performance profiles](figures/performance_profiles.png) and
[individual-run scatter](figures/completion_time_scatter.png) use Dantzig DFO clocks and separately measured point costs.
The [cost breakdown](figures/cost_breakdown.png) uses the same current QHD selection.
Successful CSTR30 retry points use the retry time alone. Failed evaluations keep their measured costs.
The profiles show cumulative target success against **absolute completion time in seconds**
(logarithmic x-axes), with no division by the fastest method. All paired starts remain
in the denominator, including target failures. A successful run contributes at its
NLP-inclusive completed-run time; this is not its first-hit time. The four DFO methods
are compared here; GDPopt and MINLP remain in the separate all-method time table below.
The profile CSV records `profile_completion_s` as the completion estimate for target
hits and infinity for misses; `estimated_total_s` retains every run's actual estimated cost.
All FMQA-SA paths now come from the [current QHD PyTorch dataset](../fmqa_qhd_20261012/README.md). The other methods include the verified October 12 follow-ups:
Column adds seed 10 for all four methods. Small Batch replaces all four methods
with ten runs each on the original GDP domain `{1,2,3}^3` (27 points, 12 feasible),
using budget 10 and seeds 0–9. RBFOpt uses MSRSM + sampling.
The [full-domain report](../small_batch_full_domain_20261012/README.md) and
[audit](../small_batch_full_domain_20261012/audit.json) verify all 400 callbacks,
including 197 infeasible evaluations and seven repeated evaluations.
Small Batch target counts are DSDA 8/10, RBFOpt 5/10, BAM 2/10, and FMQA-SA 6/10.
Infeasible point costs include measured preprocessing rejection time;
they are charged even though IPOPT was not invoked for those configurations.
The [follow-up audit](../process_followup_20261012/audit.json) and
[callback cost ledger](../process_followup_20261012/nlp_costs.json) preserve the
Column supplement and earlier restricted-domain RBFOpt runs. Those restricted
Small Batch runs are retained as evidence and are excluded from current plots.
Every callback with a measurement uses its measured point cost, including Column
`(8,5)` from the original GAMS/IPOPT-profile preprocessing measurement.
For consistency with the original figures, plot costs use each method's
`result_record.wall_time_s`; the follow-up ledger also retains the outer runner
clock. Original archived runs remain available as historical evidence.

The source table contains all 360 runs. The scatter shows available individual completion-time estimates: ten runs per
method for every panel. Circles mark target hits,
crosses mark target misses, and black lines mark medians across all runs only when every cost is available.
Horizontal offsets follow seed order. The existing `tts99.png` and `tts99.pdf`
URLs now show this scatter; the figure's axis is completion time in seconds.

The retained TTS99 summary table uses the observed hit rate and the median completion cost across all runs:
`ceil(log(0.01) / log(1-p)) * median_time`. For `p=1`, one run is used; `p=0` is infinite.
This assumes independent restarts and is not a 99% statistical confidence guarantee.

The [all-method time table](figures/all_method_completion_times.png) covers DFO, GDPopt RIC/GLOA/LOA,
and Big-M/Hull MINLP on all nine models. DFO values are means of fixed-path estimates;
GDPopt/MINLP values are single measured completions, including preparation. Their time limits,
target attainment and bound conflicts remain visible. No TTS99 is inferred from these single solver runs.

Full-precision data: [profile runs](figures/performance_profile_runs.csv), [TTS99 summary](figures/tts99_summary.csv),
[scatter runs](figures/completion_time_scatter_runs.csv),
[all-method times and objectives](figures/all_method_completion_times.csv),
and [all 45 GDPopt/MINLP records](figures/gdp_minlp_runs.csv).
PDF versions share the figure names. [Provenance and definitions](figures/performance.manifest.json).
The [scatter manifest](figures/completion_time_scatter.manifest.json) records its inputs and all 36 group summaries.

```bash
python -m scripts.plot_dantzig_cost_breakdown
python -m scripts.plot_dantzig_performance
# Update only the individual-run scatter and its legacy figure URLs:
python -m scripts.plot_dantzig_run_scatter
```

## Current FMQA timing coverage

Existing original IPOPT enumeration records supply 101 additional coordinates. The [96-point Dantzig supplement](../archives/fmqa_qhd_points_20261012_234651_f39la8cf.zip) completes the remaining logical-rejection costs: 26.449262 seconds across unique points, charged as 30.558524 seconds across 112 visits in 42 runs. All 140 current FMQA process runs now have complete costs, and every plotted method/panel has ten timed runs. The [publication ledger](../fmqa_qhd_20261012/publication_evaluation_costs.csv.gz) retains each visit and its cumulative point time. The pre-QHD plots are preserved in the [NumPy legacy snapshot](../archives/fmqa_numpy_legacy_figures_20261012.zip).

The `analysis/` directory is the immutable October 2 source audit; use `figures/` for current QHD comparisons.
