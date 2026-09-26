# Full GDP benchmark refresh

Current results: [analysis and findings](analysis/README.md).

The September 25 GDPopt/BARON run replaces the contaminated September 22 CPU 0 run. The old raw archive, extracted files and derived comparisons were deleted from this repository working tree.

- [Original ZIP](../archives/dantzig_gdp_compare_20260925_172020_5m9m_kxx.zip) and [checksums](raw/SHA256SUMS).
- `raw/`: unmodified server records, all 204 internal checksums verified.
- `analysis/`: 36 independently rechecked saved solutions, objective/time tables, NLP statuses and bound conflicts.
- [Updated DFO/GDP comparison](../fmqa_20260925/analysis/nlp/README.md).

GDP used CPU 2, FMQA Grid CPU 0, and FMQA cases CPU 4; their recorded physical cores are distinct. One-thread settings are retained. No exclusive server reservation is claimed.

Reproduce the audit with `python gdp_comparison_analysis.py`. Generated PNG/PDF figures remain local by user instruction.
