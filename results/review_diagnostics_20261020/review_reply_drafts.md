# Review reply drafts

## Minor 5

We audited the actual archived FMQA execution sources and added limited iteration-level diagnostics without rerunning the performance benchmark.
The archived PyTorch model uses MSE loss and Adam with no explicit regularization term and default zero weight decay.
Its FM-to-QUBO converter uses upper-triangular interactions, includes the bias as an energy offset, and scales by the maximum absolute Q coefficient.
Synthetic constant models expose a zero-scale division that produces nonfinite coefficients, which the wrapper rejects with a ValueError before annealing or uniform fallback.
We have not changed the frozen implementation, and the archived records do not establish whether this boundary occurred in any historical fit.
We fixed three diagnostic runs and selected their first SA proposal, first fallback proposal if present and final proposal, yielding seven distinct iterations.
Because fitted-weight snapshots were absent, we reconstructed only these fits from their pre-proposal observations, logged targets, seeds and archived source.
All 3,328 binary strings satisfy the reported FM/QUBO/BQM identity tolerance, and stored sample energies agree within the stated comparison tolerance.
The two selected Dynamic fallback iterations contain no eligible stored SA sample and have an out-of-domain binary minimum in the reconstructed model.
These diagnostics do not identify the separate causal contributions of learning and fallback, estimate their population frequencies, or prove that a reconstructed energy landscape equals the historical one.

## Minor 6

We independently restored and reevaluated the fixed CSTR15 witness W03 in the pinned original GDP, including bounds, integrality, disjunctions and logic.
The reevaluated objective `2.82935061823614` and maximum unscaled violation `5.634494497502862e-7` reproduce the original audit.
The archived A12 GLOA lower bound remains `3.522552007803194`, with a bound-minus-witness difference of `0.6932013895670543` under the original audit convention.
We prepared a fixed-disjunct NLP with the original objective, constraints and bounds and attempted two bounded polishing calls from the saved continuous values.
Both calls failed at the local AMPL driver's unsupported `acceptable_iter` command keyword before optimization, so tightened feasibility has not been established.
The final diagnostic driver supplies this option through an options file and avoids repeating an interface error, but it has not been solver-tested within the exhausted two-call allocation.
We retain the failures and do not describe the unchanged start vectors as new polished witnesses.
A separately authorized follow-up in a compatible solver environment remains necessary for the tighter residual claim.
The current evidence supports only numerical feasibility under the original stated residual test and does not prove exact feasibility, global optimality or mathematical invalidity of a reported bound.
