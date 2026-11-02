#!/usr/bin/env bash
# Live DFO runs on the corrected catalytic distillation column (see README.md).
#   GAMS_EXE=/path/to/gams bash experiments/catalytic_distillation_live/run_dantzig.sh test      preflight, about 2 min
#   GAMS_EXE=/path/to/gams bash experiments/catalytic_distillation_live/run_dantzig.sh run       start or resume the 210 runs
#   bash experiments/catalytic_distillation_live/run_dantzig.sh status                            progress
#   bash experiments/catalytic_distillation_live/run_dantzig.sh collect                           summary and one zip to send back
# By default the runs use one logical CPU on each of CATDIST_WORKERS (16) idle physical cores;
# set CPUS="c1 c2 ..." (or a range such as 0-15) to choose them.
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPOSITORY=$(cd -- "$HERE/../.." && pwd)
DFO_PYTHON=${DFO_PYTHON:-$REPOSITORY/.venv-dantzig-nlp-overnight/bin/python}
FMQA_PYTHON=${FMQA_PYTHON:-$REPOSITORY/.venv-dantzig-fmqa-qhd/bin/python}
MIDFO_PYTHON=${MIDFO_PYTHON:-$REPOSITORY/.venv-mi-dfo/bin/python}
COIN_BIN=${COIN_BIN:-$REPOSITORY/.venv-dantzig/bin}
BAM_LICENSE_FILE=${BAM_LICENSE_FILE:-/local/scratch/a/lee4382/bamlice.txt}
OUTPUT=${CATDIST_OUTPUT:-$REPOSITORY/results/catalytic_distillation_live}
WORKERS=${CATDIST_WORKERS:-16}
export PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES="" MPLBACKEND=Agg
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
cd "$HERE"

need_gams() {
    : "${GAMS_EXE:?Set GAMS_EXE to the GAMS executable (GAMS 54 or later with CONOPT)}"
    [[ -x $GAMS_EXE ]] || { echo "GAMS_EXE is not executable: $GAMS_EXE" >&2; exit 1; }
}

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
    sys.exit(f"Only {len(free)} idle physical cores observed; set CPUS or CATDIST_WORKERS")
print(",".join(map(str, free[-needed:])))
PY
}

mode=${1:-run}
case $mode in
    test)
        need_gams
        "$DFO_PYTHON" -c "import rbfopt, bam, numpy, pandas"
        "$FMQA_PYTHON" -c "import torch, dimod, numpy"
        "$MIDFO_PYTHON" -c "import PyNomad, soogo"
        [[ -s $BAM_LICENSE_FILE ]] || { echo "BAM license not found: $BAM_LICENSE_FILE" >&2; exit 1; }
        [[ -x $COIN_BIN/bonmin && -x $COIN_BIN/ipopt ]] || { echo "Bonmin or IPOPT not found in $COIN_BIN" >&2; exit 1; }
        GAMS_EXE=$GAMS_EXE "$DFO_PYTHON" -m pytest -q "$REPOSITORY/tests/test_catalytic_distillation_live.py"
        "$MIDFO_PYTHON" -m pytest -q "$REPOSITORY/tests/test_catalytic_distillation_live.py" -k adapters
        BAM_LICENSE_FILE=$BAM_LICENSE_FILE "$DFO_PYTHON" -m pytest -q "$REPOSITORY/tests/test_catalytic_distillation_live.py" -k "surrogate and bam"
        "$FMQA_PYTHON" -m pytest -q "$REPOSITORY/tests/test_catalytic_distillation_live.py" -k "surrogate and fmqa"
        echo "Preflight passed." ;;
    plan)
        "$DFO_PYTHON" run.py plan --output "$OUTPUT" ;;
    run)
        need_gams
        [[ -f $OUTPUT/plan.json ]] || "$DFO_PYTHON" run.py plan --output "$OUTPUT"
        cpus=${CPUS:-$(idle_cpus "$WORKERS")}
        cpus=${cpus// /,}
        echo "HEAD $(git rev-parse --short HEAD); CPUs $cpus"
        nohup "$DFO_PYTHON" run.py run --output "$OUTPUT" --gams "$GAMS_EXE" --cpus "$cpus" \
            --python-default "$DFO_PYTHON" --python-bam "$DFO_PYTHON" --python-fmqa "$FMQA_PYTHON" \
            --python-midfo "$MIDFO_PYTHON" --bonmin "$COIN_BIN/bonmin" --ipopt "$COIN_BIN/ipopt" \
            --bam-license "$BAM_LICENSE_FILE" "${@:2}" >> "$OUTPUT/controller.log" 2>&1 &
        echo "Controller PID $!; log $OUTPUT/controller.log"
        echo "Check progress with: bash experiments/catalytic_distillation_live/run_dantzig.sh status" ;;
    status)
        total=$(python3 -c "import json; print(len(json.load(open('$OUTPUT/plan.json'))['jobs']))")
        done=$(find "$OUTPUT/runs" -name result.json 2>/dev/null | wc -l)
        echo "$done of $total runs finished"
        tail -n 3 "$OUTPUT/controller.log" 2>/dev/null || true ;;
    collect)
        "$DFO_PYTHON" run.py summarize --output "$OUTPUT" \
            --reference "$REPOSITORY/results/catalytic_distillation_pilot_20261030/final_pilot_200_conopt/solves.csv"
        archive="$(dirname -- "$OUTPUT")/catalytic_distillation_live_$(hostname -s)_$(date -u +%Y%m%d_%H%M%S).zip"
        (cd "$(dirname -- "$OUTPUT")" && python3 -m zipfile -c "$archive" "$(basename -- "$OUTPUT")")
        echo "Please send back: $archive" ;;
    *)
        echo "Unknown mode $mode; use test, plan, run, status, or collect" >&2; exit 2 ;;
esac
