#!/usr/bin/env bash
# Solve fixed configurations in the GDP form and in the three MINLP forms (product, Big-M, hull).
#
#   GAMS_EXE=/path/to/gams bash experiments/catalytic_distillation_minlp/validate.sh OUT [JOBS]
#
# Each form starts from init.gdx with the binaries fixed: CONOPT solves the GDP and product forms,
# and SBB (which then solves one NLP with CONOPT) the Big-M and hull reformulations of JAMS.
# Writes OUT/validation.csv with one row per form and configuration.
set -euo pipefail

OUT=$(realpath -m "${1:?output folder}")
JOBS=${2:-8}
GAMS=${GAMS_EXE:-gams}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
M=$ROOT/gdp_models/catalytic_distillation
CONFIGS=("8 8 12 17 17 21" "7 8 11 16 16 20" "3 4 5 11 11 14" "4 4 9 10 14 17" "3 6 12 14 19 21" "2 3 9 10 20 21"
         "4 4 6 8 8 10" "3 4 5 6 8 9" "13 13 15 16 17 19")

run() {
    local form=$1 f1=$2 c1=$3 c2=$4 c3=$5 f2=$6 b=$7
    local dir="$OUT/$form/${f1}_${c1}_${c2}_${c3}_${f2}_${b}"
    mkdir -p "$dir"
    local args=(--f1="$f1" --c1="$c1" --c2="$c2" --c3="$c3" --f2="$f2" --b="$b" --init="$M/init" --out="$dir/result.txt" lo=2)
    cd "$dir"
    # The license check can fail when many GAMS jobs start at once; such a job writes no result.
    for attempt in 1 2 3; do
        case $form in
            gdp) "$GAMS" "$M/solve_configuration.gms" --model="$M/distillation_model_corrected.gms" "${args[@]}" ;;
            product) "$GAMS" "$M/solve_minlp.gms" --model="$M/minlp_model_corrected.gms" "${args[@]}" ;;
            bigm|chull) "$GAMS" "$M/solve_emp.gms" --model="$M/emp_model_corrected.gms" --reform="$form" \
                            --solver=sbb --reslim=600 "${args[@]}" ;;
        esac > log.txt 2>&1 || true
        [[ -s result.txt ]] || ! grep -qs "network session" ./*.log || { sleep $((attempt * 5)); continue; }
        break
    done
}
export -f run
export OUT GAMS M

for form in gdp product bigm chull; do
    for config in "${CONFIGS[@]}"; do
        echo "$form $config"
    done
done | xargs -P "$JOBS" -L 1 bash -c 'run "$@"' _

{
    echo "form,f1,c1,c2,c3,f2,b,modelstat,solvestat,zobj"
    for form in gdp product bigm chull; do
        for config in "${CONFIGS[@]}"; do
            read -r f1 c1 c2 c3 f2 b <<< "$config"
            line=$(cat "$OUT/$form/${f1}_${c1}_${c2}_${c3}_${f2}_${b}/result.txt" 2>/dev/null || true)
            field() { sed -n "s/.* $1=\([^ ]*\).*/\1/p" <<< " $line"; }
            echo "$form,$f1,$c1,$c2,$c3,$f2,$b,$(field modelstat),$(field solvestat),$(field zobj)"
        done
    done
} > "$OUT/validation.csv"
echo "wrote $OUT/validation.csv"
