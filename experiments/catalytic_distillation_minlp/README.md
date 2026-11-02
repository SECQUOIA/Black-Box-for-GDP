# Catalytic distillation column as a MINLP

Conventional MINLP solvers on the corrected column (`gdp_models/catalytic_distillation/distillation_model_corrected.gms`), for comparison with the DFO configuration search of `experiments/catalytic_distillation_live`.
Three MINLP forms are compared: the product form of the published MINLP code, and the Big-M and convex hull reformulations that GAMS EMP (JAMS) generates from a disjunctive form of the model.
Results are in `results/catalytic_distillation_minlp_20261101`.

## Product form

`make_minlp.py` writes `gdp_models/catalytic_distillation/minlp_model_corrected.gms`, following the published MINLP form of the column (SECQUOIA/dsda-gdp, `dsda-minlp-cd-column`):

- `yf1`, `yf2`, `yc`, and `yb` (ethanol feed, butenes feed, catalyst, boil-up return) are binary; the reflux stays at stage 2 as in both published forms.
- `par` (stage exists) and `ye` (equilibrium stage) are variables defined by the published linear expressions.
- Property, kinetic, and feed-enthalpy equations hold on every stage.
- Switched pairs become products, e.g. `ETin = yf1*FE` and `boilup_flow = yb*BR*L`.
- Equilibrium relations are multiplied by `ye`, hydraulic definitions by `par` (`par*lhs = par*rhs`), and flooding and weeping inequalities by `par`.
- The 120 C catalyst limit becomes `Temp <= Tcatmax + (Temp.up - Tcatmax)*(1 - yc)`.

The products are exact for binary values. Keeping the property and kinetic equations on every stage is not: the bounds of their variables then also apply on stages that do not exist or hold no catalyst, where the GDP form has no such equations. `solve_minlp.gms` solves the form, or with `--f1 ... --b` the NLP of one configuration.

## Disjunctive (EMP) form

`make_emp.py` writes `emp_model_corrected.gms`, and `solve_emp.gms` declares five disjunctions for each internal stage and solves the model through JAMS with `--reform=bigm` or `--reform=chull`:

| Indicator | True | False |
|---|---|---|
| `par` stage exists | equilibrium, tray hydraulics, pressure drop, flooding and weeping, tray height | vapor passes through, no pressure drop, no height |
| `yc` catalyst | kinetics, catalyst hydraulics and flooding, reaction terms, 120 C limit | no reaction, no catalyst pressure drop |
| `yf1`, `yf2` feeds | feed flow | no feed flow |
| `yb` boil-up return | boil-up flow | no boil-up flow |

Property and feed-enthalpy equations hold on every stage, as in the product form. The kinetics stay in the catalyst disjunction: on every stage, the bounds of the reaction rate restrict the temperature of stages without catalyst. With kinetics on every stage and the binaries of (3, 4, 5, 11, 11, 14) fixed, the Big-M form stopped at 32,075 $/yr with `Rx` at its lower bound on stage 14, and the GDP form continues from that point to 30,822 $/yr.

Two steps make the JAMS reformulations valid for this model:

- **Linear disjuncts.** A nonlinear disjunct equation `F: h(x) = 0` becomes `def_F: s_F*r_F = h(x)`, which holds on every stage, and the disjunct constraint `r_F = 0`. The JAMS hull evaluates every disjunct function at zero (`(1-eps)*y + eps` perspective with `eps*g(0)`), where `1/rhoL`, `1/T`, and `L**(-0.59)` are not defined; with linear disjuncts it never does.
- **Scaling.** Every disjunct constraint is scaled by `s_F`, an interval bound on `|h|`, so that `M = 1` is a valid Big-M for all of them (JAMS takes one M per disjunction and rejects a binary that governs more than one disjunction). `compute_emp_scales.py` exports the model with GAMS CONVERT to Pyomo, tightens the bounds by FBBT over the constraints that hold for every configuration, computes the interval of each residual, sets `s = 1.01*max(|lo|, |hi|)`, and writes `gdp_models/catalytic_distillation/emp_scales.gms` with the scales, the bounds of the residual variables, and 101 implied variable bounds. It then repeats the computation with the scales in place and checks that every scaled residual lies in [-1, 1] (largest: 0.990).

Further details:

- The scales range from 0.10 to 1.3e18; the largest is the rate equation `EqRx`.
- The flooding and weeping correlations have finite interval bounds only if the liquid is denser than the vapor, which the source bounds do not imply. The EMP form therefore defines the mass densities `rhoLm` and `rhoVm` (kg/m3) with `rhoLm >= 200` and `5 <= rhoVm <= 150`. Every validated solution has `rhoLm >= 529` and `rhoVm <= 34`.
- JAMS chull rejects equalities, so every disjunct equality `F` is written as `F` (<=) and `F_ge` (>=); Big-M of the pair is Big-M of the equality.
- `--big` is the M of Big-M (default 1) or, for the hull, the bound JAMS gives disaggregated variables without bounds (default 1e5, above every variable bound).

## Validation

`validate.sh` fixes the binaries at nine configurations and solves each form with CONOPT from `init.gdx` (Big-M and hull through JAMS and SBB):

| Configuration | GDP form | Product form | Big-M | Hull |
|---|---:|---:|---:|---:|
| (8, 8, 12, 17, 17, 21), best known | 24,895.552861 | 24,895.552861 | 24,895.552861 | 24,895.552861 |
| (7, 8, 11, 16, 16, 20), pilot best | 25,271.327689 | 25,271.327689 | 25,271.327689 | 25,271.327689 |
| (3, 4, 5, 11, 11, 14) | 30,822.023648 | 30,822.023648 | 30,822.023648 | 30,822.023648 |
| (4, 4, 9, 10, 14, 17) | 28,373.983437 | 28,373.983437 | 28,373.983437 | 28,373.983437 |
| (3, 6, 12, 14, 19, 21) | 31,116.599264 | 32,320.552308 | 31,116.599265 | 31,116.599265 |
| (2, 3, 9, 10, 20, 21) | 35,745.425433 | 35,194.648498 | 35,745.425433 | 35,745.425433 |
| (4, 4, 6, 8, 8, 10), (3, 4, 5, 6, 8, 9), (13, 13, 15, 16, 17, 19) | infeasible | infeasible | infeasible | infeasible |

The Big-M and hull reformulations reproduce the GDP form at every feasible configuration, and all forms agree on feasibility.
The product form reaches other CONOPT local optima at two configurations; 35,194.648498 is a local optimum of the GDP form too, which stays there when started from it.

## Solvers

```bash
GAMS_EXE=/path/to/gams bash experiments/catalytic_distillation_minlp/run_solvers.sh FORM OUT 3600 dicopt sbb baron scip
```

`FORM` is `product`, `bigm`, or `chull`. Each solver runs on one core (`CPUS`) with a 3,600 s limit and a hard kill of its process group, from `init.gdx` and the configuration (3, 4, 5, 6, 8, 9) stored in it, which is locally infeasible and is also the initialization of every DFO evaluation. The script checks that the committed model is the output of its generator.

`check_point.gms` checks a stored point of the product form with the GAMS Examiner or starts SCIP or BARON from it.

## Rerun on Dantzig

```bash
export GAMS_EXE=/path/to/gams   # GAMS 54 or later; the column campaign used /package/gams/54.3/gams (54.3.1)
nohup bash experiments/catalytic_distillation_minlp/run_dantzig.sh > ../catdist_minlp_dantzig.log 2>&1 &
```

The preflight prints the GAMS version it found and stops unless every solver is licensed. `run_dantzig.sh` repeats every run of `results/catalytic_distillation_minlp_20261101` on 16 idle cores (`CPUS` to choose them) in about 1 h 15 min: a license preflight, the scale reproduction (with Pyomo in `SCALES_PYTHON`), `validate.sh`, the certificate and Examiner checks, the twelve solver runs, and the fixed-design BARON and SCIP runs. It keeps the full output outside the checkout and writes `results/catalytic_distillation_minlp_dantzig_<date>` with the same files, `comparison.txt` against the workstation runs, and a zip of the full output with its SHA-256.

## Reproduction

```bash
python experiments/catalytic_distillation_minlp/make_minlp.py
python experiments/catalytic_distillation_minlp/make_emp.py
GAMS_EXE=/path/to/gams python experiments/catalytic_distillation_minlp/compute_emp_scales.py   # needs Pyomo
GAMS_EXE=/path/to/gams bash experiments/catalytic_distillation_minlp/validate.sh OUT
```

`tests/test_catalytic_distillation_minlp.py` checks that the committed models are the generator output, that every disjunct equation is in its disjunction, that the scales cover every disjunct equation, and, with GAMS and Pyomo, that the scales are reproduced and that both reformulations reproduce the best known design.
