#!/usr/bin/env bash
set -Eeuo pipefail
RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
POINT_REPOSITORY=${POINT_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
POINT_ENV=${POINT_ENV:-$POINT_REPOSITORY/.venv-dantzig-nlp-overnight}
[[ $(uname -s) == Linux ]] || { echo 'Run on Dantzig/Linux.' >&2; exit 2; }
[[ -x "$POINT_ENV/bin/python" ]] || { echo "Missing original point-measurement environment: $POINT_ENV" >&2; exit 2; }
export RBFOPT_GDP_SOURCES=${RBFOPT_GDP_SOURCES:-$POINT_REPOSITORY/external}
export PYTHONPATH=$RUNNER PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 MPLBACKEND=Agg
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
export MPLCONFIGDIR=${MPLCONFIGDIR:-${TMPDIR:-/tmp}/fmqa-points-mpl-$UID}
export PYOMO_CONFIG_DIR=${PYOMO_CONFIG_DIR:-${TMPDIR:-/tmp}/fmqa-points-pyomo-$UID}
cd "$RUNNER"
mode=${1:-check}
if [[ $# -gt 0 ]]; then shift; fi
exec "$POINT_ENV/bin/python" fmqa_qhd_point_runner.py "$mode" \
  --cpu "${POINT_CPU:-6}" --output-root "$POINT_REPOSITORY/results/fmqa_qhd_points" "$@"
