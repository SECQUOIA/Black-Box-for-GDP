# CSTR15 W03 single-call Dantzig check

This package prepares one additional fixed-configuration GAMS/IPOPT numerical check from the original W03 vector.
Packaging and local validation invoked no NLP solver; the subsequent [returned Dantzig result](../results/review_cstr15_dantzig_20261021/README.md) is now available.
The user runs the package on Dantzig and returns its result ZIP for independent verification.
The previous macOS success and failures, historical execution-provider revisions, performance tables and manuscript files remain unchanged.

## Evidence and fixed protocol

The base repository revision is `d05b392d4a93e4233a2ee69617da2767395fd27b`.
The successful local AMPL/IPOPT record is retained at revision `854a1a7fc5a20a5489d82ef7991a16aaf89025f3` in `results/review_feasibility_tautology_20261020/`.
The input selection and original W03 evidence come from `results/review_feasibility_followup_20261020/` and `reproduction/data/algebraic_audit/`.
The original W03 vector, rather than the local polished vector, supplies all continuous starting values.
The source model is pinned to `dsda-gdp` revision `3e469dbeea8931670b8cd6752014ab7a767d3af5`.
Preparation verifies archived evidence hashes, restores W03 on the original GDP and rechecks its objective, residuals and discrete configuration before any solver call.
The objective and maximum unscaled violation reproduce `2.82935061823614` and `5.634494497502862e-7`, respectively; these values are read and checked against the original records, not substituted into generated results.

The existing exact-arithmetic proof is repeated for `logic_to_linear.transformed_constraints[16]`, `[17]` and `[18]`.
Only these three exact fixed-binary `1=1` identities are deactivated on the computational clone.
The original GDP, variable bounds, starting values and objective remain intact.
The model has 156 free continuous variables and changes from 306 constraints/158 equalities to 303 constraints/155 equalities.
The GAMS writer substitutes fixed values and adds an objective variable and equality, giving 156 mapped original free variables plus the objective variable, and 304 exported equations.
The mapping records every original active row, free variable, substituted fixed value and starting level separately from any solver presolve counts.

The historical environment is extracted from `results/archives/dantzig_gdp_gams_20260922_050038_p4q8hy54.zip`, whose SHA256 is `e406b8fae2a90191835eb7332d483c719ebb1675d14d3b0e6d3bf5f7789a197b`.
Its CSTR15 log identifies GAMS 52.2.0, IPOPT 3.14.19 and MUMPS 5.8.1.
The archived GAMS executable is `/package/gams/52.2/gams`, with SHA256 `11bd33943b5b2542afa73cbf3eb8a1f1b27eb1bde1ba56e85f8a262cfdd29245`.
Preparation requires that binary hash and the recorded Python 3.11.16, Pyomo 6.10.0, SymPy 1.14.0, NumPy 2.4.6, NetworkX 3.6.1 and Matplotlib 3.11.2 environment.
The launcher reuses the existing `.venv-dantzig-gdp/bin/python`; `CSTR15_PYTHON` can identify another existing interpreter only if it passes the same checks.
No installation, alternate solver or automatic fallback is attempted.
Support-library and option-definition file hashes are captured before the single call, and the actual IPOPT/MUMPS banners must match the archived versions afterward.

The [GAMS 52 IPOPT option-file interface](https://www.gams.com/52/docs/S_IPOPT.html#IPOPT_SPECIFICATION_OF_OPTIONS) uses the following `ipopt.opt` file and `GAMS_MODEL.optfile=1`.
The installed `optipopt.def` must contain every requested option name before execution, and the actual log is checked for option values and errors afterward.

```text
tol 1e-10
constr_viol_tol 1e-10
acceptable_iter 0
bound_relax_factor 0
honor_original_bounds yes
nlp_scaling_method none
max_iter 3000
warm_start_init_point no
linear_solver mumps
```

`NLP=IPOPT`, a 290-second GAMS resource limit and one thread are explicit in the generated input.
The outer worker limit is 300 seconds; timeout kills its process group, including GAMS and solver children.
No `available()`, license probe, version-command execution or smoke optimization is used.
The historical archive contains its own old smoke-test record, which is preserved as history and never replayed.
The original performance run used different tolerances and a 60-second point limit; this is a separate tightened-feasibility diagnostic, not a reproduction of those performance measurements.

## Build and transfer

Build from this branch with its pinned submodule available.
The builder reads stored files and writes a standalone ZIP, without invoking a solver or downloading anything.
The ZIP contains the necessary evidence archives and exact pinned model files, but no manuscript files, figure regeneration or solver binaries.

```bash
python build_cstr15_dantzig_check.py --output /tmp/cstr15_dantzig_check_20261021.zip
scp /tmp/cstr15_dantzig_check_20261021.zip \
    /tmp/cstr15_dantzig_check_20261021.zip.sha256 \
    lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

On Dantzig, verify and extract into a new directory without changing the existing repository checkout.
Inspect both logical siblings before selecting an idle CPU; the launcher pins itself and its descendants to that one logical CPU.

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
sha256sum -c cstr15_dantzig_check_20261021.zip.sha256
PACKAGE_DIR=$(mktemp -d "$PWD/cstr15_dantzig_package_XXXXXX")
unzip -q cstr15_dantzig_check_20261021.zip -d "$PACKAGE_DIR"
cd "$PACKAGE_DIR/cstr15_dantzig_runner"
lscpu -e=CPU,CORE,SOCKET
ps -eo pid,psr,pcpu,args --sort=-pcpu | head -25
read -r -p 'Idle CPU number: ' CPU
bash run_cstr15_dantzig_check.sh all --cpu "$CPU" 2>&1 | tee "$PACKAGE_DIR/console.log"
```

The launcher prints `RESULT_DIR` and `RESULT_ZIP`, including for a preparation or solver failure once an output directory exists.
It creates a fresh result directory under `results/review_cstr15_dantzig_<UTC timestamp>_<suffix>/` and a neighboring return ZIP with SHA256.
The global allocation ledger is `results/cstr15-w03-gams52-20261021-one-call.json` in the existing server repository.
An exclusive ledger write immediately before launching GAMS charges the only permitted call, including an option error or launch failure.
Neither a different output directory nor rerunning `run` resets that allocation.
Do not delete the ledger or automatically retry after any charged call.

Download the printed ZIP and its checksum from a local terminal, replacing the example path with the exact `RESULT_ZIP` value.

```bash
scp lee4382@dantzig.ecn.purdue.edu:/absolute/path/from/RESULT_ZIP.zip \
    lee4382@dantzig.ecn.purdue.edu:/absolute/path/from/RESULT_ZIP.zip.sha256 \
    ~/Downloads/
```

## Separate preparation, execution and verification

`prepare` is solver-free and `run` consumes at most the single allocation.
The wrapper supplies the fixed thread environment, CPU affinity, package hashes, original input directory and global ledger.
A prepared directory cannot be reused for preparation, and preparation/runtime hash mismatches stop before execution.

```bash
bash run_cstr15_dantzig_check.sh prepare --cpu "$CPU"
# Use the printed RESULT_DIR without creating another preparation.
bash run_cstr15_dantzig_check.sh run --cpu "$CPU" --run-dir "$RESULT_DIR"
# This recheck reads saved results and never calls a solver.
bash run_cstr15_dantzig_check.sh verify --cpu "$CPU" --run-dir "$RESULT_DIR"
bash run_cstr15_dantzig_check.sh pack --run-dir "$RESULT_DIR"
```

The Python CLI also supports explicit paths independently of the launcher.
Its `prepare` and `run` modes still enforce the same environment, hashes and allocation controls.

```bash
python -m review_diagnostics.cstr15_gams prepare \
  --input results/review_feasibility_followup_20261020 \
  --directory /path/to/new/result \
  --gams /package/gams/52.2/gams \
  --allocation-ledger /path/to/repository/results/cstr15-w03-gams52-20261021-one-call.json
python -m review_diagnostics.cstr15_gams run --directory /path/to/new/result
python -m review_diagnostics.cstr15_gams verify \
  --directory /path/to/returned/result --output /path/to/new/verification.json
```

Solver-free verification can run on macOS using this checkout or the extracted runner and its compatible Python/Pyomo dependencies.
It does not require the GAMS binary, server CPU affinity or server Python version.
It verifies saved hashes, reconstructs the original GDP, repeats the exact identity proof and recomputes the returned point's residuals and comparison.
The exported floating-point vector is preserved exactly, with a `1e-12` numerical comparison tolerance for cross-platform replay reports; the feasibility criterion itself remains `1e-8`.
The returned October 21 result exposes a cross-platform mismatch in the original verifier's derived Hull ratio and near-zero residual ranking comparisons, while all named primal checks and feasibility classifications agree.
That original verifier and its failure are preserved in the [result analysis](../results/review_cstr15_dantzig_20261021/README.md).
For this returned result, run `python -m review_diagnostics.cstr15_gams_analysis --output /path/to/new/analysis` from the results branch to reproduce the separate full comparison and explicit metadata checks without a solver.

## Returned evidence and interpretation

`selection.json`, `preflight.json`, `input_evidence.json`, `historical_environment.json` and `environment.json` record the fixed target, limits, sources, provenance and runtime checks.
`solver_input/model.gms`, `ipopt.opt`, `gams_mapping.json`, logs, listing and DAT files preserve the actual submitted problem and raw results.
`solver_call.json`, `worker_result.json` and `execution.json` distinguish the charged call, GAMS return and outer timeout.
`summary.json`, `comparison.csv`, `bound_comparison.csv` and the result README separate the original W03, retained macOS point and actual Dantzig outcome.
`solution.json` and `residuals.json` exist only when a complete, finite returned free-variable vector can be reconstructed and independently inspected.
Missing free-variable levels are rejected; only explicitly mapped fixed values are restored without a solver return.
Raw solver statuses and auxiliary unavailable statistics are preserved without converting missing values into feasible evidence.
A local infeasibility status with a complete returned iterate remains a candidate for independent inspection and is not a mathematical infeasibility proof.

The `1e-8` test checks the original active algebraic constraints, bounds, integrality, disjunctions, logical conditions, unchanged configuration and all three omitted identities.
Numerical feasibility and confirmation of the requested GAMS/IPOPT/MUMPS/options protocol are separate fields.
For each retained GLOA and Hull lower bound, `delta = lower_bound - f`, `tau = 1e-5 * max(1, abs(f))` and `rho = delta / tau` are reported separately.
Tightened bound-discrepancy persistence is unestablished unless both the returned point and execution protocol qualify.
No result is forced to reproduce the macOS objective, iterations or bound-comparison outcome.
This is numerical evidence for one fixed configuration, not exact feasibility, global optimality, reproduction of LOA/BARON or proof of a solver defect.
The generated result README contains conditional reviewer/manuscript wording, but no manuscript is edited.

`manifest.json` hashes the prepared or completed outputs, while the return ZIP's `RETURN_MANIFEST.json` also hashes any later verification reports.
Neither manifest replaces an original execution-provider revision.
The returned result and solver-free local comparison are now linked from `docs/review_comparison_status.md`.
The original server archive and its execution revision are retained unchanged alongside the new analysis.

## Local validation

The repository's pytest convention is retained, with a targeted solver-free test command.
All process-spawning paths in these tests are mocked; replay fixtures never become published new solver evidence.

```bash
python -m pytest -q tests/test_cstr15_gams.py \
  tests/test_review_diagnostics_feasibility.py \
  tests/test_review_feasibility_followup.py \
  tests/test_review_feasibility_tautology.py
python -m ruff check review_diagnostics/cstr15_gams.py \
  build_cstr15_dantzig_check.py tests/test_cstr15_gams.py
bash -n run_cstr15_dantzig_check.sh
```

The [local preparation report](validation/cstr15_dantzig_preparation_20261021.json) records 60 passing tests, lint and shell checks, independent replay of the retained local success and the protected-file hash inventory.
The standalone package was extracted without Git metadata and successfully restored W03 and exported the mapped GAMS input without invoking a solver.
The local test environment is deliberately distinguished from the required Dantzig execution environment.
