CSTR penalty 1e6: returned Dantzig data analysis

120/120 runs completed; 0 execution failures; 0 missing point costs.
D-SDA: 15/60 -> 15/60 target hits; 60/60 coordinate paths and 60/60 best objectives identical.
RBFOpt primary (MSRSM/auto/genetic): 56/60 -> 45/60 hits; 11 lost hits, 0 gained.
30/60 RBFOpt coordinate paths changed. Best accepted objective worsened in 13 runs,
was unchanged in 47, and improved in 0.

Hits per 10 seeds (+inf -> 1e6):
Size   Budget   D-SDA      RBFOpt
5      8        2->2       10->8
10     15       2->2       9->6
15     22       2->2       8->7
20     29       3->3       9->7
25     36       3->3       10->8
30     43       3->3       10->9

Interpretation
Within these fixed budgets/seeds, using 1e6 did not improve either method.
D-SDA begins from the best accepted initial point and accepts only improving moves;
every accepted lookup objective is below 10, so replacing +inf by 1e6 still rejects
the same unaccepted moves. Identical observed paths support this explanation.
RBFOpt models the responses; finite failures can affect its model/scaling and subsequent
candidate choices. Its auto scaling and median dynamism clipping were NOT changed.
The coordinate logs establish path changes; they do not isolate which internal scaling
or interpolation decision caused each divergence. No claim of universal optimal penalty.

Accounting and timing
2704 actual callbacks: 1174 D-SDA and 1530 RBFOpt.
D-SDA stopped naturally before B in 34/60 runs; RBFOpt in 0/60.
RBFOpt rejected callbacks: 490 -> 431; fewer rejections did not yield more target hits.
Three archived initial points, their order, full integer domain, budgets, settings,
repeated visits and terminal BudgetStop policy are preserved. Callback B is included
in best accepted/target summaries even though it is not returned to the optimizer.
A finite rejection never becomes accepted. Raw candidate objective/status remain intact.
Estimated completion = measured search - measured lookup + historical per-callback NLP cost.
Point keys include CSTR size and coordinates; repeated and rejected visits are charged.
CSTR30 uses the existing same-size structural rejection cost supplement. No NLP reruns.
RBFOpt median measured search: 0.986368 -> 0.849257 s.
RBFOpt median estimated completion: 37.887196 -> 39.706415 s.
These are descriptive medians across six sizes (10 seeds each), not paired speedup estimates.
Host, Python, package versions, platform and auxiliary solver binaries match the baselines.
CPU affinity is retained in runtime_audit.csv as execution metadata, not treated as
an explanation for the changed target hits or evaluation coordinates.
Installed RBFOpt module hashes are recorded for the new runs; the historical runtime
did not record these hashes, so installed source byte identity cannot be established.
No additional +inf control experiment was performed or included.

Reproduce from the repository root (standard library only; no archive code execution):
python experiments/cstr_penalty_1e6/analyze.py --output /tmp/cstr_penalty_analysis_replay
Optional static figures: add --plots using the existing matplotlib environment.

Files: audit.json; paired_runs.csv; condition_summary.csv; method_summary.csv;
callback_paths.csv (both policies); rbfopt_coordinates.csv (new RBFOpt); runtime_audit.csv.
Raw return ZIP and submitted runner ZIP are retained under results/archives and results/runners.
Original commands, paths, source/lookup hashes and raw JSONL callbacks remain in the ZIP.
Historical validation logs in the submitted bundle describe preparation, not returned run status.
No paper/Overleaf/source figure/table was replaced; this is a separate experiment report.

RBFOpt lost-hit seeds:
  cstr_5, seed 3: first path divergence at callback 4; objective 3.06201457661 -> 3.13019813303
  cstr_5, seed 7: first path divergence at callback 4; objective 3.06201457661 -> 3.13019813303
  cstr_10, seed 4: first path divergence at callback 4; objective 2.8895369686 -> 3.13019813303
  cstr_10, seed 7: first path divergence at callback 4; objective 2.8895369686 -> 3.13019813303
  cstr_10, seed 9: first path divergence at callback 4; objective 2.8895369686 -> 3.13019813303
  cstr_15, seed 3: first path divergence at callback 4; objective 2.82939406309 -> 3.13019813303
  cstr_20, seed 4: first path divergence at callback 4; objective 2.79940642511 -> 3.06201457662
  cstr_20, seed 7: first path divergence at callback 4; objective 2.79940642511 -> 3.06201457662
  cstr_25, seed 4: first path divergence at callback 4; objective 2.78148259268 -> 3.00727797421
  cstr_25, seed 7: first path divergence at callback 4; objective 2.78148259268 -> 3.13019813303
  cstr_30, seed 7: first path divergence at callback 4; objective 2.7695697199 -> 2.79125169782
