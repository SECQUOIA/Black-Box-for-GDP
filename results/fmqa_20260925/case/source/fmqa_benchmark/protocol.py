"""Frozen original designs and lookup problems, without solver dependencies."""

import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(__file__).with_name("reference")
CASES = ("column", "cstr", "small_batch", "dynamic")
CSTR_SIZES = (5, 10, 15, 20, 25, 30)
METHOD = "FMQA-SA"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def point_hash(points):
    return hashlib.sha256(json.dumps(points, separators=(",", ":")).encode()).hexdigest()


def grid_size(csv_name):
    match = re.fullmatch(r"compl_enum_cstr_(\d+)_baron_hull.csv", csv_name)
    return int(match[1]) if match else None


def key(row):
    return (row["csv_name"], int(row["seed"]), int(row["n_starts"]),
            int(row.get("max_evaluations", row.get("max_evals"))))


def job_id(spec):
    case = f"cstr_{spec['grid_size']}" if spec["case_name"] == "cstr" else spec["case_name"]
    return f"{case}_B{spec['max_evaluations']}_seed{spec['seed']}"


def reference_plan(cases=CASES, sizes=CSTR_SIZES, seeds=None):
    original = json.loads((REFERENCE / "original.manifest.json").read_text())
    frozen = json.loads((REFERENCE / "initial_designs.json").read_text())
    if frozen["original_manifest_sha256"] != sha(REFERENCE / "original.manifest.json"):
        raise ValueError("Original initialization manifest checksum mismatch")
    designs = {(d["case_name"], d.get("grid_size"), d["seed"]): d for d in frozen["designs"]}
    expected = {(d["case_name"], d.get("grid_size"), d["seed"]): d
                for d in original["provenance"]["initial_design"]["designs"]}
    if designs.keys() != expected.keys():
        raise ValueError("Incomplete frozen initial designs")
    for k, d in designs.items():
        if (point_hash(d["points"]) != expected[k]["sha256"] or
                len(d["points"]) != expected[k]["n_starts"]):
            raise ValueError(f"Initial coordinates do not match the original run: {k}")
    plan = []
    for row in original["protocol"]["planned_run_keys"]:
        if row["method"] != "rbfopt" or row["case_name"] not in cases:
            continue
        size = grid_size(row["csv_name"])
        if size is not None and size not in sizes:
            continue
        if seeds is not None and row["seed"] not in seeds:
            continue
        d = designs[(row["case_name"], size, row["seed"])]
        spec = {**row, "method": "fmqa_sa", "grid_size": size,
                "starting_points": d["points"], "initial_design_sha256": d["sha256"]}
        spec["job_id"] = job_id(spec)
        plan.append(spec)
    if not plan:
        raise ValueError("Selection contains no original benchmark runs")
    return plan


def verify_lookup_sources():
    original = json.loads((REFERENCE / "original.manifest.json").read_text())
    expected = dict(original["provenance"]["data_files_sha256"])
    # Dynamic's objective table is embedded in its Python source.
    name = "case_studies/dynamic_case.py"
    expected[name] = original["provenance"]["source_files_sha256"][name]
    for name, digest in expected.items():
        if sha(ROOT / name) != digest:
            raise ValueError(f"Objective data differ from the original benchmark: {name}")
    return expected


def problem(spec):
    """Return an oracle; optimization receives no table or known-best objective."""
    case = spec["case_name"]
    if case == "grid":
        from .grid_protocol import grid_problem
        return grid_problem(spec["csv_name"])
    if case == "cstr":
        from case_studies.cstr_case import load_cstr_case_data
        data = load_cstr_case_data(spec["grid_size"])
        bounds = ([1, 1], [spec["grid_size"]] * 2)
        values = data["feasible_objectives"]
    elif case == "column":
        from case_studies.column_case import COLUMN_FEASIBLE_OBJECTIVES, LOWER_BOUNDS, UPPER_BOUNDS
        values, bounds = COLUMN_FEASIBLE_OBJECTIVES, (LOWER_BOUNDS, UPPER_BOUNDS)
    elif case == "small_batch":
        from case_studies.small_batch_case import SMALL_BATCH_FEASIBLE_OBJECTIVES, LOWER_BOUNDS, UPPER_BOUNDS
        values, bounds = SMALL_BATCH_FEASIBLE_OBJECTIVES, (LOWER_BOUNDS, UPPER_BOUNDS)
    elif case == "dynamic":
        from case_studies.dynamic_case import DYNAMIC_FEASIBLE_OBJECTIVES, LOWER_BOUNDS, UPPER_BOUNDS
        values, bounds = DYNAMIC_FEASIBLE_OBJECTIVES, (LOWER_BOUNDS, UPPER_BOUNDS)
    else:
        raise ValueError(f"Unknown case: {case}")
    return {"objective": lambda point: values.get(tuple(point), float("inf")),
            "lower": list(map(int, bounds[0])), "upper": list(map(int, bounds[1])),
            "target": min(values.values())}
