# Grid-only target stopping SCP workflow

The installer is ready and the full Dantzig experiment has not yet started.
Local validation passed 13 semantic tests and three Grid smoke comparisons against the retained baseline source in the same local environment.
The Csendes local CSV parser differs from the archived Dantzig values by at most 5.293955920339377e-23, while callback coordinates and same-environment old/new prefixes are exact.
The server gate still requires exact callback values and descent-prefix agreement against the original Dantzig return and does not relax comparison tolerances.

Run this transfer in the Mac terminal.

```bash
scp /Users/albertlee0125/Repos/RBFopt_Test/results/dsda_grid_target_stop_preparation_20261028/dsda_grid_target_stop_run.py lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/RBFopt_Test/
```

Run the installer and launcher in the authenticated Dantzig terminal.

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
.venv-dantzig/bin/python dsda_grid_target_stop_run.py
```

The command installs experiments/dsda_grid_target_stop, validates the retained baseline archive, checks other D-SDA workflow locks, records the repository state and running-process snapshot, and launches in the background.
The detached process runs the Grid-only tests, selects an observed idle physical core, pins one logical CPU, runs three Grid smoke jobs, and then runs the 1050-job cohort sequentially.
It prints PID, LOG, RESULTS, and EXPECTED_RETURN_ARCHIVE paths and continues after SSH disconnects.
Use tail -f with the printed LOG path to monitor actual CPU selection and completion.
The final RETURN_ARCHIVE and SHA256 lines identify the completed result to download into ~/Downloads/ using SCP.
The first target-hit callback and actual termination callback are recorded separately.
No Process job, other method, new NLP, GAMS, or SCIP solve is allowed.
No commit, push, PR update, CI request, or manuscript change is performed by this installer.
Publication to PR 52 is pending the real Dantzig return and independent verification.
