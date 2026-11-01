# NLP subproblems solved: DFO, GDPopt, and enumeration

Presentation of existing records only; no optimizer or NLP solver is run.
Each panel shows one process model at the budget used in the main text (Dynamic at B=12).
DFO rows show all ten seeds; GDPopt rows show the single SCIP-master/IPOPT-subproblem run.
NOMAD and MISO come from the audited Dantzig return of PR #56 (`results/pr56_dantzig_return_20261031`), and D-SDA from the rerun without re-evaluated configurations (`results/dsda_no_revisit_20261031`).
DFO counts are stored fixed-configuration evaluations that reach the NLP stage; GDPopt counts are confirmed IPOPT calls.
Logical and FBBT preprocessing rejections are not NLP solves.
The dashed line is the number of NLP solves needed to evaluate every configuration in the DFO box, and the dotted line is the evaluation budget.
Direct Big-M and Hull runs are omitted because their internal NLP counts are unavailable.

```sh
python -m review_comparison.joint_process_nlp --output /tmp/joint-process-nlp
```
