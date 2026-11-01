# Lomustine flowsheet: configurations evaluated by simulation-based optimization

This case selects the flowsheet of a lomustine manufacturing process whose model is a PharmaPy simulation, not an algebraic program.
It is the simulation-based case of the manuscript: fixing a configuration leaves an optimization over continuous operating inputs whose constraints and objective are available only through the simulator.

## Configurations and responses

The superstructure (SECQUOIA/pd_ising PR 28, `ds-mfg`, PharmaPy model `3194efd`) has:

- a first and a second reactor, each a batch reactor, a CSTR, or a PFR;
- a batch vaporizer;
- a crystallizer, either an unseeded batch cooling crystallizer (`batchU`) or a train of one, two, or three MSMPR crystallizers (`cont1`, `cont2`, `cont3`).

The external variables are the option indices `(R01, R02, CR01)` in `{0,1,2} x {0,1,2} x {0,1,2,3}`, ordered as in the source table: reactors `(batch, CSTR, PFR)` and crystallizers `(batchU, cont1, cont2, cont3)`.
The choices are categorical, so this order is a convention; the neighborhoods of D-SDA and NOMAD and the surrogate models act on it.
All 36 points are admissible. The four single-reactor semibatch options of the source do not fit this box and are excluded.

For each configuration, the source ran PyNomad (PyNomadBBO 4.6.0) on the 12 to 16 normalized operating inputs with 60 PharmaPy simulations.
`data/run_objmassprodcrys_sum_corrected_nomad.csv` is the corrected-model table of that work, copied unchanged from commit `633cf923f07abba88970fa1fa816c4d06769751e` (`ds-mfg/simulation/data/corrected_model_pharmapy_current/`; SHA-256 `c44dd7b2...`, checked by `case.py`).
For every configuration it stores:

- `Best Objective Value`, `-(m_lom / 1e-4 + 2 d50)` with the production rate `m_lom` in kg/s and the median crystal size `d50` in micrometers (minimized);
- `g1_solub_path_con`, the solubility path constraint (feasible when at most zero; all 36 satisfy it);
- `Evaluation Time`, the wall time in seconds of the inner optimization (91 to 1,019 s), charged as the cost of the evaluation.

The best configuration is `(PFR, batch, batch, batchU)` at -487.842; enumerating all 36 takes 5.3 h.

## Runs

`case.py` plugs into the seven-method harness of `experiments/catalytic_distillation_live` through `LIVE_DFO_CASE`.
The protocol follows the process benchmarks: three distinct shared initial configurations per seed from a seeded Latin hypercube, seeds 0-9, budgets 10, 15, and 20, unaccepted responses `1e6` (none occur), and the target tolerance `1e-5 * max(1, |f_ref|)`.
D-SDA uses the L-infinity neighborhood of the published process D-SDA and never evaluates a configuration twice.

```bash
export LIVE_DFO_CASE=$PWD/experiments/lomustine_simulation/case.py
cd experiments/catalytic_distillation_live
python run.py plan --output OUT
python run.py run --output OUT --gams none --cpus 0-6 --python-bam PY --python-fmqa PY --python-midfo PY \
    --bonmin BONMIN --ipopt IPOPT --bam-license LICENSE
python run.py summarize --output OUT
cd ../..
python experiments/lomustine_simulation/analyze.py --runs OUT --output ANALYSIS
```

Responses are table lookups, so the 210 runs take a few minutes; completion times add the measured search time to the recorded inner-optimization times.
The results of 31 October 2026 are in `results/lomustine_simulation_20261031`.
