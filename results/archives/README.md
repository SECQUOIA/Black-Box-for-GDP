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
| Full GDPopt / BARON comparison, September 22 | [dantzig_gdp_compare_20260922_181805_4u7k1d0n.zip](dantzig_gdp_compare_20260922_181805_4u7k1d0n.zip) |
| FMQA-SA process cases, September 25, CPU 4 | [dantzig_fmqa_20260925_174150_2m7pmr0d.zip](dantzig_fmqa_20260925_174150_2m7pmr0d.zip) |
| FMQA-SA Grid, September 25, CPU 0 | [dantzig_fmqa_grid_20260925_172020_9n7j9oh1.zip](dantzig_fmqa_grid_20260925_172020_9n7j9oh1.zip) |

Verify from the repository root:

```bash
shasum -a 256 -c results/archives/SHA256SUMS
```

The two September 25 FMQA ZIPs passed CRC validation, all 4,964 internal file
checksums, source and coordinate audits, and completion checks (139 case runs
and 1,050 Grid runs). Their source hashes and CPU topology appear in
[the published result provenance](../fmqa_20260925/publication.json).
The September 22 FMQA archives and derived result files were deleted by user
instruction because of their overlap with GDP jobs on CPU 0. They are not
inputs to current analyses. The other archive bytes are unchanged.

These nine ZIPs contain the current FMQA runs and the other supplied benchmark
archives. Earlier GDP point failures remain part of their provenance; archiving a run does
not make every outcome a successful or globally certified solution. The
unmodified GDP archives retain all originally run CSTR sizes. The curated
point-timing dataset remains CSTR30-only under
`results/gdp_point_timings_20260922/`; extracted FMQA data remain under
`results/fmqa_20260925/`. The full GDPopt/BARON comparison is still the September
22 run, pending receipt of its CPU 2 rerun; its timing caveat remains explicit.

Four shell wrappers have byte-identical copies in the remaining September 22 result ZIPs:
`run_gdp_dantzig.sh`, `run_gdp_gams_dantzig.sh`,
`run_cstr30_retry_dantzig.sh` and `run_gdp_comparison_dantzig.sh`.
The current FMQA archives use Python entry points and contain no shell wrappers.
The original September 10 and BAM ZIPs do not contain the local
`run_dantzig.sh` or `run_bam_dantzig.sh` wrappers.
