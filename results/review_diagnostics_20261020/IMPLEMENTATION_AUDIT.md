# FMQA implementation audit

## Execution sources and versions

The authoritative sources are the files inside the three execution archives named in [selection.json](selection.json), not today's adapter.
The `source_comparison` entries record the archive member, historical SHA256, current SHA256 and byte-equality result for every compared file.
The original QHD_Data core is pinned to `eb3a20d4b5a3773d17ff31d72a35d51f58e84e56`.
The historical Grid optimizer SHA256 is `98116708aba935b15f32b1169f7e6ceee5d469552c4e7bda833eb5cc170ddc53`, and the Process optimizer SHA256 is `183651ad5e30aca279ef001d3171b1d87b15d595abc04dba0d70e35204cfa68e`.
Their only source difference is the default trainer import, while the historical QHD training wrapper SHA256 is `3642a7e6d85f3a783e5d1a4ecedfc11d97a825f5203629bb0050892de4d6fced` in all three archives.
The Grid optimizer defaults to the older `.surrogate` import, but archived `process_followup_runner.py:250–253` explicitly injects `EXPERIMENT.train`.
Archived `fmqa_qhd_experiment.py:17` binds that entry point to `qhd_surrogate.train`, so the selected Grid run also follows the QHD PyTorch path.
The Process optimizer imports `qhd_surrogate.train` directly.
The converter SHA256 is `95553689bb0a88328869996fe7da58e81089d19078c5bca3d63aeac444f50d65`, and the FM implementation SHA256 is `7841d99f9bb648446f7f42e75656cb336954cd76790ba0b13e5b481f05c14017`.
These two vendored core files are byte-identical to the archived versions.
The current optimizer adds indexed sampling of unseen points and moves the timing start, while the current training wrapper scopes and restores PyTorch settings.
The historical optimizer materializes a lexicographically ordered lattice and chooses the seeded kth unseen point from it.
The current public `adapter.py` was absent from these execution snapshots and cannot establish their historical execution path.
The [source diffs](source_diffs) retain the precise changes without modifying either source version.
The reconstruction loads the unmodified archived package into a temporary namespace, including its historical training wrapper and domain encoding.

## Training and regularization

In archived `fmqa_benchmark/optimizer.py:54`, observed finite responses are rescaled to [0,1], and observed failures receive training target 2.
When all finite observed responses are equal, their targets become zero, which does not imply that fitted QUBO coefficients are exactly zero.
In archived `fmqa_benchmark/qhd_surrogate.py:47–79`, training uses CPU float32, one intra-op thread, one inter-op thread, deterministic PyTorch algorithms and a forked RNG seeded with the logged FM seed.
The selected runs use 1,000 epochs, learning rate 0.01 and factorization size 8, as recorded in their settings and the constructor default.
In `fmqa_benchmark/vendor/qhd/fmqa/fmqa/factorization_machine.py:43–59`, the loss is `MSELoss` and the optimizer is `Adam(self.parameters(), lr=learning_rate)`.
There is no explicit regularization term in this loss and no supplied weight-decay parameter.
The actual PyTorch 2.8.0 Adam default inspected by the synthetic diagnostic is `weight_decay=0`.
Historical runtime records specify PyTorch 2.8.0+cpu on Linux/Python 3.11.16, while these diagnostic fits use PyTorch 2.8.0 on macOS ARM64/Python 3.12.13.
NumPy 2.2.6, dimod 0.12.21 and dwave-samplers 1.6.0 match the recorded version numbers.
These environment differences are retained and prohibit an assumption of bitwise historical weight identity.

## FM, QUBO, scaling and offset

For binary x, the unscaled prediction is `b + sum_i h_i x_i + sum_(i<j) dot(V[:,i],V[:,j]) x_i x_j`.
`VtoQ` at `factorization_machine.py:21–30` zeros the diagonal and lower triangle, so each interaction occurs once without a factor of two.
The converter at `fm_binary_quadratic_model.py:152–174` places h on the diagonal of Q and retains b as the offset.
Its scale is `s = max(abs(Q))`, excluding the bias.
The actual BQM stores `Q/s` and offset `b/s`, so multiplying its full energy, including offset, by positive s restores the original scale.
The exhaustive check evaluates the float32 FM forward path, an independent float64 FM formula, the unscaled converter and the stored scaled BQM for every binary string.
The comparison criterion is `abs(a-b) <= 1e-6 + 1e-5*max(abs(a),abs(b))`.
Reported relative identity errors use `max(abs(unscaled_energy), 1e-6)` as denominator, so near-zero energies can have large relative errors while satisfying the combined test.
Energy ties use an absolute scaled-energy difference of at most `1e-10`.

## Zero scale and exception handling

The converter divides by s without checking for s=0 at `fm_binary_quadratic_model.py:166–168`.
Two manually assigned two-bit models, with h=0, V=0 and bias respectively 0 and 3, reproduce NaN coefficients and a NaN or infinite offset.
The [synthetic report](fmqa/synthetic.json) preserves the warnings and nonfinite values as strings rather than replacing them with zero.
No synthetic fit or annealing call was needed to create these exact boundary models.
Injecting these constructed BQMs into the historical wrapper's training-return boundary raises `ValueError: PyTorch FMBQM has invalid coefficients, dtype or device` at `qhd_surrogate.py:75–79`.
This injection tests the actual coefficient guard but does not claim that a recorded fit produced zero scale.
The historical optimizer catches only `BudgetExpired` at `optimizer.py:168`, so the ValueError propagates before sampling and before uniform fallback.
The fallback at `optimizer.py:157–161` is reached only after sampling returns no eligible candidate.
The archived CSTR worker at `ipopt_dfo_cstr.py:448–479` records a propagated non-budget exception as `execution_failed`.
The archived non-CSTR worker has the same outer exception policy, and the Grid worker at `process_followup_runner.py:283–285` records an error after printing its traceback.
Consequently, a zero-scale error must not be described as automatically invoking uniform sampling.
No fitted-weight snapshots establish whether this boundary occurred in the historical benchmark population.

## Candidate eligibility and inference boundary

Eligibility uses only the original integer box and membership in the evaluated-point prefix.
In particular, a Process point with an unobserved infeasible objective is still eligible if it lies in the box and has not been evaluated.
The selected point and every stored sample are decoded by the historical encoding and checked against the logged classification.
The reconstructed models use only points observed before the selected proposal and exactly the logged training targets and FM seed.
All stored sample energies agree with reconstruction within `1e-5 + 1e-5*max(abs(recorded),abs(reconstructed))`, but this checks only stored sample locations.
No historical full model or unsampled-energy identity is established, and `historical_SA_optimality_miss` therefore remains null.
No new SA call is performed, because the archived samples suffice for the stated comparison on reconstructed models.
The two selected Dynamic fallback iterations have no eligible stored SA sample and have an out-of-domain minimum in the reconstructed binary energy table.
This does not exclude a separate annealing miss mechanism elsewhere or establish how frequently either mechanism occurred.

## Future changes, not applied to the benchmark

A future converter change should explicitly define behavior for zero scale, preserve the constant offset and reject nonfinite coefficients before sampler invocation.
A future experiment should persist fitted weights or complete BQM snapshots if exact historical energy-landscape attribution is required.
Neither recommendation was applied to the frozen optimizer, vendored core, benchmark paths or performance results.
