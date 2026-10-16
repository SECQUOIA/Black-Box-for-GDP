#!/usr/bin/env bash
set -Eeuo pipefail
RUNNER=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROCESS_REPOSITORY=${PROCESS_REPOSITORY:-/local/scratch/a/lee4382/repository/RBFopt_Test}
mode=${1:-check}
if [[ $# -gt 0 ]]; then shift; fi
exec bash "$RUNNER/run_process_followup_dantzig.sh" "$mode" \
    --experiment small_batch_full_domain \
    --output-root "$PROCESS_REPOSITORY/results/small_batch_full_domain" "$@"
