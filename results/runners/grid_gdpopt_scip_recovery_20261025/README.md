# Error-only Grid SCIP recovery delivery

The three ZIPs contain exactly 46 error jobs: RIC 12, LOA 19 and GLOA 15.
They use CPUs 12, 14 and 16 and leave the original combined run on CPU 6 alone.
The five original time limits and twelve reported-optimal jobs are excluded.
Each ZIP is a complete independent package with its own checksum and result directory.
COMMANDS_RIC.txt, COMMANDS_LOA.txt and COMMANDS_GLOA.txt provide separate upload, launch, tail and download blocks.
An OK checksum message only verifies bytes; the launch block and RUN_DIR/START/DONE logs establish execution.
The launch command refuses to overwrite an already extracted runner directory.
No Dantzig solver was executed during package preparation.
The original analysis is stored in results/grid_gdpopt_scip_20261025, and the recovery source and policy are in experiments/grid_scip_recovery.
All 961 bohachevsky2 configurations and bounded network-recovery behavior pass solver-free regression checks.
Validation also verifies the exact 46-job selection, frozen budgets and SCIP routing, package integrity, rejected scope changes and preservation of unfinished GAMS diagnostic files.
The new bounded retries cannot guarantee network or license-service availability, and a failed preflight must be investigated before interpreting the run.
Future results must be paired and reported separately from the preserved original first attempts.
