# Process DSDA budget-fairness return — October 14, 2026

The returned Dantzig matrix contains **139 validated runs out of 140 planned**,
with **2,589 callbacks and 75 target hits**. Completion is distinct from target
attainment. The original ZIP and all 1,056 internal hashes are verified; all 139
completed callback paths were independently replayed without changing the data.

The missing completed record is `cstr_15_B22_seed9_dsda`. It executed all 22
callbacks, then the audit rejected a valid tolerance-aware DSDA return. The
engine retained `(5,2)` at `3.130198133025365`; the observed strict minimum at
`(5,1)` was `3.13019813302511`. Their difference, approximately `2.55e-13`, is
below the unchanged DSDA improvement tolerance of `1e-12`. This is a validator
defect, not an optimizer crash. It remains a target miss. The original final
method clock was not retained, so a separate single-job Dantzig recovery is
required. Local replay time is never substituted for server time.

## Existing infeasible-cost reuse

The user directed reuse of existing measurements for the same logically
infeasible coordinate across CSTR sizes. Existing exact costs remain selected;
four missing joins are filled by preferring CSTR30, then the largest available
measured instance. Every donor has `preprocessing_infeasible`, zero solver
time and a positive measured evaluation time. These are reused measurements,
not newly measured runtimes for the requested size.

| Requested instance | Coordinate | Measured instance | Evaluation seconds |
|---|---|---|---:|
| CSTR20 | (6,7) | CSTR30 | 0.20002566697075963 |
| CSTR20 | (17,19) | CSTR30 | 0.1995336510008201 |
| CSTR25 | (22,24) | CSTR30 | 0.2000632556155324 |
| CSTR30 | (13,15) | CSTR20 | 0.6212939228862524 |

The last row is explicitly a CSTR20 measurement. No CSTR30 measurement for
that coordinate was located in the retained archives. All four selected values
were checked against their original records and hashes; see
[reused_infeasible_costs.json](reused_infeasible_costs.json).
There are **zero remaining missing callback costs** for the 139 validated runs.
The original ZIP's four-missing-cost summary remains unchanged as evidence of
the earlier exact-size policy. New derived tables record the revised policy.

## Inspect and reproduce

- [Audit](audit.json), [runtime](runtime.json), [current summary](analysis/summary.json)
- [Per-run results](analysis/runs.csv), [callback cost ledger](analysis/callbacks_and_costs.csv)
- [Group summaries](analysis/dsda_summary.csv), [old/new comparison](analysis/old_vs_new_summary.csv)
- [Original returned ZIP](../archives/process_dsda_budget_fairness_20261014_pudvsttz_1792004864773526053.zip)
- [Single-job recovery instructions](../../docs/process_dsda_fairness_dantzig.txt)
- [Overleaf work instructions](../../docs/process_dsda_overleaf_update_prompt.txt)

```bash
python scripts/import_process_dsda_fairness.py \
  results/archives/process_dsda_budget_fairness_20261014_pudvsttz_1792004864773526053.zip
```

The importer verifies original traces, sources, seals, starts, budgets, lookup
responses, cost donors and deterministic paths. It performs no NLP solves.
The new cost estimate subtracts recorded lookup time from method time, adds
the selected point cost for every callback including repeats, and adds one
reference Dynamic preparation. It is a fixed-path completion estimate, not
online execution or first-hit time.

The CSTR15 group remains incomplete: no nine-seed median, hit-rate estimate or
TTS99 is published as a ten-seed result. Original non-DSDA results, figures and
archives remain untouched. A complete 140-run candidate selection and final
figure replacement await the recovered server result.
