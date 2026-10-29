Three independent Grid GDPopt SCIP packages, 2026-10-25.
Each ZIP runs all 21 Grid problems from the beginning with one method.
RIC uses CPU 12, LOA CPU 14 and GLOA CPU 16.
The original 63-job Grid execution on CPU 6 is left running separately.
The server launcher checks all six experiment CPU IDs 6, 8, 10, 12, 14 and 16 for distinct allowed physical cores before solver execution.
CPU affinity does not reserve a core against unrelated server jobs.
Each new method has a separate result directory and result_zip.txt pointer.
Each problem retains its 1800-second worker budget, so each 21-job method has a 10.5-hour cumulative worker budget plus preparation and packaging.
MIP and NLP solver routing both remain GAMS/SCIP.
All 59 unchanged base payload files, including optimization source, model and input bytes, retain their original hashes.
Package metadata, README and manifests are updated, and a method-specific launch wrapper is added.
Grid coordinate paths, solver calls and returned solution vectors remain recorded by the original runner.
Use COMMANDS_RIC.txt, COMMANDS_LOA.txt and COMMANDS_GLOA.txt for separate upload, execution, progress, solver-log and download commands.
Upload and download commands run on the Mac; start and log commands run on Dantzig.
START/DONE progress is recorded for all 21 jobs, and RESULT_ZIP identifies the generated return archive.
A partial or preflight-failed archive is distinguished by all_jobs_finished and completed_jobs in its summary.
The source builder, exact base ZIP hash, per-package manifests and local validation results are included beside the ZIPs.
Local verification checks all checksums, standalone 21-job plans, exact method and solver routing, separate output roots, duplicate-launch exclusion, CPU-conflict blocking, shell syntax and Ruff.
CPU conflict tests use synthetic topology; actual Dantzig CPU availability and topology are checked at launch time.
No new solver or server benchmark was executed while creating these packages.
The delivered ZIPs have independent SHA256 sidecars.
