#!/usr/bin/env bash
set -Eeuo pipefail
RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPOSITORY=${CSTR15_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
PYTHON=${CSTR15_PYTHON:-$REPOSITORY/.venv-dantzig-gdp/bin/python}
GAMS=${CSTR15_GAMS:-/package/gams/52.2/gams}
LEDGER=$REPOSITORY/results/cstr15-w03-gams52-20261021-one-call.json
export PYTHONPATH="$RUNNER" RBFOPT_DIAGNOSTICS_REPO="$RUNNER" RBFOPT_GDP_SOURCES="$RUNNER/external"
export PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
export MPLCONFIGDIR=${TMPDIR:-/tmp}/cstr15-gams-mpl-$UID
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 GOTO_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 NUMEXPR_MAX_THREADS=1 OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
mode=${1:-}
if [[ $# -gt 0 ]]; then shift; fi
run_dir=''
cpu=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir) run_dir=$2; shift 2 ;;
    --cpu) cpu=$2; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -x "$PYTHON" ]] || { echo "Missing existing Python: $PYTHON; no installation or fallback is performed." >&2; exit 2; }
cd "$RUNNER"
sha256sum --status -c RUNNER_SHA256SUMS
if [[ "$mode" == pack ]]; then
  [[ -n "$run_dir" ]] || { echo '--run-dir is required.' >&2; exit 2; }
  exec "$PYTHON" -m review_diagnostics.cstr15_gams pack --directory "$run_dir"
fi
[[ $(uname -s) == Linux && -n "$cpu" ]] || { echo 'Run on Dantzig/Linux and specify an idle --cpu N.' >&2; exit 2; }
taskset -pc "$cpu" $$ >/dev/null
mkdir -p "$REPOSITORY/results"
if [[ "$mode" == all || "$mode" == prepare ]]; then
  if [[ -z "$run_dir" ]]; then
    run_dir=$REPOSITORY/results/review_cstr15_dantzig_$(date -u +%Y%m%d_%H%M%S)_${RANDOM}
  fi
  [[ ! -e "$run_dir" ]] || { echo 'Prepare requires a new output directory.' >&2; exit 2; }
  echo "RESULT_DIR=$run_dir"
  trap 'code=$?; if [[ -d "$run_dir" ]]; then "$PYTHON" -m review_diagnostics.cstr15_gams pack --directory "$run_dir"; fi; exit "$code"' EXIT
  "$PYTHON" -m review_diagnostics.cstr15_gams prepare --directory "$run_dir" --gams "$GAMS" --allocation-ledger "$LEDGER"
  if [[ "$mode" == prepare ]]; then exit 0; fi
fi
[[ -n "$run_dir" && -d "$run_dir" ]] || { echo 'An existing --run-dir is required for run/verify.' >&2; exit 2; }
case "$mode" in
  all|run)
    trap 'code=$?; "$PYTHON" -m review_diagnostics.cstr15_gams pack --directory "$run_dir"; exit "$code"' EXIT
    "$PYTHON" -m review_diagnostics.cstr15_gams run --directory "$run_dir"
    "$PYTHON" -m review_diagnostics.cstr15_gams verify --directory "$run_dir" --output "${run_dir}/verification_$(date +%s).json" ;;
  verify)
    "$PYTHON" -m review_diagnostics.cstr15_gams verify --directory "$run_dir" --output "${run_dir}/verification_$(date +%s).json" ;;
  *) echo 'Usage: bash run_cstr15_dantzig_check.sh all|prepare|run|verify|pack [--run-dir PATH] --cpu ID' >&2; exit 2 ;;
esac
