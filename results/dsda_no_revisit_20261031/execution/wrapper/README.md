# PR #56: D-SDA no-revisit

This ZIP runs only task A, with 1,470 planned results.
The two packages can run concurrently and do not depend on each other.
The original algorithms, models, settings, environments, and licenses remain unchanged.
This wrapper installs nothing and refuses to run experiments outside Dantzig.

## Upload from the Mac

```bash
cd /Users/albertlee0125/Repos/RBFopt_Test/results/runners
scp pr56_dsda_offline_20261031.zip pr56_dsda_offline_20261031.zip.sha256 lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/
```

## Extract and launch on Dantzig

```bash
cd /local/scratch/a/lee4382/repository
if sha256sum -c pr56_dsda_offline_20261031.zip.sha256 && test ! -e pr56_dsda_offline_20261031; then
  unzip pr56_dsda_offline_20261031.zip && bash pr56_dsda_offline_20261031/RUN.sh
else
  echo "Checksum failed or extraction directory already exists; nothing overwritten."
fi
```

RUN.sh returns immediately after starting a detached supervisor.
SSH disconnection does not terminate the experiment.
Unzipping alone does not execute anything.
Start the other package independently without waiting for this experiment to finish.

```bash
bash /local/scratch/a/lee4382/repository/pr56_dsda_offline_20261031/STATUS.sh
bash /local/scratch/a/lee4382/repository/pr56_dsda_offline_20261031/COLLECT.sh
```

STATUS.sh reports real process identity, terminal records, validation, and errors.
Logs and metadata are retained under state/ in this package.
After validated collection, the result return and checksum are generated automatically.
COLLECT.sh also creates a status-only ZIP after the supervisor stops, including safe diagnostics for a failed or blocked stage.
Private GAMS listings remain on the server and are excluded from diagnostic returns.

## Revision and CPU protection

Required branch: `review/manuscript-revision-20261030`.
Required execution SHA: `c186408728c6f95ac33a5465edd53035d85c5620`.
The branch head was verified through GitHub when this ZIP was built; its timestamp is in REMOTE_VERIFICATION.json.
The server uses the bundled exact commit and verifies its integrity without contacting GitHub.
No GitHub username, password, token, fetch, clone, or pull is needed on the server.
A live remote-head comparison at execution time is unavailable offline and is not claimed.
Every tracked source and input file at the pinned commit is included in a self-contained Git snapshot.
Unneeded external submodule pointers are preserved without downloading those repositories.
The existing checkout at /local/scratch/a/lee4382/repository/RBFopt_Test stays on its current branch.
A new detached worktree is created, with a new name if the requested directory already exists.
Existing changes are not stashed, reset, deleted, or overwritten.
A newly discovered AGENTS.md stops unattended execution for review.
No remote is added or changed in the existing repository.
Local Git commands create an isolated worktree from source.git inside this package, preserving the exact execution SHA.
The packages coordinate Git preparation and CPU assignments through `/local/scratch/a/lee4382/repository/.pr56_57_coordination/`.
Only Git preparation is serialized; the actual experiments run independently.
Both packages sample CPU activity for five seconds and require at least 95% observed idle time on all SMT siblings.
CPUs must be allowed by the launching process affinity and belong to distinct physical cores.
The common allocation record prevents the two packages from choosing the same physical core.
This record coordinates these packages only and does not reserve resources against other server users.
Server allocation policy takes precedence, and no other user process is moved or stopped.
Numerical libraries use one thread; workers remain pinned after selection.
When no suitable core is available, the package reports the obstacle instead of forcing a busy CPU.

## Task A

A uses one physical core and the existing RBFopt_Test/.venv-dantzig/bin/python.
It invokes experiments/dsda_no_revisit/run_dantzig.sh unchanged.
The experiment searches stored configuration responses without new GDP/NLP solves.
The plan contains 1,050 Grid jobs and 140 Process jobs for each of single, ranked, and ranked_random.
The original checks and an independent data-only audit must pass for all 1,470 jobs.
Grid cross-check hits at B=10/30/50/70/100 are 13/78/91/101/101 out of 210 each.
Process single/ranked/ranked_random cross-check hits are 79/80/80 out of 140 each.
A disagreement blocks validation without changing the measured output.
The audit checks uniqueness, historical replay, the distinct historical prefix, non-worsening objectives, retained historical hits, and matching first descents.
The original archive, checksum, logs, and summaries are preserved.
An English README and audit metadata are added to the dated result directory.
RETURN_A.zip is available independently of B.

## Download results from the Mac

```bash
mkdir -p /Users/albertlee0125/Downloads/pr56_results_20261031
scp 'lee4382@dantzig.ecn.purdue.edu:/local/scratch/a/lee4382/repository/pr56_dsda_offline_20261031/RETURN_A.zip*' /Users/albertlee0125/Downloads/pr56_results_20261031/
```

For a failed or blocked stage, run COLLECT.sh and download its named RETURN_STATUS ZIP and checksum instead.
The ZIP contains no automatic Git commit, push, PR comment, Slack message, or manuscript edit.
Return the evidence for independent review before the already requested result-only commit, ordinary push, and PR summary comment.
Do not publish virtual environments, standalone caches, working directories, or license files.

## Package checks

PACKAGE_SHA256.json protects the transfer files and is verified before launching.
SOURCE_MANIFEST.json records the pinned source tree, every tracked file's Git object ID, and SHA256 hashes of the relevant experiment files.
PACKAGE_VALIDATION.json records local wrapper checks only; it does not claim Dantzig preflight or experiment success.
