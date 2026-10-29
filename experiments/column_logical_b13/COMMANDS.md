# Column 64/B13: upload, run and return results

This v3 package is prepared but has not been executed on Dantzig.
Both earlier packages stopped before any search job at the CPU occupancy guard, and their packages and diagnostic runs remain unchanged.
Launch v3 as a fresh run because its guard and package hash differ, while the 50-job plan and all experimental inputs remain identical.
Do not use the old blocked run directory with the v3 resume command.
The original process NLP call count during preparation is zero.
Run the upload command on the Mac, then run the launch command in an authenticated Dantzig terminal.
CPU 2 and its SMT siblings must pass the occupancy checks before any of the 50 jobs starts.
Existing SCIP jobs remain untouched.
The CPU and environment guards cannot be bypassed by these commands.

## Upload from the Mac

```bash
scp \
  /Users/albertlee0125/Repos/RBFopt_Test/results/runners/column_logical_b13_20261025_v3/column_logical_b13_dantzig_20261025_v3.zip \
  /Users/albertlee0125/Repos/RBFopt_Test/results/runners/column_logical_b13_20261025_v3/column_logical_b13_dantzig_20261025_v3.zip.sha256 \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

## Launch on Dantzig

The extraction refuses an existing package directory, and the launcher also uses an inherited global lock to prevent duplicate execution.

```bash
bash <<'BASH'
set -euo pipefail
cd /local/scratch/a/lee4382/repository/RBFopt_Test
sha256sum -c column_logical_b13_dantzig_20261025_v3.zip.sha256
test ! -e results/runners/column_logical_b13_dantzig_20261025_v3
unzip -q column_logical_b13_dantzig_20261025_v3.zip -d results/runners
cd results/runners/column_logical_b13_dantzig_20261025_v3
sha256sum -c SHA256SUMS > verify.log
nohup bash run_dantzig.sh run > launch.log 2>&1 < /dev/null &
echo "$!" > launcher.pid
printf 'LAUNCHER_PID=%s\n' "$(cat launcher.pid)"
printf 'LOG=%s/launch.log\n' "$PWD"
BASH
```

## Watch progress on Dantzig

The CPU inspection takes at least 12 seconds, followed by environment checks that do not execute any seed.
The controller emits RUN_DIR, PREFLIGHT, START, DONE and RESULT_ZIP records.
An individual optimizer may stay silent between START and DONE, while its worker log and callback journal remain available under RUN_DIR/jobs.

```bash
tail -n 80 -F /local/scratch/a/lee4382/repository/RBFopt_Test/results/runners/column_logical_b13_dantzig_20261025_v3/launch.log
```

Press Ctrl-C to stop viewing the log while leaving the detached run active.
For detailed status, the following commands select the directory printed by this package's launch log.

```bash
COLUMN_PACKAGE=/local/scratch/a/lee4382/repository/RBFopt_Test/results/runners/column_logical_b13_dantzig_20261025_v3
COLUMN_RUN_DIR=$(sed -n 's/^RUN_DIR=//p' "$COLUMN_PACKAGE/launch.log" | tail -n 1)
test -n "$COLUMN_RUN_DIR" && bash "$COLUMN_PACKAGE/run_dantzig.sh" status --run-dir "$COLUMN_RUN_DIR"
find "$COLUMN_RUN_DIR/jobs" -name run.log -type f -exec tail -n 8 {} \;
```

## Resume after an infrastructure interruption

Do not use resume to replace a poor outcome or an algorithm failure.
All sealed jobs, including failures, are skipped.
Any previous unsealed worker must have stopped before resumption, and its files are preserved in their original attempt directory.
Replace the directory assignment with the exact RUN_DIR from the original launch log.

```bash
COLUMN_PACKAGE=/local/scratch/a/lee4382/repository/RBFopt_Test/results/runners/column_logical_b13_dantzig_20261025_v3
COLUMN_RUN_DIR=/local/scratch/a/lee4382/repository/RBFopt_Test/results/column_logical_b13/REPLACE_WITH_ORIGINAL_RUN_DIR
nohup bash "$COLUMN_PACKAGE/run_dantzig.sh" resume --run-dir "$COLUMN_RUN_DIR" --resume-interrupted > "$COLUMN_RUN_DIR/resume_$(date -u +%Y%m%d_%H%M%S).log" 2>&1 < /dev/null &
```

Resumption repeats the same CPU and environment checks without changing the assigned CPU or installing software.
Any callbacks in interrupted attempts remain in the attempt inventory and total recorded callback count, separately from the selected 50-job cohort.

## Download the result on the Mac

After completion, copy the exact RESULT_ZIP value from launch.log into the assignment below.
Each snapshot has a unique name and preserves earlier result ZIPs.
A blocked preflight can also produce a diagnostic ZIP, which is not a completed experiment.

```bash
RESULT_ZIP=/local/scratch/a/lee4382/repository/RBFopt_Test/results/column_logical_b13/REPLACE_WITH_RESULT_ZIP.zip
scp \
  "lee4382@dantzig.ecn.purdue.edu:${RESULT_ZIP}" \
  "lee4382@dantzig.ecn.purdue.edu:${RESULT_ZIP}.sha256" \
  /Users/albertlee0125/Downloads/
```

Return the downloaded ZIP for analysis.
All callback records, selected original IPOPT point records, baseline records, environment reports, execution sources and hashes are retained in the result archive.
The replay analyzer never invokes an optimizer or process NLP solver.
