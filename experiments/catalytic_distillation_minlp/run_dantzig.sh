#!/usr/bin/env bash
# Rerun every MINLP experiment of the catalytic distillation column on Dantzig and package the results.
#
#   export GAMS_EXE=/path/to/gams     # GAMS 54 or later with CONOPT, CPLEX, DICOPT, SBB, BARON, and SCIP
#   nohup bash experiments/catalytic_distillation_minlp/run_dantzig.sh > ../catdist_minlp_dantzig.log 2>&1 &
#
# Steps, each GAMS job pinned to one core and started from init.gdx:
#   1. Preflight: GAMS version and licenses of CONOPT, CPLEX, DICOPT, SBB, BARON, SCIP, and JAMS.
#   2. Scales: compute_emp_scales.py must reproduce gdp_models/catalytic_distillation/emp_scales.gms
#      (skipped when SCALES_PYTHON, default .venv-dantzig/bin/python, has no Pyomo).
#   3. validate.sh: nine fixed configurations in the GDP, product, Big-M, and hull forms.
#   4. Certificates: the product form solved at (7,8,11,16,16,20) and at the best known design, checked
#      by the Examiner, and used as the start of SCIP and BARON on the whole MINLP (check_point.gms, 900 s).
#   5. Examiner on the CONOPT solution of the Big-M reformulation at the best known design.
#   6. run_solvers.sh: DICOPT, SBB, BARON, and SCIP on the product, Big-M, and hull forms (MINLP_RESLIM,
#      3,600 s), together with BARON and SCIP on Big-M and hull with the binaries fixed at the best
#      known design (FIXED_RESLIM, 1,200 s).
# It needs 16 idle physical cores for about 1 h 15 min; CPUS="c1 c2 ..." (16 CPUs) chooses them.
# The full output stays outside the checkout (MINLP_OUTPUT). results/catalytic_distillation_minlp_dantzig_<date>
# (MINLP_DEST) receives the files of results/catalytic_distillation_minlp_20261101, a comparison with
# them, and a zip of the full output with its SHA-256.
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPOSITORY=$(cd -- "$HERE/../.." && pwd)
cd "$REPOSITORY"
: "${GAMS_EXE:?Set GAMS_EXE to the GAMS executable (GAMS 54 or later)}"
[[ -x $GAMS_EXE ]] || { echo "GAMS_EXE is not executable: $GAMS_EXE" >&2; exit 1; }
M=$REPOSITORY/gdp_models/catalytic_distillation
MINLP_RESLIM=${MINLP_RESLIM:-3600}
FIXED_RESLIM=${FIXED_RESLIM:-1200}
STAMP=$(date -u +%Y%m%d_%H%M%S)
OUTPUT=${MINLP_OUTPUT:-$(dirname -- "$REPOSITORY")/catdist_minlp_dantzig_$STAMP}
DEST=${MINLP_DEST:-$REPOSITORY/results/catalytic_distillation_minlp_dantzig_$(date -u +%Y%m%d)}
REFERENCE=$REPOSITORY/results/catalytic_distillation_minlp_20261101
BEST=(--f1=8 --c1=8 --c2=12 --c3=17 --f2=17 --b=21)
mkdir -p "$OUTPUT"
export OMP_NUM_THREADS=1

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
    sys.exit(f"Only {len(free)} idle physical cores observed; set CPUS")
print(" ".join(map(str, free[-needed:])))
PY
}

read -r -a C <<< "${CPUS:-$(idle_cpus 16)}"
(( ${#C[@]} >= 16 )) || { echo "Need 16 CPUs, got: ${C[*]}" >&2; exit 1; }
gams() { local cpu=$1; shift; taskset -c "$cpu" "$GAMS_EXE" "$@" lo=2; }
log() { echo "[$(date -u +%H:%M:%S)] $*"; }

log "HEAD $(git rev-parse HEAD); output $OUTPUT; CPUs ${C[*]}"
{
    echo "head=$(git rev-parse HEAD)"
    echo "host=$(hostname)"
    echo "cpu_model=$(lscpu | sed -n 's/^Model name: *//p' | head -1)"
    echo "cpus=${C[*]}"
    echo "gams_exe=$GAMS_EXE"
    echo "minlp_reslim=$MINLP_RESLIM fixed_reslim=$FIXED_RESLIM"
    echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$OUTPUT/environment.txt"

# 1. Preflight.
log "preflight"
mkdir -p "$OUTPUT/preflight"
cat > "$OUTPUT/preflight/tiny.gms" <<'EOF'
binary variable y; positive variable x; variable z;
x.up = 2;
equations e1, e2;
e1.. z =e= sqr(x - 1.5) + y;
e2.. x =l= 1 + y;
model m /all/;
option nlp = conopt, mip = cplex, minlp = %solver%, threads = 1;
solve m using minlp minimizing z;
file r / '%out%' /;
put r "solver=%solver% modelstat=" m.modelstat:0:0 " solvestat=" m.solvestat:0:0 " z=" z.l:0:6 /;
putclose r;
EOF
for solver in dicopt sbb baron scip; do
    (cd "$OUTPUT/preflight" && gams "${C[0]}" tiny.gms --solver=$solver --out="$OUTPUT/preflight/$solver.txt" > /dev/null 2>&1 || true)
    line=$(cat "$OUTPUT/preflight/$solver.txt" 2>/dev/null || echo "solver=$solver no result")
    echo "$line"
    [[ $line =~ modelstat=(1|2|8)\ solvestat=1 ]] || { echo "PREFLIGHT FAILED for $solver; see $OUTPUT/preflight" >&2; exit 1; }
done
grep -h -o -m1 'GAMS [0-9.]*  *[0-9a-f]*' "$OUTPUT/preflight/tiny.lst" | head -1 | sed 's/^/gams_version=/' | tee -a "$OUTPUT/environment.txt"
mkdir -p "$OUTPUT/preflight/emp"
(cd "$OUTPUT/preflight/emp" && gams "${C[0]}" "$M/solve_emp.gms" --model="$M/emp_model_corrected.gms" --init="$M/init" \
    --reform=bigm --solver=sbb --reslim=600 "${BEST[@]}" --out="$OUTPUT/preflight/emp/result.txt" > /dev/null 2>&1 || true)
cat "$OUTPUT/preflight/emp/result.txt"
grep -q 'modelstat=2 solvestat=1 zobj=24895.55' "$OUTPUT/preflight/emp/result.txt" \
    || { echo "PREFLIGHT FAILED: JAMS Big-M does not reproduce 24895.55 at the best design" >&2; exit 1; }

# 2. Scales.
SCALES_PYTHON=${SCALES_PYTHON:-$REPOSITORY/.venv-dantzig/bin/python}
if [[ -x $SCALES_PYTHON ]] && "$SCALES_PYTHON" -c "import pyomo" 2> /dev/null; then
    log "scales"
    GAMS_EXE=$GAMS_EXE taskset -c "${C[0]}" "$SCALES_PYTHON" "$HERE/compute_emp_scales.py" "$OUTPUT/emp_scales.gms" \
        > "$OUTPUT/emp_scales.log" 2>&1 || true
    if cmp -s "$OUTPUT/emp_scales.gms" "$M/emp_scales.gms"; then
        echo "scales=reproduced" | tee -a "$OUTPUT/environment.txt"
    else
        echo "scales=DIFFERENT (see $OUTPUT/emp_scales.log)" | tee -a "$OUTPUT/environment.txt"
    fi
else
    echo "scales=skipped (no Pyomo in $SCALES_PYTHON)" | tee -a "$OUTPUT/environment.txt"
fi

# 3. Fixed-configuration validation.
log "validation"
GAMS_EXE=$GAMS_EXE taskset -c "$(IFS=,; echo "${C[*]:0:8}")" bash "$HERE/validate.sh" "$OUTPUT/validation" 8 > /dev/null

# 4. Certificates and 5. Examiner on the Big-M reformulation.
log "certificates and Examiner"
certificate() {
    local name=$1 cpu=$2; shift 2
    local d=$OUTPUT/certificates/$name
    mkdir -p "$d/point"
    (cd "$d/point" && gams "$cpu" "$M/solve_minlp.gms" --model="$M/minlp_model_corrected.gms" --init="$M/init" "$@" \
        --out="$d/point/result.txt" --gdx="$d/point/point.gdx" > /dev/null 2>&1 || true)
    for mode in examine scip_free baron_free; do
        mkdir -p "$d/$mode"
        (cd "$d/$mode" && gams "$cpu" "$HERE/check_point.gms" --model="$M/minlp_model_corrected.gms" \
            --point="$d/point/point" --mode=$mode > /dev/null 2>&1 || true)
    done
}
examine_bigm() {
    local cpu=$1 d=$OUTPUT/examine_bigm_fixed_best
    mkdir -p "$d/sol" "$d/ex"
    (cd "$d/sol" && gams "$cpu" "$M/solve_emp.gms" --model="$M/emp_model_corrected.gms" --init="$M/init" --reform=bigm \
        --solver=sbb "${BEST[@]}" --out="$d/sol/emp_result.txt" --gdx="$d/sol/sol.gdx" > /dev/null 2>&1 || true)
    printf 'examineInitPoint 1\nexamineSolvPoint 0\nsubsolver none\n' > "$d/ex/examiner.opt"
    (cd "$d/ex" && taskset -c "$cpu" "$GAMS_EXE" "$M/solve_emp.gms" --model="$M/emp_model_corrected.gms" --init="$d/sol/sol" \
        --reform=bigm --solver=examiner --subopt=1 "${BEST[@]}" --out="$d/ex/emp_result.txt" lo=3 > "$d/ex/log.txt" 2>&1 || true)
}
certificate 7_8_11_16_16_20 "${C[0]}" --f1=7 --c1=8 --c2=11 --c3=16 --f2=16 --b=20 &
certificate 8_8_12_17_17_21 "${C[1]}" "${BEST[@]}" &
examine_bigm "${C[2]}" &
wait

# 6. MINLP solvers, and BARON and SCIP with the binaries fixed at the best known design.
log "MINLP solvers (${MINLP_RESLIM} s) and fixed-design runs (${FIXED_RESLIM} s)"
i=0
for form in product bigm chull; do
    CPUS="${C[*]:$i:4}" GAMS_EXE=$GAMS_EXE bash "$HERE/run_solvers.sh" "$form" "$OUTPUT/$form" "$MINLP_RESLIM" \
        dicopt sbb baron scip > "$OUTPUT/$form.txt" 2>&1 &
    i=$((i + 4))
done
for reform in bigm chull; do
    for solver in baron scip; do
        d=$OUTPUT/fixed_best/$reform/$solver
        mkdir -p "$d"
        (cd "$d" && setsid taskset -c "${C[$i]}" timeout --kill-after=60 $((FIXED_RESLIM + 600)) "$GAMS_EXE" "$M/solve_emp.gms" \
            --model="$M/emp_model_corrected.gms" --init="$M/init" --reform=$reform --solver=$solver --reslim="$FIXED_RESLIM" \
            "${BEST[@]}" --out="$d/result.txt" lo=3 > "$d/gams.log" 2>&1 || true) &
        i=$((i + 1))
    done
done
wait
echo "finished_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT/environment.txt"

# Package the files of results/catalytic_distillation_minlp_20261101.
log "packaging $DEST"
mkdir -p "$DEST/validation" "$DEST/evidence"
cp "$OUTPUT/validation/validation.csv" "$DEST/validation/"
cp "$OUTPUT/environment.txt" "$DEST/"
for form in product bigm chull; do
    for solver in dicopt sbb baron scip; do
        mkdir -p "$DEST/$form/$solver"
        cp "$OUTPUT/$form/$solver/"{result.txt,wall.txt,gams.log} "$DEST/$form/$solver/" 2> /dev/null || true
    done
done
gzip -9 -c "$OUTPUT/bigm/baron/reformulated_bigm.gms" > "$DEST/bigm/reformulated_bigm.gms.gz" || true
gzip -9 -c "$OUTPUT/chull/baron/reformulated_chull.gms" > "$DEST/chull/reformulated_chull.gms.gz" || true
for reform in bigm chull; do
    for solver in baron scip; do
        mkdir -p "$DEST/fixed_best/$reform/$solver"
        cp "$OUTPUT/fixed_best/$reform/$solver/"{result.txt,gams.log} "$DEST/fixed_best/$reform/$solver/" 2> /dev/null || true
    done
done
mkdir -p "$DEST/examine_bigm_fixed_best"
cp "$OUTPUT/examine_bigm_fixed_best/ex/log.txt" "$DEST/examine_bigm_fixed_best/log.txt" || true
cp "$OUTPUT/examine_bigm_fixed_best/sol/emp_result.txt" "$DEST/examine_bigm_fixed_best/conopt_result.txt" || true
for name in 7_8_11_16_16_20 8_8_12_17_17_21; do
    mkdir -p "$DEST/certificates/$name/point"
    cp "$OUTPUT/certificates/$name/point/result.txt" "$DEST/certificates/$name/point/" || true
    for mode in examine scip_free baron_free; do
        mkdir -p "$DEST/certificates/$name/$mode"
        cp "$OUTPUT/certificates/$name/$mode/check_point.log" "$DEST/certificates/$name/$mode/" || true
        gzip -9 -c "$OUTPUT/certificates/$name/$mode/check_point.lst" > "$DEST/certificates/$name/$mode/check_point.lst.gz" || true
    done
done
python3 "$HERE/summarize.py" "$DEST" > /dev/null
python3 - "$DEST" "$REFERENCE" <<'PY' | tee "$DEST/comparison.txt"
"""Compare this rerun with the workstation runs of results/catalytic_distillation_minlp_20261101."""
import csv, sys
from pathlib import Path

dest, ref = Path(sys.argv[1]), Path(sys.argv[2])
key = lambda r: (r["form"], r["f1"], r["c1"], r["c2"], r["c3"], r["f2"], r["b"])
new = {key(r): r for r in csv.DictReader((dest / "validation/validation.csv").open())}
old = {key(r): r for r in csv.DictReader((ref / "validation/validation.csv").open())}
print("Validation (form, configuration: modelstat zobj here | workstation)")
ok = True
for k in sorted(new):
    n, o = new[k], old.get(k, {})
    print(f"  {k[0]:8s} {','.join(k[1:]):18s} {n['modelstat']:>2s} {n['zobj']:>18s} | {o.get('modelstat', '-'):>2s} {o.get('zobj', '-'):>18s}")
gdp = {k[1:]: r for k, r in new.items() if k[0] == "gdp"}
for k, r in new.items():
    if k[0] in ("bigm", "chull") and gdp[k[1:]]["modelstat"] == "2":
        if r["modelstat"] != "2" or abs(float(r["zobj"]) - float(gdp[k[1:]]["zobj"])) > 1e-5 * float(gdp[k[1:]]["zobj"]):
            ok = False
            print(f"  CHECK: {k[0]} differs from the GDP form at {k[1:]}")
print("Big-M and hull reproduce the GDP form at every feasible configuration:", ok)
print("Solvers (form, solver: modelstat zobj wall_s here | workstation)")
old = {(r["form"], r["solver"]): r for r in csv.DictReader((ref / "summary.csv").open())}
for r in csv.DictReader((dest / "summary.csv").open()):
    o = old.get((r["form"], r["solver"]), {})
    print(f"  {r['form']:8s} {r['solver']:7s} {r['modelstat']:>2s} {r['zobj']:>18s} {r['wall_s']:>8s} | "
          f"{o.get('modelstat', '-'):>2s} {o.get('zobj', '-'):>18s} {o.get('wall_s', '-'):>8s}")
PY
ARCHIVE=$DEST/evidence/$(basename -- "$OUTPUT").zip
(cd "$(dirname -- "$OUTPUT")" && zip -q -r -9 "$ARCHIVE" "$(basename -- "$OUTPUT")" -x '*.gdx' -x '*/225?/*')
(cd "$DEST/evidence" && sha256sum "$(basename -- "$ARCHIVE")" > "$(basename -- "$ARCHIVE").sha256")
log "PACKAGED $DEST ($(du -sh "$DEST" | cut -f1))"
