# Corrected BAM Process returns

These two immutable returns supply **all 140 BAM runs** in the
[final IPOPT Process comparison](../process_ipopt_bam_v2_20261015/README.md):

| Return | Slots | Callbacks | Target hits / misses |
|---|---:|---:|---:|
| [CSTR](ipopt_dfo_cstr_20261015_223017_ncd_12gx/) | 60 | 1,530 | 18 / 42 |
| [Column, Dynamic, Small Batch](ipopt_dfo_non_cstr_20261015_223138_r3ifrgaq/) | 80 | 1,900 | 29 / 51 |

The native budget limit receives the terminal objective value. Neither return
has a budget overrun or execution failure. The final selection replaces every
BAM slot, not just the earlier failures or favorable outcomes. Original BAM
records and their protocol failures remain in the earlier CSTR/non-CSTR
directories and ZIPs.

Each folder retains `audit.json`, `job_metadata.json`, `callbacks.csv.gz`,
`runs.csv`, frozen IPOPT inputs and the original-member hash inventory. Raw
logs, callback/proposal files and executed source snapshots remain in
`results/archives/<return-name>.zip`. Submitted packages are
`results/runners/bam_cstr_budget_v2.zip` and `bam_non_cstr_budget_v2.zip`.
See the final comparison's manifest for hashes, exact source revisions and
solver-free verification commands.
