#!/usr/bin/env bash
# D-SDA without re-evaluating explored configurations, on Dantzig: stored responses only, a few minutes.
# On success, the return is packaged in results/dsda_no_revisit_<date>/ for the commit.
set -Eeuo pipefail
REPOSITORY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$REPOSITORY"
export PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=""
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export OMP_DYNAMIC=FALSE MKL_DYNAMIC=FALSE
# The adopted D-SDA rerun used this interpreter (Python 3.11.16, numpy 2.4.6, pandas 2.3.3).
PYTHON=${DSDA_PYTHON:-$REPOSITORY/.venv-dantzig/bin/python}
test -x "$PYTHON" || { echo "Python not found: $PYTHON (set DSDA_PYTHON)" >&2; exit 1; }
STAMP=$(date -u +%Y%m%d_%H%M%S)_$$
# The unpacked runs stay outside the checkout; only the archive and summaries are committed.
OUTPUT=${DSDA_OUTPUT:-$(dirname -- "$REPOSITORY")/dsda_no_revisit_$STAMP}
echo "HEAD $(git rev-parse HEAD)"
# --cpu auto waits for an idle physical core and pins to one of its logical CPUs.
if ! "$PYTHON" experiments/dsda_no_revisit/run.py \
        --output "$OUTPUT" --cpu "${DSDA_CPU:-auto}" "$@" 2>&1 | tee "$OUTPUT.log"; then
    echo "CHECKS FAILED or the run stopped; see $OUTPUT.log and $OUTPUT/checks.csv. Nothing was packaged." >&2
    exit 1
fi
DEST=$REPOSITORY/results/dsda_no_revisit_$(date -u +%Y%m%d)
mkdir -p "$DEST/evidence"
cp "$OUTPUT.zip" "$OUTPUT.log" "$DEST/evidence/"
(cd "$DEST/evidence" && sha256sum "$(basename -- "$OUTPUT.zip")" > "$(basename -- "$OUTPUT.zip").sha256")
cp "$OUTPUT"/{runs.csv,condition_summary.csv,checks.csv,checks.json,manifest.json} "$DEST/"
echo "PACKAGED $DEST"
