# Dantzig catalytic Column MINLP comparison

This directory archives the completed Dantzig reproduction of the workstation MINLP comparison.
The original 210-run Column DFO campaign was preserved and was not rerun.
This publication performs data verification and reporting only; it runs no solver, preflight or optimization experiment.
All 12 main MINLP runs, 4 fixed-best runs and 36 fixed-configuration validation records are present, with no duplicates.
One of the 12 main runs returned a feasible design and none reached the existing best-known reference.
The other 11 runs remain in the denominator and retain their original logs and status codes.

## Main results

The reference is the observed design `(f1,c1,c2,c3,f2,b) = (8,8,12,17,17,21)` at **24,895.552861 USD/year**, which is not a proven global optimum.
The objective is minimized, and target proximity uses the existing absolute-difference rule `abs(z - reference) <= 1e-5 * max(1, abs(reference))` (0.24895552861 USD/year).
Target proximity is evaluated only for a returned feasible solution.
Product/SBB returned **28,717.220843 USD/year** at `(4,4,5,6,6,9)`, **15.3508% above** the reference.
The reference was reproduced in fixed-design checks, but no main search found it from the original initialization.

| Form | Solver | Model/solver status | Feasible objective (USD/year) | Dantzig wall (s) | Workstation wall (s) | Interpretation |
|---|---|---|---:|---:|---:|---|
| product | DICOPT | 9/4 | - | 686.5 | 638.0 | Terminated without feasible solution |
| product | SBB | 8/1 | 28717.220843 | 10.4 | 8.2 | Feasible; reference not reached |
| product | BARON | 19/1 | - | 255.3 | 73.6 | Reported infeasible; no solution |
| product | SCIP | 19/1 | - | 9.1 | 5.3 | Reported infeasible; no solution |
| bigm | DICOPT | 9/4 | - | 901.8 | 1246.7 | Terminated without feasible solution |
| bigm | SBB | 14/5 | - | 37.9 | 88.9 | Evaluation interrupt; no solution |
| bigm | BARON | 19/1 | - | 214.5 | 157.6 | Reported infeasible; no solution |
| bigm | SCIP | 14/3 | - | 3601.0 | 3602.4 | Time limit; no solution |
| chull | DICOPT | 9/4 | - | 211.3 | 154.0 | Terminated without feasible solution |
| chull | SBB | 14/5 | - | 130.3 | 123.1 | Evaluation interrupt; no solution |
| chull | BARON | 19/1 | - | 362.4 | 126.7 | Reported infeasible; no solution |
| chull | SCIP | 14/3 | - | 3601.0 | 3602.1 | Time limit; no solution |

The 12 outcomes comprise 1 feasible result, 4 reported-infeasible results, 3 solver terminations without a feasible solution, 2 evaluation interrupts and 2 solver time limits.
Both main time limits are SCIP runs at 3,600 seconds; all 16 recorded main/fixed-best process exits are zero and no external watchdog killed a run.
A zero process exit is not evidence that the optimizer succeeded.
`summary.csv` retains the raw GAMS levels, while `reviewed_runs.csv` leaves the feasible objective empty when no feasible solution was returned.
Raw values such as 23,671.193740 or the negative DICOPT objectives are not feasible improvements.
The preserved listings identify model status 9 as `Intermediate Non-Integer`; it is not an accepted integer design even when the rounded configuration or `maxfrac` looks integral.
See the [GAMS status definitions](https://www.gams.com/54/docs/UG_GAMSOutput.html) for the distinction between model and solver termination status.

## Comparison with the workstation

The baseline is `../catalytic_distillation_minlp_20261101/`, recorded with GAMS 54.2.2 and CONOPT 4.39.1 on an Intel Xeon w5-2565X workstation under WSL2.
All 12 model/solver status pairs match the baseline, and the only feasible main result has the same objective and design.
All 36 validation CSV records match the baseline exactly at their stored precision.
Small differences in failed DICOPT objective levels are retained in `reviewed_runs.csv` and are not solution improvements.
Wall times differ in both directions, as shown above; the changed GAMS build, hardware and shared-server conditions prevent attributing those differences to one cause.
The conclusions agree with the workstation run without establishing a global optimum or proving global infeasibility.

## Validation and limitations

EMP scales reproduce the committed `emp_scales.gms` byte for byte, and all 47 recorded source-file hashes match execution revision `a1c3bf336493dc496bb2571e160b1054f237e0be`.
The four tiny solver preflights and the JAMS Big-M preflight are preserved in `evidence/raw.zip`.
Each of the nine fixed configurations has GDP, product, Big-M and hull records (36/36).
Six configurations are locally feasible in each form and three terminate locally infeasible in each form.
Big-M and hull match GDP at all six feasible configurations within the original tolerance; the largest absolute objective difference is approximately 0.000001 USD/year.
The product form reproduces its previously observed different local solutions at two configurations, as documented in the existing experiment README.
These tests support the reported fixed-configuration comparison and do not prove equivalence over all configurations.

| Fixed-best form | Solver | Model/solver status | Observed wall (s) | Interpretation |
|---|---|---|---:|---|
| bigm | BARON | 19/1 | 105.79 | Reported infeasible; no solution |
| bigm | SCIP | 14/3 | 1201.26 | Time limit; no solution |
| chull | BARON | 19/1 | 179.27 | Reported infeasible; no solution |
| chull | SCIP | 14/3 | 1201.00 | Time limit; no solution |

The four fixed-best runs returned no feasible solution: BARON reported infeasibility in two runs and SCIP reached its 1,200-second solver limit in two runs.
Those infeasibility reports conflict with the preserved feasible CONOPT point and are reported as solver claims, not mathematical conclusions.
The two product-form Examiner checks and the Big-M initial-point check report primal bounds and constraints satisfied within `1e-6`.
The Big-M Examiner subsequently reports an unknown `none` subsolver; its initial primal checks are usable evidence, but the full invocation is not presented as error-free and there is no subsolver solution.
The BARON warm-start checks warn that `baron.opt` is missing and continue with default options; the warning and the original code are preserved without repair or rerun.
SCIP and BARON each report optimality when initialized at both 25,271.3276887951 and 24,895.5528611452 USD/year in the same free product MINLP.
Both points passed the recorded primal checks, so the higher claimed optimum is contradicted by the lower feasible point.
These four warm-start results are diagnostic evidence of unreliable optimality claims, not independent discoveries of the reference or validated global certificates.
The automatic `finished_pending_review` triggers are therefore documented as status-aware interpretation issues rather than counted as additional successes.
The original automated review is preserved in `validation_audit.json` and `execution_provenance/audit.json`.

## Execution provenance

Execution revision: `a1c3bf336493dc496bb2571e160b1054f237e0be`.
Publication base revision: `a1c3bf336493dc496bb2571e160b1054f237e0be` on `feature/catalytic-distillation-pilot`.
The results commit is separate from the execution revision and does not change the recorded provenance.
Host: `dantzig.ecn.purdue.edu`, AMD EPYC 7643 48-Core Processor.
Controller PID: `422377`; start: `2026-11-01T21:39:05.538141+00:00`; exit: `2026-11-01T22:45:52.444740+00:00` (UTC), exit code 0.
The controller elapsed time was **4,006.906599 seconds (1 hour 6 minutes 46.91 seconds)**, including preparation and packaging.
The main and fixed-best phase began at `21:45:35 UTC`, and the last main job ended at `22:45:36.826454 UTC`.
`environment.txt` records the end of solver work at second precision, before packaging completes.
GAMS job banners use local clock values consistent with UTC-5; the authoritative timestamp metadata explicitly uses UTC.
GAMS executable: `/package/gams/54.3/gams`; actual GAMS version: **54.3.1**, build `61154be4`.
Executable SHA256: `d5e3b28c93702383a65c98acd4cf7e7ea6020c51b3bd9e6792175a9d41d8f6ff`.
Observed backends: CONOPT **4.39.1**, BARON **26.5.27**, SCIP **10.0.3** (`d409edf9f6`) and CPLEX **22.1.2.0**.
DICOPT identifies itself as `Dicopt 2` in the GAMS 54.3.1 interface banner; finer DICOPT and standalone SBB backend versions are not recorded.
Scale Python: `/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig/bin/python`, Python **3.11.16**, Pyomo **6.10.0**.
The version of the separate supervisor Python is not recorded.
The 16 main/fixed-best jobs each have a recorded singleton CPU affinity on a different physical core, with OpenMP and numerical-library threads set to one.
Validation used up to eight concurrent children, each pinned to one CPU, and all 36 child affinity records are preserved.
No scheduler reservation is recorded; affinity and advisory locks do not guarantee exclusive use against other server users.

| Logical CPU | Socket | Physical core | SMT siblings |
|---:|---:|---:|---|
| 31 | 0 | 41 | 31, 79 |
| 32 | 0 | 42 | 32, 80 |
| 33 | 0 | 43 | 33, 81 |
| 34 | 0 | 44 | 34, 82 |
| 35 | 0 | 45 | 35, 83 |
| 36 | 0 | 48 | 36, 84 |
| 37 | 0 | 49 | 37, 85 |
| 38 | 0 | 50 | 38, 86 |
| 39 | 0 | 51 | 39, 87 |
| 40 | 0 | 52 | 40, 88 |
| 41 | 0 | 53 | 41, 89 |
| 42 | 0 | 56 | 42, 90 |
| 44 | 0 | 58 | 44, 92 |
| 45 | 0 | 59 | 45, 93 |
| 46 | 0 | 60 | 46, 94 |
| 47 | 0 | 61 | 47, 95 |

The unchanged original runner used `init.gdx` and the initial configuration `(3,4,5,6,8,9)` for the main searches.
Limits were 3,600 seconds for main MINLP, 1,200 seconds for fixed-best runs and 900 seconds for the free warm-start checks.
`BASH_ENV` instrumentation gated version/scale checks and pinned validation children; a timeout shim recorded the original watchdog exits.
No mathematical model, initialization, solver option or acceptance criterion was changed during this publication.

## Evidence and verification

`evidence/RETURN_MINLP54.zip` is the uploaded archive, preserved byte for byte at **14,481,684 bytes**.
Its SHA256 is `e47443dda2e2376e764ddcff85975e9d707632c347c0ee389be3dd2ea6579f9c`.
`evidence/raw.zip` is the original runner archive, preserved byte for byte at **14,705,155 bytes**.
Its SHA256 is `f432d0172e699c29fe0e1d1e176ed32527e725ee980e13542377b4ae01deb1e0`.
Both archives pass CRC and SHA256 verification and are individually below 90 MB.
The uploaded manifest validates all 80 listed files, and CSV values, statuses, configurations and times match the individual records.
Recursive inspection of the uploaded ZIP, its nested ZIP and gzip members decoded 506 text members and found no Korean characters in text or filenames.
The original archive excludes `*.gdx` and `*/225?/*`; it is not a complete copy of the server working directory.
Full raw output remains at `/local/scratch/a/lee4382/m54_2hwupl6j/raw`, with the controller log at `/local/scratch/a/lee4382/m54_2hwupl6j/controller.log`.
The original server README and checksum manifest are preserved under `execution_provenance/`, and the uploaded archive also retains the original package unchanged.
`FILE_SHA256.json` describes the final publication files; the original upload manifest is `execution_provenance/RETURN_FILE_SHA256.json`.

The following commands verify stored data only and do not launch GAMS or another solver.
Run them from the repository root at the publication revision, which contains the execution source and the unchanged workstation baseline.

```bash
result=results/catalytic_distillation_minlp_dantzig_20261101
(cd "$result/evidence" && shasum -a 256 -c RETURN_MINLP54.zip.sha256 && shasum -a 256 -c raw.zip.sha256)
python3 -m zipfile -t "$result/evidence/RETURN_MINLP54.zip"
python3 -m zipfile -t "$result/evidence/raw.zip"
python3 "$result/verify_results.py" "$result" .
```

The historical execution command was `bash experiments/catalytic_distillation_minlp/run_dantzig.sh` with the environment recorded in `execution_provenance/environment_wrapper.json`.
It is recorded for provenance and was not executed during this analysis.
Only this new result directory is included in the publication commit; models, execution code, manuscript, Overleaf and other experiment records are unchanged.
