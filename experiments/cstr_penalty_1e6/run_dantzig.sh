#!/usr/bin/env bash
set -Eeuo pipefail
RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPOSITORY=${CSTR_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
export PYTHONPATH="$RUNNER" PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE CUDA_VISIBLE_DEVICES="" MPLBACKEND=Agg
export PATH="$REPOSITORY/.venv-dantzig/bin:$PATH"
CSTR_CONDA=${CSTR_CONDA:-${CONDA_EXE:-}}
if [[ ! -x "$CSTR_CONDA" ]]; then CSTR_CONDA=$(type -P conda || true); fi
if [[ ! -x "$CSTR_CONDA" && -x "$REPOSITORY/.venv-miniforge/bin/conda" ]]; then
    CSTR_CONDA="$REPOSITORY/.venv-miniforge/bin/conda"
fi
mode=${1:-dry-run}
if [[ $# -gt 0 ]]; then shift; fi
cd "$RUNNER"
exec python3 runner.py "$mode" \
    --output-root "${CSTR_OUTPUT_ROOT:-$REPOSITORY/results}" \
    --python "${CSTR_PYTHON:-$REPOSITORY/.venv-dantzig/bin/python}" \
    --conda "$CSTR_CONDA" \
    --bonmin "$REPOSITORY/.venv-dantzig/bin/bonmin" \
    --ipopt "$REPOSITORY/.venv-dantzig/bin/ipopt" "$@"
