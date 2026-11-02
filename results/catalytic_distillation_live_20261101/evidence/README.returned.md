# Dantzig live-NLP catalytic distillation results

Execution revision: `5580a7eacdc8b4098ba5c239822de2300e667a1c`.
Host: `dantzig.ecn.purdue.edu`; workers: 3; CPUs: `17,38,43`.
Started: `2026-11-01T00:13:21.828690+00:00`; finished: `2026-11-01T03:00:54.444394+00:00` (UTC).
GAMS/CONOPT: `{"conopt_version": "4.39.1", "conopt_version_evidence": [{"line": 58, "source": "probe_solver_private.log", "source_sha256": "64bba8310c1fe9c5c4d9dfb9ceb049b12275094373c52ad3dfb0fdaf9cfa0ce1", "version": "4.39.1"}, {"line": 4552, "source": "probe_private.lst", "source_sha256": "2ebf1f658ce26253267c5b5ece441da1a086656dbd50117c61983cbee012ff58", "version": "4.39.1"}], "gams_executable": "/package/gams/54.3/gams", "gams_sha256": "d5e3b28c93702383a65c98acd4cf7e7ea6020c51b3bd9e6792175a9d41d8f6ff", "gams_version": "54.3.1", "modelstat": "2", "objective": 25271.327689, "preflight_only": true, "solvestat": "1"}`.
Python environments: `{"DFO_PYTHON": {"distribution_paths": {"bam-solver": "/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-nlp-overnight/lib/python3.11/site-packages", "numpy": "/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-nlp-overnight/lib/python3.11/site-packages", "pandas": "/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-nlp-overnight/lib/python3.11/site-packages", "rbfopt": "/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-nlp-overnight/lib/python3.11/site-packages"}, "executable": "/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-nlp-overnight/bin/python", "packages": {"bam-solver": "5.0.0", "numpy": "2.4.6", "pandas": "3.0.5", "rbfopt": "4.3.0"}, "preflight_only_dependencies": {"distribution_paths": {"Pygments": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support", "iniconfig": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support", "packaging": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support", "pluggy": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support", "pytest": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support"}, "executable": "/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-nlp-overnight/bin/python", "packages": {"Pygments": "2.21.0", "iniconfig": "2.3.1", "packaging": "26.3", "pluggy": "1.7.0", "pytest": "9.1.1"}, "python": "3.11.16"}, "python": "3.11.16"}, "FMQA_PYTHON": {"distribution_paths": {"dimod": "/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-fmqa-qhd/lib/python3.11/site-packages", "dwave-samplers": "/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-fmqa-qhd/lib/python3.11/site-packages", "numpy": "/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-fmqa-qhd/lib/python3.11/site-packages", "torch": "/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-fmqa-qhd/lib/python3.11/site-packages"}, "executable": "/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-fmqa-qhd/bin/python", "packages": {"dimod": "0.12.21", "dwave-samplers": "1.6.0", "numpy": "2.2.6", "torch": "2.8.0+cpu"}, "preflight_only_dependencies": {"distribution_paths": {"Pygments": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support", "iniconfig": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support", "packaging": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support", "pluggy": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support", "pytest": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support"}, "executable": "/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-fmqa-qhd/bin/python", "packages": {"Pygments": "2.21.0", "iniconfig": "2.3.1", "packaging": "26.3", "pluggy": "1.7.0", "pytest": "9.1.1"}, "python": "3.11.16"}, "python": "3.11.16"}, "MIDFO_PYTHON": {"distribution_paths": {"PyNomadBBO": "/local/scratch/a/lee4382/repository/RBFopt_Test/pr56_dantzig_ready_20261031_c4d7db6b/.venv-mi-dfo/lib/python3.11/site-packages", "numpy": "/local/scratch/a/lee4382/repository/RBFopt_Test/pr56_dantzig_ready_20261031_c4d7db6b/.venv-mi-dfo/lib/python3.11/site-packages", "pandas": "/local/scratch/a/lee4382/repository/RBFopt_Test/pr56_dantzig_ready_20261031_c4d7db6b/.venv-mi-dfo/lib/python3.11/site-packages", "scipy": "/local/scratch/a/lee4382/repository/RBFopt_Test/pr56_dantzig_ready_20261031_c4d7db6b/.venv-mi-dfo/lib/python3.11/site-packages", "soogo": "/local/scratch/a/lee4382/repository/RBFopt_Test/pr56_dantzig_ready_20261031_c4d7db6b/.venv-mi-dfo/lib/python3.11/site-packages"}, "executable": "/local/scratch/a/lee4382/repository/RBFopt_Test/pr56_dantzig_ready_20261031_c4d7db6b/.venv-mi-dfo/bin/python", "packages": {"PyNomadBBO": "4.6.0", "numpy": "2.4.6", "pandas": "2.3.3", "scipy": "1.17.1", "soogo": "2.1.0"}, "preflight_only_dependencies": {"distribution_paths": {"Pygments": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support", "iniconfig": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support", "packaging": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support", "pluggy": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support", "pytest": "/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/test_support"}, "executable": "/local/scratch/a/lee4382/repository/RBFopt_Test/pr56_dantzig_ready_20261031_c4d7db6b/.venv-mi-dfo/bin/python", "packages": {"Pygments": "2.21.0", "iniconfig": "2.3.1", "packaging": "26.3", "pluggy": "1.7.0", "pytest": "9.1.1"}, "python": "3.11.16"}, "python": "3.11.16"}}`.
Every numeric worker used one thread and one logical CPU on a distinct observed idle physical core.
Planned runs: 210; completed: 210; result failures: 0; worker failures: 0; worker timeouts: 0; missing: 0; duplicates: 0.
Execution failures and timeouts remain in the planned denominator of ten seeds per method-budget condition.
Best-known objective: `24895.552861` at positions `[8, 8, 12, 17, 17, 21]`.
Best-known means the best accepted observed value from this campaign or the specified same-protocol pilot, not a global optimum or a proven lower bound.
Unique cache entries: 3499; recorded NLP calls: 3500; exact total identifiable: False.
Unique cache rows and recorded solved_now counters are not an exact total NLP-call count: concurrent cache misses can solve the same point before INSERT OR IGNORE, and non-forked workers may report that race as cached; prior native attempts can also be uncounted. The existing cache and recording code are unchanged.
Preflight solves use separate temporary data and are excluded from campaign statistics.
Original ZIP: `evidence/catalytic_distillation_live_dantzig_20261101_030054.zip`; bytes: 1808154; SHA256: `1ff96f101b3e30cbb0c47663af13d5d8fc680eb1466c425868e1e25825718e26`; CRC passed.

| Method | Budget | Planned | Result files | Completed | Hits |
| --- | ---: | ---: | ---: | ---: | ---: |
| bam | 25 | 10 | 10 | 10 | 0 |
| bam | 50 | 10 | 10 | 10 | 0 |
| bam | 100 | 10 | 10 | 10 | 0 |
| dsda | 25 | 10 | 10 | 10 | 0 |
| dsda | 50 | 10 | 10 | 10 | 0 |
| dsda | 100 | 10 | 10 | 10 | 3 |
| fmqa_sa | 25 | 10 | 10 | 10 | 0 |
| fmqa_sa | 50 | 10 | 10 | 10 | 0 |
| fmqa_sa | 100 | 10 | 10 | 10 | 0 |
| miso | 25 | 10 | 10 | 10 | 0 |
| miso | 50 | 10 | 10 | 10 | 1 |
| miso | 100 | 10 | 10 | 10 | 3 |
| nomad | 25 | 10 | 10 | 10 | 0 |
| nomad | 50 | 10 | 10 | 10 | 0 |
| nomad | 100 | 10 | 10 | 10 | 0 |
| rbfopt | 25 | 10 | 10 | 10 | 0 |
| rbfopt | 50 | 10 | 10 | 10 | 1 |
| rbfopt | 100 | 10 | 10 | 10 | 1 |
| uniform | 25 | 10 | 10 | 10 | 0 |
| uniform | 50 | 10 | 10 | 10 | 0 |
| uniform | 100 | 10 | 10 | 10 | 0 |

Reproduce with a fresh offline package, the recorded environment and CPU-range repairs, and the existing environments:

```bash
export DFO_PYTHON='/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-nlp-overnight/bin/python'
export FMQA_PYTHON='/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig-fmqa-qhd/bin/python'
export MIDFO_PYTHON='/local/scratch/a/lee4382/repository/RBFopt_Test/pr56_dantzig_ready_20261031_c4d7db6b/.venv-mi-dfo/bin/python'
export COIN_BIN='/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig/bin'
export BAM_LICENSE_FILE='/local/scratch/a/lee4382/bamlice.txt'
export GAMS_EXE='/package/gams/54.3/gams'
unset CPUS
bash '/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/RUN.sh'
bash '/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/STATUS.sh'
bash '/local/scratch/a/lee4382/repository/pr57_catdist_offline_20261031/COLLECT.sh'
```

The original model, configuration, cache policy, optimizer settings, and native statuses remain unchanged.
The orchestration selects idle physical cores only within logical CPU 17-48 and records the preflight-only binding of the original test's CPU argument.
Only this packaged result directory is intended for the PR; the working output, environment, and license files must not be staged.
