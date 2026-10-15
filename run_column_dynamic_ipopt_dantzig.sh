#!/usr/bin/env bash
set -Eeuo pipefail
ENUM_RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ENUM_REPOSITORY=${ENUM_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
ENUM_PYTHON=${ENUM_PYTHON:-$ENUM_REPOSITORY/.venv-dantzig-gdp/bin/python}
export RBFOPT_GDP_SOURCES=${RBFOPT_GDP_SOURCES:-$ENUM_REPOSITORY/external}
export GAMS_BIN=${GAMS_BIN:-/package/gams/52.2/gams}
export PYTHONPATH=$ENUM_RUNNER PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 MPLBACKEND=Agg
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
export MPLCONFIGDIR=${MPLCONFIGDIR:-${TMPDIR:-/tmp}/column-dynamic-enum-mpl-$UID}
export PYOMO_CONFIG_DIR=${PYOMO_CONFIG_DIR:-${TMPDIR:-/tmp}/column-dynamic-enum-pyomo-$UID}
[[ $(uname -s) == Linux ]] || { echo 'Run this launcher on Dantzig/Linux.' >&2; exit 2; }
[[ -x "$ENUM_PYTHON" ]] || { echo "Missing original GDP environment: $ENUM_PYTHON" >&2; exit 2; }
cd "$ENUM_RUNNER"
mode=${1:-check}
if [[ $# -gt 0 ]]; then shift; fi
run_dir=''
cpu=${ENUM_CPU:-}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir) run_dir=$2; shift 2 ;;
    --cpu) cpu=$2; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [[ -z "$cpu" ]]; then
  cpu=$("$ENUM_PYTHON" -c 'import os; print(min(os.sched_getaffinity(0)))')
fi
taskset -pc "$cpu" $$ >/dev/null
case "$mode" in
  check)
    sha256sum -c RUNNER_SHA256SUMS
    "$ENUM_PYTHON" enumerate_column_ipopt.py --check
    "$ENUM_PYTHON" enumerate_dynamic_ipopt.py --check
    exit 0 ;;
  run)
    [[ -z "$run_dir" ]] || { echo 'run creates a new directory; use resume for existing results.' >&2; exit 2; }
    mkdir -p "$ENUM_REPOSITORY/results/column_dynamic_box_ipopt"
    run_dir=$(mktemp -d "$ENUM_REPOSITORY/results/column_dynamic_box_ipopt/dantzig_column_dynamic_ipopt_$(date -u +%Y%m%d_%H%M%S)_XXXXXX") ;;
  resume|pack)
    [[ -n "$run_dir" && -d "$run_dir" ]] || { echo '--run-dir must identify an existing result directory.' >&2; exit 2; } ;;
  *) echo 'Usage: bash run_column_dynamic_ipopt_dantzig.sh check|run|resume|pack [--run-dir PATH] [--cpu N]' >&2; exit 2 ;;
esac
if [[ "$mode" == pack ]]; then
  exec "$ENUM_PYTHON" -c 'import sys; from enumerate_process_ipopt import pack_run; pack_run(sys.argv[1])' "$run_dir"
fi
"$ENUM_PYTHON" -c 'import sys; from enumerate_process_ipopt import snapshot_bundle; snapshot_bundle(sys.argv[1])' "$run_dir"
echo "RESULT_DIR=$run_dir"
trap '"$ENUM_PYTHON" -c '\''import sys; from enumerate_process_ipopt import pack_run; pack_run(sys.argv[1])'\'' "$run_dir"' EXIT
for case_name in column dynamic; do
  resume_args=()
  if [[ -f "$run_dir/$case_name/manifest.json" ]]; then resume_args=(--resume); fi
  "$ENUM_PYTHON" "enumerate_${case_name}_ipopt.py" --output-dir "$run_dir/$case_name" "${resume_args[@]}"
done
