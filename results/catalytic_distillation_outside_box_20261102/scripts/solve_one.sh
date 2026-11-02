#!/usr/bin/env bash
set -u
M=/home/bernalde/repos/RBFopt_Test/.worktrees/catdist/gdp_models/catalytic_distillation
read -r f1 c1 c2 c3 f2 b <<< "$*"
d=/dev/shm/outside/runs/${f1}_${c1}_${c2}_${c3}_${f2}_${b}
mkdir -p "$d" && cd "$d"
for attempt in 1 2 3; do
  timeout 400 /home/bernalde/packages/gams54.2_linux_x64_64_sfx/gams "$M/solve_configuration.gms" --model="$M/distillation_model_corrected.gms" --init="$M/init" \
    --f1=$f1 --c1=$c1 --c2=$c2 --c3=$c3 --f2=$f2 --b=$b --out="$d/result.txt" o=/dev/null lo=0 > /dev/null 2>&1
  [[ -s result.txt ]] && break
  sleep $((attempt * 3))
done
