# Preserved GDPopt diagnostic package

This is the original October 23 solver-free investigation supplied for review.
Its [report](REPORT.md) is retained byte-for-byte; statements about no commit or
push describe that original investigation, before this evidence import.
The [new SCIP return analysis](../../results/grid_scip_20261023/README.md)
reconciles it with all four completed Dantzig result archives.

Detailed input copies, analysis sources, scripts, logs and candidate patches are
stored once in [dantzig_package.zip](dantzig_package.zip). The package is an
analysis snapshot and a prepared diagnostic runner, not the result of executing
that runner on Dantzig. Its accounting records zero new optimizer calls.

The original [SHA256SUMS](SHA256SUMS) covers 235 files. Most are ZIP members under
`gdpopt_20261023/`; four files not included in that ZIP remain at their original
relative paths here: the ZIP itself, its sidecar, `package_manifest.json`, and
`inputs/cstr_witness/package_manifest.json`. `REPORT.md` is also exposed for
reading. The ZIP has its own `PACKAGE_SHA256SUMS`, and the supplied external
inventory is intentionally unchanged. Verification resolves each listed path
inside the ZIP first, then in this directory:

```bash
python scripts/analyze_grid_scip_return.py --output /tmp/grid-scip-audit
```

To inspect or repeat the original solver-free probes, extract the package to a
temporary directory and follow its archived README. Do not execute the prepared
Dantzig optimization commands as part of an audit. The new analysis reran its
five solver-free regressions on a temporary copy; the original evidence here
was not rewritten. Candidate Pyomo patches remain diagnostic evidence and have
not been applied to the executed SCIP benchmark or repository dependencies.
