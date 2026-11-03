# Third-party source notices

Original project code is covered by the root [MIT license](LICENSE).
The source components below retain their upstream notices and terms; the root
license does not replace them. Historical execution archives also retain source
snapshots and their original provenance.

## Vendored FMQA sources

The retained source imports are pinned independently:

| Local directory | Upstream source revision | Retained notice |
| --- | --- | --- |
| `fmqa_benchmark/vendor/bbo_via_fmqa` | [SECQUOIA/bbo_via_fmqa](https://github.com/SECQUOIA/bbo_via_fmqa/tree/4bd0aa331cd2f996e7a0507e8fc236cf43ad4e63), `4bd0aa331cd2f996e7a0507e8fc236cf43ad4e63` | [MIT, copyright 2026 SECQUOIA](fmqa_benchmark/vendor/bbo_via_fmqa/LICENSE) |
| `fmqa_benchmark/vendor/tsudalab` | [tsudalab/fmqa](https://github.com/tsudalab/fmqa/tree/51d827d1f88d602278dd0ab5e827ac4fbf8f0b29), `51d827d1f88d602278dd0ab5e827ac4fbf8f0b29` | [MIT, copyright 2019 Tsuda Laboratory](fmqa_benchmark/vendor/tsudalab/LICENSE) |
| `fmqa_benchmark/vendor/qhd` | [SECQUOIA/bbo_via_fmqa, QHD_Data](https://github.com/SECQUOIA/bbo_via_fmqa/tree/eb3a20d4b5a3773d17ff31d72a35d51f58e84e56), `eb3a20d4b5a3773d17ff31d72a35d51f58e84e56` | [SECQUOIA MIT notice and incorporated Tsuda Laboratory MIT notice](fmqa_benchmark/vendor/qhd/LICENSE.SECQUOIA), plus the [FM package MIT notice](fmqa_benchmark/vendor/qhd/fmqa/LICENSE) |

The QHD repository notice was obtained separately from upstream revision
`e92ac6c9840f74c54fbc8031c5df8bbb1a7f3f3e`; it does not change the pinned source
revision. File hashes, source paths, and the notice provenance are retained in
[the original import manifest](fmqa_benchmark/vendor/provenance.json) and
[the QHD import manifest](fmqa_benchmark/vendor/qhd/provenance.json).
The [adapter guide](docs/fmqa_adapter.md) describes which source definitions
are used and which historical drivers are retained as references.

## Copied and adapted catalytic distillation sources

The original catalytic distillation models, D-SDA code, initialization files,
and neighborhood files in `gdp_models/catalytic_distillation` come from
[SECQUOIA/dsda-gdp](https://github.com/SECQUOIA/dsda-gdp/tree/3e469dbeea8931670b8cd6752014ab7a767d3af5)
at `3e469dbeea8931670b8cd6752014ab7a767d3af5`, principally
`catalytic_distillation/dsda-gdp-cd-column`. The MINLP work also follows the
upstream `catalytic_distillation/dsda-minlp-cd-column` formulation.
The [model guide](gdp_models/catalytic_distillation/README.md) and
[model review](gdp_models/catalytic_distillation/REVIEW.md) describe local
translations, corrections, and derived formulations.

The exact upstream `LICENSE.md` is retained beside the copied sources as
[LICENSE.dsda-gdp](gdp_models/catalytic_distillation/LICENSE.dsda-gdp).
It contains the IDAES PSE Framework copyright, three redistribution conditions,
disclaimer, and enhancements provision. These terms apply to the incorporated
upstream source; it is not relicensed under the root MIT notice.
The MATLAB neighborhood generator has its own
[copyright 2006 Matt Fig notice](gdp_models/catalytic_distillation/neighborhood_MATLAB/license.txt),
which is retained separately.

## Pinned external submodules

| Submodule | Pinned revision | License status at that revision |
| --- | --- | --- |
| [external/dsda-gdp](https://github.com/SECQUOIA/dsda-gdp/tree/3e469dbeea8931670b8cd6752014ab7a767d3af5) | `3e469dbeea8931670b8cd6752014ab7a767d3af5` | Upstream [LICENSE.md](external/dsda-gdp/LICENSE.md), also retained in the copied-source notice above; nested components retain their separate notices. |
| [external/ld-sda-dynamic](https://github.com/SECQUOIA/LD-SDA-Dynamic/tree/482e14ebf9caabbd35d959986942cb028778a1d7) | `482e14ebf9caabbd35d959986942cb028778a1d7` | No license file is present in the pinned source. The maintainer confirmed ownership and redistribution permission on November 3, 2026; the root MIT notice does not relicense it. |

The companion package builder expands both submodules into its ZIP. The
maintainer confirmed that Dynamic is their own repository and approved its
redistribution on November 3, 2026. This records that permission without adding
an upstream license or changing the pinned source. An explicit upstream license
would make the reuse terms easier for readers to find. The
[original-model guide](docs/original_gdp_models.md#original-sources) also
documents the absent license file and the distinction from the root MIT notice.
