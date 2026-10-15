# Published Dantzig runners

These are frozen ZIPs prepared for Dantzig experiments.
Each includes a source snapshot and an internal SHA256 inventory;
the adjacent `.zip.sha256` checks the whole ZIP. Historical instructions inside
the bundles reflect their preparation dates. The October 1 outcomes are in the
[completed comparison](../gdp_comparison_current/analysis/README.md).

- [RIC/GLOA BARON + HiGHS](gdpopt_baron_highs_runner.zip): nine models, two
  methods, CPU 2, one thread, 1,800 seconds per job.
- [LOA BARON + HiGHS on CPU 6](gdpopt_loa_cpu6_runner.zip): nine models, LOA
  only, one thread, 1,800 seconds per job. CPU topology is checked before launch.

The original run-specific source snapshots also remain in the final result
archives. The unused 15-job follow-up wrapper and local bundle were removed;
they were never an experimental source. Current execution instructions are in
[`docs/gdpopt_baron_highs.md`](../../docs/gdpopt_baron_highs.md) and
[`docs/gdpopt_loa_baron_highs.md`](../../docs/gdpopt_loa_baron_highs.md).

## CSTR full-box IPOPT measurements

The [5/10/15 runner](cstr_box_ipopt_5_10_15_20261015.zip) remains unchanged.
Its returned 350-coordinate data is retained under
[`results/cstr_box_ipopt`](../cstr_box_ipopt/INDEX.txt), including the CSTR10
rejected attempt at `[10,1]`.

The [20/25 runner](cstr_box_ipopt_20_25_20261015.zip) plans all 1,025 coordinates
with the same mass-balance initialization, solver settings and acceptance rule.
Its `run.sh` selects only sizes 20 and 25. See the
[execution instructions](../../docs/cstr_box_ipopt_dantzig.txt).

## Column and Dynamic full-box IPOPT measurements

The [full-box runner](column_dynamic_box_ipopt_20261015.zip) measured all 81
Column and 72 Dynamic coordinates, including logical/preprocessing exclusions
and IPOPT failures. The [verified return](../column_dynamic_box_ipopt/INDEX.txt)
preserves every time and unchanged accepted objectives (29 Column, 37 Dynamic).
The frozen IPOPT DFO runners and their earlier inputs remain unchanged.

## Original DFO trace runner

The frozen [October 2 executed runner](dantzig_dfo_trace_nlp_20261002.zip) records 417 original lookup searches and separate visited-coordinate costs, reusing the original 139 FMQA traces. It is preserved byte-for-byte, including its historical instructions. Current instructions are [English](../../docs/dfo_trace_nlp_dantzig.md), and newly built bundles use `README.md` in English. The [completed result report](../dfo_trace_nlp_20261002/analysis/README.md) supersedes the runner's preliminary tables.

The withdrawn expanded online experiment bundle is retained only in ignored local review storage and is not a published runner.

The October 14 [DSDA v5 recovery ZIP](process_dsda_fairness_20261014_v5.zip)
preserves 139 returned jobs and remeasures only CSTR15/B22/seed9. It repairs
the audit tolerance check and reuses the four existing same-coordinate CSTR
logical-rejection costs with explicit donor provenance. No NLP measurements
are launched. See [completed results and reproduction](../../docs/process_dsda_fairness_dantzig.txt).
