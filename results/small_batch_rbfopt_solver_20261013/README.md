# Small Batch RBFOpt with solver-based search — October 13, 2026

All ten Dantzig runs completed with `MSRSM`, `global_search_method=solver`,
`rbf=auto`, and the original frozen initial designs for seeds 0–9. Each run used
budget 10 including three initial evaluations, on the full `{1,2,3}^3` domain.
CPU affinity was `[6]`, with numerical-library threads set to one.

These ten runs replace only Small Batch RBFOpt in the current process figures.
The [previous sampling dataset](../small_batch_full_domain_20261012/README.md)
remains archived. DSDA, BAM, FMQA-SA and the other process cases are unchanged.

| Quantity | Result |
|---|---:|
| Completed runs | 10/10 |
| Objective callbacks / callbacks with measured point costs | 100 / 100 |
| Feasible / infeasible callbacks | 65 / 35 |
| Repeated callbacks | 0 |
| Actual Bonmin auxiliary solves | 72 |
| Nonoptimal auxiliary returns / solver exceptions | 0 / 0 |
| Target hits | 5/10 |
| Median recorded optimizer time | 1.084597 s |
| Median NLP-inclusive completion estimate | 6.015541 s |
| Estimated TTS99 | 42.108790 s |
| Coordinator elapsed time, including checks and exports | 28.407325 s |

All 72 recorded auxiliary calls used Bonmin and returned `optimal`. IPOPT passed
preflight but was not separately invoked by RBFOpt in these runs. These solvers
optimize RBFOpt's surrogate subproblems; they do not establish global optimality
of the original Small Batch GDP. Five seeds (1, 4, 5, 7, 9) attained the frozen
lookup target of 167427.65711470306 within the publication tolerance.

The completion estimate is `recorded optimizer time - lookup callback time +
measured point costs along the trajectory`, including infeasible callbacks.
It uses the existing 27-point Dantzig measurements and is not an online NLP run.
TTS99 is the median completion estimate times seven independent restarts,
estimated from a 5/10 hit rate. The previous sampling data also hit 5/10, with
median completion 5.082049 s and TTS99 35.574343 s.

The [audit](audit.json) verified the archive's 180 evidence files, 101 source
files, ten job seals, ordered callback records, solver call pairs and checksums,
original point measurements and byte-for-byte regeneration of all aggregate CSVs.

- [Immutable raw ZIP](../archives/small_batch_rbfopt_solver_20261013_172454_czzqkizx.zip)
  and [SHA256](../archives/small_batch_rbfopt_solver_20261013_172454_czzqkizx.zip.sha256):
  all raw trajectories, solver calls, logs, result records and executed source.
- [Trajectories](trajectories.csv), [solver calls](auxiliary_solver_calls.csv),
  [per-callback costs](evaluation_costs.csv), [completion estimates](completion_estimates.csv).
- [Settings and initial designs](run.json), [runtime](runtime_dfo.json),
  [summary](summary.json), [method summary](method_summary.csv).
- Updated [per-run scatter](../dfo_trace_nlp_20261002/figures/tts99.png),
  [absolute-time success profile](../dfo_trace_nlp_20261002/figures/performance_profiles.png),
  [TTS99 summary](../dfo_trace_nlp_20261002/figures/tts99_summary.csv).

Reproduce the import and figures without running optimizers:

```bash
python -m scripts.import_small_batch_rbfopt_solver \
  results/archives/small_batch_rbfopt_solver_20261013_172454_czzqkizx.zip
python -m scripts.plot_dantzig_cost_breakdown
python -m scripts.plot_dantzig_performance
```
