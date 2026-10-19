#!/usr/bin/env bash
set -Eeuo pipefail
RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
IPOPT_DFO_REPOSITORY=${IPOPT_DFO_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
IPOPT_DFO_PYTHON=${IPOPT_DFO_PYTHON:-$IPOPT_DFO_REPOSITORY/.venv-dantzig-nlp-overnight/bin/python}
IPOPT_FMQA_PYTHON=${IPOPT_FMQA_PYTHON:-$IPOPT_DFO_REPOSITORY/.venv-dantzig-fmqa-qhd/bin/python}
IPOPT_DFO_CONDA=${IPOPT_DFO_CONDA:-${CONDA_EXE:-}}
if [[ ! -x "$IPOPT_DFO_CONDA" ]]; then IPOPT_DFO_CONDA=$(command -v conda || true); fi
if [[ ! -x "$IPOPT_DFO_CONDA" && -x "$IPOPT_DFO_REPOSITORY/.venv-miniforge/bin/conda" ]]; then
    IPOPT_DFO_CONDA=$IPOPT_DFO_REPOSITORY/.venv-miniforge/bin/conda
fi
COIN_BIN=${COIN_BIN:-$IPOPT_DFO_REPOSITORY/.venv-dantzig/bin}
BAM_LICENSE_FILE=${BAM_LICENSE_FILE:-/local/scratch/a/lee4382/bamlice.txt}
[[ $(uname -s) == Linux ]] || { echo 'Run on Dantzig/Linux.' >&2; exit 2; }
export PYTHONPATH=$RUNNER PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 MPLBACKEND=Agg
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE CUDA_VISIBLE_DEVICES=""
export MPLCONFIGDIR=${MPLCONFIGDIR:-${TMPDIR:-/tmp}/ipopt-dfo-mpl-$UID}
export PYOMO_CONFIG_DIR=${PYOMO_CONFIG_DIR:-${TMPDIR:-/tmp}/ipopt-dfo-pyomo-$UID}
export PATH="$COIN_BIN:$PATH"
cd "$RUNNER"
mode=${1:-check}
if [[ $# -gt 0 ]]; then shift; fi
# Standard-library controller also works when one experiment environment is absent.
exec python3 ipopt_dfo_non_cstr.py "$mode" --output-root "$IPOPT_DFO_REPOSITORY/results" \
    --dfo-python "$IPOPT_DFO_PYTHON" --fmqa-python "$IPOPT_FMQA_PYTHON" \
    --conda "$IPOPT_DFO_CONDA" --bonmin "$COIN_BIN/bonmin" --ipopt "$COIN_BIN/ipopt" \
    --bam-license "$BAM_LICENSE_FILE" "$@"
