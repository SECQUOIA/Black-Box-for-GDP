#!/usr/bin/env bash
set -Eeuo pipefail
RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export PYTHONPATH="$RUNNER" PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE CUDA_VISIBLE_DEVICES="" MPLBACKEND=Agg
mode=${1:-plan}
if [[ $# -gt 0 ]]; then shift; fi
cd "$RUNNER"
exec python3 -m review_comparison.runner "$mode" "$@"
