#!/usr/bin/env bash
# Sequential follow-up: missing RIC/GLOA six jobs, then LOA nine jobs.
set -euo pipefail
RUNNER_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -d "$RUNNER_DIR/external" ]]; then
    DEFAULT_REPOSITORY=$RUNNER_DIR
else
    DEFAULT_REPOSITORY=/local/scratch/a/lee4382/repository/RBFopt_Test
fi
export GDP_REPOSITORY=${GDP_REPOSITORY:-$DEFAULT_REPOSITORY}
export GDP_PYTHON=${GDP_PYTHON:-$GDP_REPOSITORY/.venv-dantzig-gdp/bin/python}
export GDP_CPU=${GDP_CPU:-2}
mode=${1:-run}
if [[ $# -gt 0 ]]; then shift; fi
case "$mode" in run|check) ;; *) echo 'Usage: bash run_gdpopt_followup_dantzig.sh [run|check]' >&2; exit 2 ;; esac
[[ -x "$GDP_PYTHON" ]] || { echo "Missing Python: $GDP_PYTHON" >&2; exit 2; }

# The supplied archive was copied while Column RIC was running. Do not start
# another benchmark on the same physical core if that process is still alive.
if [[ "$mode" == run && "$(uname -s)" == Linux ]]; then
    "$GDP_PYTHON" - "$GDP_CPU" <<'PY'
import os
from pathlib import Path
import sys
cpu = int(sys.argv[1])
siblings = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list")
reserved = {cpu}
if siblings.exists():
    for part in siblings.read_text().strip().split(','):
        ends = [int(x) for x in part.split('-')]
        reserved.update(range(ends[0], ends[-1] + 1))
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        if proc.stat().st_uid != os.getuid():
            continue
        args = (proc / 'cmdline').read_bytes().decode().split('\0')
        is_run = any(Path(arg).name == 'gdp_compare.py' and args[i + 1:i + 2] == ['run']
                     for i, arg in enumerate(args))
        if is_run and reserved.intersection(os.sched_getaffinity(int(proc.name))):
            raise SystemExit(f'Not started: GDP job PID {proc.name} is still on CPU {cpu} or its sibling. '
                             'Wait for it to finish and check its final results before restarting the missing jobs.')
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        continue
PY
fi

echo 'Phase 1/2: Column, Dynamic, Small Batch x RIC/GLOA = 6 jobs'
bash "$RUNNER_DIR/run_gdpopt_baron_highs_dantzig.sh" "$mode" \
    --cases column,dynamic,small_batch --methods ric,gloa \
    --output-root "$GDP_REPOSITORY/results/gdpopt_followup" "$@"
echo 'Phase 2/2: all nine models x LOA = 9 jobs'
bash "$RUNNER_DIR/run_gdpopt_loa_baron_highs_dantzig.sh" "$mode" \
    --output-root "$GDP_REPOSITORY/results/gdpopt_followup" "$@"
echo 'FOLLOWUP_FINISHED: see both RESULT_ZIP paths above.'
