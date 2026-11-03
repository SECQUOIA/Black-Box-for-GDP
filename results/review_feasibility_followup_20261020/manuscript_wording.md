# Proposed supplementary clarification

An additional CSTR15 check independently reproduced the saved W03 objective of 2.82935061823614 and maximum unscaled primal violation of 5.634494497502862e-7 on the pinned original GDP.
The point is numerically feasible under the stated residual test of 1e-5, including bounds, integrality, disjunctions and logical conditions.
A subsequent fixed-configuration polishing attempt targeted a maximum original-GDP violation of 1e-8 while preserving the original objective, bounds and full active constraint set.
IPOPT 3.12.13 accepted the native options file but stopped with a degrees-of-freedom error and returned no point.
The serialized NLP contained 156 variables and 158 equalities, including three satisfied fixed-Boolean equalities.
The tighter residual check therefore remains incomplete, and no stronger conclusion about the reported lower bound is drawn from this attempt.
The original numerical bound-consistency audit remains unchanged.

This wording has not been applied to any manuscript or Overleaf file.
