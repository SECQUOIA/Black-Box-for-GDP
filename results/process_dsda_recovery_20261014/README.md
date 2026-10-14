# Process DSDA: verified Dantzig single-job recovery

The full matrix is now complete: **140 validated DSDA runs, 2,611 callbacks,
75 target hits, and zero missing callback costs**. Only
`cstr_15_B22_seed9_dsda` was remeasured on Dantzig, using CPU 7 and the original
Python environment. No new NLP solves or local optimizer runs were performed
for this import, and no local development timing enters the results.

## Verification

- The recovered ZIP's CRC and all **931 internal file hashes** pass.
- The embedded original ZIP retains SHA256
  `3669558ab1b0197d0cf2b6ad4ff0df7c8b4f9b1a92a15747bff8909e6f5ef397`.
- All **139 original completed jobs / 834 files** are byte-identical to the
  parent archive. Their previously imported derived values also match exactly.
- All **420 non-DSDA selected records** are unchanged; their canonical JSON
  SHA256 remains `863517690121aa30c7731e842545e35f8399ce527db2b9be9114ae98f2878ec7`.
- All 67 executed source files match the supplied v5 package. The server's
  unrelated repository checkout HEAD is not the executed package provenance.
- The recovered run's ordered **22 (point, value, value-kind) callbacks** match
  the original failed validation trace exactly. The result remains a **target
  miss**, with `(5,2)` and objective `3.130198133025365`.
- Independent analysis matches the returned server data tables. Existing
  same-coordinate CSTR infeasible-cost donors and their raw hashes were checked.

## Recovered timing and complete CSTR15 group

| Quantity | Value |
|---|---:|
| Recovered seed9 method wall time | 0.0009359719988424331 s |
| Recorded lookup callback time | 0.0000338769459631294 s |
| Search overhead after subtracting lookup time | 0.0009020950528793037 s |
| Sum of existing measured callback costs | 22.746077284682542 s |
| Seed9 estimated completion cost | 22.74697937973542 s |
| CSTR15 target hits / seeds | 2 / 10 |
| CSTR15 completion median, all ten seeds | 21.92685708485078 s |
| Repeats for 99% success at empirical p=0.2 | 21 |
| CSTR15 TTS99 | 460.4639987818664 s |

Completion cost is recorded method time minus lookup callback time plus the
existing measured cost of every callback, including repeats; Dynamic also
adds one reference preparation cost. It is a fixed-path reconstruction, not
an online NLP wall-time measurement or first-target time. The method clock
above is not the worker/startup clock.

TTS99 uses all ten completion costs, including target misses:
`median * ceil(log(0.01) / log(1 - hits/10))`. The two middle CSTR15 completion
costs are 21.10673478996614 and 22.74697937973542 seconds.

The four reused logically infeasible costs remain unchanged: CSTR20 `(6,7)`
and `(17,19)` use CSTR30; CSTR25 `(22,24)` uses CSTR30; CSTR30 `(13,15)` uses
the existing **CSTR20** measurement. The last is not a direct CSTR30 timing.
See [the donor ledger](reused_infeasible_costs.json).

## Current publication input and reproduction

Use [analysis/candidate_selection.json](analysis/candidate_selection.json) for
the complete 560-row selection: 140 corrected DSDA plus 420 unchanged other
methods. [Group summaries](analysis/candidate_summary.csv),
[DSDA comparisons](analysis/old_vs_new_summary.csv), and
[callback costs](analysis/callbacks_and_costs.csv) are complete.
Candidate figures are drafts requiring manuscript layout and visual review;
the original publication figures and the historical 139-run import were not
overwritten. Earlier CSTR15 recovery-pending publication drafts are superseded
by these data and should be regenerated using the
[updated Work instructions](../../docs/process_dsda_overleaf_update_prompt.txt).

- [Verification audit](audit.json)
- [139-job file checksum evidence](preserved_job_files_sha256.json)
- [Recovered callback signature](recovered_callback_signature.json)
- [Exact metrics](recovered_job_and_cstr15.json)
- [Original recovery ZIP](../archives/process_dsda_recovered_20261014_5ozwo5rx_1792008943955816015.zip)
- [Recovery ZIP SHA256](../archives/process_dsda_recovered_20261014_5ozwo5rx_1792008943955816015.zip.sha256)

Recovery ZIP SHA256:
`7201a5d49d216a9c1eea64ecf649ec4c185dd9c1dafcc41c70117edf600e51b3`.

```bash
python scripts/import_process_dsda_recovery.py \
  results/archives/process_dsda_recovered_20261014_5ozwo5rx_1792008943955816015.zip
```

The importer verifies evidence and reconstructs tables without launching an
optimizer or solver. The original parent result and its original error remain
archived; the complete recovery is a separate, explicitly linked result.
