# Three-way benchmark validation artifacts

These files are a low-budget plotting validation for the analysis introduced by
PR #20. They are not the final multi-seed, multi-budget benchmark study.

The source dataset contains 63 rows: 21 packaged grids, one seed, and one run
each for DSDA, RBFOpt, and BAM with an evaluation cap of 10. Recreate it with:

```bash
python benchmark.py \
    --methods dsda,rbfopt,bam \
    --seeds 0 \
    --n-starts 3 \
    --max-evals 10 \
    --grids-dir benchmark_grids \
    --output results/three_way_all_grids_seed0_eval10.csv
```

The committed source CSV has SHA-256
`66801871e3b56d07f8a90ef671a085da5a2c3c7dc4df73f60020d58a4635c187`.
Generate the figures and statistics tables with:

```bash
python benchmark_analysis.py \
    --results-csv results/three_way_all_grids_seed0_eval10.csv \
    --grids-dir benchmark_grids \
    --figure-dir results/figures_three_way_seed0_eval10
```

The figures were regenerated after the PR review fixes so their performance
profile denominators, convergence averages, multiple-testing corrections, and
critical-difference group bars reflect the current analysis implementation.
