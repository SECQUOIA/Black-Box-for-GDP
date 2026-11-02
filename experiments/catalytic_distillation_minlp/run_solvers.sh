#!/usr/bin/env bash
# Solve a MINLP form of the corrected column with several MINLP solvers, one core each.
#   GAMS_EXE=/path/to/gams bash run_solvers.sh FORM OUTPUT [RESLIM_SECONDS] [SOLVER ...]
# FORM is product (minlp_model_corrected.gms) or bigm or chull (emp_model_corrected.gms through JAMS).
# Every solver starts from init.gdx and the configuration (3,4,5,6,8,9) stored in it.
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
MODEL=$(cd -- "$HERE/../../gdp_models/catalytic_distillation" && pwd)
: "${GAMS_EXE:?Set GAMS_EXE}"
FORM=${1:?FORM is product, bigm, or chull}
OUT=$(mkdir -p "$2" && cd -- "$2" && pwd)
RESLIM=${3:-3600}
shift $(( $# > 2 ? 3 : 2 ))
SOLVERS=("${@:-dicopt sbb baron scip}")
read -r -a SOLVERS <<< "${SOLVERS[*]}"
CPUS=(${CPUS:-0 8 10 22 24 26})
case $FORM in
  product) generator=make_minlp; target=minlp_model_corrected.gms; driver=solve_minlp.gms; extra=() ;;
  bigm|chull) generator=make_emp; target=emp_model_corrected.gms; driver=solve_emp.gms; extra=(--reform="$FORM") ;;
  *) echo "unknown FORM $FORM" >&2; exit 1 ;;
esac
cmp -s <(python3 -c "import sys; sys.path.insert(0, '$HERE'); import $generator as m; print(m.build(m.SOURCE.read_text()), end='')") \
    "$MODEL/$target" || { echo "$target is not the output of $generator.py" >&2; exit 1; }
i=0
for solver in "${SOLVERS[@]}"; do
  dir=$OUT/$solver
  mkdir -p "$dir"
  (
    cd "$dir"
    start=$(date +%s.%N)
    # A hard limit above reslim, on the whole process group, in case a solver ignores reslim.
    setsid taskset -c "${CPUS[$i]}" timeout --kill-after=60 $((RESLIM + 600)) "$GAMS_EXE" "$MODEL/$driver" \
        --model="$MODEL/$target" "${extra[@]}" --init="$MODEL/init" --solver="$solver" --reslim="$RESLIM" \
        --out="$dir/result.txt" --gdx="$dir/solution.gdx" curDir="$dir" lo=3 > "$dir/gams.log" 2>&1 || true
    end=$(date +%s.%N)
    echo "wall_s=$(python3 -c "print($end-$start)") cpu=${CPUS[$i]}" > "$dir/wall.txt"
  ) &
  i=$((i + 1))
done
wait
for solver in "${SOLVERS[@]}"; do
  echo "$solver: $(cat "$OUT/$solver/result.txt" 2>/dev/null || echo 'no result') $(cat "$OUT/$solver/wall.txt")"
done
