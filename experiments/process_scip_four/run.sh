#!/usr/bin/env bash
set -Eeuo pipefail
PROCESS_SCIP_RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export GDP_SCIP_REPOSITORY=${GDP_SCIP_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
PROCESS_SCIP_PYTHON=${GDP_SCIP_PYTHON:-$GDP_SCIP_REPOSITORY/.venv-dantzig-gdp/bin/python}
export PYOMO_CONFIG_DIR=${PYOMO_CONFIG_DIR:-$GDP_SCIP_REPOSITORY/.pyomo-gdp-comparison}
export PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
[[ -x "$PROCESS_SCIP_PYTHON" ]] || { echo "Missing existing GDP Python: $PROCESS_SCIP_PYTHON" >&2; exit 2; }
cd "$PROCESS_SCIP_RUNNER"
exec "$PROCESS_SCIP_PYTHON" runner.py "${@:-run}"
