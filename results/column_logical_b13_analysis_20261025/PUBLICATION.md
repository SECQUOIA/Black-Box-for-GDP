# Repository publication of the Column B13 follow-up

This publication preserves the completed Column B13 analysis and the exact v3 execution package.
The detailed result is in [README.md](README.md), with all fifty paired outcomes in [paired_runs.csv](final_comparison/paired_runs.csv).
Target hits change from 14/50 to 15/50, with no original process NLP calls during the follow-up.
The domain, budget and initial designs change together, so these results do not isolate a causal budget effect.
The original analysis, launch-package manifests and their historical statements about no commit or push are preserved unchanged as records of their preparation stages.
The user subsequently authorized publication and removal of redundant local Changes on October 25, 2026.
No manuscript or representative figure is updated by this publication.
PR 49 is already merged, so new commits on review/cstr15-dantzig-results are branch follow-ups and do not automatically enter main.

The committed return ZIP retains every original log, callback, input, solver journal and runtime record.
The v3 delivery ZIP retains every execution source, frozen optimizer and input record.
Expanded copies are excluded from Git because their exact bytes are already in those ZIPs.
The retained v1 and v2 ZIPs document the earlier launch checks without adding their obsolete expanded directories.
Editable copies of the v3 preparation sources are available under experiments/column_logical_b13.
The original source revision and package hashes remain those recorded at execution time.

## Replay from a clean checkout

Run the following commands from the repository root with an existing Python environment containing the analysis dependencies.
The example creates fresh temporary extraction and output directories and invokes no optimization algorithm or NLP solver.
Set COLUMN_PYTHON to that environment's Python executable if python3 is not the intended interpreter.

```bash
COLUMN_PYTHON=${COLUMN_PYTHON:-python3}
COLUMN_REPLAY=$(mktemp -d "${TMPDIR:-/tmp}/column-b13-replay.XXXXXX")
COLUMN_RECORD=results/column_logical_b13_analysis_20261025
COLUMN_DELIVERY=results/runners/column_logical_b13_20261025_v3
"$COLUMN_PYTHON" -m zipfile -e "$COLUMN_RECORD/source/column_logical_b13_20261025_193902_31iulfak_snapshot_1792957295361892009.zip" "$COLUMN_REPLAY/run"
"$COLUMN_PYTHON" -m zipfile -e "$COLUMN_DELIVERY/column_logical_b13_dantzig_20261025_v3.zip" "$COLUMN_REPLAY/package"
COLUMN_RUN="$COLUMN_REPLAY/run/column_logical_b13_20261025_193902_31iulfak"
COLUMN_PACKAGE="$COLUMN_REPLAY/package/column_logical_b13_dantzig_20261025_v3"
"$COLUMN_PYTHON" "$COLUMN_PACKAGE/analyze.py" --run-dir "$COLUMN_RUN" --output "$COLUMN_REPLAY/replayed"
"$COLUMN_PYTHON" "$COLUMN_RECORD/compare.py" --run "$COLUMN_RUN" --package "$COLUMN_PACKAGE" --replay "$COLUMN_REPLAY/replayed" --output "$COLUMN_REPLAY/comparison"
```

The preparation sources retain their original instructions and are not needed to repeat optimization for this analysis.
The separate workspace cleanup record maps every retired local file to exact committed bytes or a preserved ZIP member.
