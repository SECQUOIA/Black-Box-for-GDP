# Preserving experiment records before local cleanup

The user requested publication of the completed Column record and cleanup of redundant local Changes, including SCIP preparation work.
The original PR 49 is already merged, and the publication destination remains its review/cstr15-dantzig-results branch.
Existing commits are retained, and no Git history is rewritten.
The complete Column result includes all fifty new jobs and its historical failed run in the comparison denominator.
The SCIP result archives retain all first attempts, including errors and time limits, rather than keeping only successful cases.
The 46-job recovery plan and its three delivery ZIPs remain unchanged under results/runners/grid_gdpopt_scip_recovery_20261025.
No running Dantzig process is contacted, interrupted or modified by this cleanup.

preservation_map.json records the SHA-256 and exact committed file or ZIP member for all 2516 visible local file changes before cleanup.
Each destination was compared byte-for-byte by hash before retirement was prepared.
The three modified SCIP integration files are already exact members of the committed Process return archive, and their local diff is additionally retained in retired_scip_worktree.patch.
The 290 files not already found in committed evidence are preserved in retired_unique_files.zip with their original repository-relative paths.
These additional files include preparation and smoke-test logs, earlier delivery packages, an earlier CSTR penalty README and a diagnostic checksum inventory.
Preparation or smoke-test outputs are historical evidence and are not promoted to completed Dantzig benchmark results.
The archive checksum is f469c70f236423db89411e5baed1eaf0314d066dcd7cd8fdf906b98ccd0fb4cf.
The archive contains no new optimization result or source change.

The cleanup procedure first pushes the preservation commit, confirms the remote branch SHA and verifies every mapped Git blob or ZIP member.
It then removes only the matching untracked copies and restores the three matching tracked modifications to the existing main HEAD.
If any local file has changed since this inventory, cleanup must stop rather than discard the new content.
The clean branch worktree retains the Column analysis and all active recovery packages for future result processing.
Local machine paths in historical artifacts remain unchanged because they are provenance records.
