#!/usr/bin/env bash
set -Eeuo pipefail
COLUMN_RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$COLUMN_RUNNER"
export PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=""
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE MPLBACKEND=Agg
COLUMN_PYTHON=/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig/bin/python
test -x "$COLUMN_PYTHON" || { echo "Recorded Dantzig Python is unavailable: $COLUMN_PYTHON" >&2; exit 1; }
if [[ -d "${COLUMN_PYTHON%/bin/python}/conda-meta" ]]; then
    COLUMN_CONDA=/local/scratch/a/lee4382/miniconda3/bin/conda
    test -x "$COLUMN_CONDA" || { echo "Recorded conda is unavailable: $COLUMN_CONDA" >&2; exit 1; }
    exec "$COLUMN_CONDA" run --no-capture-output --prefix "${COLUMN_PYTHON%/bin/python}" python runner.py "$@"
fi
exec "$COLUMN_PYTHON" runner.py "$@"
