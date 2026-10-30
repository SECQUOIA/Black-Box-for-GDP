# Joint process comparison

This exploratory supplement compares existing DFO and algebraic records without running any optimizer or solver.
The two figures retain all fourteen DFO conditions and all forty-five algebraic runs.
Each DFO method has ten seeds per condition; each algebraic method has one execution per problem.
The six Dynamic panels reuse the same five algebraic observations for context, not as new replicates.
No algebraic success probability, confidence interval, or inferential paired comparison is estimated.

DFO completion costs are reconstructed full-run estimates, with repeated evaluations charged along the recorded path.
Algebraic costs use the recorded total including preparation, retaining time limits and missing accepted solutions.
Neither is plotted as first-target time.
DFO target status uses the archived absolute reference agreement; algebraic status uses the archived feasible at-or-below-reference rule.
Bound-conflict flags are retained and do not certify optimality.
The plot shows Q25, Q50, and Q75 with inclusive linear interpolation at rank (n-1)p for DFO only.
Summary rows keep the original sample sizes; the algebraic rows have blank quartile fields.

The NLP table maps every DFO callback to its current archived configuration status.
Accepted and rejected NLP evaluations count as one; logical and preprocessing rejections count as zero.
The one CSTR30 solver-error configuration was never visited by the current cohort; any visited unclassified status raises an error.
Counts describe corresponding NLP work on the recorded path, not actual online calls during lookup-only search.
GDPopt counts confirmed SCIP NLP interface invocations, including unsuccessful returns, rather than internal IPOPT iterations.
One CSTR25 LOA attempt and one CSTR30 RIC attempt lack a confirmed solver start and are reported separately.
Direct Big-M and Hull internal NLP counts are unavailable, not zero.
NLP calls differ in formulation and computational effort; the count alone does not establish efficiency.

Input hashes are verified against the original analysis manifests and checksum inventories.
All 700 DFO run keys, 45 algebraic run keys, callback sequences, and current coverage counts are checked.
No historical archive, analysis, execution revision, target definition, or solver result is replaced.
The supplement text uses one sentence per source line.

Reproduce from the repository root into a new directory:

```sh
python -m review_comparison.joint_process --output /tmp/joint-process-review
```
