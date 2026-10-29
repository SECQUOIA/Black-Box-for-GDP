# Pre-solver logging correction for the selective LOA diagnostic

The user reported that the original delivery stopped at holder_table [3,1] with zero fixed solver calls and zero full LOA runs.
The error was TypeError: Object of type ConfigDict is not JSON serializable.
The original returned ZIP remains on Dantzig and has not been ingested locally, so user_reported_status.txt is labeled as user-supplied evidence.
This is an execution-recorder failure before any optimization, not a failed SCIP solution or evidence about subproblem_presolve=False.
No new objective, residual, time comparison or presolve-effect conclusion is available for holder_table, michalewicz or shubert.

The fixed worker now records mip_solver_args.value() and nlp_solver_args.value() instead of passing the live ConfigDict objects to JSON.
The live GDPopt configuration, original model, SCIP/GAMS route, tolerances, initialization, deadlines and stopping rule remain unchanged.
The installed Pyomo files are not modified.
The original archived execution source still differs only by the previously disclosed conditional subproblem_presolve=False keyword.
Only diagnostic recording and delivery bookkeeping changed relative to the original diagnostic package.

The v2 launcher uses a fresh result directory and a fresh exclusive claim.
It reads the original stopped ZIP and requires the exact reported first-worker serialization failure with zero optimizer calls.
It verifies the original package identity, result checksums, counters, launch ledger and absence of solver execution artifacts before accepting this correction.
An earlier solver call, a different failure or a repeated v2 launch is refused.
The stopped ZIP and its verification record are included in the new return archive, while the original server directory and claim remain untouched.
The aggregate experiment limits remain at most six fixed calls of 60 seconds each and at most three full LOA runs of 1,800 seconds each.
Any actual fixed-solver failure still stops the sequence without a whole-job retry or an additional solver patch.

The regression test executes the actual fixed worker through the original subprocess launcher.
Restoring the two faulty expressions reproduces the reported serialization failure before the mocked optimizer boundary.
The corrected worker reaches that boundary for all six configurations with unchanged solver arguments and valid recorded JSON.
These are mock boundary checks and do not count as SCIP or GAMS execution.
All 42 related tests passed, and Ruff, shell syntax and whitespace checks passed.
The local solver-free inspection and package rebuild are verified separately in replay_verification.json.
All 2,339 pre-existing tracked files outside the four intentional source/test/documentation edits retain their prior hashes.
The original delivery, historical results, archives, manifests, manuscript, Overleaf material and representative figures are preserved.

The corrected package is prepared but has not been executed on Dantzig by the assistant.
See DANTZIG_COMMANDS.txt for upload, extraction, one-use launch, tail and download commands.
The existing three-problem selective diagnostic remains separate from the 21-grid performance inventory.
The changes are intended for review/cstr15-dantzig-results, whose merged PR 49 does not cause later pushes to update main.
