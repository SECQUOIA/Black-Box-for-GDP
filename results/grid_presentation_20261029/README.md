# Grid figure and cost quartiles

This is a presentation update using completed experiments; no searches or solvers are run.
The input is the archived D-SDA publication analysis from 28 October 2026.
Its input hashes, all 6,300 primary Grid run slots, and all 30 evaluation curves are verified before rendering.
The figure retains every archived curve coordinate and method style, labels configuration evaluations and the target explicitly, and removes the prefix shading and legend notes.
The target is agreement with the normalized reference zero within an absolute tolerance of 1e-5.

The cost table uses all 210 runs per method at B=100, including target misses.
Entries are Q50 [Q25, Q75] in seconds, computed separately for each component by inclusive linear interpolation at ranks (n-1)p.
Summed configuration-evaluation cost includes every callback along the full recorded path, with the original stored costs unchanged.
These quartiles describe variation across 21 functions and ten seeds, not confidence intervals or repeated timing measurements.
Component quartiles need not sum to the completion quartiles.

| Method | Targets | Full-run completion | Summed configuration evaluation | Retained search |
| --- | --- | --- | --- | --- |
| D-SDA | 101/210 | 24.0803 [15.5815, 49.4878] | 24.0764 [15.5777, 49.4839] | 0.0039 [0.0037, 0.0043] |
| RBFOpt | 171/210 | 70.8057 [54.8306, 93.0910] | 60.8422 [44.3117, 82.1541] | 7.5790 [4.1226, 14.8207] |
| BAM | 147/210 | 64.4212 [48.7418, 81.6748] | 63.9662 [48.3428, 81.2240] | 0.4301 [0.3682, 0.5124] |
| FMQA-SA | 129/210 | 124.1326 [105.5749, 139.2568] | 62.3406 [43.9793, 77.5228] | 62.0359 [61.5775, 62.5295] |
| Uniform | 45/210 | 60.5088 [43.3316, 78.5961] | 60.5061 [43.3289, 78.5934] | 0.0026 [0.0026, 0.0027] |
| BAM-prefix control | 124/210 | 61.8060 [40.9561, 78.3313] | 61.8033 [40.9535, 78.3286] | 0.0026 [0.0026, 0.0027] |

Reproduce from the repository root:

```sh
python -m review_comparison.grid_presentation --input results/dsda_publication_20261028 --output /tmp/grid-presentation
```
