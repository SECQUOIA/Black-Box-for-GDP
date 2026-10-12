# Grid: current GDP point-cost figures and historical lookup data

The TTS99 and profile links below now use the
[October 11 Grid GDP path-cost analysis](../../../grid_gdp_dfo_20261011/README.md):
4,200 DFO runs with individually measured IPOPT point costs. Profiles compare
DSDA, RBFOpt, BAM and FMQA only. The selected 105 GDP/MINLP outcomes appear in a
separate per-problem time/outcome comparison. PNG and PDF are available in that report.

| Figure | PNG |
|---|---|
| Raw evaluations to first target: cumulative success | [Open](evaluation_performance_profiles.png) |
| Estimated TTS99 with measured IPOPT point costs | [Open](tts99_comparison.png) |
| Absolute completion time: cumulative success | [Open](timing/time_performance_profiles.png) |
| Separate GDPopt/MINLP time and outcome comparison | [Open](../../../grid_gdp_dfo_20261011/gdp_minlp_comparison.png) |
| Historical September lookup convergence | [Open](convergence_curves.png) |
| Historical September lookup time/work comparison | [Open](timing/time_work_tradeoff.png) |

The current profiles use absolute costs, not ratios to the fastest method.
Time profiles use full successful-run completion; failed DFO runs remain in
the denominator. The current TTS99 table uses the new RBFOpt/BAM
traces, original DSDA log coordinates and September 25 FMQA traces. It includes
all seed costs. DSDA lacks callback clocks, so its small historical lookup
runtime is retained in full. See the current report for all timing qualifications.

`benchmark.csv`, its manifest, convergence and time/work outputs remain the
historical September lookup comparison. They are not the input to the updated
figures. [Figure provenance](grid_gdp_figures.manifest.json) points to the current
data and reproducible analysis command. For process-case results, use the
[October 2 trace report](../../../dfo_trace_nlp_20261002/analysis/README.md).
