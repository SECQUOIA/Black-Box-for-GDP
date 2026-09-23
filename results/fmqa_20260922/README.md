# Dantzig FMQA-SA results — September 22, 2026

Raw results from the completed process-case and QHDOpt-derived Grid experiments.
Both used the three initial points frozen from the original benchmark designs,
the original evaluation budgets, and local simulated annealing (no quantum
hardware). These runs evaluated lookup objectives; they do not include added
GDP/NLP solution costs.

| Dataset | Completed runs | Recorded server run |
|---|---:|---|
| [Process cases](case/process_case_studies.csv) | 139 / 139 | `dantzig_fmqa_20260922_190404_srlq79h8` |
| [Grid](grid/benchmark.csv) | 1,050 / 1,050 | `dantzig_fmqa_grid_20260922_193807_xee_59ti` |

Each dataset preserves its original `run.json`, `summary.json`, result CSV and
manifest, per-job evaluation/proposal traces, outcomes, logs, and non-shell
source snapshots. The NumPy FM implementation is an adapted version of the
upstream code, as recorded in the source snapshots and runtime metadata.

All original internal checksums were verified before copying. Published files
retain their original bytes, except that the original `SHA256SUMS` is named
`SOURCE_SHA256SUMS`. The new `SHA256SUMS` covers the files actually included here.
Shell scripts and generated figures are excluded. Original manifests still
record the hashes of omitted shell scripts; those references are provenance,
not missing result records. See [publication.json](publication.json) for the
exact source identities, archive hashes, counts and omissions.

Verify the published files on macOS:

```bash
(cd results/fmqa_20260922/case && shasum -a 256 -c SHA256SUMS)
(cd results/fmqa_20260922/grid && shasum -a 256 -c SHA256SUMS)
```

The comparison figures and NLP-inclusive timing analyses remain separate from
this raw-result publication. The server's single-thread configuration does not
establish exclusive CPU use; runtime interpretation must retain the recorded
execution-environment qualifications.
