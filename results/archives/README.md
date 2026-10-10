# Original Dantzig result archives

These are the original result ZIPs currently committed to the repository.
They retain their original bytes, including any source snapshots and shell
scripts present in the server archive.

| Run | Original archive |
|---|---|
| DSDA / RBFOpt / BAM, September 10 | [dantzig_20260910_170759_slN8tv.zip](dantzig_20260910_170759_slN8tv.zip) |
| BAM 5.0.0, September 16 | [dantzig_bam_20260916_231228_FNzbAA.zip](../../dantzig_bam_20260916_231228_FNzbAA.zip) |
| Initial GDP point run, September 22 (dependency failures retained) | [dantzig_gdp_20260922_030057_6tb50i44.zip](dantzig_gdp_20260922_030057_6tb50i44.zip) |
| Updated GDP point run, September 22 | [dantzig_gdp_20260922_033846_u0tjt7i7.zip](dantzig_gdp_20260922_033846_u0tjt7i7.zip) |
| GAMS IPOPT / IPOPTH / CONOPT point runs, September 22 | [dantzig_gdp_gams_20260922_050038_p4q8hy54.zip](dantzig_gdp_gams_20260922_050038_p4q8hy54.zip) |
| Seven CSTR30 retries, September 22 | [dantzig_cstr30_retry_20260922_153133_ld1g1zau.zip](dantzig_cstr30_retry_20260922_153133_ld1g1zau.zip) |
| Full GDPopt / BARON comparison, September 25, CPU 2 | [dantzig_gdp_compare_20260925_172020_5m9m_kxx.zip](dantzig_gdp_compare_20260925_172020_5m9m_kxx.zip) |
| FMQA-SA process cases, September 25, CPU 4 | [dantzig_fmqa_20260925_174150_2m7pmr0d.zip](dantzig_fmqa_20260925_174150_2m7pmr0d.zip) |
| FMQA-SA Grid, September 25, CPU 0 | [dantzig_fmqa_grid_20260925_172020_9n7j9oh1.zip](dantzig_fmqa_grid_20260925_172020_9n7j9oh1.zip) |
| RIC/GLOA BARON + HiGHS, October 1, CPU 2, 18 completed jobs | [dantzig_gdp_compare_20261001_175249_6lvrs3wy.zip](dantzig_gdp_compare_20261001_175249_6lvrs3wy.zip) |
| LOA BARON + HiGHS, October 1, CPU 6, 9 completed jobs | [dantzig_gdp_compare_20261001_204801_1gfd4d02.zip](dantzig_gdp_compare_20261001_204801_1gfd4d02.zip) |
| Grid GDP, October 9, CPU 6, 20,181 point timings and 105 benchmark outcomes | [grid_gdp_run_20261008_210901_dw5vq37s.zip](grid_gdp_run_20261008_210901_dw5vq37s.zip) |
| Grid GDP retry, October 9, CPU 6, 21 error retries | [grid_gdp_retry_all_20261009_153057_czhvd9w7.zip](grid_gdp_retry_all_20261009_153057_czhvd9w7.zip) |
| Corrected Grid GDP retry, October 9, CPU 6, ten cases | [grid_gdp_retry_fixed_all_20261009_204028_lu6vdgkt.zip](grid_gdp_retry_fixed_all_20261009_204028_lu6vdgkt.zip) |
| RBFOpt Grid trajectories, October 10, CPU 0, all 1,050 runs | [grid_trace_rbfopt_20261008_190603_og2app39.zip](grid_trace_rbfopt_20261008_190603_og2app39.zip) |
| Superseded partial RIC/GLOA snapshot, not a comparison input | [gdpopt_baron_highs_20261001_partial.tar.gz](gdpopt_baron_highs_20261001_partial.tar.gz) |

Verify from the repository root:

```bash
shasum -a 256 -c results/archives/SHA256SUMS
```

The two September 25 FMQA ZIPs passed CRC validation, all 4,964 internal file
checksums, source and coordinate audits, and completion checks (139 case runs
and 1,050 Grid runs). Their source hashes and CPU topology appear in
[the published result provenance](../fmqa_20260925/publication.json).
The September 25 GDP archive passed all 204 internal checksums and all 36 saved
solutions passed independent original-GDP feasibility checks. Its CPU 2 is a
different physical core from both FMQA jobs. The September 22 FMQA and full-GDP
archives and derived result files were deleted by user instruction because of
their overlap on CPU 0. They are not inputs to current analyses.

The two final October 1 GDPopt ZIPs pass their supplied external checksums and
all 189 internal file checksums. Their 27 saved solutions pass independent
original-GDP feasibility checks. The partial tar.gz is retained as historical
evidence only; all 12 CSTR records already complete in it match the final ZIP.

These ZIPs contain the current FMQA runs and the other supplied benchmark
archives. Earlier GDP point failures remain part of their provenance; archiving a run does
not make every outcome a successful or globally certified solution. The
unmodified GDP archives retain all originally run CSTR sizes. The curated
point-timing dataset remains CSTR30-only under
`results/gdp_point_timings_20260922/`; extracted FMQA data remain under
`results/fmqa_20260925/`. The [current full-GDP comparison](../gdp_comparison_current/analysis/README.md)
uses the October 1 RIC/GLOA/LOA runs plus September 25 Big-M/Hull. The September 25
IPOPT RIC/GLOA results remain historical. Solver-reported
optimality is not automatically a valid global certificate; see its audit.

Three shell wrappers have byte-identical copies in the remaining September 22 result ZIPs:
`run_gdp_dantzig.sh`, `run_gdp_gams_dantzig.sh`,
and `run_cstr30_retry_dantzig.sh`.
The September 25 FMQA and full-GDP archives use Python entry points and contain
no shell wrappers. The October 1 GDPopt archives include their runner wrappers
in the source snapshots.

The October 9 Grid GDP archive passes CRC validation and all 807 internal
checksums. All 20,181 fixed-point evaluations succeeded. The 105 full-GDP
outcomes include 32 unsupported cases, 21 errors and one hard timeout; saved
feasible incumbents do not imply successful termination. The
[Grid GDP timing summary](../grid_gdp_20261009/README.md) includes exact exported
tables, per-method times and a reproducible analysis without new solver runs.
The [corrected ten-case retry](../grid_gdp_corrected_20261009/README.md) passes
all 130 internal hashes and independently matches every saved solution to the
CSV minimum. It has seven optimal terminations and three time limits, with no
errors. Its changed Pyomo processing profile is explicit; the earlier raw
results and all 20,181 IPOPT point measurements remain intact.
The [complete RBFOpt Grid trajectories](../grid_trace_rbfopt_20261010/README.md)
pass all 5,546 internal hashes and contain 1,050 complete runs, 54,600 ordered
objective callbacks and 7,514 unique grid/coordinate pairs. Every original
per-run JSONL is also extracted and indexed for use with the IPOPT point data.
The original September 10 and BAM ZIPs do not contain the local
`run_dantzig.sh` or `run_bam_dantzig.sh` wrappers.
