#!/usr/bin/env bash
set -Eeuo pipefail
RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
NLP_REPOSITORY=${NLP_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
NLP_ENV=${NLP_ENV:-$NLP_REPOSITORY/.venv-dantzig-nlp-overnight}
NLP_BASE_ENV=${NLP_BASE_ENV:-$NLP_REPOSITORY/.venv-dantzig-bam}
NLP_CONDA=${NLP_CONDA:-${CONDA_EXE:-}}
if [[ ! -x "$NLP_CONDA" ]]; then NLP_CONDA=$(command -v conda || true); fi
if [[ ! -x "$NLP_CONDA" ]]; then NLP_CONDA=$NLP_REPOSITORY/.venv-miniforge/bin/conda; fi
[[ -x "$NLP_CONDA" ]] || { echo 'Set NLP_CONDA to the conda executable.' >&2; exit 2; }
[[ $(uname -s) == Linux ]] || { echo 'Run this wrapper on Dantzig/Linux.' >&2; exit 2; }
export COIN_BIN=${COIN_BIN:-$NLP_REPOSITORY/.venv-dantzig/bin}
export GAMS_BIN=${GAMS_BIN:-/package/gams/52.2/gams}
export BAM_LICENSE_FILE=${BAM_LICENSE_FILE:-/local/scratch/a/lee4382/bamlice.txt}
export RBFOPT_GDP_SOURCES=${RBFOPT_GDP_SOURCES:-$NLP_REPOSITORY/external}
export PYTHONPATH=$RUNNER PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 MPLBACKEND=Agg
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
export MPLCONFIGDIR=${MPLCONFIGDIR:-$RUNNER/.matplotlib-cache}
export PYOMO_CONFIG_DIR=${PYOMO_CONFIG_DIR:-$RUNNER/.pyomo-config}
export PATH="$COIN_BIN:$PATH"
mode=${1:-check}
if [[ $# -gt 0 ]]; then shift; fi
cd "$RUNNER"
if [[ $mode == setup ]]; then
    if [[ ! -x "$NLP_ENV/bin/python" ]]; then
        [[ -x "$NLP_BASE_ENV/bin/python" ]] || { echo "Missing BAM base environment: $NLP_BASE_ENV" >&2; exit 2; }
        "$NLP_CONDA" create --yes --prefix "$NLP_ENV" --clone "$NLP_BASE_ENV"
    fi
    "$NLP_CONDA" run --no-capture-output --prefix "$NLP_ENV" python -m pip install -r requirements-dfo-trace-nlp.txt
    exec "$NLP_CONDA" run --no-capture-output --prefix "$NLP_ENV" python -c 'from gdp_models.dantzig import setup_sources; setup_sources()'
fi
[[ -x "$NLP_ENV/bin/python" ]] || { echo 'Run: bash run_dfo_trace_nlp_dantzig.sh setup' >&2; exit 2; }
case "$mode" in
    run|check)
        exec "$NLP_CONDA" run --no-capture-output --prefix "$NLP_ENV" python -m overnight_benchmark "$mode" \
            --cpu "${NLP_CPU:-6}" --solver "${NLP_SOLVER:-gams_ipopt}" \
            --output-root "$NLP_REPOSITORY/results/dfo_trace_nlp" "$@"
        ;;
    resume|status|pack)
        exec "$NLP_CONDA" run --no-capture-output --prefix "$NLP_ENV" python -m overnight_benchmark "$mode" "$@"
        ;;
    *) echo 'Usage: setup | check | run | resume --run-dir PATH | status --run-dir PATH | pack --run-dir PATH [--live]' >&2; exit 2 ;;
esac
