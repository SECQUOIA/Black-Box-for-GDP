#!/usr/bin/env bash
set -Eeuo pipefail
RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
FMQA_REPOSITORY=${FMQA_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
FMQA_QHD_ENV=${FMQA_QHD_ENV:-$FMQA_REPOSITORY/.venv-dantzig-fmqa-qhd}
FMQA_QHD_PYTHON=$FMQA_QHD_ENV/bin/python
[[ $(uname -s) == Linux ]] || { echo 'Run this wrapper on Dantzig/Linux.' >&2; exit 2; }
mode=${1:-check}
if [[ $# -gt 0 ]]; then shift; fi
export PYTHONPATH=$RUNNER PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 MPLBACKEND=Agg
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE CUDA_VISIBLE_DEVICES=""
export MPLCONFIGDIR=${MPLCONFIGDIR:-${TMPDIR:-/tmp}/fmqa-qhd-mpl-$UID}
mkdir -p "$MPLCONFIGDIR"
cd "$RUNNER"
if [[ "$mode" == setup ]]; then
    FMQA_QHD_BASE_PYTHON=${FMQA_QHD_BASE_PYTHON:-$FMQA_REPOSITORY/.venv-dantzig-fmqa/bin/python}
    if [[ ! -x "$FMQA_QHD_BASE_PYTHON" ]]; then FMQA_QHD_BASE_PYTHON=$(command -v python3); fi
    "$FMQA_QHD_BASE_PYTHON" -c 'import sys; assert (3, 10) <= sys.version_info[:2] <= (3, 13), "Use Python 3.10-3.13 (3.11 recommended)"'
    if [[ ! -x "$FMQA_QHD_PYTHON" ]]; then
        "$FMQA_QHD_BASE_PYTHON" -m venv "$FMQA_QHD_ENV"
    fi
    [[ -f "$FMQA_QHD_ENV/pyvenv.cfg" ]] || { echo 'FMQA_QHD_ENV must be a dedicated Python venv.' >&2; exit 2; }
    "$FMQA_QHD_PYTHON" -m pip install -r requirements-fmqa.txt
    "$FMQA_QHD_PYTHON" -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
    "$FMQA_QHD_PYTHON" -m pip check
    mode=check
fi
[[ -x "$FMQA_QHD_PYTHON" ]] || { echo 'First run: bash run_fmqa_qhd_dantzig.sh setup' >&2; exit 2; }
exec "$FMQA_QHD_PYTHON" process_followup_runner.py "$mode" \
    --experiment fmqa_qhd --fmqa-python "$FMQA_QHD_PYTHON" \
    --output-root "$FMQA_REPOSITORY/results/fmqa_qhd" --cpu "${FMQA_QHD_CPU:-6}" "$@"
