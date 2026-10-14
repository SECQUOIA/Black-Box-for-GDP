#!/usr/bin/env bash
set -Eeuo pipefail
DSDA_RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DSDA_REPOSITORY=${DSDA_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
export DSDA_REPOSITORY
if [[ -z ${DSDA_PYTHON:-} ]]; then
    for DSDA_ENV in .venv-dantzig-nlp-overnight .venv-dantzig-grid-trace; do
        if [[ -x "$DSDA_REPOSITORY/$DSDA_ENV/bin/python" ]]; then
            DSDA_PYTHON="$DSDA_REPOSITORY/$DSDA_ENV/bin/python"
            break
        fi
    done
fi
[[ -x ${DSDA_PYTHON:-} ]] || { echo 'Set DSDA_PYTHON to the existing DFO Python (numpy 2.4.6, scipy 1.17.1; pandas version recorded).' >&2; exit 2; }
export PYTHONPATH="$DSDA_RUNNER" PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE MPLBACKEND=Agg
DSDA_MODE=${1:-run}
if [[ $# -gt 0 ]]; then shift; fi
cd "$DSDA_RUNNER"
DSDA_PREFIX=${DSDA_PYTHON%/bin/python}
DSDA_CMD=("$DSDA_PYTHON")
if [[ -d "$DSDA_PREFIX/conda-meta" ]]; then
    if [[ ! -x ${DSDA_CONDA:-} ]]; then
        # An activated conda shell exports CONDA_EXE; `conda` itself may only
        # be a shell function, unavailable in a noninteractive SSH/nohup shell.
        for DSDA_CANDIDATE in "${CONDA_EXE:-}" "$(type -P conda || true)" \
            "$DSDA_REPOSITORY/.venv-miniforge/bin/conda"; do
            if [[ -x "$DSDA_CANDIDATE" ]]; then
                DSDA_CONDA=$DSDA_CANDIDATE
                break
            fi
        done
    fi
    [[ -x ${DSDA_CONDA:-} ]] || { echo 'Existing conda environment detected; set DSDA_CONDA to its conda executable (or export CONDA_EXE from the activated shell).' >&2; exit 2; }
    DSDA_CMD=("$DSDA_CONDA" run --no-capture-output --prefix "$DSDA_PREFIX" python)
fi
# CPU 7 leaves the existing GDPopt run on CPU 6 untouched. No exclusive reservation.
exec "${DSDA_CMD[@]}" process_dsda_fairness.py "$DSDA_MODE" \
    --output-root "${DSDA_OUTPUT_ROOT:-/local/scratch/a/lee4382/dsda14}" \
    --cpu "${DSDA_CPU:-7}" "$@"
