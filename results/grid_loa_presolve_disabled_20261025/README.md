# LOA subproblem-presolve diagnostic: package prepared, remote execution pending

The latest local and remote review/cstr15-dantzig-results revision at preparation was 24df0376881409a533b98d9a8490c902eef38b5b, matching the requested review baseline.
Both the main checkout and the separate results-branch worktree were clean before this task.
All prior records and publication files are preserved.
The only selected full jobs are holder_table/LOA, michalewicz/LOA and shubert/LOA.

Dantzig rejected the noninteractive SSH authentication attempt.
No new fixed-configuration SCIP solve and no new full LOA run has been executed in this task.
The actual counts are zero fixed solver calls and zero full LOA runs.
No local optimizer was substituted for the unavailable Dantzig environment.
The prepared package is ready for the user's authenticated server execution, and its remote result remains unknown.

## Completed local checks

All six original-GDP reference witnesses satisfy the existing 1e-5 acceptance and target criteria.
All six default-presolve false rejections are reproduced with local Pyomo 6.10.0, with installed module hashes unchanged.
The local environment is macOS with Python 3.13.12, whereas the historical Dantzig environment is Linux with Python 3.11.16.
The local inspection is explicitly solver-free and is not represented as an equivalent server solve.
Tests use a labelled mock solver to verify that the official disabled-presolve path reaches the SCIP NLP interface for all six configurations.
That mock-routing result is not evidence that actual SCIP will return acceptable solutions.

The archived execution source is preserved byte-for-byte in original_source.
Only one conditional keyword insertion changes an existing execution file, explicitly passing subproblem_presolve=False into the real GDPopt solve call.
The archived default path remains unchanged when the diagnostic flag is absent.
The diagnostic records GDPopt's own effective configuration and rejects missing option forwarding or a changed mip_presolve value.
All installed Pyomo and FBBT implementation files remain unchanged.
All historical network handling and correction code is preserved separately from the option change.

## Baseline and pending comparison

| Grid | Prior objective | Prior termination | Prior max violation | Prior worker seconds | Prior reference evaluations | New disabled-presolve result |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| holder_table | 0.14516723995340786 | optimal | 0 | 1623.761 | 0 | Not run |
| michalewicz | 0.08649170482029742 | optimal | 0 | 1490.761 | 0 | Not run |
| shubert | 0.08242781075119937 | optimal | 0 | 1278.446 | 0 | Not run |

The unchanged reference minimum is 0 for each problem.
The prepared analyzer will add the independently checked new objective, residual, termination, bound consistency, time and reference-coordinate evaluation counts after execution.
The actual benefit of disabling presolve is not established yet.
The official option bypasses additional preprocessing as well as FBBT, so timing and solver-call types may differ.
No existing 21-problem result is replaced and no overall ranking is recalculated.

## Execution limits and delivery

The fixed sequence contains exactly the four holder_table indices, one michalewicz index and one shubert index requested by the user.
Each fixed point permits one actual solver-interface call at most and a 60-second worker limit.
The first failed fixed check stops the entire sequence before any full LOA run.
Only if all six pass does the package launch the three selected full LOA jobs, each once with the existing 1,800-second limit.
Fresh midpoint models prevent diagnostic optima from becoming full-run initial values or warm starts.
A persistent one-use claim prevents repeated launch, and no whole-job retry or resume mode is supplied.
The inherited network retry policy logs every full-run internal attempt and consumes the same job deadline.
The short fixed budget cannot satisfy that policy's retry reserve, and an additional one-call guard enforces the user's cap.
No existing server process is stopped or existing result directory overwritten.

The ZIP is [grid_loa_presolve_disabled_dantzig_20261025.zip](grid_loa_presolve_disabled_dantzig_20261025.zip).
Exact upload, extraction, execution, tail and download commands are in [DANTZIG_COMMANDS.txt](DANTZIG_COMMANDS.txt).
The remote result ZIP has a fixed separate path under results/grid_loa_presolve_disabled_20261025.
A failure after the launcher starts also produces a partial result ZIP for diagnosis.
A failure before Python starts, such as a missing original Python environment, is visible in launch.log and produces no solver result.

The runtime requires the original GAMS 52.2.0 binary hash, Pyomo 6.10.0, recorded Python/package versions, CPU 14 and one-thread settings.
It additionally checks Pyomo module bytes against the recorded local 6.10.0 diagnostic reference, explicitly labelled separately because historical Dantzig module-byte hashes were not recorded.
Actual SCIP 9.2.4 is verified from the first fixed solve's banner rather than by adding an uncounted smoke solve.
Any environment mismatch is recorded and stops execution without installation or upgrade.
CPU affinity is not an exclusive-core reservation.

## Validation and reproducibility

All 40 related tests pass, including option forwarding, default-path preservation, exact selection, one-call and one-launch caps, failed-gate stopping, original constraints and solver-free result-analysis replay.
The deterministic package rebuild and local inspection reproduce exactly in fresh locations.
The preservation record verifies all 2,322 prior tracked regular files, original submodule state and the clean main checkout.
The manifest records the baseline revision and return ZIP, original and changed source hashes, expected and actual local environments, run status, commands and output hashes.
The source tree's README explains the runtime protocol and links the official Pyomo 6.10.0 implementation.
No new solver-derived numerical result is asserted in this preparation report.

PR 49 is already merged, so a normal push to review/cstr15-dantzig-results does not automatically update main.
