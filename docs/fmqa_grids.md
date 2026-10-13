# Grid FMQA-SA

The default FMQA-SA uses QHD_Data PyTorch with CPU simulated annealing. It is not the QHDOpt optimizer. There are 21 grids, budgets 10/30/50/70/100, ten seeds, and three initial points charged to each budget: 1,050 runs.

```bash
python fmqa_grid_benchmark.py plan
python fmqa_grid_benchmark.py run
python scripts/analyze_grid_gdp_paths.py --update-published
```

See [current data and figures](../results/fmqa_qhd_20261012/README.md), the [Grid GDP report](../results/grid_gdp_dfo_20261011/README.md), and the [Dantzig runner guide](fmqa_qhd_dantzig.md). All coordinates are recorded. Current profiles use absolute NLP-inclusive completion times and raw evaluation counts; GDPopt/MINLP comparisons remain separate.

The [historical NumPy runner guide](../results/fmqa_numpy_legacy_20260925/grid_runner_guide.txt) is preserved with the old records; use `--legacy-numpy` explicitly to reproduce that implementation.
