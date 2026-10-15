#!/usr/bin/env bash
set -Eeuo pipefail
CSTR_RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CSTR_REPOSITORY=${CSTR_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
CSTR_PYTHON=${CSTR_PYTHON:-$CSTR_REPOSITORY/.venv-dantzig-gdp/bin/python}
[[ $(uname -s) == Linux ]] || { echo 'Run this wrapper on Dantzig/Linux.' >&2; exit 2; }
[[ -x "$CSTR_PYTHON" ]] || { echo "Set CSTR_PYTHON to the prepared GDP Python: $CSTR_PYTHON" >&2; exit 2; }
export RBFOPT_GDP_SOURCES=${RBFOPT_GDP_SOURCES:-$CSTR_REPOSITORY/external}
export GAMS_BIN=${GAMS_BIN:-/package/gams/52.2/gams}
export PYTHONPATH=$CSTR_RUNNER PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 MPLBACKEND=Agg
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
export MPLCONFIGDIR=${MPLCONFIGDIR:-${TMPDIR:-/tmp}/cstr-box-mpl-$UID}
export PYOMO_CONFIG_DIR=${PYOMO_CONFIG_DIR:-${TMPDIR:-/tmp}/cstr-box-pyomo-$UID}
cd "$CSTR_RUNNER"
mode=${1:-check}
if [[ $# -gt 0 ]]; then shift; fi
exec "$CSTR_PYTHON" cstr_box_ipopt.py "$mode" \
  --output-root "$CSTR_REPOSITORY/results/cstr_box_ipopt" "$@"
