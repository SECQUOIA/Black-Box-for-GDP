The default FMQA-SA now uses the [QHD PyTorch dataset](../fmqa_qhd_20261012/README.md). Previous NumPy results and figures are preserved in the [legacy archive](../fmqa_numpy_legacy_20260925/README.md).

# Grid GDP: measured point costs along recorded DFO paths

The current comparison joins **4,200 runs and 201,833 objective evaluations**
to all **20,181 single-thread GAMS/IPOPT point measurements**. Relative-to-best
performance ratios are replaced by cumulative success versus absolute seconds
and raw objective-evaluation counts. No optimizer or NLP solver is rerun by this
analysis.

The performance profiles compare **DSDA, RBFOpt, BAM 5.0.0 and FMQA-SA only**.
GDPopt and MINLP reformulation results have a separate per-problem comparison
showing measured time and target attainment directly.

| Figure | PNG | PDF |
|---|---|---|
| Estimated TTS99, including IPOPT point costs | [View](tts99.png) | [Download](tts99.pdf) |
| Cumulative success versus absolute completion time | [View](performance_profiles.png) | [Download](performance_profiles.pdf) |
| Cumulative success versus raw evaluations to first target | [View](evaluation_profiles.png) | [Download](evaluation_profiles.pdf) |
| Separate GDPopt/MINLP comparison by problem | [View](gdp_minlp_comparison.png) | [Download](gdp_minlp_comparison.pdf) |

## Accounting and interpretation

For a recorded DFO path $p_1,\ldots,p_n$, the reconstructed completion cost is

$$\widehat T = T_{\mathrm{recorded}} - \sum_{i=1}^{n}t_{\mathrm{lookup},i}
              + \sum_{i=1}^{n}t_{\mathrm{IPOPT},p_i}.$$

Here $t_{\mathrm{IPOPT},p_i}$ is the individual `point_wall_s` measurement for
that function and integer coordinate, not a mean time multiplied by the number
of evaluations. Initial calls and repeated callbacks are charged in their
original order. Internal optimizer cache hits without objective callbacks do
not count as fresh evaluations. The IPOPT measurement includes fresh model
preparation, GAMS/IPOPT invocation and verification; source audit and log
archival are excluded. Fixing a grid point leaves zero original continuous
degrees of freedom, so this is the cost of the specified evaluation protocol,
not evidence of a difficult continuous optimization subproblem.

**DSDA qualification:** its original verbose logs retain every evaluated
coordinate but no callback clocks or lookup-time total. We retain its full
original Dantzig `wall_time_s` and add the point costs. Thus its tiny lookup
component is not removed: it is bounded above by the entire recorded run time
(at most 0.015572 s). We do not substitute locally measured overhead or invent
first-hit timestamps. RBFOpt and BAM use `search_wall_s` minus `lookup_wall_s`;
FMQA uses `wall_time_s` minus `objective_wall_s`. These retain their original
timer scopes, including different amounts of initialization and tracing.

These are **fixed-path estimates**, not measurements of online DFO runs that
called IPOPT. Each coordinate was timed once and that observation is reused
across every visit. Measurements were taken on different dates/physical cores
of Dantzig with one-thread settings; CPU affinity was not an exclusive resource
reservation. Long external-call delays are retained, with no winsorization or
replacement by the approximately 0.001 s rounded internal IPOPT log value.

## Success, profiles and TTS99

A target hit satisfies
`abs(value - CSV_minimum) <= 1e-5 * max(1, abs(CSV_minimum))`. The grids have
normalized minima of zero. This tests target attainment, not a proof of global
optimality by the optimization algorithm.

- **Evaluation figure:** first-hit callback number, including all three initial
  calls. Raw counts are not divided by another method or by dimension. Each
  budget is a separate experiment; a B100 trajectory is not assumed to be an
  extension of B10. Missing hits have infinite cost. GDPopt master iterations,
  subproblem calls and BARON iterations are not equated to DFO evaluations.
- **Time figure:** full completion cost of a target-reaching run. Unsuccessful
  runs have infinite profile cost even though their actual runtime remains in
  the run table. This is a completion-time profile, not a first-hit-time plot.
  The four DFO curves each contain 210 runs per method/budget. Each grid has
  equal weight. GDPopt and MINLP reformulations are not included in these
  profiles or their axis limits.
- **Separate GDPopt/MINLP figure:** 21 problem rows and five method columns,
  with one measured run per cell. Cell values show measured worker completion
  seconds, including target misses and time limits. Colors distinguish target
  attainment, target misses and unsupported cases; `T` identifies a time limit
  and `*` a corrected Pyomo profile. GDP/MINLP costs already include their
  actual solver work, so no DFO point costs are added. This direct comparison
  uses no cumulative profile or restart estimate.
- **TTS99:** for each grid/method/budget, $p=h/10$ and
  $R=\lceil\log(0.01)/\log(1-p)\rceil$. TTS99 is $R$ times the median completion
  cost of **all ten seeds, including unsuccessful runs**. For $p=1$, $R=1$;
  for $p=0$, TTS99 is infinite. Each plotted dot summarizes one grid; the black
  bar is the extended-real median over all 21 grids, including infinities.
  Independent restarts with the observed probability are assumed; ten seeds
  do not establish a 99% statistical confidence guarantee. We do not infer
  TTS99 for GDP/MINLP from a single run per problem.

## Sources and GDP selection

| Method | Runs | Actual evaluations | Coordinate source |
|---|---:|---:|---|
| DSDA | 1,050 | 38,033 | September 10 verbose neighbor/line-search logs plus frozen initial designs |
| RBFOpt | 1,050 | 54,600 | October 8-10 callback traces |
| BAM 5.0.0 | 1,050 | 54,600 | October 8 callback traces; sealed completed replacement for the interrupted attempt |
| FMQA-SA | 1,050 | 54,600 | October 12 QHD PyTorch callback traces |

All DSDA paths are recovered from the original log, without replaying its
search. Coordinate counts, printed objective values and every reconstructed
incumbent are checked against the original result CSV. The callback archives
are verified by member hashes, run identities, completion seals where provided,
ordered initial designs, clocks, objectives and full incumbent sequences.
There are no missing point-cost joins. The new RBFOpt/BAM paths replace their
older lookup experiments; they are not assumed identical to those paths.

GDP selection starts with the
[105 original/unchanged-profile records](../grid_gdp_retry_20261009/benchmark_current.csv),
which already include the 11 normal infrastructure retries, and replaces the
remaining ten errors with the
[ten corrected retries](../grid_gdp_corrected_20261009/results.csv).
Those ten use the explicitly identified `pyomo610-grid-v1` FBBT/LOA fixes;
they are not silently presented as an unchanged algorithm profile. No run is
selected because it was faster or achieved a better objective.

The original per-problem time limit is 1,800 s with one thread. GDPopt uses
HiGHS for master problems and BARON as the configured nonlinear subsolver;
fixed subproblems that become linear can instead use HiGHS. Big-M/Hull use
BARON. Measured `worker_wall_s` includes model preparation and captures hard
timeouts, whereas DFO retains each trace's documented search timer scope.
Solver-reported bounds are not promoted to independently verified global
certificates. Analytic lattice enumeration used to obtain normalization and
reference values is preprocessing, as described in the formulation document.

Each GDPopt method reaches the target on **18/21** grids; the other three are
Holder Table, Michalewicz and the historical modified Shubert. Big-M reaches
**4/21**, Hull **5/21**. Each reformulation has 16 unsupported functions, retained
as unsuccessful in the 21-problem denominator. These counts measure this
implementation's coverage over the suite. They are not a speed ranking on
the five-function supported subset. All three corrected Camel3 runs attain
the target but terminate at a time limit; none is reclassified as proven
optimal. The original hard-time-limit Levy13/RIC incumbent is also included
using its independently audited saved solution.

At budget 100 (210 runs per DFO method):

| Method | Target hits | Median estimated completion | Median summed point cost |
|---|---:|---:|---:|
| DSDA | 104/210 | 24.14 s | 24.14 s |
| RBFOpt | 172/210 | 365.74 s | 61.21 s |
| BAM 5.0.0 | 147/210 | 64.42 s | 63.97 s |
| FMQA-SA | 129/210 | 124.13 s | 62.34 s |

These medians include successful and unsuccessful runs; they are not TTS99.

## Reproduction and inspectable data

From the repository root with pandas and matplotlib installed:

```bash
python scripts/analyze_grid_gdp_paths.py --update-published
python -m pytest tests/test_grid_gdp_path_analysis.py -q
```

The BAM ZIP is retained under `results/archives/`; `--bam-archive /path/to.zip`
also accepts the original supplied file and enforces its known SHA-256.
`--output /path/to/report` changes the output directory. `--no-figures` performs
the numerical analysis only. `--update-published` copies the three DFO figures
to the existing Grid figure links and updates their provenance pointers. The
separate GDPopt/MINLP figure is linked directly from the report and figure index.

- [runs.csv](runs.csv): all 4,200 DFO runs, original runtime, removed lookup
  cost, summed measured costs, completed-run estimate and first-hit evaluation.
- [point_charges.csv.gz](point_charges.csv.gz): all 201,833 ordered callbacks,
  coordinates, original objective values, cumulative measured charges, archive
  member names and DSDA log block/line references. Recorded and reconstructed
  callback clocks are available for the three traced methods; DSDA clocks are
  blank. The gzip timestamp is fixed for reproducibility.
- [tts99_summary.csv](tts99_summary.csv): all 420 grid/method/budget groups.
- [gdp_runs.csv](gdp_runs.csv): all 105 selected GDP/MINLP records, failures,
  retry profiles, original source members and result hashes.
- [budget_summary.csv](budget_summary.csv): full-precision aggregates.
- [manifest.json](manifest.json): source and output hashes, coverage and policies.
- [GDP formulation](../../docs/grid_gdp.md): the two 31-way coordinate
  disjunctions with the original analytic objective and all 21 domains.

## Why absolute profiles

Dolan and Moré's *Benchmarking Optimization Software with Performance Profiles*
was published in 2002 (technical report ANL/MCS-P861-1200; arXiv version 2001).
Its ratios use the best cost among the included solvers. Gould and Scott show
that interpreting relative rankings requires care when the solver set changes.
Absolute empirical cumulative success curves keep a method's curve unchanged
when another method is added or removed. This implements Bernal's requested
raw-evaluation comparison. It is related to Moré and Wild's data profiles;
here we explicitly retain raw evaluations rather than scaling by $n+1$.

References: [Dolan and Moré, 2002](https://arxiv.org/abs/cs/0102001),
[Gould and Scott, 2016](https://www.numerical.rl.ac.uk/media/people/nick-gould/GoulScot16_toms.pdf),
[Moré and Wild, 2009](https://www.mcs.anl.gov/~wild/papers/2009/JJMSMW07.html).
