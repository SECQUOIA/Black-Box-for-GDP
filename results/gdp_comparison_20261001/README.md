# October 1 GDPopt RIC/GLOA — completed BARON/HiGHS results

All **18/18 jobs completed**, with feasible saved incumbents: RIC and GLOA
on CSTR5/10/15/20/25/30, Column, Dynamic and Small Batch. Eight jobs ended at
the time limit and ten report `optimal`; a GDPopt status string is not a
global-optimality certificate. All 18 vectors pass an independent check in
the original GDP models at primal-feasibility tolerance 1e-5.

The run used Dantzig GAMS 52.2, BARON NLP subproblems, HiGHS MIP masters,
one thread and logical CPU 2 (physical core 2, socket 0). BARON used CLP/CBC
internally (`LPSol 8`) and IPOPT local search (`NLPSol 9`).

The original process survived the SSH disconnect. The previous tar.gz was
copied while Column RIC was still running; its 12 completed CSTR records are
identical to the final records. The full archive supersedes that snapshot.
The superseded partial archive and its checksum sidecar were removed from the
publication tree because the snapshot contained a solver license file; see
[publication sanitization](../../docs/publication_sanitization.md).
Its completed CSTR records remain in the final ZIP. The partial snapshot is
not selected for comparisons and no six-job restart result is used.

- [Original final ZIP](../archives/dantzig_gdp_compare_20261001_175249_6lvrs3wy.zip)
  and [server checksum](../archives/dantzig_gdp_compare_20261001_175249_6lvrs3wy.zip.sha256).
- `raw/`: exact run/summary records and the original checksum inventory.
  Logs, solver-call histories, source snapshots and saved vectors are retained
  in the ZIP. All **115** internal file hashes remain verifiable using the
  [archive guide](../archives/README.md#reviewing-detailed-records).
- `publication.json`: archive identity, completion count and CPU topology.
- `analysis/`: derived comparisons and independent validation without solving.
- [Five-method comparison](../gdp_comparison_current/analysis/README.md): these
  18 jobs plus nine LOA jobs and 18 September 25 Big-M/Hull jobs.

RIC reaches or improves the lookup target on 3/9 models and GLOA on 1/9.
All six CSTR GLOA jobs return worse objectives than feasible RIC solutions
despite reporting `optimal`. Column and Dynamic stop at their first BARON
NLP subproblem's time limit for both methods; saved incumbents are preserved.

Reproduce the audit and tables with `python gdp_current_analysis.py`.
