#!/usr/bin/env bash
set -Eeuo pipefail
RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROCESS_REPOSITORY=${PROCESS_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
PROCESS_DFO_ENV=${PROCESS_DFO_ENV:-$PROCESS_REPOSITORY/.venv-dantzig-nlp-overnight}
if [[ ! -x "$PROCESS_DFO_ENV/bin/python" && -x "$PROCESS_REPOSITORY/.venv-dantzig-grid-trace/bin/python" ]]; then
    PROCESS_DFO_ENV=$PROCESS_REPOSITORY/.venv-dantzig-grid-trace
fi
PROCESS_FMQA_ENV=${PROCESS_FMQA_ENV:-$PROCESS_REPOSITORY/.venv-dantzig-fmqa}
PROCESS_CONDA=${PROCESS_CONDA:-${CONDA_EXE:-}}
if [[ ! -x "$PROCESS_CONDA" ]]; then PROCESS_CONDA=$(command -v conda || true); fi
if [[ ! -x "$PROCESS_CONDA" ]]; then PROCESS_CONDA=$PROCESS_REPOSITORY/.venv-miniforge/bin/conda; fi
[[ $(uname -s) == Linux ]] || { echo 'Run this wrapper on Dantzig/Linux.' >&2; exit 2; }
[[ -x "$PROCESS_CONDA" ]] || { echo 'Set PROCESS_CONDA to the conda executable.' >&2; exit 2; }
for env_path in "$PROCESS_DFO_ENV" "$PROCESS_FMQA_ENV"; do
    [[ -x "$env_path/bin/python" ]] || { echo "Missing environment: $env_path. Set PROCESS_DFO_ENV / PROCESS_FMQA_ENV to the existing environment." >&2; exit 2; }
done
export COIN_BIN=${COIN_BIN:-$PROCESS_REPOSITORY/.venv-dantzig/bin}
export BAM_LICENSE_FILE=${BAM_LICENSE_FILE:-/local/scratch/a/lee4382/bamlice.txt}
export PYTHONPATH=$RUNNER PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 MPLBACKEND=Agg
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
export PATH="$COIN_BIN:$PATH"
mode=${1:-check}
if [[ $# -gt 0 ]]; then shift; fi
cd "$RUNNER"
exec "$PROCESS_CONDA" run --no-capture-output --prefix "$PROCESS_DFO_ENV" python process_followup_runner.py "$mode" \
    --output-root "$PROCESS_REPOSITORY/results/process_followup" --cpu "${PROCESS_CPU:-6}" \
    --dfo-python "$PROCESS_DFO_ENV/bin/python" --fmqa-python "$PROCESS_FMQA_ENV/bin/python" \
    --conda "$PROCESS_CONDA" --bonmin "$COIN_BIN/bonmin" --ipopt "$COIN_BIN/ipopt" "$@"
