# FMQA-SA (NumPy legacy)

This is the historical NumPy implementation of the MXNet-derived FM, retained for implementation comparison and reproducibility. It is not an execution of the MXNet runtime. The current default **FMQA-SA** is the [QHD PyTorch dataset](../fmqa_qhd_20261012/README.md).

The original raw records and checksums remain unchanged:

- [Grid archive: 1,050 runs](../archives/dantzig_fmqa_grid_20260925_172020_9n7j9oh1.zip)
- [Process archive: 139 original runs](../archives/dantzig_fmqa_20260925_174150_2m7pmr0d.zip)
- [Column seed-10 supplement](../archives/process_followup_20261012_015823_k6eq6mg0.zip)
- [Full-domain Small Batch supplement](../archives/small_batch_full_domain_20261012_024647_d4390oed.zip)
- [Complete pre-QHD Grid/process figure and table snapshot](../archives/fmqa_numpy_legacy_figures_20261012.zip)
- [Historical Grid run settings](../fmqa_20260925/grid/run.json) and [process run settings](../fmqa_20260925/case/run.json).
- [Detailed-record verification and extraction](../archives/README.md#reviewing-detailed-records); per-run records and source snapshots are stored in the original ZIPs.

Immutable historical records retain the method label recorded at execution. Their publication identity is **FMQA-SA (NumPy legacy)**. Stable image URLs under the September directory may point to current figures; use the snapshot above for the pre-QHD plots.

To explicitly run the historical implementation, add `--legacy-numpy` to `fmqa_benchmark_runner.py` or `fmqa_grid_benchmark.py`. The legacy optimizer passes its NumPy trainer explicitly; it cannot silently switch to PyTorch when resuming a historical run.
