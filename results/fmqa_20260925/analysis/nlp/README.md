# Dantzig process timing comparison — corrected October 1

All 556 comparison rows now use the original Dantzig completion clocks and outcomes: DSDA/RBFOpt from the September 10 archive, BAM 5.0.0 from the September 16 archive, and FMQA-SA from the September 25 archive. The baseline CSVs and manifests were checked byte-for-byte against their archives, including the recorded Dantzig host. **No Mac trace is used.** Original raw datasets are unchanged.

The earlier analysis mistakenly substituted Mac paths and clocks for the original DSDA/RBFOpt/BAM runs. Its reconstructed totals, first-hit profiles, cost-transfer profiles and completion/quality comparison have been withdrawn.

## What the corrected figures measure

- `cost_breakdown.png` / `.pdf`: replacement for the old linked image; now shows **mean recorded Dantzig lookup runtime**, with a log axis and all failed-target runs included. It does not claim an NLP/search decomposition.
- `time_performance_profiles.png`: relative **completed-run** time profiles.
- `completion_time_profiles.png`: absolute completed-run time profiles.
- `time_work_tradeoff.png`: recorded runtime versus evaluations and iterations.
- `run_costs.csv`, `case_summary.csv`, `time_profile_runs.csv`: source-preserving totals, successes and paired ratios. Failed runs remain in the denominator.

## NLP costs and missing records

The original 417 DSDA/RBFOpt/BAM rows do not contain complete ordered callback coordinates or first-hit timestamps. Their NLP-inclusive times and first-hit times are **missing, not zero**. Identical starts do not establish identical Mac/server paths, so neither Mac paths nor prorated clocks are substituted. All four lookup comparisons exclude NLP solves consistently.

FMQA has original Dantzig coordinate traces. Its separate `fmqa_nlp_run_costs.csv` and `fmqa_nlp_evaluation_costs.csv` retain exact-model cost estimates only: successful NLP evaluations charged, infeasible lookups zero by the stated accounting assumption, earlier failed attempts excluded, Dynamic preparation once. Missing CSTR5–25 costs remain missing. These estimates are not compared with NLP-exclusive DFO clocks.

`gdp_baseline_comparison.csv` retains measured full-GDP results separately. A fair NLP-inclusive four-method comparison needs complete Dantzig coordinate traces for the other methods. The original lookup timings are not online NLP solve timings.

## Reproduce

```bash
python nlp_cost_analysis.py --output results/new_dantzig_timing_comparison
```

This reads archived results only; no optimizer or NLP is rerun.
