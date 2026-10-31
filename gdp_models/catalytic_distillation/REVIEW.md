# Review of the catalytic distillation model

Review of `distillation_model.gms` while translating it.
Quantities are evaluated at the published D-SDA optimum (`f1 = 4`, catalytic stages 4, 6, 8, `f2 = 8`, `b = 10`, `zobj = 22631.78`), solved with CONOPT from `init.gdx`.
Textbook comparisons use the model's own parameters.
No finding below has been changed in the model, so it still reproduces the published optimum.

## Findings

| # | Location | Finding | Effect at the published optimum | Severity |
|---|---|---|---|---|
| 1 | `EqPhi`, line 586 | The SRK fugacity coefficient uses the dimensional `bEOS` (m³/mol) where SRK uses B = bP/(RT): `-log(Z - bEOS)`, `aEOS/bEOS`, and `log((Z - bEOS)/Z)` instead of ln(Z - B), A/B, and ln(1 + B/Z). | φ is 1.02–1.09 for the light components where SRK gives 0.79–0.92; the median deviation is 24% and the largest 37% over 88 stage-component pairs. φ enters every phase-equilibrium equation, so all K-values are affected. | High |
| 2 | `EqAlphaEOS`, line 563 | The SRK α of each component uses the mixture pseudo-critical temperature `Tcritm`, computed from the liquid composition, instead of the component critical temperature. | The vapor compressibility factor stays within 1.1% of SRK at every stage. | Low |
| 3 | `EqHVi`, line 662; `EqdepHvib`, line 726; `EqHFB`, line 807; `EqHFE`, line 839 | The enthalpy departure term `(1+m_i)·sqrt(a)/b·ln(Z/(Z+B))` has units of bar^0.5 and is not the SRK residual enthalpy RT(Z−1) + (T da/dT − a)/b·ln(1 + B/Z). | −3.3 kJ/mol in the vapor where SRK gives −1.5 kJ/mol. The same form appears in the liquid and feed enthalpies, so part of the error cancels in the energy balances. | Medium |
| 4 | `Eqrho`, line 402 | The DIPPR 105 liquid density uses the exponent `C4r`, which is zero for every component, instead of `C3r` (0.23–0.29). The densities are therefore independent of temperature. | Densities are 39–84% above DIPPR 105 with `C3r` (isobutene 15,426 vs 9,363 mol/m³ at 343 K). They enter only the hydraulic and flooding relations. | Medium |
| 5 | `Eqsigma`, line 445 | The ethanol surface-tension coefficients do not reproduce the measured value under the DIPPR 106 form used, nor under DIPPR 100. | 0.038–0.044 N/m at 343 K against about 0.018 N/m measured; the mixture value is dominated by the butenes. Hydraulics only. | Low |
| 6 | Section 6, line 269 | The title announces the IK-CAPI liquid density, but its constants `C1rh`–`C10rh` are never used. `MCR`, `cR`, and `alfa1`–`alfa3` are also declared and unused. | None | Cosmetic |
| 7 | Lines 100, 813, 1051 | Labels disagree with the code: `FE` says mol-h but is used as mol/min, the reduced temperature `Tred_e` says K, and `CostBut` said butanes for the butenes feed. Kept with a note in the translation. | None | Cosmetic |
| 8 | Parameters | Two critical-temperature sets are used (`Tcrit` for properties, `TcritSRK` for the EOS), e.g. ethanol 516.2 vs 514 K. | Small | Low |
| 9 | Line 1222 | `Temp.up = 417.89 K` is below the listed ETBE boiling point at 9.5 bar (438.8 K). The bottoms specification (83% ETBE) is active at the optimum, at 407 K. | Bound inactive at the optimum; it may cut off configurations with heavier bottoms. | Check |
| 10 | Section numbers | Sections are numbered 1, 2, 13, 14, 3, ..., 20. Some declarations omit the final `;` before the next keyword, which GAMS accepts. | None | Cosmetic |

## Consequences for the benchmark

- The model is self-consistent and reproducible: the published optimum is reached from the fixed initialization in about 0.5 s.
- Findings 1 and 3 mean the model is a numerical benchmark more than a validated ETBE design. Correcting them would change the optimum and break comparability with Liñán et al. (2020) and the D-SDA results.
- The original `D_SDA.gms` warm-starts each neighbor from the incumbent's solution, so its responses depend on the search path. `solve_configuration.gms` always starts from `init.gdx`, which makes every configuration's response a fixed lookup value.
