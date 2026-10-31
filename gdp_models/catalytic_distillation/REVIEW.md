# Review of the catalytic distillation model

Complete check of `distillation_model.gms`: every equation block, parameter table, and bound, checked against its standard form and literature values and evaluated at the published D-SDA optimum (`f1 = 4`, catalytic stages 4, 6, 8, `f2 = 8`, `b = 10`, `zobj = 22631.782909`).
That optimum is solved with CONOPT from `init.gdx`.
Independent recomputations in Python reproduce the model's vapor pressures, activity coefficients, equilibrium constant, rate, and objective to 1e-4 or better.
`distillation_model.gms` is unchanged and still reproduces the published optimum.
`distillation_model_corrected.gms` applies the fixes; see [Corrected model](#corrected-model).

## What is correct

- Material balances: per-stage residuals are at most 1e-13. Component closure with the reaction extent, 1.6098 mol/min of ETBE produced against 1.6096 mol/min in the bottoms, holds to 1e-15. The summation equations hold on every stage.
- Energy balances: overall closure is 2e-13. The heat of reaction enters only through the heats of formation in the enthalpies, so it is not counted twice.
- Superstructure logic:
  - `logic1`–`logic13` are equivalent to 2 <= f1 <= c1 < c2 < c3 <= f2 <= b <= 21.
  - Stages below the boil-up stage carry no vapor, properties, hydraulics, pressure drop, height, or reaction.
  - `par` and `ye` in `solve_configuration.gms` are identical to those in `DISTILLATION.gms`.
- Property forms: extended Antoine (DIPPR 101), NRTL with correct index order, SRK constants and mixing rules, ideal-gas Cp integral, DIPPR 106 heat of vaporization, liquid Cp. Antoine gives normal boiling points within 0.3 K of literature. NRTL reproduces the ETBE–ethanol azeotrope at 1 atm (339.0 K, x_EtOH = 0.376).
- Kinetics: the activity-based rate law, its use in mol/min with mole percentages, the stoichiometry, and the Jensen–Datta form of the equilibrium constant.
- Hydraulic and cost forms: Kister–Haas clear-liquid height and flooding factor, tray geometry, catalyst pressure drop, Guthrie/Douglas shell and tray correlations, capital-recovery factor (5 years, 5%).

## Findings

Severity is the effect on the model's use as an optimization problem: High changes which configuration is optimal or shifts K-values or energy terms by more than 10%.

### Objective

| # | Location | Finding | Effect | Severity |
|---|---|---|---|---|
| 11 | `CT`, `Csh` (lines 1064–1065), `Fobj` (line 1078) | `CT` and `Csh` already contain the annualization factor `AF = 0.230975`, and `Fobj` multiplies them by `AF` again. | Tray and shell cost enter `zobj` as 159 $/yr instead of 689 $/yr at the published optimum, so column size costs about 4.3 times too little. The ranking flips (see below). | High |
| 15 | `Fobj` (line 1079) | Revenue is `CostB*L(22)`, the whole bottoms flow at the ETBE price, although `CostB` is described as revenue from ETBE. | 0.33 mol/min of n-butene, ethanol, and isobutene in the bottoms earns 4,004 $/yr, 18% of `zobj`. The 83% purity specification binds only because impurities earn revenue; with ETBE-only revenue the bottoms purity rises to 89.4%. The ranking flips (see below). Selling the specified product stream at one price may be intended; if so, the description is wrong. | High |
| 12 | `par` (lines 137–138), `Fobj` (line 1078) | The tray-cost sum over `hs_Stage` includes the condenser and reboiler (`par('1') = par('22') = 1`); `Size` counts only internal stages. | 11 stages charged instead of 9 at the published optimum. | Low |
| 16 | `CT` (line 1064) | The tray cost uses the pressure factor `Fcol = FM*FPres = 1.15`. Guthrie/Douglas tray costs use Fs + Ft + Fm (about 2.2 for sieve trays, 12-inch spacing, carbon steel); the pressure factor belongs to the shell. | About 12 $/yr even after fixing 11. | Low |
| 17 | `C0` (line 1058) | Condenser and reboiler capital is a constant 10,000 $/yr, independent of `Qc` and `Qr`. | With the feed costs, 45,190 $/yr of `zobj` is constant across configurations. | Modeling choice |

### Thermodynamics

| # | Location | Finding | Effect | Severity |
|---|---|---|---|---|
| 1 | `EqPhi` (line 586) | The SRK fugacity coefficient uses the dimensional `bEOS` (m³/mol) where SRK uses B = bP/(RT). | φ is 1.02–1.09 for the light components where SRK gives 0.79–0.92 (median deviation 24%, largest 37%). Every K-value is affected. | High |
| 18 | `EquilibrioC0` (line 853), `Equilibrio10` (line 897), `EquilibrioR0` (line 915) | Phase equilibrium is y·P·φ = x·γ·Psat, without the saturation fugacity coefficient φ^sat or the Poynting factor. At 9.5 bar, φ^sat of the butenes is 0.78–0.85 on stages 1–10 and 0.69 in the reboiler. | With finding 1, ethanol and ETBE K-values are 17–26% too low on stages 1–10. Butene K-values are within 1% at the top, 14% high at stage 10, and 40% high in the reboiler. Fixing 1 alone would make the butene K-values 18–62% high, so 1 and 18 must be fixed together. | High |
| 3 | `EqHVi` (line 662), `EqdepHvib` (line 726), `EqHFB` (line 807), `EqHFE` (line 839) | The enthalpy departure term `(1+m_i)·sqrt(a)/b·ln(Z/(Z+B))` has units of bar^0.5 and is not the SRK residual enthalpy RT(Z−1) + (T·da/dT − a)/b·ln(1 + B/Z). | −3.3 kJ/mol in the vapor where SRK gives −1.5 kJ/mol. Partly cancels in the stage balances. | Medium |
| 19 | `EqHFE`/`VaporZeth`, `EqHFB`/`VaporZbut` | The departure term of the liquid feeds uses the vapor root of the cubic at 9.5 bar. Ethanol at 342.4 K has Psat = 0.70 bar, and `Zeth` = 0.690 is a vapor state that cannot exist. A liquid feed's enthalpy should be H_ig + H_R,V at Psat − ΔHvap, the path `EqHLi` already uses. | HFE is −277.7 instead of −271.8 kJ/mol and HFB is −25.2 instead of −22.5 kJ/mol. About 26 kJ/min of feed enthalpy, 9% of the reboiler duty, is missing; 19 kJ/min of it is independent of finding 3. | Medium |
| 20 | Heats of formation (line 644) vs `EqKetbe` (line 518) | The heat of reaction implied by the enthalpies is −31.3 kJ/mol at the catalytic stages. The van 't Hoff slope of the model's own K(T) gives −43.8 kJ/mol. The two data sets disagree; it is not established which one is correct. | About 20 kJ/min, 7% of the reboiler duty. | Low/Medium |
| 2 | `EqAlphaEOS` (line 563) | The SRK α of each component uses the liquid mixture pseudo-critical temperature `Tcritm` instead of the component critical temperature. | The vapor compressibility factor stays within 1.1% of SRK. | Low |
| 21 | `Pcrit` (lines 290–296) | All four critical pressures are gauge values, i.e. the literature value minus 1.01325 bar (isobutene 38.99 instead of 40.00 bar). | a and b are 1.7–3.6% high; K-values change by at most 1.2%. | Low |
| 8 | Parameters | Two critical-temperature sets: `Tcrit` for properties and `TcritSRK` for the EOS, e.g. ethanol 516.2 vs 514 K. | Small. | Low |
| 31 | `EqKetbe` (line 521) | The temperature coefficient is −0.01915144; the source gives −0.0191544. | At most 0.1% in K. | Cosmetic |
| 22 | `Tb` (line 651) | The reference boiling points at 9.5 bar differ from the model's own Antoine, e.g. n-butene 342.6 vs 341.7 K. | Less than 0.05 kJ/mol. | Cosmetic |

### Hydraulics

These relations enter only as constraints. At the published optimum, the active ones are `Weep` on the boil-up stage and `EqHwmin`. The diameter is set by the catalyst volume (`ammountcat`) and the slenderness limit (`DtoLratio`, H/D = 20), not by vapor load, so flooding is at 6–8%.

| # | Location | Finding | Effect | Severity |
|---|---|---|---|---|
| 14 | `EqDPq` (line 987) | The downcomer apron loss adds the squared vapor volumetric flow to the squared liquid flow. Only liquid flows under the apron. | `DPq` is 3.0–3.6e-3 bar, about three times the liquid head. The downcomer backup in `DownFlood` is 0.18–0.22 of the tray spacing at the published optimum and 0.67–0.92 at the configuration (7, 7, 11, 17, 17, 20), mostly from this term. | Medium |
| 23 | `DownFlood` (line 1006) | The backup is h_ow + (ΔP + ΔP_q)/(Δρ·g) <= HS. The textbook form is h_w + h_ow + h_t + h_da <= about 0.5(HS + h_w) for aerated liquid (Coulson & Richardson Vol. 6; Kister). It omits the weir height and any froth allowance. | Inactive at the published optimum. | Medium |
| 4 | `Eqrho` (line 402) | DIPPR 105 uses the exponent `C4r`, which is zero for every component, instead of `C3r` (0.23–0.29), so densities do not depend on temperature. | Densities are 39–84% above DIPPR 105. | Medium |
| 13 | `EqDPS` (line 983) | The dry-tray pressure drop divides the squared volumetric vapor flow by `A0` instead of `A0²`, which is dimensionally inconsistent. | Underestimated by 1/A0 = 2,293 m⁻²: 1.6e-7 bar instead of about 3.7e-4 bar. The liquid head is 1.1e-3 bar. | Low |
| 5 | `Eqsigma` (line 445) | The ethanol coefficients are DIPPR 100 polynomial coefficients with the sign of C3 flipped, used in a DIPPR 106 form. All components use the mixture `Tcritm` instead of their own critical temperature. | Ethanol 0.038–0.044 N/m at 343 K against about 0.018 measured; mixture σ up to 37% high. | Low |
| 24 | `EntrainFloodV` (line 1011) | Kister–Haas is defined on the net area AT − Ad, but the code uses At = AT − 2Ad, at 100% of flood. Designs normally use 80–85%. | Inactive. | Low |
| 25 | `EqhD` (line 939) | The crest over the weir uses the coefficient 0.6 where the Francis formula gives about 0.66. | −10% on a 1.5 mm crest. | Low |
| 26 | `EntrainFloodL` (line 1014) | Labeled entrainment, but it is a downcomer liquid-velocity limit. | Inactive. | Cosmetic |

### Bounds and structural limits

| # | Location | Finding | Effect | Severity |
|---|---|---|---|---|
| 27 | `Qr.up = 400` (line 1110) | Upper bound on the reboiler duty. | It is the main reason configurations fail. Of the 72 sampled configurations that CONOPT reports as locally infeasible, 58 solve once the operating bounds are widened. 52 of those solutions use Qr between 400 and 1,658, so the bound cuts off configurations that the column can operate. The bound is inactive at the published optimum (292) and almost active at (7, 7, 11, 17, 17, 20) (391). Other operating bounds are tight as well: `Qr.lo = 100`, `Qc.up = 900`, `RR` in [1, 10], `BR.up = 10`, `L.up = V.up = 200`. | High for the benchmark |
| 9 | `Temp.up = 417.89` (line 1222) | The bound is 0.01 K below `Tcritm.lo = 417.9`, the critical temperature of isobutene. It keeps (1 − T/Tcritm) positive in the density, surface tension, and SRK α expressions (findings 2, 4, 5). It also caps every stage below the ETBE boiling point at 9.5 bar (438.8 K). | The model cannot represent bottoms much richer in ETBE than the 83% specification. | Structural |
| 28 | `rho.lo = 8000` (line 1238) | Lower bound on the liquid molar density. | Inactive now, but real ETBE density (about 6,400 mol/m³ at 373 K) violates it once finding 4 is fixed. | Low |

### Cosmetic and usage

| # | Location | Finding |
|---|---|---|
| 6 | Section 6 (line 269) | The IK-CAPI density constants `C1rh`–`C10rh`, and `MCR`, `cR`, `alfa1`–`alfa3`, are declared but unused. |
| 7 | Lines 100, 813, 1051 | Unit labels disagree with the code (`FE` mol-h vs mol/min, `Tred_e` in K, `CostBut` butanes vs butenes). |
| 10 | Section numbers | Sections are numbered 1, 2, 13, 14, 3, ..., 20. |
| 29 | `solve_configuration.gms` | An inadmissible configuration makes the logic equations constant and infeasible; GAMS stops before writing `result.txt`. A harness must treat missing output as infeasible. |
| 30 | `execute_loadpoint` | Solution GDX files carry stale records from `init.gdx` (e.g. marginals on stages that are not generated); ignore them when reading duals. |

### Sources checked

- Kinetics: the rate, adsorption, and equilibrium constants are those of Sneesby et al. (1997, Ind. Eng. Chem. Res. 36, 1855–1869), as reported by García Serpas et al. (2024, Period. Polytech. Chem. Eng. 68, 116–123). The source gives k_r = 2.0606e12·exp(−60.4 kJ mol⁻¹/RT) mol kg⁻¹ s⁻¹. The model's 7.41816e15 is that value per hour, and `hora/3600` converts it to per minute, so the rate units are correct.
- NRTL parameters: taken from Aspen Plus, according to the model author.

## Effect on the configuration ranking

CONOPT from `init.gdx`, `zobj` in $/yr; bottoms ETBE mol% in parentheses.
The variant models change only the lines named in each column; all bounds stay unchanged.

| Configuration (f1, c1, c2, c3, f2, b) | As published | Fix 11 (single AF) | Fix 15 (ETBE-only revenue) | Fixes 11 and 15 |
|---|---|---|---|---|
| (4, 4, 6, 8, 8, 10), published D-SDA optimum | 22,631.78 (83.0) | 23,161.43 (83.0) | 26,554.63 (89.4) | 27,084.28 (89.4) |
| (7, 7, 11, 17, 17, 20), best of the random pilot | 22,527.97 (83.0) | 23,372.42 (83.0) | 26,565.52 (85.6) | 27,409.97 (85.6) |
| (12, 12, 16, 18, 18, 20) | infeasible from `init.gdx` | infeasible from `init.gdx` | 26,680.60 (83.7) | 27,525.05 (83.7) |

In the model as published, (7, 7, 11, 17, 17, 20) beats the published D-SDA optimum by 103.8 $/yr. Its advantage comes from revenue on impurities and from underpriced column height. With either fix, the published configuration is better than the other two.
The configuration (7, 7, 11, 17, 17, 20) has closed balances, a monotone temperature profile (342.5 to 407.4 K), and the same active constraints as the published optimum, so it is a sound solution of the model as written.

## Solving single configurations

Results and run descriptions are in `results/catalytic_distillation_pilot_20261030/`.
GAMS 54.2 with CONOPT 4, IPOPT 3.14, and POUNCE (an interior-point solver written in Rust and distributed with GAMS), one thread per solve.

- At the published optimum, all three solvers reach the same objective from `init.gdx`: CONOPT in 0.40 s, POUNCE in 6.7 s, and IPOPT in 35.6 s.
- CONOPT from `init.gdx` accepts 130 of 202 sampled configurations: 200 drawn at random (seed 20261031), plus the published and the initial configurations.
- The 72 failures fall into three groups:
  - 8 are feasible within the published bounds. CONOPT from the published optimum (5), POUNCE (3), or the widened-bound run found them, so for these the failure was the initialization or the solver.
  - 50 have solutions only above the operating bounds, almost all with Qr > 400 (finding 27).
  - 14 remain infeasible with wider bounds.
- Failures concentrate far from the initialization: 85–88% of configurations are solved at L1 distance 11–30 from (3, 4, 5, 6, 8, 9), but only 41% beyond 40. They are also frequent with the butenes fed at the boil-up stage (30% solved), and none of the configurations with ethanol fed at stage 11 or below were solved.

## Corrected model

`distillation_model_corrected.gms` applies these fixes:

- Thermodynamics: findings 1, 2, 3, 8, 18, 19, 21, and 22, and the equilibrium-constant coefficient (31).
- Properties and hydraulics: findings 4, 5, 13, 14, 23, and 24.
- Objective: findings 11, 12, 15, 16, and 17.
- Bounds: findings 27 and 28.

Finding 20 (heats of formation vs K(T)) and finding 25 (weir crest coefficient) are not changed, because the correct values are not established. `Temp.up` (finding 9) stays, because the DIPPR expressions require T below each component's critical temperature.

The objective is the negative annual profit in $/yr:

- **Revenue:** only the ETBE in the bottoms, with the 83 mol% purity specification kept.
- **Operating cost:** feeds, plus steam and cooling water.
- **Capital, annualized once:** column shell, sieve trays on internal stages only, catalyst, condenser, and reboiler.
- **Exchanger sizing:** the condenser and reboiler are sized from their duties with U = 0.568 kW/(m²·K), cooling water at 305–322 K, and 10-bar steam at 453 K. Their cost uses Guthrie's correlation, replacing the constant 10,000 $/yr.

The Guthrie and Douglas correlations are used far below their size range (column diameter 0.13 m), so the absolute cost is indicative. The ranking of configurations is what the benchmark uses.

At the published configuration the corrected model gives 18,488.68 $/yr, with Qr = 235, reflux ratio 2.35, and the purity specification active. On the 202 sampled configurations, CONOPT from `init.gdx` accepts 169, with a median solve of 3.1 s. Starting from the corrected model's own solution at the initial configuration accepts only 109. The published configuration is the best of the sample. Four configurations reach different local optima from the two initializations, so the evaluation protocol fixes the initialization to `init.gdx`.

## Consequences for the benchmark

- The published model is reproducible, and its balances and logic are correct. Findings 1, 11, 15, 18, and 27 change either the physics or which configuration is best, so it should not be used as a design benchmark without them.
- The corrected model, solved with CONOPT from `init.gdx`, is the black box for the live DFO runs. Every response is a deterministic function of the configuration.
