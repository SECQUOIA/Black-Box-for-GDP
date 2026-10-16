#!/usr/bin/env bash
set -Eeuo pipefail
RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
GRID_REPOSITORY=${GRID_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
GRID_ENV=${GRID_ENV:-$GRID_REPOSITORY/.venv-dantzig-grid-trace}
GRID_BASE_ENV=${GRID_BASE_ENV:-$GRID_REPOSITORY/.venv-dantzig-bam}
GRID_CONDA=${GRID_CONDA:-${CONDA_EXE:-}}
if [[ ! -x "$GRID_CONDA" ]]; then GRID_CONDA=$(command -v conda || true); fi
if [[ ! -x "$GRID_CONDA" ]]; then GRID_CONDA=$GRID_REPOSITORY/.venv-miniforge/bin/conda; fi
[[ -x "$GRID_CONDA" ]] || { echo 'Set GRID_CONDA to the conda executable.' >&2; exit 2; }
[[ $(uname -s) == Linux ]] || { echo 'Run this wrapper on Dantzig/Linux.' >&2; exit 2; }
export COIN_BIN=${COIN_BIN:-$GRID_REPOSITORY/.venv-dantzig/bin}
export BAM_LICENSE_FILE=${BAM_LICENSE_FILE:-/local/scratch/a/lee4382/bamlice.txt}
export PYTHONPATH=$RUNNER PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
export PATH="$COIN_BIN:$PATH"
mode=${1:-check}
if [[ $# -gt 0 ]]; then shift; fi
cd "$RUNNER"
if [[ $mode == setup ]]; then
    if [[ ! -x "$GRID_ENV/bin/python" ]]; then
        [[ -x "$GRID_BASE_ENV/bin/python" ]] || { echo "Missing BAM base environment: $GRID_BASE_ENV" >&2; exit 2; }
        "$GRID_CONDA" create --yes --prefix "$GRID_ENV" --clone "$GRID_BASE_ENV"
    fi
    exec "$GRID_CONDA" run --no-capture-output --prefix "$GRID_ENV" python -m pip install -r requirements-grid-trace.txt
fi
[[ -x "$GRID_ENV/bin/python" ]] || { echo 'Run: bash run_grid_trace_dantzig.sh setup' >&2; exit 2; }
exec "$GRID_CONDA" run --no-capture-output --prefix "$GRID_ENV" python grid_trace_runner.py "$mode" \
    --output-root "$GRID_REPOSITORY/results/grid_dfo_trace" "$@"
