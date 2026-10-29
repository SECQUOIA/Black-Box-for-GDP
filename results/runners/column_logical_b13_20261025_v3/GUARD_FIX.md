# CPU occupancy guard correction, v3

The v2 run column_logical_b13_20261025_193016_4g3iw_be stopped before environment preflight and before any search job.
The user supplied the exact blocker executable /opt/microsoft/mdatp/sbin/wdavdaemon and an unrestricted affinity mask covering CPU IDs 0 through 95.
The reported full-window CPU loads were 0.07710100231302919% on CPU 2 and 0.15396458814472824% on sibling CPU 50.
The maximum reported interval load was 0.4608294930875576% on each sibling.
The v2 process rule nevertheless treated any tick increase on either sibling as an unconditional occupancy blocker.

Version 3 assesses this specifically identified system service through the existing total CPU load limits when its affinity equals the complete online CPU set.
The executable must match the full first command token rather than a substring or a basename.
An unrelated executable, Python command, lookalike path, restricted service affinity or missing online-CPU information does not qualify.
The process remains in the raw inspection record and receives a visible CPU_BACKGROUND entry in launch.log.
Its CPU activity remains included in the unchanged limits of 5% for every interval and 2% for the full observation window on both siblings.
No service is stopped, modified, disabled or reassigned.
Other observed process activity, constrained compute affinity, unknown process inspection and unresolved scheduler allocation retain their blocking behavior.
The original 12-second minimum multi-interval inspection and CPU-2-only worker affinity remain unchanged.

This correction is covered by synthetic fixtures reproducing the reported load values and unrestricted service activity, with additional tests for running and sleeping service threads on each sibling.
Tests also retain rejection of actual compute tasks, unknown programs, constrained affinity, elevated load, unavailable inspection and unresolved allocation.
The original 50-job plan, all common initial points, IPOPT records, optimizer code, native stopping rules, versions and response policies remain byte-identical to the earlier package.
The earlier ZIPs and blocked result directories are preserved, and v3 starts in a fresh result directory.
No formal search job, original process NLP calculation, commit or push is performed during this correction.
