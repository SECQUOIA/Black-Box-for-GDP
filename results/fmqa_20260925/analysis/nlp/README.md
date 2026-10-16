# Historical Dantzig lookup timing comparison

**Current trace and all-outcome NLP cost report:** [October 2 results](../../../dfo_trace_nlp_20261002/analysis/README.md). This directory preserves the earlier September lookup clocks.

All 556 comparison rows use the original Dantzig completion clocks and outcomes: DSDA/RBFOpt from the September 10 archive, BAM 5.0.0 from the September 16 archive, and FMQA-SA from the September 25 archive. The baseline CSVs and manifests were checked byte-for-byte against their archives, including the recorded Dantzig host. **No Mac trace is used.** Original raw datasets are unchanged.

The earlier analysis mistakenly substituted Mac paths and clocks for the original DSDA/RBFOpt/BAM runs. Its reconstructed totals, first-hit profiles, cost-transfer profiles and completion/quality comparison have been withdrawn.

## What the corrected figures measure

- `cost_breakdown.png` / `.pdf`: replacement for the old linked image; now shows **mean recorded Dantzig lookup runtime**, with a log axis and all failed-target runs included. It does not claim an NLP/search decomposition.
- `time_performance_profiles.png`: relative **completed-run** time profiles.
- `completion_time_profiles.png`: absolute completed-run time profiles.
- `time_work_tradeoff.png`: recorded runtime versus evaluations and iterations.
- `run_costs.csv`, `case_summary.csv`, `time_profile_runs.csv`: source-preserving totals, successes and paired ratios. Failed runs remain in the denominator.

## NLP costs and missing records

The original 417 DSDA/RBFOpt/BAM rows do not contain complete ordered callback coordinates or first-hit timestamps. Their NLP-inclusive times and first-hit times are **missing, not zero**. Identical starts do not establish identical Mac/server paths, so neither Mac paths nor prorated clocks are substituted. All four lookup comparisons exclude NLP solves consistently.

The previous FMQA cost tables were withdrawn because they assigned zero cost to infeasible lookups and omitted rejected attempts. They are not regenerated. Use the [October 2 trace and all-outcome cost report](../../../dfo_trace_nlp_20261002/analysis/README.md) for 417 new Dantzig traces, the original 139 FMQA traces and complete point coverage.

`gdp_baseline_comparison.csv` retains measured full-GDP results separately, using the completed October 1 BARON/HiGHS RIC/GLOA/LOA jobs and September 25 Big-M/Hull: 45 completed jobs across five methods and nine models. Absolute target matching and at-or-better target attainment are separate columns. See the [current GDP audit](../../../gdp_comparison_current/analysis/README.md). The October 2 report provides the new traces and separate point costs. The original lookup timings are not online NLP solve timings.

## Reproduce

```bash
python nlp_cost_analysis.py --legacy-lookup-only --output results/new_historical_lookup_comparison
```

This reads archived results only; no optimizer or NLP is rerun.
