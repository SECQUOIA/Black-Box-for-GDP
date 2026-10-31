# Catalytic distillation column for ETBE

Equilibrium-stage GDP model of a catalytic distillation column that produces ethyl *tert*-butyl ether (ETBE) from isobutene and ethanol, from Liñán, Bernal, Ricardez-Sandoval, and Gómez, "Optimal design of superstructures for placing units and streams with multiple and ordered available locations. Part II: Rigorous design of catalytic distillation columns," *Computers & Chemical Engineering* (2020).
The files come from `catalytic_distillation/dsda-gdp-cd-column` of [SECQUOIA/dsda-gdp](https://github.com/SECQUOIA/dsda-gdp) at `3e469dbeea8931670b8cd6752014ab7a767d3af5` (the `external/dsda-gdp` submodule).

## Files

| File | Content | Change from the source |
|---|---|---|
| `distillation_model.gms` | Sets, parameters, variables, equations, bounds, and `model DSDA /all/` | Spanish comments and descriptions translated to English; code unchanged |
| `DISTILLATION.gms` | Includes the model and generates the D-SDA external-variable files (embedded Python) | Model moved to `distillation_model.gms`; CONOPT replaces MSNLP, which current GAMS releases no longer distribute |
| `D_SDA.gms`, `main.gms` | Original D-SDA implementation and its driver | One Spanish comment translated |
| `solve_configuration.gms` | Solves the NLP for one configuration from a fixed initialization | New |
| `init.gdx` | Initialization of the source, for configuration (3, 4, 5, 6, 8, 9) | Unchanged |
| `DSDA_solution_CONOPT.gdx` | Published D-SDA optimum with CONOPT | Unchanged |
| `neighborhood_MATLAB/` | Neighborhood definitions read by `DISTILLATION.gms`, with the MATLAB generator and its license | Unchanged |

## Configuration space

Stage 1 is the condenser, stage 22 the reboiler, and the reflux returns to stage 2.
The six external variables are the ethanol feed stage `f1`, three catalytic stages `c1 < c2 < c3`, the butenes feed stage `f2`, and the boil-up stage `b`.
The logical constraints admit `2 <= f1 <= c1 < c2 < c3 <= f2 <= b <= 21`, which gives 100,947 configurations.
Stages below the boil-up stage are not physically present.

## Solving one configuration

```sh
gams solve_configuration.gms --f1=4 --c1=4 --c2=6 --c3=8 --f2=8 --b=10
```

Optional arguments: `--solver` (default `conopt`), `--init` (default `init`), `--out` (default `result.txt`), `--model`, and `--gdx` to unload the solution.
Every call starts from `init.gdx`, so the result does not depend on earlier solves, unlike `D_SDA.gms`, which warm-starts neighbors from the incumbent.

## Verification

The original source model and the translated `distillation_model.gms` generate the same model (1,569 equations and 1,579 variables) and reach the same solution at the published optimum, `zobj = 22631.782909`, with CONOPT in about 0.5 s from `init.gdx` under GAMS 54.2.
This reproduces the published D-SDA optimum (22631.7829089) at `f1 = 4`, catalytic stages 4, 6, and 8, `f2 = 8`, and `b = 10`.

## Review

See [REVIEW.md](REVIEW.md) for the model check, including thermodynamic expressions that differ from their textbook forms.
