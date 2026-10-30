# Updated joint process comparison

This follow-up replaces the 27 GDPopt observations with the completed SCIP-master/IPOPT-subproblem campaign.
All 700 DFO observations and all 18 direct Big-M/Hull SCIP observations retain their previous values, time definitions and target rules.
The source revision is `329c6f93f4940436425582ae60323c0c9f95b581`.
The earlier joint comparison remains unchanged in `results/joint_process_comparison_20261029`.
No optimizer, NLP solver or benchmark is rerun by this analysis.

DFO points show ten seeds, with inclusive Q25--Q75 intervals and median ticks.
Each conventional GDP method contributes one measured observation per problem, without an estimated success probability.
The six Dynamic panels reuse the same five conventional observations, not additional replications.
Times are full-run completion costs: reconstructed evaluation plus search cost for DFO, and measured completion plus preparation for conventional methods.
Neither axis represents time to first target.
Target misses, time limits and runs without accepted solutions remain visible.
The existing absolute-reference rule for DFO and feasible-at-or-below-reference rule for conventional methods are preserved.
The DFO display order is BAM, D-SDA, FMQA-SA, RBFOpt and Uniform.

The workload table keeps the corresponding fixed-configuration DFO NLP counts and uses confirmed IPOPT execution banners in the new GDPopt journals.
Preprocessing rejections do not count as NLP solves; unsuccessful solver returns do count when an execution is confirmed.
DFO median counts can be fractional because each condition has ten seeds.
These counts do not equate formulation, initialization, internal iterations or computational effort.
Direct Big-M/Hull internal NLP counts remain unavailable, not zero.

Bound flags are recomputed against the best independently checked saved feasible point in the current 45-run cohort.
Thus a retained direct result can acquire a flag when the new campaign supplies a better checked witness.
Flags match the updated main process table and S7; they do not certify global optimality.
Existing logs, manifests, execution revisions, historical reports and original figure generators remain unchanged.

| Method | Target hits out of nine |
| --- | ---: |
| Big-M | 5 |
| Hull | 7 |
| GLOA | 1 |
| LOA | 5 |
| RIC | 5 |

Reproduce from the repository root into a fresh directory:

```sh
python -m review_comparison.joint_process_ipopt --output /tmp/joint-process-ipopt
python -m pytest tests/test_joint_process_ipopt.py tests/test_joint_process.py -q
```
