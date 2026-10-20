# Proposed wording for later manuscript revision

These notes are not edits to the manuscript or Overleaf project.

## FMQA implementation and limited diagnostics

The retained FMQA implementation uses a float32 factorization machine trained by MSE loss and Adam without an explicit regularization term or nonzero weight decay.
The upper-triangular QUBO includes the FM bias as an offset and is normalized by its largest absolute nonconstant coefficient.
The historical converter does not guard against an exactly zero normalization factor, and the benchmark wrapper rejects resulting nonfinite coefficients before candidate sampling.
Seven reconstructed diagnostic fits from three fixed runs were exhaustively checked over their binary domains, totaling 3,328 strings, without changing any benchmark path.
These reconstructions are distinct from historical fitted weights, which were not saved.
The selected Dynamic fallback examples illustrate inadmissible low-energy binary states and absent eligible SA samples, but they do not isolate causal contributions or establish prevalence across the benchmark.

## Bound consistency and numerical feasibility

The original CSTR15 comparison witness was independently verified at the recorded residual tolerance, reproducing its objective and unscaled violation.
The attempted tighter polishing was not completed because the solver interface rejected the supplied option before optimization.
No stronger feasibility claim should be added until a compatible, separately authorized follow-up returns a point that passes the independent original-GDP residual and discrete-configuration checks.
The archived lower bound and original witness values should remain unchanged.
