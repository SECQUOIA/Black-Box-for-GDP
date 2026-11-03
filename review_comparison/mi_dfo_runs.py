"""NOMAD and MISO runs from the audited Dantzig return of PR #56; no solver calls.

The rows come from results/pr56_dantzig_return_20261031/analysis, whose files are checked
against the analyzer's REPRODUCTION.json before use.
"""

import csv
import hashlib
import io
import json

RETURN = "results/pr56_dantzig_return_20261031/analysis"
METHODS = ["miso", "nomad"]
LABELS = {"miso": "MISO", "nomad": "NOMAD"}


def read(root, name, inputs=None):
    """Bytes of an analysis file, verified against REPRODUCTION.json."""
    expected = json.loads((root / RETURN / "REPRODUCTION.json").read_text())["outputs_sha256"][name]
    data = (root / RETURN / name).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ValueError(f"{RETURN}/{name} does not match REPRODUCTION.json")
    if inputs is not None:
        inputs[f"{RETURN}/{name}"] = digest
    return data


def runs(root, inputs=None):
    """All 2,380 NOMAD and MISO runs with typed fields; times are None where not observed."""
    rows = []
    for r in csv.DictReader(io.StringIO(read(root, "individual_new_runs.csv", inputs).decode())):
        rows.append(dict(
            scope=r["scope"], case=r["case"], budget=int(r["budget"]), seed=int(r["seed"]), method=r["method"],
            status=r["status"], hit=r["hit"] == "True", first_hit=int(r["first_hit"]) if r["first_hit"] else None,
            best_objective=float(r["best_objective"]), evaluations=int(r["evaluations"]),
            nlp_solves=int(r["nlp_solves"]), point_cost_s=float(r["point_cost_s"]), prep_s=float(r["prep_s"]),
            search_s=float(r["retained_search_s"]) if r["retained_search_s"] else None,
            completion_s=float(r["completion_s"]) if r["completion_s"] else None))
    if len(rows) != 2380:
        raise ValueError("Expected 2,380 NOMAD and MISO runs")
    return rows


def process_joint_rows(root, inputs=None):
    """Process runs in the schema of the joint process figures."""
    return [dict(case=r["case"], method=r["method"], family="DFO", budget=r["budget"], seed=r["seed"],
                 nlp_calls=r["nlp_solves"], target_reached=r["hit"], completion_s=r["completion_s"],
                 bound_conflict=False, termination="", time_limit=False)
            for r in runs(root, inputs) if r["scope"] == "process"]
