# Execution evidence

The Dantzig run used the unchanged experiment at revision c186408728c6f95ac33a5465edd53035d85c5620.
The original launcher is experiments/dsda_no_revisit/run_dantzig.sh at that revision.
The recorded command, interpreter, CPU topology, PID, start and finish timestamps, and zero exit code are in ../wrapper_execution.json.
The experiment manifest and original launcher log are preserved in the parent result directory and its evidence/ directory.

wrapper/ contains byte-identical copies of the scripts, configuration, tests, and manifests from the A offline transfer package.
Its PACKAGE_CONFIG.json restricts the package to task A.
The full source snapshot inside the approximately 510 MB transfer ZIP is already available in Git at the execution revision and is not duplicated in this result commit.
deployment.json records the transfer ZIP checksum, original server paths, and the hashes of all included wrapper files.
The complete-package SHA256 manifest is retained as provenance, including entries for the omitted source snapshot.
The archived wrapper needs that original source.git snapshot to launch, so use the pinned experiment launcher below for a fresh reproduction.

The offline wrapper creates a separate detached worktree without GitHub authentication, selects an allowed idle physical core, pins the experiment, preserves the existing checkout and environments, and validates and collects the return.
It coordinates physical-core assignments with the separate B package, although A does not depend on B.
No optimizer, model, target, initial point, seed, budget, stopping rule, or cached response is changed by the wrapper.

The observed invocation was equivalent to the following command from /local/scratch/a/lee4382/repository/dsda_no_revisit:

```bash
DSDA_PYTHON=/local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig/bin/python \
DSDA_CPU=47 \
DSDA_OUTPUT=/local/scratch/a/lee4382/repository/dsda_no_revisit_output_20261031_230829 \
bash experiments/dsda_no_revisit/run_dantzig.sh
```

For a new run, use a new output directory and an allowed idle core under the server allocation policy rather than reusing the recorded destination.
The original launcher supports DSDA_CPU=auto for its idle-core selection.
The original run output and logs remain unchanged on Dantzig.
