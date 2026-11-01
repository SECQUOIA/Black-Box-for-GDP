"""D-SDA runs without re-evaluated configurations, from the audited Dantzig return; no solver calls.

The rows come from results/dsda_no_revisit_20261031, whose files are checked against its
FILE_SHA256.json before use. They replace the published D-SDA runs, which evaluated
revisited configurations again and charged them to the budget.
"""

import csv
import hashlib
import io
import json
import zipfile

RETURN = "results/dsda_no_revisit_20261031"
OUTPUT = "evidence/dsda_no_revisit_output_20261031_230829.zip"
OUTPUT_SHA256 = "6ef180d61c02259fd36f9334221a201aa0b8dff39f79c0082e3fdb8e0dab4b9d"
PRIMARY = ("grid", "single")
RESTARTS = ("single", "ranked", "ranked_random")


def read(root, name, inputs=None):
    """Bytes of a return file, verified against FILE_SHA256.json."""
    if name == OUTPUT:
        expected = OUTPUT_SHA256
    else:
        expected = json.loads((root / RETURN / "FILE_SHA256.json").read_text())[name]
    data = (root / RETURN / name).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ValueError(f"{RETURN}/{name} does not match its recorded hash")
    if inputs is not None:
        inputs[f"{RETURN}/{name}"] = digest
    return data


def number(value):
    return float(value) if value not in ("", None) else None


def all_runs(root, inputs=None):
    """All 1,470 runs (Grid and the three process variants) with typed fields."""
    raw = list(csv.DictReader(io.StringIO(read(root, "runs.csv", inputs).decode())))
    if len(raw) != 1470 or any(r["evaluations"] != r["distinct_evaluations"] for r in raw):
        raise ValueError("Expected 1,470 runs without repeated evaluations")
    rows = []
    for r in raw:
        rows.append(dict(
            scope=r["scope"], case=r["case"], budget=int(r["budget"]), seed=int(r["seed"]), variant=r["variant"],
            method="dsda", status=r["status"], hit=r["hit"] == "True",
            first_hit=int(r["first_hit"]) if r["first_hit"] else None, best_objective=number(r["best_objective"]),
            evaluations=int(r["evaluations"]), unused_budget=int(r["unused_budget"]),
            search_s=number(r["retained_search_s"]), point_cost_s=number(r["point_cost_s"]),
            prep_s=number(r["prep_s"]), completion_s=number(r["completion_s"])))
    return rows


def runs(root, inputs=None):
    """The primary D-SDA cohort: 1,050 Grid and 140 single-descent process runs."""
    rows = [r for r in all_runs(root, inputs) if r["variant"] in PRIMARY]
    if len(rows) != 1190:
        raise ValueError("Expected 1,190 primary D-SDA runs")
    return rows


def callbacks(root, inputs=None, variant="single"):
    """Callback points of each process run of one variant, keyed by (case, budget, seed)."""
    out = {}
    with zipfile.ZipFile(io.BytesIO(read(root, OUTPUT, inputs))) as z:
        for name in z.namelist():
            parts = name.split("/")
            if len(parts) == 4 and parts[3] == "callbacks.jsonl" and parts[2].endswith("__" + variant):
                job = parts[2].rsplit("__", 1)[0]
                if job.startswith("grid_"):
                    continue
                spec = json.loads(z.read(name.replace("callbacks.jsonl", "result.json")))["spec"]
                out[spec["case"], spec["budget"], spec["seed"]] = [
                    tuple(json.loads(line)["point"]) for line in z.read(name).splitlines()]
    return out


COVERAGE = "results/dsda_publication_20261028/tables/configuration_coverage.csv"
NLP = {"accepted": 1, "rejected": 1, "solver_error": 1, "preprocessing_infeasible": 0, "logical_infeasible": 0}


def process_joint_rows(root, inputs=None):
    """Process runs in the schema of the joint process figures.

    NLP solves count callbacks whose configuration reaches the NLP stage, as for the
    published D-SDA rows; logical and FBBT rejections are not NLP solves.
    """
    manifest = json.loads((root / "results/dsda_publication_20261028/manifest.json").read_text())
    data = (root / COVERAGE).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != manifest["outputs_sha256"]["tables/configuration_coverage.csv"]:
        raise ValueError(f"{COVERAGE} does not match its manifest")
    if inputs is not None:
        inputs[COVERAGE] = digest
    status = {(r["case"], tuple(json.loads(r["coordinates"]))): r["status"]
              for r in csv.DictReader(io.StringIO(data.decode()))}
    paths = callbacks(root, inputs)
    rows = []
    for r in runs(root, inputs):
        if r["scope"] != "process":
            continue
        points = paths[r["case"], r["budget"], r["seed"]]
        if len(points) != r["evaluations"]:
            raise ValueError(f"Callback count differs: {r['case']}/{r['budget']}/{r['seed']}")
        rows.append(dict(case=r["case"], method="dsda", family="DFO", budget=r["budget"], seed=r["seed"],
                         nlp_calls=sum(NLP[status[r["case"], p]] for p in points), target_reached=r["hit"],
                         completion_s=r["completion_s"], bound_conflict=False, termination="", time_limit=False))
    return rows
