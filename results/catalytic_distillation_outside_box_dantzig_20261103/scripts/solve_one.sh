#!/usr/bin/env bash
# Solve one configuration of the Catalytic Column with CONOPT, as in the outside-box check of
# results/catalytic_distillation_outside_box_20261102, here with GAMS 54.3.1 on Dantzig.
set -u
BASE=/local/scratch/a/dbernaln/catdist_outside_box_54_3_20261103
M=$BASE/model
read -r f1 c1 c2 c3 f2 b <<< "$*"
d=/dev/shm/dbernaln_outside_box/runs/${f1}_${c1}_${c2}_${c3}_${f2}_${b}
mkdir -p "$d" && cd "$d"
for attempt in 1 2 3; do
  timeout 400 /package/gams/54.3/gams "$M/solve_configuration.gms" --model="$M/distillation_model_corrected.gms" --init="$M/init" \
    --f1=$f1 --c1=$c1 --c2=$c2 --c3=$c3 --f2=$f2 --b=$b --out="$d/result.txt" o=/dev/null lo=0 > /dev/null 2>&1
  [[ -s result.txt ]] && break
  sleep $((attempt * 3))
done
mkdir -p "$BASE/runs/${f1}_${c1}_${c2}_${c3}_${f2}_${b}"
cp -f "$d/result.txt" "$BASE/runs/${f1}_${c1}_${c2}_${c3}_${f2}_${b}/" 2>/dev/null || true
