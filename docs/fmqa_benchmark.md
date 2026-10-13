# FMQA-SA on Dantzig

The default is the QHD_Data PyTorch implementation. See the [current runner guide](fmqa_qhd_dantzig.md), [current dataset](../results/fmqa_qhd_20261012/README.md), and [NumPy legacy archive](../results/fmqa_numpy_legacy_20260925/README.md).

```bash
python -m pip install -r requirements-fmqa.txt
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
python fmqa_benchmark_runner.py plan
python fmqa_benchmark_runner.py check
python fmqa_benchmark_runner.py run --scope all
python fmqa_grid_benchmark.py run
```

The process default covers 140 runs; `--scope all` includes all 1,190 runs. The Grid entry point covers 1,050. Both keep all callback coordinates and SA proposals. Dantzig deployment, CPU affinity and environment setup use `run_fmqa_qhd_dantzig.sh`.

The old runner remains available with `--legacy-numpy`; its [archived guide](../results/fmqa_numpy_legacy_20260925/runner_guide.txt) describes historical conditions, including the restricted Small Batch domain. Those conditions are not the current publication protocol.
