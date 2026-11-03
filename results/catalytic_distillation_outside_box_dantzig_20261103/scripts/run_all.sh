#!/usr/bin/env bash
# Run every configuration with 12 workers and record start and end times.
set -u
BASE=/local/scratch/a/dbernaln/catdist_outside_box_54_3_20261103
cd "$BASE"
{ echo "start $(date -u +%FT%TZ) host $(hostname)"; head -c 200 /package/gams/54.3/gamsstmp.txt; echo; } > run.log
xargs -P 12 -L 1 "$BASE/scripts/solve_one.sh" < "$BASE/configs.txt"
echo "end $(date -u +%FT%TZ) results $(ls runs | wc -l)" >> run.log
