# Current and historical generated tables

The [current publication analysis](../../results/dsda_publication_20261028/tables/) adopts the verified D-SDA tolerance and Grid target-stopping records on top of the Column and CSTR30 updates.
The following files are byte-identical copies from that analysis.

- grid_hits.tex
- grid_intervals_B100.tex
- process_cost.tex
- process_hits.tex
- run_records.csv
- paired_grid.csv
- paired_process.csv
- configuration_coverage.csv

Every other pre-existing file in this directory is a historical companion, not a complete representation of the current cohort.
In particular, paired_comparisons.csv, numerical_summary.json, the other grid_intervals files, process_intervals.tex, process_tts.tex and rbfopt_process_variants.tex retain preceding cohorts.
Use paired_grid.csv and paired_process.csv for the current comparisons involving D-SDA.
The original FMQA-uniform analysis remains unchanged and is linked separately in the supplementary text.
The current main and supplementary sources embed their displayed tables directly and do not load these generated TeX files.
See the [current manuscript README](../README.md) for results and reproduction commands.

The Grid cost table now uses [presentation-update rows](../../results/grid_presentation_20261029/grid_cost_rows.tex) in grid_cost.tex and full-precision quartiles in grid_cost_quartiles.csv.
These are descriptive Q25/Q50/Q75 statistics over the same completed B=100 runs, including target misses.
