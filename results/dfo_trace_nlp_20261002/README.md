# Dantzig DFO trace and NLP timing import — October 2, 2026

Start with the [verified English report, tables and figures](analysis/README.md).

The original [ZIP](../archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip) and [checksum](../archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip.sha256) preserve all 7,968 checksummed evidence files, including ordered callback traces, point results, job completion records and the executed source snapshot. They are immutable evidence. Current English runner instructions are in [the runner guide](../../docs/dfo_trace_nlp_dantzig.md).

The archive was extracted locally under `results/dantzig_review/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p/`. The extracted copy is ignored by Git to avoid duplicating thousands of archived files. Reproduction verifies and extracts the archive automatically into a temporary directory; it never runs an optimizer or NLP solver.

```bash
python dfo_trace_analysis.py
```
