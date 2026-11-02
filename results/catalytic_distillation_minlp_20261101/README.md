# MINLP solvers on the catalytic distillation column

Runs of `experiments/catalytic_distillation_minlp` (see its README for the forms and the scripts), at the commit that adds this folder.
GAMS 54.2.2 on one core each of an Intel Xeon w5-2565X workstation (WSL2), with CONOPT 4.39.1 for the NLPs.
The reference is the best known design of `results/catalytic_distillation_live_20261101`, (f1, c1, c2, c3, f2, b) = (8, 8, 12, 17, 17, 21) at 24,895.552861 $/yr.

## Contents

- `validation/validation.csv`: nine configurations with the binaries fixed, in the GDP, product, Big-M, and hull forms (`validate.sh`).
- `product`, `bigm`, `chull`: `run_solvers.sh FORM ... 3600 dicopt sbb baron scip`, from `init.gdx` and the configuration (3, 4, 5, 6, 8, 9). Each `<solver>` folder has `result.txt` (one line written by the solve script), `wall.txt`, and `gams.log`. `bigm/reformulated_bigm.gms.gz` and `chull/reformulated_chull.gms.gz` are the scalar models that JAMS generated and passed to the solvers.
- `summary.csv`: the twelve runs (`summarize.py`). `zobj` and the configuration are the levels that GAMS returns; with model status 9 (intermediate infeasible), 14 (no solution returned), or 19 (infeasible), they are not a feasible design.
- `fixed_best`: BARON and SCIP on the Big-M and hull reformulations with the binaries fixed at the reference design, 1,200 s limit.
- `examine_bigm_fixed_best`: the GAMS Examiner on the CONOPT solution of the Big-M reformulation at the reference design (`log.txt`).
- `certificates`: the product form at (7, 8, 11, 16, 16, 20) and at the reference, solved with the binaries fixed (`point`), checked by the Examiner (`examine`), and used as the starting point of SCIP and BARON on the whole MINLP (`scip_free`, `baron_free`, 900 s limit), with `check_point.gms`.

## Results

| Form | Solver | Outcome | Wall time (s) |
|---|---|---|---:|
| product | DICOPT | no feasible design; every NLP subproblem infeasible, major iteration limit | 638 |
| product | SBB | 28,717.22 at (4, 4, 5, 6, 6, 9), 15.4% above the reference | 8 |
| product | BARON | declared infeasible (lower bound +inf) | 74 |
| product | SCIP | declared infeasible | 5 |
| bigm | DICOPT | no feasible design; an NLP subproblem returned no solution | 1,247 |
| bigm | SBB | no feasible design; domain violation limit after 47 nodes | 89 |
| bigm | BARON | declared infeasible (lower bound +inf) | 158 |
| bigm | SCIP | no feasible design at the time limit; lower bound -5.66e7 | 3,600+ |
| chull | DICOPT | no feasible design; an NLP subproblem returned no solution | 154 |
| chull | SBB | no feasible design; domain violation limit after 27 nodes | 123 |
| chull | BARON | declared infeasible (lower bound +inf) | 127 |
| chull | SCIP | no feasible design at the time limit; lower bound -5.66e7 | 3,600+ |

The infeasibility claims are wrong:

- With the binaries fixed at the reference design, BARON declares both reformulations infeasible, and SCIP finds no feasible point in 1,200 s.
  The Examiner confirms that the CONOPT solution of the Big-M reformulation at that design satisfies every constraint and bound within 1e-6.
- Started from a feasible design of the product form, SCIP and BARON certify it as the global optimum: 25,271.33 from (7, 8, 11, 16, 16, 20) (SCIP 22 s; BARON 65 s, best possible 25,271.3277) and 24,895.55 from the reference (SCIP 12 s; BARON 67 s, best possible 24,895.5529).
  The Examiner confirms both points within 1e-6, so the first certificate is contradicted by the second design.

In the Big-M reformulation passed to the solvers, the matrix coefficients range from 1e-17 to 1.3e18, because the valid scale of the rate equation over the variable bounds is 1.3e18.
In every form, the equations of absent stages and of stages without catalyst remain in the model, multiplied by zero or relaxed.
The GDP evaluation of the DFO runs solves only the equations of the selected configuration.
