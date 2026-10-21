# Additional frozen-data comparisons on Dantzig

The [October 20 return and verified analysis](../results/review_comparison_20261020/README.md)
now contain all 3,430 slots. The original ZIP preserves the guide and code as
executed. Use the analysis-only commands in that report to inspect existing
results; the commands below launch new DFO searches when explicitly requested.

This package prepares the professor's requested comparison. It does not claim
that genetic candidate search improves RBFOpt. Existing MSRSM/solver results
remain valid historical measurements and are labelled `rbfopt_msrsm_solver`.
No original GDP/NLP, GAMS enumeration, BAM optimization, or FMQA optimization is
run by this package. Bonmin/IPOPT calls made internally by RBFOpt remain enabled.
No environment installation, license transfer, or solver upgrade is performed.

## Scope and immutable inputs

- `rbfopt_msrsm_genetic`: 1,050 Grid + 140 Process jobs.
- `uniform_without_replacement`: the same 1,190 jobs.
- `bam_predetermined_uniform`: 1,050 Grid jobs.
- Total: 3,430 new slots; 4,760 historical rows retained separately.
- Grid 21 functions, budgets 10/30/50/70/100, seeds 0–9.
- Process CSTR N/B=5/8,10/15,15/22,20/29,25/36,30/43; Column16;
  Small Batch10; Dynamic12/15/20/30/37/50, seeds 0–9.

`plan.json` is frozen before any results: ordered initial coordinates, domains,
original settings, environment requirements and pilot membership. Saved designs
are read from original execution archives, never regenerated with a newer LHC.
`evidence/source_provenance.json` identifies historical ZIPs; `inventory.json`
hashes every input/source. The historical source snapshots under `frozen/` are
byte-preserved, including their original default `solver` configuration.
The adapter supplies `genetic` explicitly and verifies the entire actual settings
dictionary differs from the recorded dictionary in that one option only.
Grid settings defaults are cross-checked against the recorded RBFOpt 4.3.0
Process defaults with the Grid budget and seed and the frozen Grid constructor.
Executable paths and SHA256, Python 3.11.16 and package versions must match.
Unknown environment changes fail preflight; do not upgrade packages to bypass it.

The final Process cost tables have 2,455 points, including structural supplements.
Original objective/status/cost fields are checked against the executed input
rows; supplements only fill logical exclusions, never overwrite an NLP attempt.
The Grid inventory has 20,181 measured points (21×961); cost/objective keys are
checked. Missing costs remain null and are reported, never filled with zero.
Targets are used only for reporting. The frozen Grid wrapper receives its
reference target for constructing its result record, never as an optimizer
setting; Process target extraction occurs after search. Neither candidate
selection nor sampling sees a target or feasible mask. Reporting tolerance is `abs(best-target)<=1e-5*max(1,abs(target))`.

## Build and upload from the Mac

```bash
python3 -m review_comparison.build --output /tmp/review_comparison_20261020.zip
scp /tmp/review_comparison_20261020.zip /tmp/review_comparison_20261020.zip.sha256 \
  lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

The ZIP contains sources, frozen inputs, plan, provenance, old results, tests
when present in the inventory, and analysis tools. It does not need Git or a
network download on the server. Do not extract over a historical experiment.

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
sha256sum -c review_comparison_20261020.zip.sha256
mkdir review_comparison_20261020
unzip -n review_comparison_20261020.zip -d review_comparison_20261020
cd review_comparison_20261020/review_comparison_runner
bash run_review_comparison_dantzig.sh plan
```

The frozen runner defaults to `.venv-dantzig-grid-trace` (Grid) and
`.venv-dantzig-nlp-overnight` (Process), but the completed October 20 run used
`.venv-dantzig/bin/python` for both. The default Grid environment had newer
pandas/Pyomo versions and failed preflight before any search. The original
`.venv-dantzig` environment passed all historical version and binary checks.
No environment was modified. Reuse the recorded routing explicitly:

```bash
REVIEW_PY=/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig/bin/python
REVIEW_ENV=(--grid-python "$REVIEW_PY" --process-python "$REVIEW_PY")
```

Existing conda executable: `/local/scratch/a/lee4382/miniconda3/bin/conda`.
Override `--grid-python`, `--process-python`, `--conda` only to select matching
existing environments, and retain these options on every launch/resume.
The old repository path on Dantzig is intentional; the GitHub repository rename
does not move server directories. Solver paths remain the original `.venv-dantzig/bin`.

## Inspect CPU availability, check, and pilot

```bash
lscpu -e=CPU,CORE,SOCKET,ONLINE
ps -eo pid,ppid,psr,pcpu,comm,args --sort=-pcpu | head -35
# Choose a CPU not occupied/reserved by another experiment; 0 below is an EXAMPLE.
CPU=0
RUN_DIR=/local/scratch/a/lee4382/repository/RBFopt_Test/results/review_comparison_$(date +%Y%m%d_%H%M%S)
bash run_review_comparison_dantzig.sh check --run-dir "$RUN_DIR" --cpu "$CPU" "${REVIEW_ENV[@]}"
# Continue only after both preflight checks pass.
nohup bash run_review_comparison_dantzig.sh pilot --run-dir "$RUN_DIR" --cpu "$CPU" \
  --ack-idle-cpu "${REVIEW_ENV[@]}" > "${RUN_DIR}_pilot.log" 2>&1 &
```

`check` verifies files, environment, binary hashes and imports, **without any
solver trial**. It writes process activity and topology records. Affinity is
not an exclusive reservation; `--ack-idle-cpu` confirms the operator checked
availability. Concurrency is deliberately one worker; numerical libraries and
solver children inherit one CPU and one-thread limits. No other process is killed
or reassigned. Separate independent scopes can be scheduled manually on verified
separate idle physical cores, with distinct output directories and no overlap.

Fixed pilot: seed0; Ackley B10, Rosenbrock B100, Column B16, CSTR30 B43,
Small Batch B10, all six Dynamic budgets. That is 24 jobs across applicable
methods (11 genetic, 11 uniform, 2 BAM-prefix controls). Pilot jobs are real
members of the full plan and are reused after checksum verification.

```bash
bash run_review_comparison_dantzig.sh status --run-dir "$RUN_DIR"
```

Status reports per-job wall times and min/max observed-pilot scenario estimates
for the priority/full scope. These are uncertain extrapolations, not time bounds.
No estimate is produced for unmeasured scope/method strata. Inspect the pilot
before issuing a full-run command. The package never automatically starts all jobs.

## Explicit priority/full run and recovery

```bash
# Headline Process conditions first (CSTR30, Column, Small Batch, all Dynamic budgets).
nohup bash run_review_comparison_dantzig.sh run --scope priority \
  --run-dir "$RUN_DIR" --cpu "$CPU" --ack-idle-cpu "${REVIEW_ENV[@]}" > "${RUN_DIR}_priority.log" 2>&1 &
# After inspecting the pilot, explicitly start the full remaining plan:
nohup bash run_review_comparison_dantzig.sh run --scope all \
  --run-dir "$RUN_DIR" --cpu "$CPU" --ack-idle-cpu "${REVIEW_ENV[@]}" > "${RUN_DIR}_full.log" 2>&1 &
# Do not run these controllers concurrently against the same RUN_DIR.
bash run_review_comparison_dantzig.sh resume --run-dir "$RUN_DIR" --cpu "$CPU" --ack-idle-cpu "${REVIEW_ENV[@]}"
```

Additional filters: `--methods rbfopt_msrsm_genetic`, `--scope grid|process|priority`,
`--cases column dynamic`, `--seeds 0 1`, `--budgets 12 15`.
Use identical routing/CPU options when resuming. `--controller-seconds 3600` stops
at the next job boundary; a job can finish after that allowance. It does not
shorten the original per-job optimizer limit. Grid has no added watchdog;
Process retains the recorded 2,100s worker watchdog. RBFOpt native limits/defaults
are unchanged. An external interrupt/watchdog leaves partial traces, not a target
miss. Completed outcomes, including execution failures, are never automatically
retried. `--retry-interrupted` explicitly starts a new attempt only for an
unsealed job; earlier partial files and total attempt time remain available.
First sealed outcome is selected, never best-of-retries. The controller and child
share a file lock to prevent duplicate launches after controller death.

## Accounting and analysis

Grid uses the frozen `EvaluationTrace` endpoint after the benchmark wrapper returns
and before trace validation/export. Process uses the frozen worker endpoint after
exception/terminal handling and before summary. CSTR failures remain +inf; other
Process RBFOpt failures remain 1e6. Budget-B terminal observations are retained
even if the original Process wrapper raises before returning them. Grid retains
native cache/stopping behavior. Repeated actual callbacks count; native cache hits
without callbacks do not. Failed seeds are never substituted.

Uniform sampling starts with the same three observations and samples the remaining
full integer domain without replacement. Its MT19937 stream has a separately
recorded SHA256-derived seed; there is no feasibility filtering or target stop.
The BAM control copies callbacks 4–13 from each original trace (budget truncated),
including repeats of earlier points, then samples unseen points uniformly.
All 1,050 traces verify the same ten-point prefix; callback14 varies. Native BAM
code is proprietary: this is an empirically verified prefix-preserving control,
not a claim of a full causal decomposition of every BAM component.

```bash
bash run_review_comparison_dantzig.sh summarize --run-dir "$RUN_DIR"
bash run_review_comparison_dantzig.sh pack --run-dir "$RUN_DIR"
```

Each analysis writes a new `analysis_<id>/`: all slots and completed rows,
ten-seed condition summaries, fixed-path alpha scenarios, paired differences,
Grid exclusions and an optional PDF if Matplotlib is installed. No installation
is attempted. The analysis works before new runs exist using historical rows,
and explicitly leaves new slots `not_run`. New-run extraction/export timings are
reported separately; old unmeasured summary costs are not assumed zero.
Process Dynamic preparation is charged once; Grid preparation is already in
point costs. Historical Grid DSDA has no separate lookup timer and retains that
limitation. Each repeat charges the same recorded point cost again.
Paired Grid bootstrap resamples whole problem vectors of ten paired seeds;
Process resamples seed pairs within condition. Incomplete condition pairs are
omitted from estimates but remain in slot counts. Bootstrap intervals with only
ten seeds can degenerate at boundaries; no 99% performance guarantee is inferred.
TTS99 is an empirical restart estimate, not a measured 99th percentile.

`pack` prints a unique `RESULT_ZIP` and SHA256 sidecar containing every attempt,
log, callback, setting, analysis, and the exact execution package. Download:

```bash
scp lee4382@dantzig.ecn.purdue.edu:/absolute/path/printed/as/RESULT_ZIP ~/Downloads/
```

See `review_comparison_status.md` for unresolved review items. No Overleaf edits
or messages to the professor are made by these commands.
