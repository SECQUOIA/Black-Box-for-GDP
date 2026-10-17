#!/usr/bin/env bash
set -Eeuo pipefail
CSTR30_RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CSTR30_REPOSITORY=${CSTR30_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
CSTR30_PYTHON=${CSTR30_PYTHON:-$CSTR30_REPOSITORY/.venv-dantzig-gdp/bin/python}
export RBFOPT_GDP_SOURCES=${RBFOPT_GDP_SOURCES:-$CSTR30_REPOSITORY/external}
export PYTHONPATH=$CSTR30_RUNNER PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 MPLBACKEND=Agg
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
export MPLCONFIGDIR=${MPLCONFIGDIR:-${TMPDIR:-/tmp}/cstr30-structural-mpl-$UID}
[[ $(uname -s) == Linux ]] || { echo 'Run on Dantzig/Linux.' >&2; exit 2; }
[[ -x "$CSTR30_PYTHON" ]] || { echo "Missing original environment: $CSTR30_PYTHON" >&2; exit 2; }
cd "$CSTR30_RUNNER"
mode=${1:-check}
if [[ $# -gt 0 ]]; then shift; fi
cpu=${CSTR30_CPU:-}
run_dir=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cpu) cpu=$2; shift 2 ;;
    --run-dir) run_dir=$2; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [[ -z "$cpu" ]]; then
  cpu=$("$CSTR30_PYTHON" -c 'import os; print(min(os.sched_getaffinity(0)))')
fi
taskset -pc "$cpu" $$ >/dev/null
args=("$mode" --output-root "$CSTR30_REPOSITORY/results/cstr30_structural_rejections")
if [[ -n "$run_dir" ]]; then args+=(--run-dir "$run_dir"); fi
exec "$CSTR30_PYTHON" measure_cstr30_structural_rejections.py "${args[@]}"
