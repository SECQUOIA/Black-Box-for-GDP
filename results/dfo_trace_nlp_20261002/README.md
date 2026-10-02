# Dantzig DFO trace and NLP timing import — October 2, 2026

Start with the [verified English report, tables and figures](analysis/README.md).

The original [ZIP](../archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip) and [checksum](../archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip.sha256) preserve all 7,968 checksummed evidence files, including ordered callback traces, point results, job completion records and the executed source snapshot. They are immutable evidence. Current English runner instructions are in [the runner guide](../../docs/dfo_trace_nlp_dantzig.md).

The archive was extracted locally under `results/dantzig_review/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p/`. The extracted copy is ignored by Git to avoid duplicating thousands of archived files. Reproduction verifies and extracts the archive automatically into a temporary directory; it never runs an optimizer or NLP solver.

```bash
python dfo_trace_analysis.py
```

The updated [cost breakdown](figures/cost_breakdown.png), [performance profiles](figures/performance_profiles.png)
and [TTS99 plot](figures/tts99.png) use Dantzig DFO clocks and separately measured point costs.
Successful CSTR30 retry points use the retry time alone. Failed evaluations keep their measured costs.
The profiles use completed-run time and keep all paired starts in the denominator, including target failures.
TTS99 uses the observed hit rate and the median completion cost across all runs:
`ceil(log(0.01) / log(1-p)) * median_time`. For `p=1`, one run is used; `p=0` is infinite.
This assumes independent restarts and is not a 99% statistical confidence guarantee.

The [all-method time table](figures/all_method_completion_times.png) covers DFO, GDPopt RIC/GLOA/LOA,
and Big-M/Hull MINLP on all nine models. DFO values are means of fixed-path estimates;
GDPopt/MINLP values are single measured completions, including preparation. Their time limits,
target attainment and bound conflicts remain visible. No TTS99 is inferred from these single solver runs.

Full-precision data: [profile runs](figures/performance_profile_runs.csv), [TTS99 summary](figures/tts99_summary.csv),
[all-method times and objectives](figures/all_method_completion_times.csv),
and [all 45 GDPopt/MINLP records](figures/gdp_minlp_runs.csv).
PDF versions share the figure names. [Provenance and definitions](figures/performance.manifest.json).

```bash
python -m scripts.plot_dantzig_cost_breakdown
python -m scripts.plot_dantzig_performance
```
