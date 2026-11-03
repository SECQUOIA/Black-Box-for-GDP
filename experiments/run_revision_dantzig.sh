#!/usr/bin/env bash
# Dantzig runs for the revision (PR #56): D-SDA restarts, then NOMAD and MISO on the stored responses.
#   bash experiments/run_revision_dantzig.sh           start: D-SDA in the foreground (about 1 min), then six background runs
#   bash experiments/run_revision_dantzig.sh status    progress of the six runs
#   bash experiments/run_revision_dantzig.sh collect   once all six have finished: one zip to send back
# By default each run gets one logical CPU of a different idle physical core; set CPUS="c1 c2 c3 c4 c5 c6" to choose.
set -Eeuo pipefail
REPOSITORY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$REPOSITORY"
OUT=${REVISION_OUTPUT:-$REPOSITORY/results/revision_dantzig}
RUNS=(
    "nomad|--methods nomad"
    "miso_process|--methods miso --scopes process"
    "miso_grid_b10_b30|--methods miso --scopes grid --budgets 10 30"
    "miso_grid_b50|--methods miso --scopes grid --budgets 50"
    "miso_grid_b70|--methods miso --scopes grid --budgets 70"
    "miso_grid_b100|--methods miso --scopes grid --budgets 100"
)

idle_cpus() {
    python3 - "$1" <<'PY'
import os, sys, time

def sample():
    out = {}
    for line in open("/proc/stat"):
        if line.startswith("cpu") and line[3].isdigit():
            fields = line.split()
            values = list(map(int, fields[1:]))
            out[int(fields[0][3:])] = (values[3] + values[4], sum(values))
    return out

before = sample()
time.sleep(5)
after = sample()
idle = {c: (after[c][0] - before[c][0]) / max(1, after[c][1] - before[c][1]) for c in after}
cores = {}
for cpu in sorted(os.sched_getaffinity(0)):
    try:
        siblings = open(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list").read().strip()
    except OSError:
        siblings = str(cpu)
    cores.setdefault(siblings, []).append(cpu)
free = sorted(min(cpus) for cpus in cores.values() if all(idle.get(c, 0) > 0.95 for c in cpus))
needed = int(sys.argv[1])
if len(free) < needed:
    sys.exit(f"Only {len(free)} idle physical cores observed; set CPUS explicitly")
print(" ".join(map(str, free[-needed:])))
PY
}

start() {
    mkdir -p "$OUT"
    if compgen -G "$OUT/*.log" > /dev/null; then
        echo "$OUT already has runs; use status or collect, or set REVISION_OUTPUT to a new folder" >&2
        exit 1
    fi
    echo "HEAD $(git rev-parse --short HEAD) on $(git branch --show-current)"
    DSDA_OUTPUT="$OUT/dsda_process_multistart" bash experiments/dsda_process_multistart/run_dantzig.sh
    read -r -a cpus <<< "${CPUS:-$(idle_cpus ${#RUNS[@]})}"
    if [[ ${#cpus[@]} -ne ${#RUNS[@]} ]]; then
        echo "Need ${#RUNS[@]} CPUs, got: ${cpus[*]}" >&2
        exit 1
    fi
    for i in "${!RUNS[@]}"; do
        name=${RUNS[$i]%%|*}
        read -r -a args <<< "${RUNS[$i]#*|}"
        echo "== $name on CPU ${cpus[$i]}"
        MIDFO_CPU=${cpus[$i]} MIDFO_OUTPUT="$OUT/$name" bash experiments/mixed_integer_dfo/run_dantzig.sh "${args[@]}"
    done
    echo "Started ${#RUNS[@]} runs on CPUs ${cpus[*]}."
    echo "Check progress with: bash experiments/run_revision_dantzig.sh status"
}

status() {
    for run in "${RUNS[@]}"; do
        name=${run%%|*}
        log="$OUT/$name.log"
        if [[ ! -f $log ]]; then
            printf '%-18s not started\n' "$name"
        elif grep -q '^RETURN_ARCHIVE' "$log"; then
            printf '%-18s finished: %s\n' "$name" "$(grep '^CHECKS' "$log" | cut -c1-60)"
        else
            printf '%-18s running: %s\n' "$name" "$(grep '^\[' "$log" | tail -1 | cut -c1-70)"
        fi
    done
}

collect() {
    local missing=0
    for run in "${RUNS[@]}"; do
        name=${run%%|*}
        grep -q '^RETURN_ARCHIVE' "$OUT/$name.log" 2>/dev/null || { echo "$name has not finished"; missing=1; }
    done
    [[ $missing -eq 0 ]] || exit 1
    archive="$(dirname -- "$OUT")/revision_dantzig_$(hostname -s)_$(date -u +%Y%m%d_%H%M%S).zip"
    (cd "$OUT" && python3 -m zipfile -c "$archive" ./*.zip ./*.log dsda_process_multistart*)
    echo "Please send back: $archive"
    echo "For example: scp $(hostname):$archive ."
}

case ${1:-start} in
    start) start ;;
    status) status ;;
    collect) collect ;;
    *) echo "Use start, status, or collect" >&2; exit 2 ;;
esac
