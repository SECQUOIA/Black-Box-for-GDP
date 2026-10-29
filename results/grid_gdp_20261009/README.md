# Grid GDP point timings and benchmarks, October 9, 2026

The [October 9 retry publication](../grid_gdp_retry_20261009/README.md) combines
the normally terminated network retries with the original benchmark records
and links these unchanged IPOPT measurements. This directory preserves the
original run without replacing its raw results.

The Dantzig run measured all **21 × 961 = 20,181 fixed grid points** with
GAMS/IPOPT on one thread, with no failed point attempts. It also finished
processing all **105 scheduled GDP benchmark cases**. Processing a case does
not imply successful optimization: 32 were unsupported, 21 ended with errors,
and one was stopped by the hard time limit.

The original run started at **2026-10-08 21:09:03 EDT** and its final summary
was written at **2026-10-09 12:01:59 EDT**. The elapsed time was **14:52:56.527**.
ZIP packaging after that summary is outside this interval.

## Records and reproduction

- [Original ZIP](../archives/grid_gdp_run_20261008_210901_dw5vq37s.zip)
  preserves every solver log, point journal, saved solution, and source snapshot.
  Its [SHA-256](../archives/grid_gdp_run_20261008_210901_dw5vq37s.zip.sha256)
  was computed from the supplied local archive.
- [Point records](raw/point_timings.csv) contain all 20,181 measurements.
- [Per-grid point summaries](raw/point_budget_summary.csv) and
  [benchmark records](raw/benchmark.csv) are byte-for-byte archive copies.
- [Run configuration](raw/run.json) and [original summary](raw/summary.json)
  preserve the server's reported settings and outcome counts.
- [Timing summary](timing_summary.json) includes per-grid and per-method totals
  computed by [analyze.py](analyze.py). No solver is rerun by this analysis.

From the repository root:

```bash
python3 results/grid_gdp_20261009/analyze.py
shasum -a 256 -c results/archives/grid_gdp_run_20261008_210901_dw5vq37s.zip.sha256
```

The analysis verifies ZIP CRCs, all **807 internal file hashes**, all exported
raw files against the ZIP, all point timing rows against their journals, and
the 21 × 961 point and 21 × 5 method coverage. It also checks each benchmark's
status and worker time against its original result record.

## Cost of one fixed grid point

| Timing measure | Mean (s) | Median (s) | 95th percentile (s) |
|---|---:|---:|---:|
| Full point evaluation | 0.652221 | 0.372685 | 0.407089 |
| GAMS/IPOPT invocation | 0.644813 | 0.365341 | 0.398905 |
| GAMS-reported solve time | 0.016370 | 0.016000 | 0.021000 |
| IPOPT-reported internal time | 0.001 | 0.001 | 0.001 |

Full point evaluation includes fresh model preparation, the GAMS/IPOPT call,
and verification. Source auditing and log archival are measured separately.
The point evaluation times sum to **13,162.464 s (3:39:22.464)**. The timestamp
span of the point phase, including surrounding work, is **3:40:07.749**.

Most evaluations take about **0.37 s**. The 99th percentile is **12.441 s** and
the maximum is **55.054 s**. The long delays occur in the full solver call;
the slowest point still reports only 0.017 s for GAMS solve time and 0.001 s
inside IPOPT. These records do not identify the cause of the external delay.

All original model variables are fixed at each point. GAMS adds its standard
objective variable/equation. These measurements describe the fixed-coordinate
evaluation procedure; they do not measure the difficulty of optimizing an
unfixed GDP. Every IPOPT log reports 0.001 s at three-decimal precision, so
these logs cannot establish finer sub-millisecond timing differences.

For a rough budget, 10/30/50/70/100 evaluations correspond to
**6.52/19.57/32.61/45.66/65.22 s** using the overall mean. These estimates exclude
the DFO optimizer's own computation. Reconstructing a known DFO trajectory can
instead sum the measured `point_wall_s` for its actual visited coordinates.
Each point was measured once; the observed delays remain in those measurements.

| Grid | Mean per point (s) | Median per point (s) |
|---|---:|---:|
| ackley | 0.604 | 0.373 |
| alpine1 | 0.590 | 0.374 |
| alpine2 | 0.640 | 0.373 |
| bohachevsky2 | 0.504 | 0.371 |
| camel3 | 0.599 | 0.371 |
| csendes | 0.653 | 0.372 |
| deflected_corrugated_spring | 0.585 | 0.373 |
| dropwave | 0.623 | 0.372 |
| easom | 0.688 | 0.372 |
| griewank | 0.471 | 0.373 |
| holder_table | 0.608 | 0.371 |
| hosaki | 0.653 | 0.379 |
| levy | 0.636 | 0.372 |
| levy13 | 0.617 | 0.373 |
| michalewicz | 0.534 | 0.373 |
| rastrigin | 0.709 | 0.371 |
| rosenbrock | 1.021 | 0.372 |
| shubert | 0.579 | 0.373 |
| styblinski_tang | 0.801 | 0.373 |
| sum_of_squares | 0.854 | 0.374 |
| xin_she_yang3 | 0.730 | 0.374 |

## GDP benchmark time

The **73 attempted benchmark workers** took **40,211.778 s (11:10:11.778)**
in total. The benchmark timestamp span through the final summary is
**11:12:47.315**, including scheduling, unsupported-case handling and reporting.
The table uses `worker_wall_s`, which includes model preparation and the hard
timeout. Summing `method_wall_s` alone would omit the hard-timeout case.

| Method | Attempted | Unsupported | Total worker time | Mean per attempted case (s) |
|---|---:|---:|---:|---:|
| GDPopt RIC | 21 | 0 | 3:32:42.871 | 607.756 |
| GDPopt GLOA | 21 | 0 | 3:53:49.024 | 668.049 |
| GDPopt LOA | 21 | 0 | 3:43:30.255 | 638.584 |
| Big-M / BARON | 5 | 16 | 0:00:05.003 | 1.001 |
| Hull / BARON | 5 | 16 | 0:00:04.624 | 0.925 |

Big-M/Hull means cover only the five supported grids and cannot be compared
directly with the GDPopt means over all 21 grids. Their unsupported cases have
no solve time; they are not zero-time successful solves.

The original `status` counts are **51 finished, 21 error, one hard time limit,
32 unsupported expression**. Of the 51 finished cases, 47 report `optimal`
and four report `maxTimeLimit`; the hard-timeout case also reports
`maxTimeLimit`. The summary's `feasible_benchmarks=73` counts saved feasible
incumbents, including error and timeout cases. It does not mean that 73 cases
solved successfully or were globally certified. Original objective, target-hit,
bound and certificate fields are preserved without promoting their claims.

The recorded error messages comprise nine interval/fractional-power errors,
one differentiation error for `abs(0)`, and eleven GAMS solve errors. This
publication preserves these outcomes; it does not repair or rerun them.

## Configured solvers and actual benchmark calls

The run used GAMS 52.2 and Pyomo 6.10.0 on Dantzig, pinned to logical CPU 6,
one solver/BLAS thread, without an exclusive CPU reservation. Point solves
used IPOPT with a 60 s solver limit. Full methods used a 1,800 s limit.
GDPopt RIC/GLOA/LOA were configured with HiGHS for MIP and BARON for NLP,
with CLP/IPOPT configured inside BARON. The benchmark call journals show that
all **41,584 calls across the 63 GDPopt jobs were to HiGHS; BARON was never
called by these Grid GDPopt jobs**. After fixed-coordinate presolve, the
linear subproblems also used the MIP solver. The previous wording described
the NLP configuration as if it had actually been exercised.

Big-M/Hull did call BARON, with CPLEX/IPOPT configured internally: five
supported grids per method, ten MINLP calls in total. Unsupported cases made
no BARON call. The separate grid-point evaluation phase used IPOPT.

The [October 24 solver-call audit](../grid_scip_20261023/README.md#2-configured-solvers-versus-actual-calls)
also verifies both retry archives and the new SCIP-configured returns.
Both old and new Grid GDPopt benchmarks actually used HiGHS, so they do not
measure a BARON-versus-SCIP NLP performance comparison. Original archives,
raw records and the performance tables above are unchanged.
