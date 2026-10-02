# October 1 GDPopt LOA — completed BARON/HiGHS results on CPU 6

All **9/9 jobs completed**, with feasible saved incumbents: six CSTR sizes,
Column, Dynamic and Small Batch. Six jobs ended at the time limit and three
report `optimal`. All nine vectors pass an independent original-GDP
feasibility check at tolerance 1e-5. LOA on these nonconvex models does not
receive a global certificate solely from its termination status or BARON use.

The run used Dantzig GAMS 52.2, BARON NLPs, HiGHS MIP masters and one thread
on logical CPU 6 (physical core 8, socket 0; sibling 54). The concurrent
RIC/GLOA run used logical CPU 2, physical core 2, so the recorded physical
cores differ. This does not establish an otherwise idle server.

- [Original final ZIP](../archives/dantzig_gdp_compare_20261001_204801_1gfd4d02.zip)
  and [server checksum](../archives/dantzig_gdp_compare_20261001_204801_1gfd4d02.zip.sha256).
- `raw/`: exact final archive contents. All **74** internal file hashes match.
- `publication.json`: archive identity, completion count and CPU topology.
- `analysis/`: completed-job table, solver-status audit and saved-vector checks.
- [Five-method comparison](../gdp_comparison_current/analysis/README.md).
- [Runner instructions](../../docs/gdpopt_loa_baron_highs.md).

LOA reaches or improves the lookup target on 4/9 models. Three are symmetric
matches within tolerance; CSTR15 is better than the lookup value and is
counted separately by the one-sided attainment metric. Its independently
checked maximum primal violation is about 5.63e-7. This difference does not
certify a new global optimum.

LOA improves on RIC's objectives for CSTR15/20/25/30. Column and Dynamic
stop at their first BARON NLP subproblem's time limit and return the same
incumbents as RIC/GLOA. Raw statuses, clocks and objectives are retained.

Reproduce validation and tables with `python gdp_current_analysis.py`.
