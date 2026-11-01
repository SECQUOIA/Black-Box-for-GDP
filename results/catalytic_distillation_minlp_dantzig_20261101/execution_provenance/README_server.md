# Dantzig catalytic Column MINLP reproduction

This run reproduces the existing workstation MINLP comparison using GAMS 54.3.1.
The completed 210-job Column DFO campaign was not rerun.
Execution revision: `a1c3bf336493dc496bb2571e160b1054f237e0be`; publication revision is pending review.
Host: `dantzig.ecn.purdue.edu`; allocated physical cores: `[{"core": 41, "cpu": 31, "siblings": [31, 79], "socket": 0}, {"core": 42, "cpu": 32, "siblings": [32, 80], "socket": 0}, {"core": 43, "cpu": 33, "siblings": [33, 81], "socket": 0}, {"core": 44, "cpu": 34, "siblings": [34, 82], "socket": 0}, {"core": 45, "cpu": 35, "siblings": [35, 83], "socket": 0}, {"core": 48, "cpu": 36, "siblings": [36, 84], "socket": 0}, {"core": 49, "cpu": 37, "siblings": [37, 85], "socket": 0}, {"core": 50, "cpu": 38, "siblings": [38, 86], "socket": 0}, {"core": 51, "cpu": 39, "siblings": [39, 87], "socket": 0}, {"core": 52, "cpu": 40, "siblings": [40, 88], "socket": 0}, {"core": 53, "cpu": 41, "siblings": [41, 89], "socket": 0}, {"core": 56, "cpu": 42, "siblings": [42, 90], "socket": 0}, {"core": 58, "cpu": 44, "siblings": [44, 92], "socket": 0}, {"core": 59, "cpu": 45, "siblings": [45, 93], "socket": 0}, {"core": 60, "cpu": 46, "siblings": [46, 94], "socket": 0}, {"core": 61, "cpu": 47, "siblings": [47, 95], "socket": 0}]`.
Start: `2026-11-01T21:39:05.538141+00:00`; end: `2026-11-01T22:45:52.444740+00:00` (UTC).
GAMS executable: `/package/gams/54.3/gams`, SHA256 `d5e3b28c93702383a65c98acd4cf7e7ea6020c51b3bd9e6792175a9d41d8f6ff`.
CONOPT backend: `4.39.1`; other observed solver banners are preserved in `validation_audit.json`.
Unreported backend versions remain unconfirmed; interface build numbers are not substituted for them.
All original models, initialization and mathematical solver options were preserved.
The main MINLP limit is 3600 seconds and the four fixed-design limits are 1200 seconds.
The supervisor preserves the original script and adds version/scale gates, validation-child affinity, and watchdog exit logging.
Scale reproduction: `True`; fixed-form records: 36/36.
Big-M/Hull reproduce the GDP form: `True`.
The reference 24895.552861 USD/year is an observed best, not a proven global optimum.
The absolute-difference tolerance is `1e-5 * max(1, abs(reference))`.

| Form | Solver | Model status | Solver status | Objective | Outcome |
|---|---|---:|---:|---:|---|
| bigm | baron | 19 | 1 | 23671.193740 | no_feasible_solution_reported |
| bigm | dicopt | 9 | 4 | -56644055.376813 | no_feasible_solution_reported |
| bigm | sbb | 14 | 5 | 23671.193740 | no_feasible_solution_reported |
| bigm | scip | 14 | 3 | 23671.193740 | solver_resource_limit |
| chull | baron | 19 | 1 | 23671.193740 | no_feasible_solution_reported |
| chull | dicopt | 9 | 4 | -13144920.786558 | no_feasible_solution_reported |
| chull | sbb | 14 | 5 | 23671.193740 | no_feasible_solution_reported |
| chull | scip | 14 | 3 | 23671.193740 | solver_resource_limit |
| product | baron | 19 | 1 | 23671.193740 | no_feasible_solution_reported |
| product | dicopt | 9 | 4 | 28680.457608 | no_feasible_solution_reported |
| product | sbb | 8 | 1 | 28717.220843 | normal_feasible_reported |
| product | scip | 19 | 1 | 23671.193740 | no_feasible_solution_reported |

Workstation values, objective differences, missing files and termination details are retained alongside every row in `validation_audit.json`.
Failures, resource limits, watchdog timeouts and missing results are not omitted from the twelve planned combinations.
Full raw output remains at `/local/scratch/a/lee4382/m54_2hwupl6j/raw`.
The original ZIP excludes `*.gdx` and `*/225?/*`; it is not a complete copy of all raw files.
Original evidence ZIPs and checksum files were retained without recompression or alteration.
Evidence: `raw.zip`, 14705155 bytes, SHA256 `f432d0172e699c29fe0e1d1e176ed32527e725ee980e13542377b4ae01deb1e0`, CRC passed.

Publication review reasons:
- Certificate 8_8_12_17_17_21/baron_free: reported objective 24895.5528611452 near or below reference; inspect termination before publication
- Certificate 8_8_12_17_17_21/baron_free: reported objective 24895.553 near or below reference; inspect termination before publication
- Certificate 8_8_12_17_17_21/scip_free: reported objective 24895.5528611452 near or below reference; inspect termination before publication
- Certificate 8_8_12_17_17_21/scip_free: reported objective 24895.553 near or below reference; inspect termination before publication
- Fixed-best bigm/baron: returned objective 23671.19374; review solver status
- Fixed-best bigm/scip: returned objective 23671.19374; review solver status
- Fixed-best chull/baron: returned objective 23671.19374; review solver status
- Fixed-best chull/scip: returned objective 23671.19374; review solver status
- bigm/baron: returned objective 23671.19374, difference -1224.3591210000013, modelstat=19.0, solvestat=1.0; interpret before publication
- bigm/dicopt: returned objective -56644055.376813, difference -56668950.929674, modelstat=9.0, solvestat=4.0; interpret before publication
- bigm/sbb: returned objective 23671.19374, difference -1224.3591210000013, modelstat=14.0, solvestat=5.0; interpret before publication
- bigm/scip: returned objective 23671.19374, difference -1224.3591210000013, modelstat=14.0, solvestat=3.0; interpret before publication
- chull/baron: returned objective 23671.19374, difference -1224.3591210000013, modelstat=19.0, solvestat=1.0; interpret before publication
- chull/dicopt: returned objective -13144920.786558, difference -13169816.339419, modelstat=9.0, solvestat=4.0; interpret before publication
- chull/sbb: returned objective 23671.19374, difference -1224.3591210000013, modelstat=14.0, solvestat=5.0; interpret before publication
- chull/scip: returned objective 23671.19374, difference -1224.3591210000013, modelstat=14.0, solvestat=3.0; interpret before publication
- product/baron: returned objective 23671.19374, difference -1224.3591210000013, modelstat=19.0, solvestat=1.0; interpret before publication
- product/scip: returned objective 23671.19374, difference -1224.3591210000013, modelstat=19.0, solvestat=1.0; interpret before publication

Reproduction uses the pinned offline source and the environment recorded in `execution_provenance/environment_wrapper.json`.
```bash
bash experiments/catalytic_distillation_minlp/run_dantzig.sh
```
No manuscript, Overleaf document, model, existing result, CI setting or unrelated benchmark was changed.
