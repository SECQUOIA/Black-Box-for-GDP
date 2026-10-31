#!/usr/bin/env bash
# NOMAD and MISO on the stored Grid and process responses (no NLP solves).
set -Eeuo pipefail
REPOSITORY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$REPOSITORY"
export PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=""
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
# A separate environment keeps the published DFO environment unchanged.
ENVIRONMENT=${MIDFO_ENV:-$REPOSITORY/.venv-mi-dfo}
if [[ ! -x "$ENVIRONMENT/bin/python" ]]; then
    BASE=${MIDFO_BASE_PYTHON:-$REPOSITORY/.venv-dantzig/bin/python}
    "$BASE" -m venv "$ENVIRONMENT"
    "$ENVIRONMENT/bin/python" -m pip install --upgrade pip
    "$ENVIRONMENT/bin/python" -m pip install -r requirements-mi-dfo.txt
fi
PYTHON="$ENVIRONMENT/bin/python"
"$PYTHON" -c "import PyNomad, soogo" || { echo "PyNomadBBO or soogo is missing in $ENVIRONMENT" >&2; exit 1; }
# Quick preflight: harness, NOMAD, and MISO on four jobs before the full run.
"$PYTHON" -m pytest -q tests/test_mixed_integer_dfo.py
STAMP=$(date -u +%Y%m%d_%H%M%S)_$$
OUTPUT=${MIDFO_OUTPUT:-$REPOSITORY/results/mixed_integer_dfo_$STAMP}
echo "HEAD $(git rev-parse HEAD)"
nohup "$PYTHON" experiments/mixed_integer_dfo/run.py --output "$OUTPUT" --cpu "${MIDFO_CPU:-auto}" "$@" \
    > "$OUTPUT.log" 2>&1 &
echo "PID $!"
echo "LOG $OUTPUT.log"
echo "The last log lines print CHECKS and RETURN_ARCHIVE when the run finishes."
