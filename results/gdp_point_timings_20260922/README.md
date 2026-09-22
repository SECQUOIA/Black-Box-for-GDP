# Dantzig GDP point timings — September 22, 2026

Measured fixed-integer NLP costs for **Column, CSTR30, Small Batch and Dynamic**
using GAMS 52.2 on Dantzig. CSTR5–25 measurements, Mac validation runs and the
earlier missing-dependency run are excluded. This dataset does not change the
historical lookup objectives or performance-profile figures.

The main table is [points.jsonl](points.jsonl): one JSON object per
`(case, cstr_size, point, solver)`. It contains 1,779 rows. GAMS IPOPT, IPOPTH
and CONOPT remain separate; no result is silently substituted across solvers.

| Case | Points per solver | IPOPT accepted | IPOPTH accepted | CONOPT accepted |
|---|---:|---:|---:|---:|
| Column | 64 | 29 | 26 | 29 |
| CSTR30 | 465 | **465** | 459 | 464 |
| Small Batch | 27 | 12 | 12 | 12 |
| Dynamic | 37 | 37 | 37 | 37 |

IPOPT's CSTR30 count includes seven successful retries. Its original pass
accepted 458/465. The repaired points are `(5,1), (5,3), (6,2), (6,4), (23,2),
(26,2), (29,3)`. CONOPT's `(26,9)` retains its GAMS availability error, and
IPOPTH's six nonaccepted CSTR30 outcomes remain nonaccepted. All attempted
points, including preprocessing rejections and failures, retain measured costs.
Solver acceptance indicates the recorded local/optimal termination and primal
feasibility checks; it does not certify global optimality.

## Files and provenance

- `points.jsonl`: selected result per coordinate and solver, timings, status,
  initialization, selected attempt ID and full attempt history IDs.
- `attempts.jsonl`: all **1,786 original records** (1,779 initial attempts plus
  seven retries), nested without altering their recorded values; each has an
  original run/path/SHA256 and an initial/retry label.
- `dynamic_preparation.json`: deduplicated one-time model/DAE preparation.
- `summary.json`: per-case/solver coverage, acceptance and recorded time sums.
- `provenance.json`: source run identities, selected job manifests, solver and
  model source versions, runtime/CPU settings, checksum verification evidence
  and merge-script hash. Original source manifests included more CSTR sizes;
  only the published jobs are retained here.
- `sources/`: original Python runner snapshots, requirements and license from
  each run. Server shell files are excluded.
- `SHA256SUMS`: checksums for the machine data and original source snapshots.

Source runs:

1. `dantzig_gdp_gams_20260922_050038_p4q8hy54`
2. `dantzig_cstr30_retry_20260922_153133_ld1g1zau`

Both extracted archives passed their full internal SHA256 verification. The
retry's recorded parent identity matches the original run, and the seven
repaired records use the same original model source. Original archives and
full solver logs remain local; this publication includes the result records
and reproducibility metadata without the large archives.

## Which time to use

All time fields are seconds. A missing measurement is `null`, never zero.

| Field | Meaning |
|---|---|
| `solve_wall_s` | GAMS interface call, including process/file overhead |
| `total_wall_s` | Selected point evaluation, including model preparation and validation |
| `worker_process_wall_s` | Fresh Python worker lifetime; recorded only for the seven retries |
| `all_attempts_total_wall_s` | Sum of original and retry evaluation costs for this same solver/coordinate |

The first three timers overlap; do not add them. `all_attempts_total_wall_s`
is a sum of separately measured attempts, not an observed sequential fallback
or end-to-end DFO runtime. The CSTR30 IPOPT selected evaluations sum to
832.0176 s; including the seven original failures gives 840.4877 s. These sums
exclude outer runner/preflight/archiving time. Each row retains its own time;
do not replace the measurements by a uniform two-second cost.

The seven retries used `mass_balance_zero_recycle` initialization and independent
Python processes. Original CSTR30 attempts used constructor defaults in one
batch process. Thus the merged table mixes these explicitly labeled policies;
it is not a rerun of all 465 points under one initialization policy.

Dynamic's single shared preparation ID has a total cost of 0.1090063 s
(model construction 0.0647381 s + DAE discretization 0.0442682 s). The same ID
appeared in all three solver folders and is stored once. Point evaluation times
exclude it. Account for preparation once per modeled process, not once per point.

For a DFO trajectory, join by case, CSTR size, exact integer coordinates and an
explicit solver. A sum along a recorded lookup trajectory is a **retrospective
cost estimate**, since changing the objective/solver failures can also change
the trajectory. Repeated callbacks need an explicit cache policy; absent points
outside the enumerated logical domain are unmeasured, not zero-cost. Reusing
CSTR30 costs for a smaller integer domain means evaluating that domain with the
CSTR30 model, not claiming a measured CSTR5–25 model runtime.

## Reproduce and read

From the repository root, with the two original archives already extracted:

```bash
python scripts/merge_gdp_timings.py \
  --parent /path/to/dantzig_gdp_gams_20260922_050038_p4q8hy54 \
  --retry /path/to/dantzig_cstr30_retry_20260922_153133_ld1g1zau \
  --output /path/to/new_output_folder
```

This uses only Python's standard library, verifies all input file hashes,
filters to the four published cases, and refuses to overwrite a nonempty
output folder. No solver is called. Output is deterministic for the same inputs
and script version. Validate the saved files with `sha256sum -c SHA256SUMS`
inside this dataset directory (on macOS: `shasum -a 256 -c SHA256SUMS`).

```python
import json
from pathlib import Path

root = Path("results/gdp_point_timings_20260922")
points = [json.loads(line) for line in (root / "points.jsonl").read_text().splitlines()]
cstr30_ipopt = {
    tuple(row["point"]): row for row in points
    if row["case"] == "cstr" and row["cstr_size"] == 30 and row["solver"] == "gams_ipopt"
}
print(cstr30_ipopt[(5, 3)]["total_wall_s"])
```
