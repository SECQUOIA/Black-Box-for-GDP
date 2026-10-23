CSTR unaccepted response = 10^6; Dantzig transfer bundle

Returned-data analysis is now available at:
  results/cstr_penalty_1e6_analysis_20261022/README.txt
All 120 runs completed on Dantzig; no execution failures. D-SDA hits stayed
15/60; RBFOpt primary hits changed from 56/60 to 45/60. Original returned and
submitted ZIPs are preserved byte-for-byte. Analyze without rerunning searches:
  python experiments/cstr_penalty_1e6/analyze.py --output /tmp/cstr_penalty_replay
The preparation instructions and local validation counts below describe the
submitted bundle before the returned run; see the analysis audit for run status.

Exactly 120 runs: CSTR N=5,10,15,20,25,30; B=8,15,22,29,36,43;
D-SDA and primary RBFOpt; original seeds 0..9 and three ordered archived starts.
Both methods use the SAME 1,000,000 unaccepted response. Accepted objectives,
raw NLP status, logical rejection and original acceptance stay unchanged.

Transfer this ZIP anywhere on Dantzig, extract to a NEW directory, then:
  unzip cstr_penalty_1e6_dantzig_20261022.zip
  cd cstr_penalty_1e6_runner
  sha256sum -c SHA256SUMS
  bash run_dantzig.sh dry-run
  bash run_dantzig.sh check
  nohup bash run_dantzig.sh run > launch.log 2>&1 < /dev/null &
  tail -f launch.log

dry-run validates hashes, 120 slots, inputs, original starts and penalty range;
it requires only Python's standard library and performs no optimization.
check additionally checks actual Dantzig environments and runs protocol tests,
without starting any optimization. run repeats these checks before searching.
Default Python is the ACTUAL archived runtime:
  /local/scratch/a/lee4382/repository/RBFopt_Test/.venv-dantzig/bin/python
The older generic wrapper defaulted to .venv-dantzig-nlp-overnight, but the
archived primary results used .venv-dantzig. This bundle preserves the recorded
Python/Bonmin/IPOPT paths, Python 3.11.16, NumPy 2.4.6, SciPy 1.17.1,
RBFOpt 4.3.0/Pyomo 6.10.0 and DSDA pandas 2.3.3. No package installation.
Exact method package versions, host and auxiliary binary hashes are checked.
CSTR_PYTHON/CSTR_CONDA can select the existing environment/conda launcher;
strict historical checks still apply. --cpu N optionally selects an allowed CPU.
All numerical threads=1; sequential isolated workers; hard watchdog=2100s.
The original CPU separation procedure is reused, without changing other jobs.

Output directory is NEW each time:
  /local/scratch/a/lee4382/repository/RBFopt_Test/results/cstr_penalty_1e6_TIMESTAMP_RANDOM/
RESULT_DIR and RESULT_ZIP are printed. Existing repository/data/solver/output
paths are not renamed, moved, replaced or edited. Read-only frozen copies in
this package are portable; provenance/manifest.json and each plan entry retain
the original archive paths and exact members. New trajectories preserve callback
order, repeated visits, rejection statuses and algorithm return/delivery flags.

After the controller stops:
  bash run_dantzig.sh status --run-dir /absolute/RESULT_DIR
  bash run_dantzig.sh resume --run-dir /absolute/RESULT_DIR
  bash run_dantzig.sh pack --run-dir /absolute/RESULT_DIR
Resume executes only genuinely unstarted jobs. Completed, failed or interrupted
attempts are never replaced by successful retries. Interrupted attempts become
execution_failed, with partial callbacks preserved. The inherited controller
lock prevents a second controller while an orphan worker remains alive.
Use a run directory, not a check directory, for continuation of actual execution.

Primary baseline selection (no mixing with sensitivity variants)
  DSDA: ipopt_dfo_cstr_20261015_174637_r1dzn5tk, 60 CSTR jobs.
  RBFOpt: review_comparison_20261020_124949, 60 CSTR MSRSM/auto/genetic jobs.
The old generic CSTR source defaults to solver search. Each frozen RBFOpt spec
here explicitly uses genetic and all actual settings must equal the recorded
GENETIC primary settings. Auxiliary solvers are retained for local/refinement
steps. No new package initialization: init_node_pos=archived starts,
init_node_val=None, do_init_strategy=False. RBFOpt seed and all defaults match.
DSDA uses the full integer box, unit L-infinity neighborhood, original first-tie
order, discrete line search, 1e-12 tolerance and best ACCEPTED initial point.
If none of the three starts is accepted, the original failure rule is retained.

Implementation and processing path
  provenance/penalty.patch is the only algorithm-boundary change to the frozen
  original ipopt_dfo_cstr.py. The explicit spec key unaccepted_response=1000000
  is permitted only for CSTR DSDA/RBFOpt. Omitted or '+inf' keeps legacy behavior.
  No entire-repository substitution. Original sources and PR49 source hashes
  are recorded; no commit or push is made by this package.
  Original Oracle directly returned +inf to DSDA/RBFOpt (no prior finite map).
  Now it returns 1e6 only for original evaluated rejections or declared logical
  exclusions. Missing required lookup rows, invalid coordinates or code errors
  remain errors. Finite penalty never changes accepted=False.
  RBFOpt 4.3.0 applies its UNCHANGED function_scaling=auto and
  dynamism_clipping=auto. Effective dynamism clipping is median; when dynamism
  exceeds 1000, large response values may be clipped to the observed median.
  At cycle decisions function scaling chooses log if observed median-minimum
  exceeds 1e6, otherwise off. Thus 1e6 is the boundary response, not a promise
  that the RBF model sees an untransformed 1e6. actual_settings.json,
  effective_rbfopt_settings.json and installed module hashes are retained.

Budget and accounting
  Every actual lookup callback, including the initial three and repeated points,
  is charged. Internal cache hits without callbacks are not charged. A method
  that naturally stops before B stays stopped. Callback B records its raw result
  and then raises the original BudgetStop; it does not deliver a numeric value
  to the optimizer. The final accepted summary includes callback B. Its explicit
  value_returned_to_optimizer=false is preserved. Beyond-B requests are errors,
  blocked before table access and recorded as attempted callbacks, not charges.
  Tests check boundary responses, original behavior, all 60 ordered designs,
  terminal observation, no-accepted result, failures and missing cost handling.

Reports after execution
  jobs/*/callbacks.jsonl: original callback path, raw objective/candidate/status,
    accepted flag, method_value, penalty_applied, delivery flag and timestamps.
  jobs/*/{runtime,actual_settings,process,result}.json and optimizer.log.
  runs.csv, paired_comparison.csv: best ACCEPTED objective/point, target hit,
    first target evaluation, charges, accepted/rejected counts, status, time,
    baseline values and changes. Never treat a penalty as an incumbent/target.
  summary.csv/json: size/method target hits out of 10. Execution failure remains
    excluded from success even when an earlier callback observed the target.
  callbacks.csv: cost ledger keyed by model/size/coordinates and repeated visits.
  rbfopt_coordinates.csv: RBFOpt-only coordinates in callback order, grouped by
    case/seed/job; includes requested and integer coordinates, repeats, objective,
    acceptance and penalty/delivery flags, including callback B. Every individual
    run also keeps its original durable jobs/*/callbacks.jsonl trajectory.
  Estimated completion = measured search - measured lookup + per-callback
    historical cost sum. Original selected NLP attempts and same-size structural
    rejection supplement are retained. Missing costs remain null and are listed;
    no borrowed other-size costs or zero filling. Search time is separate.
  README.txt, run.json, reproduction/: outcomes, commands, hashes and provenance.

No real Dantzig searches were performed while preparing this ZIP. The authorized
120 slots remain to be run there. Local protocol checks are not server timing.
Even with pinned software, load, CPU choice and logging differ; wall-clock
changes cannot be attributed exclusively to penalty. No extra +inf control runs
are scheduled. BAM/FMQA/sampling/other benchmarks, NLP enumeration, manuscript,
Overleaf and old figures/tables/results are not changed or rerun.
