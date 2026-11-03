# Catalytic column: configurations outside the search box, rerun on Dantzig with GAMS 54.3.1

This rerun repeats the check of `results/catalytic_distillation_outside_box_20261102` on the server of the
Catalytic Column campaign (Dantzig) with the campaign's GAMS 54.3.1 and CONOPT 4.39.1, so that every
reported Catalytic Column result comes from one GAMS release on one machine.
The model files (`solve_configuration.gms`, `distillation_model_corrected.gms`, `init.gdx`) and the 747
configurations are the same as in the workstation run (hashes in `STAGED_SHA256.txt` of the Dantzig run
directory match the repository copies); only the GAMS release (54.3.1 instead of 54.2.2) and the machine differ.

## Result

- 255 of the 747 configurations are accepted and 492 are locally infeasible (model status 5).
- None is better than the reference (8, 8, 12, 17, 17, 21) at 24,895.552861 $/yr. The best, (9, 9, 13, 17, 17, 21)
  at 24,930.96 $/yr, is 0.14% above it; the next are (9, 9, 12, 16, 16, 20) at 25,067.60 (0.69%) and
  (9, 9, 13, 16, 16, 20) at 25,077.17 (0.73%).
- The longest solve took 40 s, below the campaign's 300 s limit.
- Every configuration has the same model and solver status as in the workstation run, and every configuration
  accepted in both runs has the same objective to the six printed decimals (`comparison.csv`).

## Files

- `configs.txt`: the 747 configurations (from `scripts/list_configs.py`).
- `scripts/solve_one.sh`, `scripts/run_all.sh`: the scripts that ran on Dantzig with 12 workers
  (`xargs -P 12`), with the paths of that machine; `run.log` records the start, end, and GAMS release.
- `scripts/collect.py`: builds `results.csv`, `comparison.csv`, and the evidence archive from the result lines.
- `results.csv`: one row per configuration with the solver's model and solver status, objective, resource time,
  and bottoms ETBE fraction.
- `comparison.csv`: status, acceptance, and objective of each configuration in this run and the workstation run.
- `evidence/outside_box_results.zip`: the result line that GAMS wrote for each configuration
  (`runs/<f1>_<c1>_<c2>_<c3>_<f2>_<b>/result.txt`); its SHA-256 is in
  `evidence/outside_box_results.zip.sha256`, and `FILE_SHA256.txt` lists the SHA-256 of every file.

Run on 3 November 2026 (13:19 to 13:38 UTC) on dantzig.ecn.purdue.edu with GAMS 54.3.1 (`/package/gams/54.3`)
and CONOPT 4.39.1.
