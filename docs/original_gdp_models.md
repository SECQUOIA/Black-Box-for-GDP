# Original GDP models and actual NLP evaluations

The existing Dantzig experiments evaluate precomputed objective tables. Their
recorded runtime includes optimization and lookup overhead, but **does not
include solving the GDP's fixed-integer NLP subproblems**. The new `gdp_models`
package provides a separate, actual model/solver path. It does not change the
existing benchmark, data, or performance-profile figures.

For the Dantzig setup/run/ZIP/download workflow, use
[the server guide](gdp_dantzig.md) and `python -m gdp_models.dantzig`.

## Original sources

Both upstream repositories are Git submodules with fixed revisions. Their model
files are unchanged; they are not copied or relicensed as this project's code.

| Source | Pinned revision | Models |
| --- | --- | --- |
| [SECQUOIA/dsda-gdp](https://github.com/SECQUOIA/dsda-gdp/tree/3e469dbeea8931670b8cd6752014ab7a767d3af5) | `3e469dbeea8931670b8cd6752014ab7a767d3af5` | Column, CSTR, Small Batch |
| [SECQUOIA/LD-SDA-Dynamic](https://github.com/SECQUOIA/LD-SDA-Dynamic/tree/482e14ebf9caabbd35d959986942cb028778a1d7) | `482e14ebf9caabbd35d959986942cb028778a1d7` | Nine-stage nonlinear Dynamic |

`dsda-gdp` retains its upstream `LICENSE.md`. The pinned Dynamic checkout does
not contain a license file; this repository's MIT license does not apply to
that external source. Git stores a reference to its original repository.

## Setup and execution

Run from a checkout of this repository:

```bash
git submodule update --init -- external/dsda-gdp external/ld-sda-dynamic
python -m pip install -e ".[gdp]"
```

An external solver is required: IPOPT on `PATH`, or GAMS with an available
BARON license. The Python extra installs model dependencies, not solvers or
licenses. The adapter is tested with Pyomo 6.10.0; the extra restricts it to
the 6.10 series because the upstream sources use legacy Pyomo APIs.

Evaluate a CSTR subproblem using GAMS/BARON:

```bash
python -m gdp_models --case cstr --cstr-size 5 --point 3,1 \
  --solver baron --time-limit 60 --output results/live_gdp/cstr5_3_1.json
```

Other representative subproblems:

```bash
python -m gdp_models --case column --point 13,4 --solver ipopt
python -m gdp_models --case small_batch --point 2,2,1 --solver ipopt
python -m gdp_models --case dynamic --point 1,4 --solver ipopt
```

Use `--executable /path/to/ipopt` (or `/path/to/gams` for `--solver baron`) if
needed. Reports are printed as JSON; `--output` additionally saves one report.
GAMS availability, version checks and solves use that executable even when a
different GAMS is on `PATH`. Reports record the resolved effective GAMS path;
batch manifests also hash that binary.
Exit status is 0 for an accepted solution, 1 for a rejected/failed solve, and
2 for invalid arguments or missing source/configuration. `--tee` sends solver
output to stderr.

The same entry points are available in Python:

```python
from gdp_models import build_gdp, prepare_nlp, evaluate_point

gdp = build_gdp("cstr", cstr_size=5)             # original, unfixed GDP
nlp = prepare_nlp("cstr", (3, 1), cstr_size=5)  # fixed continuous subproblem
result = evaluate_point("cstr", (3, 1), solver="baron", cstr_size=5)
if result["accepted"]:
    objective = result["objective"]
```

For installations outside an editable checkout, `RBFOPT_GDP_SOURCES` can point
to a directory containing both pinned source checkouts. Source submodules are
not bundled into the Python wheel. Restart Python after changing a source:
loaded source definitions are cached for the process lifetime.

## Enumerate all integer combinations

`gdp_models.batch` evaluates external integer tuples sequentially, using the
same actual NLP evaluator as the single-point command. It does not enumerate
the exponentially larger space of all independent disjunction indicators.
No objective or feasibility lookup table is used to choose candidates.

For a complete local Small Batch run (27 tuples):

```bash
python -m gdp_models.batch --case small_batch --solver ipopt \
  --executable /Users/albertlee0125/Solvers/ampl.macos64/ipopt \
  --output-dir results/live_gdp/small_batch_all
```

On Dantzig, omit `--executable` when the solver is on `PATH`. For CSTR 30:

```bash
python -m gdp_models.batch --case cstr --cstr-size 30 --solver ipopt \
  --time-limit 60 --output-dir results/live_gdp/cstr30_ipopt
```

IPOPT failures are retained as unsuccessful outcomes, with no automatic
BARON fallback. To evaluate using BARON, select `--solver baron` and a separate
output directory. Solver limits apply to each point, not the entire batch.

The default `--domain logical` removes only combinations disallowed by the
GDP logic. These are candidate counts, not claims of continuous feasibility:

| Case | Default logical candidates | `--domain box` |
| --- | ---: | ---: |
| CSTR with `NT` positions | `NT*(NT+1)/2` | `NT*NT` |
| CSTR 30 | 465 | 900 |
| Column 17 | 64 | 225 |
| Small Batch | 27 | 27 |
| Dynamic, nine stages | 37 | 72 |

Column's default candidates satisfy reflux position `>=8` and boilup
position `<=8` (physical feed tray 9). Its minimum-tray algebraic constraint
and all other continuous constraints are checked during preparation/solving.
The filter is regression-tested against the original static GDP logic.

Use `--domain box` to include every tuple inside the original external
bounds, including logically invalid coordinates. This is useful when a DFO
trace includes such points and their rejection costs are also needed. The
default logical run has no measured cost for the tuples it excludes.

To inspect the complete coordinate list without solving or writing files:

```bash
python -m gdp_models.batch --case cstr --cstr-size 30 --solver ipopt --dry-run
```

### Output and restart

The output directory contains:

- `evaluations.csv`: one row per completed evaluation, including `x1`, `x2`,
  `x3` where applicable, objective, termination, and separate wall times.
- `records/point_*.json`: full, atomically saved per-point checkpoints.
- `manifest.json`: ordered candidate list, options, source/code hashes,
  initialization, solver executable/version, and machine identity.
- `summary.json`: candidate/completion counts, status counts, best accepted
  point and objective, and sum of recorded evaluation times.
- `run.log`: model diagnostics and exceptions; add `--tee` for solver transcripts.

The console reports progress after each completed point. Missing timing values
remain blank in CSV; they are not replaced with zero. Preprocessing-infeasible
points have no solver call, but their total evaluation cost is recorded.
`last_invocation_wall_s` covers only the latest batch invocation;
`sum_evaluation_wall_s` sums the saved complete point evaluations across
invocations. It excludes discarded work on an interrupted point and batch I/O,
so it is not total elapsed batch time or a DFO end-to-end runtime.

For a short first run, add `--max-points 3`. Continue with the same command
and output directory, remove that limit, and add `--resume`:

```bash
python -m gdp_models.batch --case small_batch --solver ipopt \
  --executable /Users/albertlee0125/Solvers/ampl.macos64/ipopt \
  --output-dir results/live_gdp/small_batch_all --resume
```

`Ctrl+C` retains finished JSON checkpoints. A point interrupted before its
checkpoint is committed is evaluated again. Resume rebuilds CSV from JSON,
then skips **all saved evaluations**, including infeasible, rejected, and
error outcomes. Use a new output directory for changed settings or a fresh
retry experiment. Resume rejects changes to candidates, initialization,
source/adapter code, solver binary/version, or machine identity; `--tee` and
`--max-points` may change. A file lock prevents simultaneous writers on macOS
and Linux. An existing nonempty directory requires explicit `--resume`.

Batch exit status 0 means the invocation finished normally (possibly paused
by `--max-points`), not that every NLP was feasible. Recorded model/solver
exceptions cause exit status 1; configuration errors use 2; `Ctrl+C` uses 130.
Inspect `summary.json` for completion and acceptance counts. Unexpected model
errors do not prevent the remaining coordinates from being evaluated.

Local validation completed all 27 Small Batch candidates using IPOPT 3.12.13:
12 accepted solutions and 15 preprocessing-infeasible points, with no model
or solver errors. A three-point pause followed by resume produced exactly 27
CSV rows and 27 JSON records; best accepted point `(2,2,1)` had objective
`167427.6571499716`. These are local adapter checks, not Dantzig benchmark results.

## Integer coordinates and initialization

| Case | External coordinates | Notes |
| --- | --- | --- |
| Column | `(reflux position, boilup position)` | Positions in the ordered interior-tray set: `(13,4)` selects physical trays `(14,5)`. The original external ranges are `1..15`; GDP logic further restricts them. The old lookup benchmark uses `(7,1)..(15,9)`. |
| CSTR | `(feed/reactor cutoff, recycle position)` | Each coordinate is `1..NT`; recycle must be in the active reactor section. `--cstr-size` sets `NT`. |
| Small Batch | `(mixer units, reactor units, centrifuge units)` | The original GDP allows `1..3` for each coordinate; the old benchmark starts at `(2,2,1)`. |
| Dynamic | `(last stage in mode 1, last stage in mode 2)` | Bounds `(1,2)..(9,9)`; `x < y` or `(9,9)`. The latter keeps all stages in mode 1. |

Every evaluation uses an independent model. Static evaluations build it afresh;
Dynamic evaluations clone one unsolved, discretized template per process.
`--initialization auto` loads the
upstream saved continuous-variable values when available; otherwise it uses
the constructor defaults and records that choice. There is no trajectory
warm start, objective cache, or lookup-table feasibility filter.

The pinned static source includes saved starts for Column 17, Small Batch,
and CSTR sizes 4–25. **CSTR 30 has no saved initialization**. Use
`--initialization saved` to require a saved start and fail if it is missing,
or `--initialization default` to explicitly use constructor defaults. Dynamic
uses its constructor defaults. These continuous initializations are separate
from the outer optimizer's integer starting points.

Dynamic uses the upstream experiment's 30 finite elements per stage, three
Radau collocation points, reconstructed disjunct constraints, and derivative
bounds `[-300,300]`. Static models receive FBBT; CSTR additionally receives
constraint propagation. Reports record these choices and actual source-file
SHA-256 hashes alongside the pinned commit.

Dynamic's DAE conversion is performed once per process, including during
preflight, and reused for all integer combinations. Neither fixing nor solving
a clone changes the template's initial values. The one-time model build and
DAE times are saved in `dynamic/preparation.json`, separately from point costs.
Resuming in a new process adds one preparation entry; points reference it via
`preparation_id`.

## Timing and result interpretation

For a common-interface GAMS 52.2 comparison of IPOPT, IPOPTH and CONOPT, use
`python -m gdp_models.dantzig check --solvers gams_ipopt,ipopth,conopt`
followed by the same command with `run`; see
[the server comparison guide](gdp_dantzig.md#gams-522-ipopt-ipopth-and-conopt-comparison).
Single-point/batch solver names are `gams_ipopt`, `ipopth`, and `conopt`, with
`--executable` pointing to GAMS. `ipopt` continues to select the native binary;
`baron` continues to use GAMS. The three-way wrapper keeps the prior `auto`
initialization and evaluates each solver independently.

Each report separates:

- `setup_wall_s`: construction (or Dynamic template cloning), initialization,
  logic fixing, and source provenance. Source loading is included if not cached.
- `preprocess_wall_s`: bound tightening, constraint propagation, and the
  check that no unfixed integer variables or active disjunctions remain.
- `solve_wall_s`: the solver interface call, including its process/file
  overhead. This is wall time, not the solver's reported CPU time.
- `total_wall_s`: the evaluation, including result validation. For Dynamic,
  this excludes one-time template construction and DAE conversion.

Logically or preprocessing-infeasible points return before calling a solver;
their elapsed total time is still recorded. Both retain status
`preprocessing_infeasible` and termination `not_solved`. The additive
`rejection_phase` field in JSON and CSV distinguishes `logical` (original GDP
Boolean rules) from `preprocessing` (FBBT or constraint propagation); it is
null for other outcomes. For example, Column `(1,15)` is rejected by logic,
while `(8,8)` fails FBBT on its minimum-tray constraint.
`time_limit_s` is the solver's
limit, not a strict limit on total wall time. A setup error or unavailable
solver must not be treated as a zero-cost successful evaluation.

`objective` is returned only when the solver reports `optimal`,
`locallyOptimal`, or `globallyOptimal`, the value is finite, and the maximum
absolute primal violation is within the configured tolerance (default
`1e-5`). A feasible incumbent after a timeout is retained as
`candidate_objective`, but is not accepted under this policy. Native solver
termination is preserved. IPOPT and `locallyOptimal` results do not establish
global optimality.

The CSTR representative point was validated with GAMS/BARON. An earlier IPOPT
probe at that point failed; therefore solver choice is an explicit required
argument, not an implicit successful fallback.

## Validation and next benchmark step

Local actual-solve checks at four representative points matched the existing
lookup objectives within `1e-4` absolute error. Local validation artifacts were
archived under the ignored `results/dantzig_review/` directory during cleanup.
They validate model connections, not full-domain solvability or comparative
optimizer performance. The subsequent Dantzig GAMS run and seven-point retry
provide accepted IPOPT results for all 465 CSTR30 points under explicitly
recorded initialization policies. The [published timing dataset](../results/gdp_point_timings_20260922/README.md)
retains those measurements and prior failures, together with Column, Small
Batch and Dynamic. Smaller CSTR measurements are excluded from publication.

Before producing GDP timing profiles, run each outer optimizer against this
actual evaluator with the same integer starts, per-case solver settings,
continuous initialization, failure policy, and hardware. Record every point,
objective, termination, and cumulative wall time, including the first time a
target is reached. The existing lookup-based DSDA runner uses pre-enumerated
feasible points, so it needs an explicit live-objective integration too;
replacing just its objective table is insufficient.

Summing freshly measured NLP costs along an old trace can provide an estimated
cost for that fixed trajectory. It cannot recover the original run's true
wall time, warm-start effects, or a new search trajectory when solver outcomes
change. The existing time-profile figures still describe lookup experiments.

## Compatibility layer and tests

The adapter omits Column's unused import of the removed `MasterProblemResult`
class. It loads only the original external-variable and logic helper function
definitions from upstream drivers, avoiding unrelated obsolete GDPopt imports.
Their function bodies and the original mathematical models are unchanged.
Column's associated Boolean values are synchronized before validating logic.

```bash
python -m pytest tests/test_gdp_models.py tests/test_gdp_batch.py -q
```

These tests require the GDP extra and source submodules, but no solver license.
They check model mappings, logic, discretization, CSTR 30 initialization, and
rejection of timeouts or infeasible candidates despite positive solver status.
Batch tests also cover complete coordinate coverage, interruption/restart,
CSV recovery, incompatible configuration rejection, and failure recording.
