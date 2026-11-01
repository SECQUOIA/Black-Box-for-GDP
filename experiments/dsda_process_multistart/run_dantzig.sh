#!/usr/bin/env bash
# Process D-SDA multistart on Dantzig: stored responses only, about one minute.
set -Eeuo pipefail
REPOSITORY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$REPOSITORY"
export PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=""
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
# The adopted D-SDA rerun used this interpreter (Python 3.11.16, numpy 2.4.6, pandas 2.3.3).
PYTHON=${DSDA_PYTHON:-$REPOSITORY/.venv-dantzig/bin/python}
test -x "$PYTHON" || { echo "Python not found: $PYTHON (set DSDA_PYTHON)" >&2; exit 1; }
STAMP=$(date -u +%Y%m%d_%H%M%S)_$$
OUTPUT=${DSDA_OUTPUT:-$REPOSITORY/results/dsda_process_multistart_$STAMP}
mkdir -p "$(dirname -- "$OUTPUT")"
echo "HEAD $(git rev-parse HEAD)"
# --cpu auto waits for an idle physical core and pins to one of its logical CPUs.
"$PYTHON" experiments/dsda_process_multistart/run.py \
    --output "$OUTPUT" --cpu "${DSDA_CPU:-auto}" "$@" 2>&1 | tee "$OUTPUT.log"
