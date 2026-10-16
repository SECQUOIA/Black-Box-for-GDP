#!/usr/bin/env bash
set -Eeuo pipefail
GRID_RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
GRID_GDP_REPOSITORY=${GRID_GDP_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
GRID_GDP_PYTHON=${GRID_GDP_PYTHON:-$GRID_GDP_REPOSITORY/.venv-dantzig-gdp/bin/python}
export GAMS_BIN=${GAMS_BIN:-/package/gams/52.2/gams}
export GDP_GAMS_VERSION=${GDP_GAMS_VERSION:-52.2}
export PYOMO_CONFIG_DIR=${PYOMO_CONFIG_DIR:-$GRID_GDP_REPOSITORY/.pyomo-gdp-comparison}
export PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
mode=${1:-check}
if [[ $# -gt 0 ]]; then shift; fi
if [[ $mode == setup ]]; then
    [[ -x "$GRID_GDP_PYTHON" ]] || { echo 'Set GRID_GDP_PYTHON to the existing GDP environment.' >&2; exit 2; }
    "$GRID_GDP_PYTHON" -m pip install -r "$GRID_RUNNER/requirements-gdp-comparison.txt"
fi
[[ -x "$GRID_GDP_PYTHON" ]] || { echo "Missing GDP Python: $GRID_GDP_PYTHON" >&2; exit 2; }
cd "$GRID_RUNNER"
exec "$GRID_GDP_PYTHON" grid_gdp_benchmark.py "$mode" \
    --cpu "${GRID_GDP_CPU:-6}" --output-root "$GRID_GDP_REPOSITORY/results/grid_gdp_benchmark" "$@"
