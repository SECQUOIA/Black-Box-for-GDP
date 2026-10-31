# Main-text joint process completion comparison

This presentation-only follow-up uses the completed joint SCIP-master/IPOPT-subproblem analysis.
No optimizer, NLP solver, or benchmark is rerun.
The six panels show CSTR5 B=8, CSTR30 B=43, Column B=13, Small Batch B=10, and Dynamic B=12 and B=30.
The CSTR endpoints and two Dynamic budgets connect the target-rate and cost examples discussed in the main text.
The full fourteen-condition figures remain in `results/joint_process_scip_ipopt_20261030`.

All ten DFO seeds per method and condition remain visible, including misses and failures.
Gray intervals and median ticks summarize all ten completion estimates using inclusive, linearly interpolated quartiles.
Conventional GDP methods each contribute one observation, not an estimated success probability.
The two Dynamic panels repeat the same five conventional observations, so 450 plotted marks represent 445 distinct saved runs.
These are 420 DFO runs and 25 distinct conventional runs.
NOMAD and MISO come from the audited Dantzig return of PR #56 (`results/pr56_dantzig_return_20261031`).
The right-hand labels show DFO hits out of ten or the single conventional yes/no outcome.
Stars retain the existing bound-conflict flags.
TL labels retain reported `maxTimeLimit` outcomes, including those whose measured time is below the configured 1800-second limit.
The axis retains actual measured times; no value is silently replaced by 1800.

DFO full-run completion costs are reconstructed from search overhead and separately measured configuration costs.
Conventional completion times are measured and include model preparation.
These are neither first-hit times nor equal-work NLP counts.
Existing target rules, completion times, statuses, source links, and execution revisions are unchanged.
The detailed conventional objective/time table and the former DFO-only completion profiles are retained in the Overleaf supplement.
This directory supplies the new figure rather than replacing historical manuscript bundles.

Reproduce from the repository root into a fresh directory:

```sh
python -m review_comparison.joint_process_main --output /tmp/joint-process-main
```
