"""QHDOpt-derived grids, frozen original run keys and BAM audit coordinates."""

import csv
from functools import lru_cache
import json
import math
from pathlib import Path

from .protocol import REFERENCE, ROOT, key, point_hash, sha


GRID_REFERENCE = REFERENCE / "grid"
GRID_BUDGETS = (10, 30, 50, 70, 100)


def metadata():
    return json.loads((GRID_REFERENCE / "reference.json").read_text())


def verify_grid_sources():
    meta = metadata()
    for filename, expected in meta["files_sha256"].items():
        if sha(GRID_REFERENCE / filename) != expected:
            raise ValueError(f"Grid reference checksum mismatch: {filename}")
    for relative, expected in meta["data_files_sha256"].items():
        if sha(ROOT / relative) != expected:
            raise ValueError(f"Grid objective data differ from the original benchmark: {relative}")
    audit = json.loads((GRID_REFERENCE / "comparison_audit.json").read_text())
    if (audit["reference_grid_csv_sha256"] != sha(GRID_REFERENCE / "original.csv")
            or audit["benchmark.csv_sha256"] != sha(GRID_REFERENCE / "bam5.csv")):
        raise ValueError("Grid baseline CSVs do not match the Dantzig BAM comparison audit")
    return meta["data_files_sha256"]


@lru_cache(maxsize=32)
def grid_problem(csv_name):
    # Use the historical pandas loader so decimal parsing matches the baseline.
    from grid_dsda import load_grid_csv
    allowed = {Path(p).name for p in metadata()["data_files_sha256"]}
    if csv_name not in allowed:
        raise ValueError(f"Unknown benchmark grid: {csv_name}")
    _, values = load_grid_csv(ROOT / "benchmark_grids" / csv_name)
    if (len(values) != 31 * 31 or set(values) != {(x, y) for x in range(31) for y in range(31)}
            or any(not math.isfinite(v) or not 0 <= v <= 1 for v in values.values())):
        raise ValueError("Expected the original finite 31 x 31 normalized grid")
    return {"objective": lambda point: values[tuple(point)], "lower": [0, 0], "upper": [30, 30],
            "target": min(values.values())}


def reference_grid_plan(names=None, seeds=None, budgets=GRID_BUDGETS):
    verify_grid_sources()
    audit = json.loads((GRID_REFERENCE / "comparison_audit.json").read_text())
    designs = {(d["csv_name"], d["seed"]): d for d in audit["grid_designs"]}
    all_names = {Path(p).name for p in metadata()["data_files_sha256"]}
    if len(designs) != 210 or set(designs) != {(n, s) for n in all_names for s in range(10)}:
        raise ValueError("Incomplete grid initial designs")
    names = all_names if names is None else [n if n.endswith(".csv") else n + ".csv" for n in names]
    if (not set(names) <= all_names or len(set(names)) != len(names)
            or not set(budgets) <= set(GRID_BUDGETS) or len(set(budgets)) != len(budgets)):
        raise ValueError("Select distinct original grid names and budgets 10,30,50,70,100")
    expected_keys = {(n, s, 3, b) for n in all_names for s in range(10) for b in GRID_BUDGETS}
    initial = {}
    for design_key, design in designs.items():
        points = design["starting_points"]
        if (len(points) != 3 or len({tuple(p) for p in points}) != 3
                or any(len(p) != 2 or any(int(v) != v or not 0 <= v <= 30 for v in p) for p in points)):
            raise ValueError("Invalid saved grid initial coordinates")
        oracle = grid_problem(design_key[0])["objective"]
        running = math.inf
        prefix = []
        for point in points:
            running = min(running, oracle(point))
            prefix.append(running)
        initial[design_key] = prefix
    original = None
    for filename, methods in (("original.csv", {"DSDA", "RBFOpt", "BAM"}), ("bam5.csv", {"BAM"})):
        with (GRID_REFERENCE / filename).open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != len(expected_keys) * len(methods):
            raise ValueError("Incomplete original grid run matrix")
        for method in methods:
            subset = [r for r in rows if r["method"] == method]
            if len(subset) != len(expected_keys) or {key(r) for r in subset} != expected_keys:
                raise ValueError(f"Grid baseline run keys differ: {filename}, {method}")
        for row in rows:
            observed = json.loads(row["incumbent_trajectory"])[:3]
            if len(observed) != 3 or any(not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
                                       for a, b in zip(observed, initial[(row["csv_name"], int(row["seed"]))])):
                raise ValueError("Saved grid coordinates do not reproduce historical initial objectives")
        if filename == "original.csv":
            original = rows
    plan = []
    for row in original:
        if row["method"] != "RBFOpt" or row["csv_name"] not in names or int(row["max_evals"]) not in budgets:
            continue
        seed = int(row["seed"])
        if seeds is not None and seed not in seeds:
            continue
        points = designs[(row["csv_name"], seed)]["starting_points"]
        spec = {"csv_name": row["csv_name"], "case_name": "grid", "grid_size": None,
                "method": "fmqa_sa", "seed": seed, "n_starts": 3, "max_evaluations": int(row["max_evals"]),
                "starting_points": points, "initial_design_sha256": point_hash(points),
                "job_id": f"grid_{Path(row['csv_name']).stem}_B{row['max_evals']}_seed{seed}"}
        plan.append(spec)
    if not plan:
        raise ValueError("Selection contains no original grid benchmark runs")
    return plan
