# Corrected Grid GDP retries, October 9, 2026

All **ten previously failing cases completed without errors**, and all ten
saved solutions independently match the original analytic objective and the
CSV minimum. Seven report `optimal`; three Camel3 cases reached a time limit.
This is the explicit **`pyomo610-grid-v1` correction profile**, preserved
separately from the original and unchanged-profile retry results.

## Records and verification

- [Original result ZIP](../archives/grid_gdp_retry_fixed_all_20261009_204028_lu6vdgkt.zip)
  and [SHA-256](../archives/grid_gdp_retry_fixed_all_20261009_204028_lu6vdgkt.zip.sha256).
  The original bytes preserve every saved solution, solver log and source snapshot.
- [Raw benchmark records](raw/benchmark.csv), [run configuration](raw/run.json),
  [summary](raw/summary.json) and [retry plan](raw/retry_plan.json) are exact
  archive copies.
- [Audited results](results.csv) keep termination status, measured time,
  independently checked coordinates/objectives and source hashes together.
- [Publication metadata](publication.json) records archive and source checks,
  timings, profile identity and the existing point-data hash.
- [Existing IPOPT point data](../grid_gdp_20261009/raw/point_timings.csv) contains
  all **20,181** original one-thread measurements. No points were remeasured.
- [Earlier retry results](../grid_gdp_retry_20261009/README.md) retain the
  unchanged-profile outcomes. Their 105-case table is not overwritten by these
  ten corrected-profile attempts.

The ZIP passed CRC validation and all **130 internal SHA-256 checks**. All
45 snapshotted source files match the [shipped correction package](../runners/grid_gdp_error_fix.md).
Parent-run hashes, each selected prior failure, terminal seals and exported raw
files were checked. The Dantzig runtime matches the earlier runs: GAMS 52.2,
Pyomo 6.10.0, logical CPU 6 and one solver/BLAS thread. Original analytic model
and reference CSVs are unchanged; HiGHS/BARON settings and 1,800 s budgets are
inherited. The correction affects fixed-exponent FBBT propagation and the
Alpine1/LOA check for convergence before another cut.

Those are configured solver settings. The ten corrected-profile call journals
record **8,418 HiGHS calls and zero BARON calls**. Fixed-coordinate presolve
routes the linear subproblems to HiGHS. See the
[historical solver-call audit](../grid_scip_20261023/README.md#2-configured-solvers-versus-actual-calls)
for the per-method counts and comparison with the SCIP-configured returns.

Reproduce the audit from the repository root with Python and Pyomo installed:

```bash
python results/grid_gdp_corrected_20261009/analyze.py
shasum -a 256 -c results/archives/grid_gdp_retry_fixed_all_20261009_204028_lu6vdgkt.zip.sha256
```

The [analysis script](analyze.py) verifies archive bytes and saved variables,
bounds, integer selections, coordinates and objective values using the archived
analytic model. It also checks CSV reference values and original IPOPT data.
It performs no new solver runs and does not change the raw records.

## Results and time

The run started **October 9 at 20:40:28 EDT** and wrote its final summary at
**22:59:17 EDT**. Elapsed time through that summary was **2:18:49.174**; measured
benchmark worker times sum to **2:18:47.631**. Final ZIP packaging is outside the
summary timestamp interval. Times below use `worker_wall_s` and include the
hard timeout, whose `method_wall_s` is absent.

| Grid | Method | Worker time | Termination | Audited CSV target hit |
|---|---|---:|---|---|
| alpine1 | LOA | 0.946 s | optimal | Yes |
| camel3 | RIC | 1,800.100 s | maxTimeLimit, external watchdog | Yes |
| camel3 | GLOA | 1,789.342 s | maxTimeLimit | Yes |
| camel3 | LOA | 1,789.645 s | maxTimeLimit | Yes |
| dropwave | RIC | 120.152 s | optimal | Yes |
| dropwave | GLOA | 176.688 s | optimal | Yes |
| dropwave | LOA | 221.958 s | optimal | Yes |
| sum_of_squares | RIC | 822.847 s | optimal | Yes |
| sum_of_squares | GLOA | 754.807 s | optimal | Yes |
| sum_of_squares | LOA | 851.145 s | optimal | Yes |

All normalized objectives equal **0**. Alpine1 selected grid index `[0, 0]`;
the other nine cases selected `[15, 15]`. These are all physical coordinates
`(0, 0)`. Dropwave's unnormalized objective is -1; the other three functions'
unnormalized objectives are 0.

The original summary counts only one `hard_time_limit_benchmarks`, namely
Camel3/RIC, because it counts external watchdog termination. Camel3/GLOA and
LOA returned normally from their worker with `termination=maxTimeLimit`.
Thus **nine `finished` statuses do not mean nine optimal terminations**:
the correct termination count is **seven optimal, three time limits**.

Camel3 found the saved minimum after approximately **997.806 s (RIC),
850.218 s (GLOA), and 64.043 s (LOA)**. It continued searching because the
algorithm's lower bound remained about -0.332655 while the incumbent was 0.
The results distinguish reaching the reference minimum from satisfying the
solver's termination criterion. Reported GDPopt bounds are not promoted to
global certificates.

The hard-timeout Camel3/RIC raw record lacks final `target_hit` and grid-audit
fields. Its sealed `solution.json` is intact and independently validates at
the CSV minimum. The derived `audited_target_hit=True` records this check;
the missing original flag is preserved rather than rewritten.
