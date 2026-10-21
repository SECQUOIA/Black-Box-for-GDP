# Proposed reply to Minor 6

We independently restored CSTR15 witness W03 on the pinned original GDP and reproduced its objective of 2.82935061823614 and maximum unscaled primal violation of 5.634494497502862e-7, including variable-bound, integrality, disjunction and logical checks.
The witness is numerically feasible under the stated residual test of 1e-5.
We then attempted fixed-configuration NLP polishing toward an independently checked 1e-8 residual target, using the original objective, bounds and complete active algebraic constraint set.
The corrected native IPOPT options file was successfully read, but the local IPOPT 3.12.13 invocation stopped with TOO_FEW_DOF before returning a point.
The serialized NLP has 156 variables and 158 equalities, including three satisfied equalities involving only fixed Boolean variables.
We retained these rows, preserved the failure and stopped after one new invocation as specified by the no-returned-solution rule.
Consequently, we cannot claim that a new point meets the tighter residual criterion or that the bound discrepancy has been verified under that criterion.
The original lower bound of 3.522552007803194 and all historical audit records remain unchanged.
This outcome neither proves mathematical infeasibility nor establishes exact feasibility, global optimality or mathematical invalidity of the reported bound.
The logs, vector checks, structural inventory and reproducible solver-free verification are retained in results/review_feasibility_followup_20261020/.

This is a proposed reply only and has not been posted or incorporated into the manuscript.
