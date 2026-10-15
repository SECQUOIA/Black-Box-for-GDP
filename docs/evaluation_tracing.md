# Complete process-case evaluation traces

Run the existing lookup objectives with `--trace-evaluations` to retain every
integer coordinate evaluated by DSDA, RBFOpt, and BAM. The default matrix has
139 problem/seed/budget combinations and 417 runs across Column, CSTR sizes
5–30, Small Batch, and Dynamic. Grid experiments are outside this rerun.

```bash
python case_study_benchmark.py \
    --methods dsda,rbfopt,bam --trace-evaluations \
    --solver-dir "$COIN_BIN" \
    --output results/my_trace_run/process_case_studies.csv
```

The existing result CSV schema is unchanged. A sibling directory named
`process_case_studies.traces/` contains one JSONL file per completed run. The
manifest lists those files and their SHA256 hashes. Each file has:

- A header identifying the problem, method, seed, budget, and clock boundary.
- One event per actual objective callback: order, requested coordinates,
  rounded integer coordinates, initial/adaptive phase, repeat flag, raw value,
  incumbent, objective-call duration, and cumulative completion timestamp.
- A completion record that must agree with the saved CSV result and trajectory.

Nonfinite values are JSON `null` with a separate `nan`, `+inf`, or `-inf` tag.
Repeated objective calls remain in the trace. Solver-internal cache reads
without a callback are absent; `repeated_point` does not mean a cache hit.
Initialization calls count toward the evaluation budget.

The cumulative clock starts at runner entry, before setup and initial
evaluations. It includes optimizer work and tracing overhead. Its boundary is
slightly broader than the existing CSV `wall_time_s` boundary. These are
**lookup first-hit timestamps**, not GDP/NLP first-hit times. Recording a
trace does not run an NLP solver for the black-box objective.

## Interruptions and resume

Each event is flushed immediately. Interrupted attempts retain a
`*.partial.jsonl` file; a killed process can leave the last line incomplete.
Only files listed in the checkpoint manifest count as completed runs. Retried
attempts get different filenames, retaining the failed attempt for diagnosis.

```bash
python case_study_benchmark.py \
    --methods dsda,rbfopt,bam --trace-evaluations \
    --solver-dir "$COIN_BIN" \
    --output results/my_trace_run/process_case_studies.csv --resume
```

Use the same arguments, source, data, and environment. Resume checks both the
existing CSV/provenance checks and every completed trace's hash, identity,
callback count, initialization count, and incumbent trajectory. Enabling
tracing halfway through a nontraced checkpoint is rejected.

## Original Dantzig starts

```bash
python trace_analysis.py --check-reference \
    results/archives/dantzig_20260910_170759_slN8tv.zip
```

This verifies all 89 distinct initial designs, the 417-run plan, input data,
and original method implementations. Changes in `instrumentation.py` and
`case_study_benchmark.py` are reported as intentional tracing changes.
Identical starts do not prove identical subsequent trajectories, especially
across solver versions and operating systems. These traces are new reruns;
they do not retroactively reveal ambiguous coordinates in the old logs.

On Dantzig, the prepared wrapper reuses `.venv-dantzig-bam`, verifies BAM
5.0.0 and the original RBFOpt/NumPy/SciPy versions, and runs methods sequentially
on one CPU with one numerical-library thread:

```bash
export BAM_LICENSE_FILE=/local/scratch/a/lee4382/bamlice.txt
bash run_traced_cases_dantzig.sh check
bash run_traced_cases_dantzig.sh run
```

For an interrupted Dantzig run:

```bash
export DANTZIG_TRACE_DIR=/absolute/path/to/dantzig_traced_cases_TIMESTAMP_SUFFIX
bash run_traced_cases_dantzig.sh resume
```

It writes a new result directory and runs the coordinate/timing audit after
completion. The historical result archives and published figures are retained.

## Join coordinates to historical costs

```bash
python trace_analysis.py results/my_trace_run/process_case_studies.csv \
    --output results/my_trace_run/trace_analysis
```

Multiple nonoverlapping result CSVs can be supplied. A checkpoint
`*.partial.csv` can also be inspected: only its completed rows are analyzed.
The tool rejects duplicate run keys, trace corruption, coordinate/value
mismatches, and mismatched initial designs. It creates:

| File | Meaning |
| --- | --- |
| `evaluation_points.csv` | Every actual callback, joined by exact integer coordinates |
| `run_summary.csv` | Evaluation counts, lookup first-hit timestamps, historical timing coverage |
| `nlp_point_requests.csv` | Distinct problem/point combinations needing consistent NLP measurements |
| `summary.json` | Input checksums, counts, and timing limitations |

The original enumeration writer assigns `Time` from
`m_solved.results.solver.user_time`. `Global_Time` is elapsed time since the
enumeration began, and must not be summed across points. See
[the pinned upstream writer](https://github.com/SECQUOIA/dsda-gdp/blob/3e469dbeea8931670b8cd6752014ab7a767d3af5/gdp/dsda/dsda_functions.py#L1633).
The local Column and Small Batch CSVs are byte-identical to that upstream
checkout. The CSTR CSVs use the same fields; their exact producing revision
and machine have not been established.

The writer's `Status=Final` row is an additional solve of the best point after
enumeration, so it is excluded from the point-cost table. Exactly one remaining
enumeration row is required. Other duplicate historical rows remain ambiguous
measurement choices and stay missing.
Missing points, nonfinite/negative times, and Dynamic's absent time table also
stay missing. No missing cost is assigned zero. A full historical cost estimate
is emitted only when every callback has one valid historical time record.
`legacy_known_cost_sum_s` is merely the sum over covered calls, not a total.
Per-call and unique-point sums are separate cost assumptions, not claims about
actual solver caching. Do not add these old solver times to new Mac/Dantzig
overheads and label the result a measured end-to-end runtime.

## Original GDP models and the next measurement step

The public source checkouts inspected on 2026-09-17 were:

- [dsda-gdp, commit 3e469db](https://github.com/SECQUOIA/dsda-gdp/tree/3e469dbeea8931670b8cd6752014ab7a767d3af5):
  Column, CSTR, and Small Batch models and external-variable reformulations.
- [LD-SDA-Dynamic, commit 482e14e](https://github.com/SECQUOIA/LD-SDA-Dynamic/tree/482e14ebf9caabbd35d959986942cb028778a1d7):
  `plot_search_path.py` contains the exact 37-point Dynamic objective map used
  here. The corresponding nine-stage model is in
  `models/nine_stage_dynamic_model_switching_nonlinear.py`; the benchmark
  discretization uses `nfe=30`, `ncp=3`. Confirm the external-index mapping
  against several archived objectives before measuring all configurations.

A preliminary local probe connected all four models at one representative
point: Column (13,4), Small Batch (2,2,1), and Dynamic (1,4) with IPOPT; CSTR
(3,1) with GAMS/BARON. The objective gaps were within the benchmark tolerance,
the maximum primal residual was below 1e-6, and no unfixed discrete variables
or active disjunctions remained. CSTR needed stronger presolve and BARON after
IPOPT failures; GAMS also required access to its license network. The old
`MasterProblemResult` imports were bypassed while retaining the original model
and reformulation function bodies. These are connection probes with different
solver policies, not a uniform timing experiment or proof of global optimality.

The next experiment should solve the points in `nlp_point_requests.csv` under
one declared solver, machine, initialization policy, and time limit. Record
model construction, logic fixing/transformation, solve time, termination,
feasibility, and objective separately. Verify no unfixed integer variables or
active disjunctions remain in an intended NLP subproblem. Include infeasible
configurations and failed solves in the cost accounting.

Use cold starts for a point-specific cost table. With warm starts, cost can
depend on the preceding point, so replay the full ordered trace instead of
assuming a fixed cost per coordinate. A fixed-table replay is an estimate;
selected live black-box GDP runs are needed to validate actual end-to-end
and first-hit timings. IPOPT/local-NLP objectives need not reproduce old
BARON/global-solver lookup values and must not silently replace them.
