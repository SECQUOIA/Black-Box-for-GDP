# Catalytic column: configurations outside the search box near the reference

The GDP of the corrected column admits 100,947 configurations (2 <= f1 <= c1 < c2 < c3 <= f2 <= b <= 21).
The DFO campaign of `results/catalytic_distillation_live_20261101` searches the gap box g_i <= 6, which holds 54,159 of them.
The reference, (f1, c1, c2, c3, f2, b) = (8, 8, 12, 17, 17, 21) at 24,895.552861 $/yr, has g1 = f1 - 2 = 6 on the bound of that box, so a better design could lie just outside it.

This check solves every configuration outside the box within two stages of the reference (L-infinity distance <= 2 in stage positions): 747 configurations, with g1 (ethanol feed at stage 9 or 10), g3, or g4 above 6.
Each is solved with `gdp_models/catalytic_distillation/solve_configuration.gms` and CONOPT from `init.gdx`, as in the campaign, and accepted under the campaign rule (model status 1 or 2 and solver status 1).

## Result

- 255 of the 747 configurations are accepted; the other 492 are locally infeasible (model status 5), and their `zobj` values are not objectives.
- None is better than the reference. The best, (9, 9, 13, 17, 17, 21) at 24,930.96 $/yr, is 0.14% above it; the next are (9, 9, 12, 16, 16, 20) at 25,067.60 (0.69%) and (9, 9, 13, 16, 16, 20) at 25,077.17 (0.73%).
- The longest solve took 97 s, below the campaign's 300 s limit.

## Files

- `configs.txt`: the 747 configurations, written by `scripts/list_configs.py`.
- `scripts/solve_one.sh`: the script that solved each configuration (run as `xargs -P 12 -L 1 ./solve_one.sh < configs.txt`, with paths for the machine that ran it).
- `results.csv`: one row per configuration with the solver's model and solver status, objective, resource time, and bottoms ETBE.

Run on 2 November 2026 on an Intel Xeon w5-2565X workstation with GAMS 54.2.2 and CONOPT 4.39.1, the CONOPT version of the Dantzig campaign (GAMS 54.3.1).
