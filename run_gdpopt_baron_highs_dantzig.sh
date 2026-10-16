#!/usr/bin/env bash
# Existing nine GDP models, RIC/GLOA, GAMS BARON NLP + HiGHS MILP.
set -euo pipefail

RUNNER_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -d "$RUNNER_DIR/external" ]]; then
    DEFAULT_REPOSITORY=$RUNNER_DIR
else
    DEFAULT_REPOSITORY=/local/scratch/a/lee4382/repository/RBFopt_Test
fi
GDP_REPOSITORY=${GDP_REPOSITORY:-$DEFAULT_REPOSITORY}
GDP_PYTHON=${GDP_PYTHON:-$GDP_REPOSITORY/.venv-dantzig-gdp/bin/python}
export GAMS_BIN=${GAMS_BIN:-/package/gams/52.2/gams}
export GDP_GAMS_VERSION=${GDP_GAMS_VERSION:-52.2}
export RBFOPT_GDP_SOURCES=${RBFOPT_GDP_SOURCES:-$GDP_REPOSITORY/external}
export PYOMO_CONFIG_DIR=${PYOMO_CONFIG_DIR:-$GDP_REPOSITORY/.pyomo-gdp-comparison}

mode=${1:-run}
if [[ $# -gt 0 ]]; then shift; fi
if [[ "$mode" == setup ]]; then
    if [[ ! -x "$GDP_PYTHON" ]]; then
        python3 -m venv "$GDP_REPOSITORY/.venv-dantzig-gdp"
    fi
    "$GDP_PYTHON" -m pip install -r "$RUNNER_DIR/requirements-gdp-comparison.txt"
    exec "$GDP_PYTHON" "$RUNNER_DIR/gdp_compare.py" setup "$@"
fi
if [[ ! -x "$GDP_PYTHON" ]]; then
    echo "Missing Python: $GDP_PYTHON. Run: bash $0 setup" >&2
    exit 2
fi

exec "$GDP_PYTHON" "$RUNNER_DIR/gdp_compare.py" "$mode" \
    --cases cstr,column,dynamic,small_batch --cstr-sizes 5,10,15,20,25,30 \
    --methods ric,gloa --nlp-solver baron --mip-solver highs --baron-lp-solver clp \
    --time-limit 1800 --cpu "${GDP_CPU:-2}" \
    --output-root "$GDP_REPOSITORY/results/gdpopt_baron_highs" "$@"
