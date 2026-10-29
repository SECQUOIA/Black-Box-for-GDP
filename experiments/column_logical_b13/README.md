# Column logical-domain and budget follow-up

This independent follow-up uses the 17-tray Column model, external bounds x1=8..15 and x2=1..8, and budget B=13 including three common initial observations.
Its frozen plan contains exactly five methods, ten seeds per method and 50 jobs, with at most 650 objective callbacks.
The methods are D-SDA, RBFOpt with genetic global candidate search, native-budget BAM, FMQA-SA and uniform sampling without replacement.
No BAM-prefix, GDPopt, MINLP reformulation, other model or other budget is added.
No commit, push, manuscript, Overleaf or existing representative figure/table update is part of this task.

The current publication manifest identifies the historical Column cohort, which is unchanged by the later CSTR30 publication overlay.
The same cost_table_column.csv bytes are present in the representative October 20 execution archive.
The original 81-coordinate table contains 64 original IPOPT records and 17 separately measured logical rejections.
Seventeen is the excluded-coordinate count, calculated as 81 minus 64, and is distinct from the old evaluation budget B=16.
The new input preserves the exact 64 original objective, acceptance and cost rows, including 29 accepted and 35 unaccepted configurations.
Every selected row is checked against its own archived point record and checksum.
The 17 excluded coordinates comprise the nine with x1=7 and the nine with x2=9, with the overlap counted once.
No accepted-only filter, new initialization, new process NLP solve, solver remeasurement or best-of-attempt selection occurs.

The pinned Column source, external-information helper and Boolean logic are inspected without solving a model.
All 225 original external coordinates are checked, proving that the requested 64-coordinate rectangle is exactly the logical domain.
Physical tray 9 corresponds to external position 8, and the external order is reflux YR followed by boilup YB.
The algebraic minimum-tray constraint remains represented by original preprocessing and acceptance records rather than by an additional search-space filter.
The fixed reference remains coordinate (13,4), objective 19346.124801006445, with absolute difference tolerance 1e-5 times max(1,abs(reference)).

The builder executes the byte-preserved original LHC generator with its original generation versions, NumPy 2.4.4 and SciPy 1.17.1.
It first reproduces all ten original 81-coordinate initial designs, then independently generates the new three-point designs from the new bounds.
Every method receives the same ordered design for its seed, even when its initial points are unaccepted.
The original integer rounding and duplicate-handling procedure is preserved.
The generation versions differ from some worker environments by design, as they did in the archived execution.

All optimizer implementations are loaded from the selected archived execution sources, whose bytes remain unchanged under frozen/.
The old 3,430-job runner is neither modified nor used as the new controller, and its original complete input audit is rerun unchanged.
RBFOpt retains disabled additional package initialization, genetic candidate search, native stopping and permitted Bonmin/IPOPT surrogate calls.
D-SDA and RBFOpt retain a 1e6 unaccepted response, BAM retains NaN, and FMQA-SA retains its original infinite raw response, training-target and fallback rules.
BAM's internal surrogate work remains included in measured search overhead, while RBFOpt auxiliary calls also retain their separate journal.
Uniform sampling retains the original independent hash-derived MT19937 stream and samples the remaining new-domain points without replacement.
Only bounds, budget-derived counts and common initial designs are changed.
An external diagnostic wrapper records any request after callback 13 without changing archived oracle responses or source bytes, and such a request is reported as an execution failure even if a backend swallows its exception.
Runtime versions, actual settings, binary hashes and source hashes are checked before interpreting a run.

The controller is restricted to Linux CPU 2 and runs one worker at a time.
Before any benchmark, seven occupancy samples spanning at least 12 seconds inspect CPU 2, its actual SMT siblings, process/thread affinities, activity and any detected scheduler allocation.
The v3 guard requires each sibling to remain at or below 5% busy in every interval and at or below 2% busy across the full accounting window.
A fully unrestricted affinity mask is distinguished from evidence of observed activity on CPU 2 or its sibling.
An existing compute process with a constrained affinity mask overlapping the core still blocks launch, even when sleeping.
Observed running or active threads from other processes on the core, unknown process permissions and unresolved resource allocation still block launch.
The exact /opt/microsoft/mdatp/sbin/wdavdaemon executable with unrestricted online-CPU affinity is assessed by the unchanged per-interval and full-window CPU load caps.
Its activity remains in CPU accounting, raw process samples and the visible CPU_BACKGROUND log record.
A constrained service affinity, unknown affinity or elevated CPU load still blocks launch.
The guard does not modify, stop or reconfigure the system service.
The controller prints the load measurements, blocking reasons and relevant process details directly to launch.log.
Uncertain availability, an overlapping compute process, an unverified scheduler allocation or observed load above the conservative threshold prevents launch.
The guard never chooses another CPU, stops another experiment or changes another process's affinity.
Existing SCIP jobs are outside this experiment and remain untouched.
All numerical thread limits are one, CUDA is disabled, and workers plus their subprocesses inherit CPU 2.
Affinity does not create an exclusive reservation, and the launch-time occupancy evidence is retained.

The recorded existing Python executables are used directly or through their existing conda prefix when required.
No packages are installed or upgraded, and no shared environment is modified.
Preflight checks all five environments without executing a seed or invoking a trial optimizer.
FMQA retains its 1,800-second native limit, and each actual worker retains the original 2,100-second watchdog.
A controller/worker-inherited file lock prevents duplicate launch even if the controller disappears before its worker.
Every completed outcome, including an algorithm failure, is sealed and is never automatically replaced.
Each result ZIP is a new immutable snapshot, so resuming a run never overwrites an earlier result archive.
An interrupted unsealed attempt can be resumed only with the explicit resume-interrupted option after its original worker has stopped, with the old attempt and reason preserved.

Use `bash run_dantzig.sh plan` to inspect the frozen plan without running optimization.
Use `bash run_dantzig.sh run` on Dantzig to check occupancy and environments, then execute all 50 jobs sequentially.
The launcher prints RUN_DIR, PREFLIGHT, START, DONE and RESULT_ZIP records.
Individual logs, callbacks, algorithm settings, runtime identities and termination records are retained under jobs/JOB_ID/attempt_NNNN/.
A checksum OK line confirms only file integrity and does not establish that a worker has started.

To resume an infrastructure-interrupted run, use `bash run_dantzig.sh resume --run-dir /absolute/RUN_DIR --resume-interrupted` after verifying that the original launcher is stopped.
Completed jobs are reused only after their terminal checksums pass, and failures are not reclassified as infrastructure interruptions.
Use `bash run_dantzig.sh status --run-dir /absolute/RUN_DIR` to read progress.
Use `python analyze.py --run-dir /absolute/RUN_DIR --output /absolute/NEW_ANALYSIS_DIR` to replay analysis without optimization.
Matplotlib is optional for replay plots, while profiles.csv is always generated.
The result archive includes the complete execution package, inputs, original references, all attempts and logs, analysis and SHA-256 inventories.

The primary success test uses the final best accepted objective and preserves every failed seed in the denominator ten.
A target first seen at callback 13 counts even if the original callback then raises its terminal budget exception.
The evaluation profile uses the first target callback for successful runs, and the completion profile uses reconstructed full-run completion, matching the publication.
Reconstructed completion subtracts measured lookup time from search wall time and adds each callback's recorded point cost, including repeats and rejected responses.
This is a recorded-path estimate, not measured online optimizer-NLP execution time.
The 64/B13 cohort and 81/B16 cohort are shown separately, and no single-factor causal claim is made because both domain and budget change.
Pending jobs have no measured success rate or time median and must not be presented as zero-time failures.
