"""Lomustine flowsheet: every configuration is evaluated by a simulation-based optimization.

The configurations are the 36 two-reactor options of the lomustine manufacturing
superstructure in SECQUOIA/pd_ising PR 28 (ds-mfg, PharmaPy model 3194efd).  For
each option, PyNomad optimizes the 12 to 16 continuous operating variables of the
PharmaPy flowsheet simulation with 60 simulations.  The stored response is the best
objective -(m_lom / 1e-4 + 2 d50) subject to the solubility path constraint g1 <= 0,
and the cost of an evaluation is the wall time of that inner optimization.  No model
equations are available to a solver; the response exists only through the simulator.

External variables, in the enumeration order of the source table:

  xi1 = R01  in (batch, CSTR, PFR)
  xi2 = R02  in (batch, CSTR, PFR)
  xi3 = CR01 in (batchU, cont1, cont2, cont3)

VAP01 is always a batch vaporizer, and all 36 box points are admissible.  The four
single-reactor semibatch options of the source do not fit this box and are excluded.
The case plugs into experiments/catalytic_distillation_live/run.py through
LIVE_DFO_CASE.
"""

import ast
import csv
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA = HERE / "data/run_objmassprodcrys_sum_corrected_nomad.csv"
DATA_SHA256 = "c44dd7b21a91b09d6243c2f9a1fc6f746d25f57edd7562c5636c674cac020a3e"
REACTORS = ("batch", "CSTR", "PFR")
CRYSTALLIZERS = ("batchU", "cont1", "cont2", "cont3")
DIM = 3
LOWER, UPPER = [0, 0, 0], [len(REACTORS) - 1, len(REACTORS) - 1, len(CRYSTALLIZERS) - 1]
COORDINATES = "option_indices"
N_STARTS = 3
STARTS_STREAM = 20261031
BUDGETS = (10, 15, 20)
# The published process D-SDA uses the unit L-infinity neighborhood.
SETTINGS = {"dsda": {"diagonal": True}}
G1_TOL = 1e-9


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def positions(point):
    """Flowsheet layout (R01, R02, VAP01, CR01) of an option-index point."""
    r1, r2, cr = point
    return (REACTORS[r1], REACTORS[r2], "batch", CRYSTALLIZERS[cr])


def gaps_of(layout):
    r1, r2, _, cr = layout
    return (REACTORS.index(r1), REACTORS.index(r2), CRYSTALLIZERS.index(cr))


def in_box(point):
    return len(point) == DIM and all(lo <= p <= hi for p, lo, hi in zip(point, LOWER, UPPER))


def admissible(point):
    return in_box(point)


def box_points():
    return itertools.product(*(range(lo, hi + 1) for lo, hi in zip(LOWER, UPPER)))


def shared_starts(seed, n=N_STARTS):
    """n distinct configurations from a seeded Latin hypercube, as in the process benchmarks."""
    import numpy as np
    from scipy.stats import qmc

    rng = np.random.default_rng([STARTS_STREAM, seed])
    sizes = np.array(UPPER) + 1
    while True:
        unit = qmc.LatinHypercube(d=DIM, seed=rng).random(n)
        chosen = [tuple(int(v) for v in np.minimum(np.floor(u * sizes), sizes - 1)) for u in unit]
        if len(set(chosen)) == n:
            return [list(p) for p in chosen]


def table():
    """The 36 stored responses keyed by option-index point, after a hash check."""
    if sha256(DATA) != DATA_SHA256:
        raise ValueError(f"{DATA} changed")
    rows = {}
    for r in csv.DictReader(open(DATA, newline="")):
        layout = ast.literal_eval(r["Layout"])
        point = gaps_of(layout)
        if 12 * point[0] + 4 * point[1] + point[2] != int(r["Combination_Index"]):
            raise ValueError(f"Unexpected enumeration order at {r['Combination_Index']}")
        g1 = float(r["g1_solub_path_con"])
        rows[point] = dict(objective=float(r["Best Objective Value"]), g1=g1, accepted=g1 <= G1_TOL,
                           inner_optimization_s=float(r["Evaluation Time"]),
                           simulations=int(r["Blackbox Evaluations"]), layout=list(layout),
                           continuous_variables=len(r["Best Solution (feasible)"].strip("() ").split()))
    if sorted(rows) != sorted(box_points()):
        raise ValueError("The table must cover every box point exactly once")
    return rows


def reference_values():
    """Objective of every accepted configuration; the space is fully enumerated."""
    return {p: r["objective"] for p, r in table().items() if r["accepted"]}


def provenance(_gams=None):
    return dict(source="SECQUOIA/pd_ising PR 28", commit="633cf923f07abba88970fa1fa816c4d06769751e",
                path="ds-mfg/simulation/data/corrected_model_pharmapy_current/run_objmassprodcrys_sum_corrected_nomad.csv",
                data_sha256=DATA_SHA256, case_sha256=sha256(__file__))


class Evaluator:
    """Stored responses of the simulation-based optimization, with the cache contract of the live harness.

    The first request of a configuration counts as its evaluation; its cost is the recorded
    wall time of the inner PyNomad optimization.
    """

    def __init__(self, cache, gams=None, solve=None):
        self.responses = table()
        self.live_solves = 0
        self.db = sqlite3.connect(cache, timeout=600, isolation_level=None)
        self.db.execute("pragma journal_mode=wal")
        self.db.execute("create table if not exists meta (key text primary key, value text)")
        self.db.execute("create table if not exists responses (gaps text primary key, record text)")
        stored = self.db.execute("select value from meta where key='provenance'").fetchone()
        current = json.dumps(provenance(), sort_keys=True)
        if stored is None:
            self.db.execute("insert or ignore into meta values ('provenance', ?)", (current,))
        elif json.loads(stored[0]) != json.loads(current):
            raise RuntimeError("Cache was built from a different table or case")

    def __call__(self, point):
        point = tuple(int(p) for p in point)
        if not admissible(point):
            return dict(accepted=False, objective=None, status="logical_infeasible", solve_wall_s=0.0, cached=False)
        key = json.dumps(point)
        row = self.db.execute("select record from responses where gaps=?", (key,)).fetchone()
        if row:
            return {**json.loads(row[0]), "cached": True}
        r = self.responses[point]
        self.live_solves += 1
        record = dict(accepted=r["accepted"], objective=r["objective"] if r["accepted"] else None,
                      status="accepted" if r["accepted"] else "g1_violated", solve_wall_s=r["inner_optimization_s"],
                      positions=r["layout"], g1=r["g1"], simulations=r["simulations"],
                      continuous_variables=r["continuous_variables"])
        self.db.execute("insert or ignore into responses values (?, ?)", (key, json.dumps(record)))
        stored = json.loads(self.db.execute("select record from responses where gaps=?", (key,)).fetchone()[0])
        return {**stored, "cached": stored != record}

    def records(self):
        return {tuple(json.loads(k)): json.loads(v) for k, v in self.db.execute("select gaps, record from responses")}
