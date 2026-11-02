# Catalytic distillation: single-configuration solves

Each run is the output of `experiments/catalytic_distillation_pilot/run.py`, with `solves.csv` (one row per configuration) and `summary.json`.
A configuration is accepted when CONOPT, IPOPT, or POUNCE reports normal completion (solver status 1) with a locally optimal model status (1 or 2).
GAMS 54.2. The machine was shared with other workloads, so times are indicative.

## Published model (`distillation_model.gms`)

| Run | Configurations | Solver and initialization | Notes |
|---|---|---|---|
| `pilot_200` | `pilot202.csv`: 200 random configurations (seed 20261031) plus the published optimum and the initial configuration | CONOPT from `init.gdx` | 130 accepted, 72 locally infeasible |
| `failed72_conopt_optinit` | `failed72.csv`, the 72 failures | CONOPT from `DSDA_solution_CONOPT.gdx` | 5 recovered |
| `failed72_pounce` | `failed72.csv` | POUNCE from `init.gdx`, 300 s | 3 recovered. Run on an oversubscribed machine with multithreaded solves, so its time limits are not conclusive |
| `failed72_wide_bounds` | `failed72.csv` | CONOPT from `init.gdx`, `wide_bounds` variant | 58 solved; 52 of them need Qr > 400 |
| `published_conopt`, `published_pounce`, `published_ipopt` | `published.csv` | each solver from `init.gdx`, one thread | 0.40 s, 6.7 s, 35.6 s; same optimum |
| `published_pilot_20_ipopt` | `pilot20.csv` (first 20 of `pilot202.csv`) | IPOPT from `init.gdx`, one thread | 6 accepted against 14 for CONOPT; median 66 s against 1.8 s; identical objectives (within 6e-6) where both solve |
| `objective_variants.csv` | three configurations | CONOPT from `init.gdx`, `variants.py` | `zobj` with findings 11 and 15 fixed separately and together |

## Corrected model (`distillation_model_corrected.gms`)

| Run | Configurations | Initialization | Notes |
|---|---|---|---|
| `corrected_pilot_200_init` | `pilot202.csv` | `init.gdx` | 169 accepted; median 3.1 s |
| `corrected_pilot_200_own_init` | `pilot202.csv` | the corrected model's solution at (3, 4, 5, 6, 8, 9), solved from `init.gdx` (not kept) | 109 accepted; median 8.7 s |
| `corrected_failed_from_published_solution` | `corrected_failed.csv`, the 93 failures of the previous run | the corrected model's solution at the published configuration | 12 recovered |

Runs with IPOPT on the 72 failures and on the eight best configurations were discarded. Their solver processes were multithreaded and outlived the time limit, so their timeouts measure machine load rather than the solver.
The runner now passes `threads=1` and kills the solver's process group on timeout.

## Final corrected model (current version)

With the open property data below plus 2010-basis prices and a 95 mol% ETBE specification:

| Run | Content |
|---|---|
| `final_pilot_200_conopt` | `pilot202.csv`, CONOPT from `init.gdx`: 132 accepted (all with b >= 13), median 4.3 s; best (7, 8, 11, 16, 16, 20) at 25,271.33 $/yr |

## Corrected model with open property data (83 mol% specification, published prices)

| Run or file | Content |
|---|---|
| `open_pilot_200_conopt` | `pilot202.csv`, CONOPT from `init.gdx`: 161 accepted, median 3.2 s (83 mol% specification, published prices) |
| `open_property_fits.json`, `open_property_parameters.json` | Output of `fit_open_properties.py` and the parameters used in the model |
| `open_pilot_20_pounce_0.14.0`, `open_pilot_20_pounce_gams54.2` | The first 20 configurations of `pilot202.csv` with POUNCE 0.14.0 (pip GAMS link, selected through `XDG_CONFIG_DIRS`) and the POUNCE bundled with GAMS 54.2.2, one thread, 600 s: neither accepts any configuration (CONOPT accepts 14). IPOPT also fails at the published configuration, with and without warm-start options |
| `open_data/` | Open experimental data with `sources.json`: isobutene + ethanol VLE, ETBE + ethanol azeotropes, ETBE vapor pressure, density, and surface tension. Used by `check_nrtl_etbe_open_data.py` |

The runs above under "Corrected model" used an earlier version, before the mixture density and surface tension, the catalyst limit, and the open pure-component data.
