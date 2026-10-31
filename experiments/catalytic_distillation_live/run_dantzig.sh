#!/usr/bin/env bash
# Live DFO runs on the corrected catalytic distillation column (see README.md).
#   GAMS_EXE=/path/to/gams experiments/catalytic_distillation_live/run_dantzig.sh [plan|run|summarize|test]
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPOSITORY=$(cd -- "$HERE/../.." && pwd)
: "${GAMS_EXE:?Set GAMS_EXE to the GAMS executable (GAMS 54 or later with CONOPT)}"
DFO_PYTHON=${DFO_PYTHON:-$REPOSITORY/.venv-dantzig-nlp-overnight/bin/python}
FMQA_PYTHON=${FMQA_PYTHON:-$REPOSITORY/.venv-dantzig-fmqa-qhd/bin/python}
MIDFO_PYTHON=${MIDFO_PYTHON:-$REPOSITORY/.venv-mi-dfo/bin/python}
COIN_BIN=${COIN_BIN:-$REPOSITORY/.venv-dantzig/bin}
BAM_LICENSE_FILE=${BAM_LICENSE_FILE:-/local/scratch/a/lee4382/bamlice.txt}
CPUS=${CPUS:-0-31}
OUTPUT=${CATDIST_OUTPUT:-$REPOSITORY/results/catalytic_distillation_live}
export PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES="" MPLBACKEND=Agg
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
cd "$HERE"
mode=${1:-run}
case $mode in
    test)
        "$DFO_PYTHON" -c "import rbfopt, bam, numpy, pandas" && "$FMQA_PYTHON" -c "import torch, dimod" &&
            "$MIDFO_PYTHON" -c "import PyNomad, soogo"
        [[ -s $BAM_LICENSE_FILE ]] || { echo "BAM license not found: $BAM_LICENSE_FILE" >&2; exit 1; }
        GAMS_EXE=$GAMS_EXE "$DFO_PYTHON" -m pytest -q "$REPOSITORY/tests/test_catalytic_distillation_live.py"
        "$MIDFO_PYTHON" -m pytest -q "$REPOSITORY/tests/test_catalytic_distillation_live.py" -k adapters ;;
    plan)
        "$DFO_PYTHON" run.py plan --output "$OUTPUT" ;;
    run)
        [[ -f $OUTPUT/plan.json ]] || "$DFO_PYTHON" run.py plan --output "$OUTPUT"
        nohup "$DFO_PYTHON" run.py run --output "$OUTPUT" --gams "$GAMS_EXE" --cpus "$CPUS" \
            --python-default "$DFO_PYTHON" --python-bam "$DFO_PYTHON" --python-fmqa "$FMQA_PYTHON" \
            --python-midfo "$MIDFO_PYTHON" --bonmin "$COIN_BIN/bonmin" --ipopt "$COIN_BIN/ipopt" \
            --bam-license "$BAM_LICENSE_FILE" "${@:2}" > "$OUTPUT/controller.log" 2>&1 &
        echo "Controller PID $! writing $OUTPUT/controller.log" ;;
    summarize)
        "$DFO_PYTHON" run.py summarize --output "$OUTPUT" \
            --reference "$REPOSITORY/results/catalytic_distillation_pilot_20261030/corrected_pilot_200_init/solves.csv" ;;
    *)
        echo "Unknown mode $mode; use test, plan, run, or summarize" >&2; exit 2 ;;
esac
