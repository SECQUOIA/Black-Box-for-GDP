#!/usr/bin/env bash
# LOA only: nine GDP instances, BARON NLP + HiGHS MILP, CPU 6 by default.
set -euo pipefail
RUNNER_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -d "$RUNNER_DIR/external" ]]; then
    DEFAULT_REPOSITORY=$RUNNER_DIR
else
    DEFAULT_REPOSITORY=/local/scratch/a/lee4382/repository/RBFopt_Test
fi
export GDP_REPOSITORY=${GDP_REPOSITORY:-$DEFAULT_REPOSITORY}
export GDP_CPU=${GDP_CPU:-6}
mode=${1:-run}
if [[ $# -gt 0 ]]; then shift; fi
if [[ ( "$mode" == run || "$mode" == check ) && "$(uname -s)" == Linux && "$GDP_CPU" != 2 ]]; then
    # The existing RIC/GLOA experiment uses CPU 2. Verify physical-core
    # separation before starting a concurrent LOA experiment.
    "${GDP_PYTHON:-$GDP_REPOSITORY/.venv-dantzig-gdp/bin/python}" \
        "$RUNNER_DIR/cpu_affinity.py" --check-pair 2 "$GDP_CPU" >&2
fi
exec bash "$RUNNER_DIR/run_gdpopt_baron_highs_dantzig.sh" "$mode" \
    --methods loa --output-root "$GDP_REPOSITORY/results/gdpopt_loa_baron_highs_cpu${GDP_CPU}" "$@"
