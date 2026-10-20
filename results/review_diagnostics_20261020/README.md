# Limited diagnostics for review Minor 5 and Minor 6

The FMQA implementation audit and seven reconstructed iteration diagnostics are complete.
The original W03 feasibility recheck is complete, but tightened-feasibility polishing is incomplete because both permitted local solver calls rejected an unsupported AMPL command-line option before optimization.
No Grid/Process benchmark, RBFOpt run, BAM run or full FMQA performance run was repeated.
No manuscript or Overleaf source was modified.

## Selection and provenance

[selection.json](selection.json) fixed the cases, iteration rule, archive/member hashes and computation limits before any diagnostic fit or NLP call.
The cases are Rosenbrock B10 seed0, CSTR15 B22 seed0 and Dynamic B12 seed0, using the lowest retained budget for the two multi-budget examples and seed0 without searching for favorable outcomes.
For each case, the rule chooses the first SA-selected proposal, the first uniform-fallback proposal if present, and the last proposal, removing duplicates.
Rosenbrock selected iterations 1 and 7, CSTR15 selected iterations 1 and 19, and Dynamic selected iterations 1, 2 and 9.
No uniform-fallback proposal exists in the selected Rosenbrock or CSTR15 run, and neither run was replaced.
This is a purposive diagnostic selection and cannot estimate population frequencies.
The archive-member inventory found no fitted-weight or QUBO snapshot in these selected jobs.
Every saved weight file is therefore labeled `reconstructed diagnostic fit` rather than a historical model.
The copied inputs preserve original bytes, including their runtime and execution provenance.
The original review-comparison execution provider remains `38d917ef75ef6767c2a9f238d88be19bf0b89160`, and this diagnostic commit does not replace any historical execution revision.

## FMQA results

The [implementation audit](IMPLEMENTATION_AUDIT.md) explains the training loss, Adam regularization setting, QUBO convention, scaling, exception propagation and source differences.
The [summary CSV](fmqa/summary.csv) links each iteration to a weight snapshot, training prefix, exhaustive-energy CSV and recorded-sample comparison in its corresponding subdirectory.
There were seven reconstructed fits, zero new SA calls and zero synthetic fits.
The FMQA child process, including imports, fitting and enumeration, finished in about 2.83 seconds under a 1,200-second external wall limit.
The diagnostic time is not included in any historical performance timing.
All 3,328 enumerated binary strings pass the documented combined absolute/relative energy-identity tolerance.

| Case | Iteration | Bits | Strings | Recorded source | Binary minimum outside domain | Selected minus eligible minimum, scaled |
|---|---:|---:|---:|---|---|---:|
| Rosenbrock | 1 | 10 | 1024 | SA | No | 0 |
| Rosenbrock | 7 | 10 | 1024 | SA | No | 0 |
| CSTR15 | 1 | 8 | 256 | SA | No | 0 |
| CSTR15 | 19 | 8 | 256 | SA | No | 0 |
| Dynamic | 1 | 8 | 256 | Uniform fallback | Yes | 2.178316189 |
| Dynamic | 2 | 8 | 256 | SA | No | 0 |
| Dynamic | 9 | 8 | 256 | Uniform fallback | Yes | 0.384911966 |

The energy gaps in this table refer to reconstructed models and the recorded selected configurations, not an established historical energy landscape.
All stored sample energies match reconstruction within the stated tolerance, with a largest absolute difference of approximately `1.328e-6`.
The Dynamic fallback iterations contain no eligible recorded SA sample, which is directly observable in the historical logs.
The synthetic constant and zero-Q checks show that zero scaling produces nonfinite coefficients and a propagated ValueError, not automatic uniform fallback.
The historical occurrence of a zero-scale fitted model remains unknown.

## W03 original-GDP recheck and failed polishing attempts

The fixed comparison is CSTR15 GLOA audit A12 versus LOA witness W03.
The pinned dsda-gdp revision is `3e469dbeea8931670b8cd6752014ab7a767d3af5`, and its model, initialization and serializer hashes match the original witness execution.
The independently reevaluated W03 objective is `2.82935061823614`, and its maximum unscaled primal violation is `5.634494497502862e-7`.
Variable bounds, integrality, disjunctions and logic pass the original `1e-5` residual test.
W03 selects all 15 CSTRs, feed position 15 and recycle position 15.
The recorded A12 lower bound remains `3.522552007803194`, giving a difference of `0.6932013895670543` and an original audit discrepancy ratio of about `24500.37`.
This establishes only that W03 is numerically feasible under the stated residual test of `1e-5`.
It does not satisfy the requested tightened target of `1e-8` before polishing.

The fixed-disjunct NLP preserves the original objective, bounds and complete active algebraic constraint set while fixing only discrete variables and retaining free continuous variables.
The original logical constraints remain independently checked on the GDP, and the NLP retains their already-generated algebraic equivalents.
The two calls used local IPOPT 3.12.13 with targets `1e-8` and `1e-10`, respectively, under separate 300-second external wall limits.
Both stopped at option parsing with `Unknown keyword "acceptable_iter"`, so neither returned a new solution vector or performed polishing iterations.
The initial driver incorrectly retried the same interface error once, consuming the permitted second call.
The [before/after CSV](feasibility/before_after.csv) retains those attempts with false tightened-feasibility flags.
The files named `attempt_1/solution.json` and `attempt_2/solution.json` contain the unchanged start after failed loading and must not be interpreted as new polished witnesses.
The raw solver output is retained inside each `worker.log`, because Pyomo did not create a separate `ipopt.log` after the rejected invocation.

The final driver now passes `acceptable_iter` through an IPOPT options file and stops immediately after an exception or missing returned solution.
The local driver's read-only option listing confirms `option_file_name` support, and mocked-solver regression tests verify the emitted options file and acceptance logic.
This portability correction has not been solver-tested because the two-call allocation is exhausted.
[executed_diagnostic_sources.zip](executed_diagnostic_sources.zip) preserves the exact pre-correction diagnostic sources used for the retained executions.
The remaining question is whether a returned polished point can meet the tighter original-GDP residual target while retaining the reported discrepancy.
The failed calls neither establish nor disprove that statement and do not prove mathematical infeasibility, invalidity of a lower bound or global optimality.

## Files and validation

[manifest.json](manifest.json) records input, execution-source, current-source, output and preservation hashes, environment information, completed tests and commands.
[fmqa/manifest.json](fmqa/manifest.json) and [feasibility/manifest.json](feasibility/manifest.json) retain the stage outcomes and output hashes.
[review_reply_drafts.md](review_reply_drafts.md) contains separate English replies for Minor 5 and Minor 6, and [manuscript_notes.md](manuscript_notes.md) contains proposed wording only.
The new synthetic tests perform no fitting, annealing or real solver calls.
The related existing test selection excludes tests that train models, run real SA or launch optimization jobs.
The original review-comparison audit is replayed without weakening any of its source or result checks.

## Verify retained results without any new experiment

Run this from the updated repository checkout using Python 3.10 or newer.

```bash
python -m review_diagnostics.verify \
  --directory results/review_diagnostics_20261020 \
  --output /tmp/review_diagnostics_saved_verification.json
```

The output path must be new.
The verification command uses only the standard library and checks the archived inputs and saved energies without fitting or invoking a solver.

## Reproduction commands for a separately authorized diagnostic allocation

The retained run has already used its two permitted NLP calls, so do not run these compute commands as an automatic continuation of that allocation.
The commands below describe the bounded workflow for a future independently authorized reproduction in a new output directory.
FMQA requires NumPy 2.2.6, PyTorch 2.8.0, dimod 0.12.21 and dwave-samplers 1.6.0, while the feasibility stage uses the repository's pinned Pyomo 6.10.0 environment and an IPOPT executable.
The two stages can use different Python executables, as in the recorded local execution.

```bash
DIAGNOSTIC_DIR="$PWD/results/review_diagnostics_new_allocation"
python -m review_diagnostics.prepare --output "$DIAGNOSTIC_DIR"
# Optional FMQA reconstruction, up to nine fits and 1200 seconds:
"$FMQA_PYTHON" -m review_diagnostics.fmqa --directory "$DIAGNOSTIC_DIR"
# Only after authorization of additional NLP calls:
"$GDP_PYTHON" -m review_diagnostics.feasibility \
  --directory "$DIAGNOSTIC_DIR" --ipopt "$IPOPT_EXECUTABLE"
```

For a CSTR-only follow-up, omit the FMQA command entirely.
The feasibility controller never runs more than two calls and kills the worker process group if a call exceeds 300 seconds.
The fixed selection and a successful original W03 recheck are prerequisites to every solver call.

## Dantzig tool bundle

The optional [diagnostic_tools.zip](diagnostic_tools.zip) contains only the diagnostic tools and this guide, with a SHA256 inventory.
It requires an existing checkout containing the frozen archives, algebraic audit data, `review_comparison` helpers and initialized pinned submodules.
It contains no solver binary or license and does not launch a job when unpacked.
To use the tool bundle without overwriting the repository, unpack it into a new directory and point it at that checkout.

```bash
unzip diagnostic_tools.zip -d "$BUNDLE_DIR"
export RBFOPT_DIAGNOSTICS_REPO=/local/scratch/a/lee4382/repository/RBFopt_Test
export PYTHONPATH="$BUNDLE_DIR/review_diagnostics_runner:$RBFOPT_DIAGNOSTICS_REPO"
cd "$BUNDLE_DIR/review_diagnostics_runner"
python -m review_diagnostics.verify \
  --directory "$RBFOPT_DIAGNOSTICS_REPO/results/review_diagnostics_20261020" \
  --output /tmp/review_diagnostics_dantzig_verification.json
```

No Dantzig job or SSH command was executed during this task.
