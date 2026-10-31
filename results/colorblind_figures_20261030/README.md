# Colorblind-safe manuscript figures

These outputs regenerate the four manuscript figures with the Okabe-Ito palette.
Only colors changed; every table, CSV, and curve-value file produced alongside them is byte-identical to the archived outputs listed below.
The regenerated `dsda_publication/tables/` were removed because all 12 files match `results/dsda_publication_20261028/tables/`; their hashes remain in `dsda_publication/manifest.json`.

| Manuscript figure | File | Generator | Archived output with the previous palette |
|---|---|---|---|
| Figure 1 | `review_display/figure_B_grid_evaluation_profiles.pdf` | `review_comparison.review_display` | `results/review_display_20261030/` |
| Figure 2 | `dsda_publication/figures/process_evaluation_profiles.pdf` | `review_comparison.dsda_publication` | `results/dsda_publication_20261028/` |
| Figure 3 | `joint_process_main/process_joint_completion.pdf` | `review_comparison.joint_process_main` | `results/joint_process_main_20261030/` |
| Figure S1 | `joint_process_supplement/joint_remaining_completion.pdf` | `review_comparison.joint_process_supplement` | `results/joint_process_supplement_20261030/` |

Method colors (`review_comparison/manuscript.py`): D-SDA blue `#0072B2`, RBFOpt vermillion `#D55E00`, BAM bluish green `#009E73`, FMQA-SA reddish purple `#CC79A7`, uniform gray `#666666`, BAM-prefix control sky blue `#56B4E9`.
The BAM-prefix control keeps its dash-dot line and open markers, so it remains distinguishable from BAM without color.
In the joint completion-time figures, target hits are blue `#0072B2` and misses vermillion `#D55E00`, with different markers for each.

Reproduce from the repository root:

```sh
python -m review_comparison.review_display --output /tmp/cb/review_display
python -m review_comparison.dsda_publication --output /tmp/cb/dsda_publication
python -m review_comparison.joint_process_main --output /tmp/cb/joint_process_main
python -m review_comparison.joint_process_supplement --output /tmp/cb/joint_process_supplement
```

No optimizer, solver, or experiment is run.
