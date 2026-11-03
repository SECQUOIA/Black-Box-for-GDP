"""Catalytic distillation column as a live black box over gap coordinates.

The six external variables are the ethanol feed stage f1, the catalytic stages
c1 < c2 < c3, the butenes feed stage f2, and the boil-up stage b, with
2 <= f1 <= c1 < c2 < c3 <= f2 <= b <= 21.  The search space is the box of gaps

    g = (f1 - 2, c1 - f1, c2 - c1 - 1, c3 - c2 - 1, f2 - c3, b - f2),  0 <= g_i <= 6,

whose points are admissible when sum(g) <= 17 (54,159 of 117,649).  Each
admissible configuration is evaluated by solving the corrected model with
CONOPT from init.gdx, so the response is a deterministic function of the
configuration; responses are cached in SQLite and solved at most once per cache.
"""

import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sqlite3
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MODEL_DIR = REPO / "gdp_models/catalytic_distillation"
MODEL = MODEL_DIR / "distillation_model_corrected.gms"
INIT = MODEL_DIR / "init"
SOLVER = "conopt"
TIMEOUT = 300.0
DIM, CAP, SUM_LIMIT = 6, 6, 17
LOWER, UPPER = [0] * DIM, [CAP] * DIM
N_STARTS = DIM + 1
STARTS_STREAM = 20261031

_spec = importlib.util.spec_from_file_location("catdist_pilot", REPO / "experiments/catalytic_distillation_pilot/run.py")
pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pilot)


def positions(gaps):
    """Stage positions (f1, c1, c2, c3, f2, b) of a gap point."""
    g1, g2, g3, g4, g5, g6 = gaps
    f1 = 2 + g1
    c1 = f1 + g2
    c2 = c1 + g3 + 1
    c3 = c2 + g4 + 1
    f2 = c3 + g5
    return (f1, c1, c2, c3, f2, f2 + g6)


def gaps_of(config):
    f1, c1, c2, c3, f2, b = config
    return (f1 - 2, c1 - f1, c2 - c1 - 1, c3 - c2 - 1, f2 - c3, b - f2)


def in_box(gaps):
    return len(gaps) == DIM and all(lo <= g <= hi for g, lo, hi in zip(gaps, LOWER, UPPER))


def admissible(gaps):
    return in_box(gaps) and sum(gaps) <= SUM_LIMIT


def box_points():
    return itertools.product(*(range(lo, hi + 1) for lo, hi in zip(LOWER, UPPER)))


def shared_starts(seed, n=N_STARTS):
    """n distinct admissible gap points spanning the space, drawn uniformly for a seed."""
    import numpy as np

    pool = [p for p in box_points() if sum(p) <= SUM_LIMIT]
    rng = np.random.default_rng([STARTS_STREAM, seed])
    while True:
        chosen = [pool[i] for i in rng.choice(len(pool), size=n, replace=False)]
        design = np.c_[np.ones(n), np.array(chosen, dtype=float)]
        if np.linalg.matrix_rank(design) == min(n, DIM + 1):
            return [list(map(int, p)) for p in chosen]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def provenance(gams):
    return {"model": MODEL.name, "model_sha256": sha256(MODEL), "init": INIT.name + ".gdx",
            "init_sha256": sha256(str(INIT) + ".gdx"), "solver": SOLVER, "threads": 1,
            "timeout_s": TIMEOUT, "gams": str(gams),
            "solve_configuration_sha256": sha256(MODEL_DIR / "solve_configuration.gms")}


class Evaluator:
    """Solves each admissible configuration once and caches the response."""

    def __init__(self, cache, gams, solve=None):
        self.gams = gams
        self.live_solves = 0
        self.solve = solve or (lambda config: pilot.solve(config, gams, SOLVER, TIMEOUT, INIT, MODEL, threads=1))
        self.db = sqlite3.connect(cache, timeout=600, isolation_level=None)
        self.db.execute("pragma journal_mode=wal")
        self.db.execute("create table if not exists meta (key text primary key, value text)")
        self.db.execute("create table if not exists responses (gaps text primary key, record text)")
        if solve is None:
            stored = self.db.execute("select value from meta where key='provenance'").fetchone()
            current = json.dumps(provenance(gams), sort_keys=True)
            if stored is None:
                self.db.execute("insert or ignore into meta values ('provenance', ?)", (current,))
            elif json.loads(stored[0]) != json.loads(current):
                raise RuntimeError("Cache was built with a different model, initialization, or solver")

    def __call__(self, gaps):
        """Response record of a gap point: accepted, objective, status, solve_wall_s, cached."""
        gaps = tuple(int(g) for g in gaps)
        if not admissible(gaps):
            return dict(accepted=False, objective=None, status="logical_infeasible", solve_wall_s=0.0, cached=False)
        key = json.dumps(gaps)
        row = self.db.execute("select record from responses where gaps=?", (key,)).fetchone()
        if row:
            return {**json.loads(row[0]), "cached": True}
        started = time.perf_counter()
        solved = self.solve(positions(gaps))
        self.live_solves += 1
        record = dict(accepted=bool(pilot.accepted(solved)), objective=solved["zobj"] if pilot.accepted(solved) else None,
                      status="accepted" if pilot.accepted(solved) else
                      "timeout" if solved["returncode"] == "timeout" else f"model{solved['modelstat']}_solve{solved['solvestat']}",
                      solve_wall_s=time.perf_counter() - started, positions=list(positions(gaps)),
                      solver_row={k: v for k, v in solved.items() if k not in pilot.FIELDS})
        self.db.execute("insert or ignore into responses values (?, ?)", (key, json.dumps(record)))
        # A concurrent run may have stored the same point first; every run sees the first record.
        stored = json.loads(self.db.execute("select record from responses where gaps=?", (key,)).fetchone()[0])
        return {**stored, "cached": stored != record}

    def records(self):
        return {tuple(json.loads(k)): json.loads(v) for k, v in self.db.execute("select gaps, record from responses")}
