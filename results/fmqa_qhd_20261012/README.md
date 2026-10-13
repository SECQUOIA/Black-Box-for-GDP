# FMQA-SA: current QHD PyTorch results

The default FMQA-SA dataset is the October 12 Dantzig QHD_Data PyTorch run at commit `eb3a20d4b5a3773d17ff31d72a35d51f58e84e56`. Figure labels remain **FMQA-SA**. Backend identity belongs in these records and manifests, without a backend-change footnote on the figures.

All **1,190 runs** completed: 1,050 Grid and 140 process runs, with **58,030 evaluation callbacks** and 54,460 recorded SA proposal sets. CPU and numerical libraries used one thread. Ordered initial points, seeds and evaluation budgets match the corresponding original experiments. Column has seeds 1-10; Small Batch uses all 27 possible coordinates, budget 10, seeds 0-9.

## Current figures

- [Grid TTS99](../grid_gdp_dfo_20261011/tts99.png) / [PDF](../grid_gdp_dfo_20261011/tts99.pdf)
- [Grid absolute completion-time profile](../grid_gdp_dfo_20261011/performance_profiles.png) / [PDF](../grid_gdp_dfo_20261011/performance_profiles.pdf)
- [Grid raw evaluation-count profile](../grid_gdp_dfo_20261011/evaluation_profiles.png) / [PDF](../grid_gdp_dfo_20261011/evaluation_profiles.pdf)
- [Process per-run completion scatter](../dfo_trace_nlp_20261002/figures/tts99.png) / [PDF](../dfo_trace_nlp_20261002/figures/tts99.pdf)
- [Process absolute completion-time profile](../dfo_trace_nlp_20261002/figures/performance_profiles.png) / [PDF](../dfo_trace_nlp_20261002/figures/performance_profiles.pdf)
- [Process cost breakdown](../dfo_trace_nlp_20261002/figures/cost_breakdown.png) / [PDF](../dfo_trace_nlp_20261002/figures/cost_breakdown.pdf)
- [Separate DFO/GDPopt/MINLP table](../dfo_trace_nlp_20261002/figures/all_method_completion_times.png)

## Timing and coverage

Completion estimates replace recorded lookup time with separately measured point costs for every visited coordinate, including repeats, initial points and rejected points. Dynamic preparation is added once. These are fixed-path estimates, not measured online NLP-in-the-loop runtimes. TTS99 uses the median full-run time across all ten seeds and the observed target hit rate; it assumes independent restarts. The target tolerance is `1e-5 * max(1, abs(target))`. The process `tts99.png/pdf` filenames remain aliases for the individual-run completion scatter; aggregate TTS99 values are in its CSV.

All **58,030 callbacks across 1,190 runs now have measured point costs**, including every callback in all 140 process runs. The original QHD export lacked 197 process coordinates; 101 were recovered from the existing same-model GAMS/IPOPT enumeration, preserving the primary successful-retry policy. The remaining **96 logically infeasible coordinates** (95 CSTR, one Column) were measured on Dantzig and imported from the [rejection-time supplement](../archives/fmqa_qhd_points_20261012_234651_f39la8cf.zip).

The supplement passed all 96 completion seals and 507 file checksums. One logical CPU and one numerical thread were used; all 96 points returned `preprocessing_infeasible`, with zero solver calls. Their fresh model preparation and logical rejection took **26.449262 seconds** in total (median **0.232034 seconds** per point). They occur in **112 callbacks across 42 process runs**, so charging every visit adds **30.558524 seconds** to those paths. These are rejection-processing costs, not IPOPT solve times. Original Grid costs, previously complete process costs, target outcomes and other methods remain unchanged.

The publication ledger records `cumulative_point_evaluation_s` in callback order within each run, counting repeated and rejected points every time. Full completion estimates add search overhead and, for Dynamic, one reference preparation. All process time profiles, scatter points, medians and TTS99 aggregates now use complete costs. If future data lack a point measurement, its time remains unavailable rather than being replaced by zero or another point's cost.

## Data and reproduction

- [Original immutable archive](../archives/fmqa_qhd_20261012_034123_8kcczd4b.zip): every raw job, callback, proposal, source snapshot, interrupted prefix and runtime transition.
- [Audit](audit.json), [runtime](runtime_fmqa.json), [frozen run](run.json), [run records](runs.csv).
- [Raw trajectories](trajectories.csv.gz), [original attached costs](evaluation_costs.csv.gz), [current expanded cost ledger](publication_evaluation_costs.csv.gz).
- [Current process runs](process_runs.csv), [verified rejection measurements and runtime](point_supplement.json). The missing-point and missing-callback files are empty because coverage is complete.
- [NumPy legacy data and figure snapshot](../fmqa_numpy_legacy_20260925/README.md).

```bash
python scripts/import_fmqa_qhd.py results/archives/fmqa_qhd_20261012_034123_8kcczd4b.zip
python scripts/analyze_grid_gdp_paths.py --update-published
python -m scripts.plot_dantzig_cost_breakdown
python -m scripts.plot_dantzig_performance
# Revalidate the completed supplement and refresh process figures:
python scripts/import_fmqa_qhd_points.py results/archives/fmqa_qhd_points_20261012_234651_f39la8cf.zip
```

The final command validates the Dantzig runtime, original GDP sources, 96 completion seals and every measured rejection before refreshing the process figures. Archived raw QHD CSVs keep their original strict-hit flags and initially attached costs; publication outcomes use the common tolerance and publication costs use the expanded ledger.
