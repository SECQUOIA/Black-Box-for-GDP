#!/usr/bin/env bash
set -Eeuo pipefail

# Process cases only: 139 instances x DSDA/RBFOpt/BAM 5.0.0, original starts.
# bash run_traced_cases_dantzig.sh check
# bash run_traced_cases_dantzig.sh run
# DANTZIG_TRACE_DIR=/absolute/path/to/run bash run_traced_cases_dantzig.sh resume

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-run}"
case "$MODE" in check|run|resume) ;; *) exit 2 ;; esac
[[ "$(uname -s)" == Linux ]] || { echo 'Run on Dantzig/Linux.' >&2; exit 1; }
ENV_DIR="${DANTZIG_TRACE_ENV:-$ROOT/.venv-dantzig-bam}"
PYTHON="$ENV_DIR/bin/python"
[[ -x "$PYTHON" ]] || { echo 'Set DANTZIG_TRACE_ENV to the BAM 5.0.0 environment.' >&2; exit 1; }
CONDA_CMD="${CONDA_EXE:-}"
if [[ ! -x "$CONDA_CMD" ]]; then CONDA_CMD="$(command -v conda || true)"; fi
if [[ ! -x "$CONDA_CMD" ]]; then CONDA_CMD="$ROOT/.venv-miniforge/bin/conda"; fi
[[ -x "$CONDA_CMD" ]] || { echo 'Set CONDA_EXE to conda.' >&2; exit 1; }
CONDA_BASE="$("$CONDA_CMD" info --base)"
set +u
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$ENV_DIR"
set -u

export PYTHONPATH="$ROOT" PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 MPLBACKEND=Agg
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 GOTO_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 NUMEXPR_MAX_THREADS=1 OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
export COIN_BIN="${COIN_BIN:-$ROOT/.venv-dantzig/bin}"
export BAM_LICENSE_FILE="${BAM_LICENSE_FILE:-/local/scratch/a/lee4382/bamlice.txt}"
[[ -f "$BAM_LICENSE_FILE" ]] || { echo 'BAM license file not found.' >&2; exit 1; }
[[ -x "$COIN_BIN/bonmin" && -x "$COIN_BIN/ipopt" ]] || { echo 'Set COIN_BIN to original BONMIN/IPOPT directory.' >&2; exit 1; }
REFERENCE="${DANTZIG_REFERENCE:-$ROOT/results/archives/dantzig_20260910_170759_slN8tv.zip}"
"$PYTHON" - <<'PY'
import bam
import importlib.metadata as metadata
assert metadata.version('bam-solver') == '5.0.0', 'BAM 5.0.0 required'
assert tuple(bam.Bam.get_solver_version()) >= (2026, 9, 10), 'Unexpected BAM native version'
for name, version in [('rbfopt', '4.3.0'), ('numpy', '2.4.6'), ('scipy', '1.17.1')]:
    assert metadata.version(name) == version, f'{name} differs from original environment'
print('BAM 5.0.0 and original RBFOpt/NumPy/SciPy versions verified.')
PY
"$PYTHON" "$ROOT/trace_analysis.py" --check-reference "$REFERENCE"
if [[ "$MODE" == check ]]; then exit 0; fi

RESUME_ARGS=()
if [[ "$MODE" == resume ]]; then
    : "${DANTZIG_TRACE_DIR:?Set DANTZIG_TRACE_DIR to the interrupted run directory}"
    RUN_DIR="$(cd "$DANTZIG_TRACE_DIR" && pwd)"
    RESUME_ARGS=(--resume)
else
    mkdir -p "$ROOT/results"
    RUN_DIR="$(mktemp -d "$ROOT/results/dantzig_traced_cases_$(date +%Y%m%d_%H%M%S)_XXXXXX")"
    mkdir "$RUN_DIR/source"
    cp "$ROOT/"{instrumentation,evaluation_trace,case_study_benchmark,trace_analysis}.py "$RUN_DIR/source/"
    cp "${BASH_SOURCE[0]}" "$RUN_DIR/run-script.sh"
    "$PYTHON" "$ROOT/trace_analysis.py" --check-reference "$REFERENCE" > "$RUN_DIR/reference-audit.json"
fi
mkdir -p "$RUN_DIR/work"
export MPLCONFIGDIR="$RUN_DIR/matplotlib-cache"
BENCH_CPU="${BENCH_CPU:-$("$PYTHON" -c 'import os; print(min(os.sched_getaffinity(0)))')}"
echo "Results: $RUN_DIR"
cd "$RUN_DIR/work"
taskset -c "$BENCH_CPU" "$PYTHON" "$ROOT/case_study_benchmark.py" \
    --methods dsda,rbfopt,bam --trace-evaluations --solver-dir "$COIN_BIN" \
    --output "$RUN_DIR/process_case_studies.csv" --max-run-seconds 1800 \
    --verbose "${RESUME_ARGS[@]}" 2>&1 | tee -a "$RUN_DIR/run.log"
"$PYTHON" "$ROOT/trace_analysis.py" "$RUN_DIR/process_case_studies.csv" \
    --output "$RUN_DIR/trace_analysis"
echo "Finished: $RUN_DIR"
