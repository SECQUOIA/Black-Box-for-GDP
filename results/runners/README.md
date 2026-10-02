# Published GDPopt runners

These are the frozen ZIPs prepared for the completed October 1 Dantzig
experiments. Each includes a source snapshot and an internal SHA256 inventory;
the adjacent `.zip.sha256` checks the whole ZIP. Historical instructions inside
the bundles reflect their preparation dates. The current outcome is documented
in the [completed comparison](../gdp_comparison_current/analysis/README.md).

- [RIC/GLOA BARON + HiGHS](gdpopt_baron_highs_runner.zip): nine models, two
  methods, CPU 2, one thread, 1,800 seconds per job.
- [LOA BARON + HiGHS on CPU 6](gdpopt_loa_cpu6_runner.zip): nine models, LOA
  only, one thread, 1,800 seconds per job. CPU topology is checked before launch.

The original run-specific source snapshots also remain in the final result
archives. The unused 15-job follow-up bundle is retained locally, not used as
an experimental source. Repository scripts and current instructions are in
[`docs/gdpopt_baron_highs.md`](../../docs/gdpopt_baron_highs.md) and
[`docs/gdpopt_loa_baron_highs.md`](../../docs/gdpopt_loa_baron_highs.md).
