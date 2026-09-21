# Local process evaluation traces (started 2026-09-17)

All **417 original process run keys** were rerun: 139 each for DSDA, RBFOpt,
and BAM 5.0.0. The **89 original initial designs match exactly**. The traces
contain **9,364 objective calls** at **1,353
distinct problem/point combinations**, including initial, repeated, and
nonfinite evaluations.

These are new lookup trajectories on macOS arm64, Python 3.13.12, RBFOpt 4.3.0,
BAM wrapper 5.0.0 / native 2026.9.10. They do not reconstruct the ambiguous
old Dantzig paths. Local jobs overlapped, and the last 17 RBFOpt runs used four
independent workers. **Do not use these elapsed times for method rankings or
replace the published Dantzig time profiles with them.**

| Case | Runs | Objective calls | Distinct problem/points | Points with legacy time | Runs with full legacy cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| column | 27 | 432 | 59 | 35 | 0 |
| cstr | 180 | 4263 | 1210 | 750 | 0 |
| small_batch | 30 | 300 | 12 | 12 | 30 |
| dynamic | 180 | 4369 | 72 | 0 | 0 |

## Files

- [evaluation_points.csv](evaluation_points.csv): every evaluated coordinate in order, raw objective, phase, repeat flag, callback timestamp, and historical cost join.
- [nlp_point_requests.csv](nlp_point_requests.csv): distinct coordinates for the next GDP/NLP measurement experiment.
- [run_summary.csv](run_summary.csv): callback counts, lookup first-hit timestamps, and timing coverage per run.
- [lookup_trace_bundle.zip](lookup_trace_bundle.zip): original CSV/manifest files, complete JSONL sidecars, source/data snapshots, and interruption diagnostics.
- [reference_audit.json](reference_audit.json): original-start/data/method-code audit.
- [gdp_model_probe.json](gdp_model_probe.json): preliminary original-model connection probes and limitations.

Every final trace was checked against the result callback count and incumbent
history, exact lookup objective, repeated-point flags, and regenerated initial
coordinates. The union contains exactly the original 417 run keys, without
duplicates. All 216 repository tests passed; shell syntax and Ruff checks passed.

## Interpretation of costs

Legacy `Time` is the original solver's reported `user_time`. `Global_Time` is
cumulative and is never summed. `Status=Final` is the upstream writer's extra
best-point solve after enumeration, so that row is excluded. Other duplicates,
missing records, and invalid times stay missing. **30
runs have complete historical point-cost coverage**; their sums are estimates
under the old solver/machine policy, not new measured GDP wall times.
`legacy_known_cost_sum_s` is only a partial sum when coverage is incomplete.

The original writer can label non-infeasible terminations `Optimal`, including
time limits; that text is not proof of global optimality. The CSV lookup
objectives were retained unchanged. Dynamic has objective values but no
point-time table in this repository.

Original-model probes fixed all discrete variables and removed active
disjunctions. Column (13,4), Small Batch (2,2,1), and Dynamic (1,4) solved with
IPOPT. CSTR (3,1) solved with GAMS/BARON after permitting its license-network
connection; its objective differed from the lookup value by about 4.8e-14.
All four witness objectives matched within the benchmark tolerance, with
maximum primal residual below 1e-6. These isolated checks use different solvers
and do not establish all-point equivalence, comparable timings, or global
optimality. CSTR's BARON termination was `locallyOptimal`; earlier IPOPT
failures and the initially blocked GAMS availability check are retained in
the diagnostics. No new objective replaces a lookup table value.

## Interruptions and provenance

The first BAM pass exited with SIGILL at Dynamic, budget 30, seed 1 after 28
callbacks. Its partial file was retained. Strict resume validated 221 completed
rows and then completed all 278 DSDA/BAM runs.

For RBFOpt, 122 rows known complete before interrupt attempts were retained.
SIGINT was handled inside the optimizer, so all subsequently checkpointed rows
were excluded; the process was stopped with SIGTERM. The remaining 17 run keys
were rerun independently, each with its own work directory and complete trace.
`rbfopt_validated_prefix.manifest.json` records the subset selection and source
CSV checksum. A running status on that prefix reflects the interrupted original
plan; full coverage is established by the validated union with the 17 completed
single-run manifests.

To reproduce the joined tables after extracting the bundle:

```bash
python trace_analysis.py \
  extracted/raw/dsda_bam.csv \
  extracted/raw/rbfopt_validated_prefix.csv \
  extracted/raw/rbfopt_remaining/dynamic_*.csv \
  --output results/rechecked_process_traces
```

For formal Dantzig timing, use the sequential wrapper in
[the tracing workflow](../../docs/evaluation_tracing.md). Remote execution was
not performed in this session because SSH authentication was unavailable.
Next, establish one validated NLP solver/initialization policy and measure the
requested points, including missing/infeasible points; replay warm-started paths
in order instead of treating their costs as fixed per point.
