"""Audit Process configuration coverage from saved callbacks, without solvers."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import platform
import zipfile

from .manuscript import CONDITIONS, GEN, PRIMARY, SOL, UNI

ROOT = Path(__file__).resolve().parents[1]
BASE = "results/review_comparison_20261020"
OLD = "results/process_ipopt_bam_v2_20261015/tables"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def readcsv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def coordinate(value):
    values = json.loads(value) if isinstance(value, str) else value
    require(isinstance(values, list) and values, "Missing coordinate")
    require(all(type(v) in (int, float) and int(v) == v for v in values),
            f"Noninteger coordinate: {values}")
    return tuple(int(v) for v in values)


def run_key(row):
    return row["case"], int(row["budget"]), int(row["seed"]), row["method"]


def primary_runs(rows):
    selected = {}
    for row in rows:
        if row["scope"] != "process":
            continue
        require(row["method"] in [*PRIMARY, SOL], "Unexpected Process method")
        if row["method"] == SOL:
            continue
        key = run_key(row)
        require(key not in selected, f"Duplicate primary run: {key}")
        selected[key] = row
    expected = {(case, budget, seed, method) for case, budget in CONDITIONS
                for seed in range(10) for method in PRIMARY}
    require(set(selected) == expected,
            f"Primary run coverage mismatch: missing={sorted(expected-set(selected))}; "
            f"unexpected={sorted(set(selected)-expected)}")
    return selected


def checked_trace(events, expected, key):
    require(len(events) == int(expected), f"Callback count mismatch: {key}")
    require([int(e["index"]) for e in events] == list(range(1, len(events) + 1)),
            f"Missing, duplicate or unordered callback index: {key}")
    require(len(events) <= key[1], f"Out-of-budget callback: {key}")


def audit(root=ROOT):
    """Validate saved inputs and return deterministic, independently countable ledgers."""
    root = Path(root)
    inputs = {}

    def verified(path, expected=None):
        data = (root / path).read_bytes()
        digest = sha(data)
        require(expected is None or digest == expected, f"Input hash mismatch: {path}")
        inputs[path] = digest
        return data

    manifest = json.loads(verified(f"{BASE}/manifest.json"))
    publication = json.loads(verified("manuscript/analysis_manifest_current.json"))
    replay = json.loads(verified("reproduction/validation/checkout_replay.json"))
    for path, expected in publication["input_sha256"].items():
        verified(path, expected)
    completed = f"{BASE}/tables/completed_runs.csv"
    verified(completed, manifest["published_files_sha256"]["tables/completed_runs.csv"])
    selected = primary_runs(readcsv(root / completed))
    published_path = "manuscript/tables/run_records.csv"
    verified(published_path, publication["outputs_sha256"]["tables/run_records.csv"])
    published = primary_runs(readcsv(root / published_path))
    for key, row in selected.items():
        require(int(row["evaluations"]) == int(published[key]["evaluations"]),
                f"Manuscript run-count mismatch: {key}")

    inventory = {}
    for case in sorted({c for c, _ in CONDITIONS}):
        path = f"{OLD}/cost_table_{case}.csv"
        verified(path, manifest["historical_input_files_unchanged"][path]["sha256"])
        for row in readcsv(root / path):
            key = case, coordinate(row["point"])
            require(key not in inventory, f"Duplicate inventory key: {key}")
            inventory[key] = row

    old_path = f"{OLD}/callbacks.csv"
    verified(old_path, replay["outputs"]["process_replay/tables/callbacks.csv"])
    old_runs_path = f"{OLD}/run_results.csv"
    old_runs = {}
    for row in readcsv(root / old_runs_path):
        row = row | {"method": SOL if row["method"] == "rbfopt" else row["method"]}
        key = run_key(row)
        require(key not in old_runs, f"Duplicate historical run: {key}")
        old_runs[key] = row
    old_events = defaultdict(list)
    for row in readcsv(root / old_path):
        row = row | {"method": SOL if row["method"] == "rbfopt" else row["method"]}
        require(row["within_budget"] == "True", "Historical out-of-budget event")
        old_events[run_key(row)].append(row)
    require(set(old_events) == set(old_runs), "Historical run/callback membership mismatch")

    counts = Counter()
    historical = Counter()
    run_members = defaultdict(set)
    runs = []

    def check_event(case, event):
        point = coordinate(event["point"])
        key = case, point
        require(key in inventory, f"Callback outside measured inventory: {key}")
        require(event["accepted"] in (True, False, "True", "False"), "Invalid acceptance")
        accepted = event["accepted"] is True or event["accepted"] == "True"
        require(accepted == (inventory[key]["accepted"] == "True"),
                f"Acceptance mismatch: {key}")
        return key

    def add_run(key, row, events, source, source_hash):
        checked_trace(events, row["evaluations"], key)
        points = set()
        for event in events:
            config = check_event(key[0], event)
            counts[key[3], config] += 1
            run_members[config].add(key)
            points.add(config[1])
        runs.append(dict(case=key[0], budget=key[1], seed=key[2], method=key[3],
                         category=row["category"], callbacks=len(events),
                         distinct_configurations=len(points),
                         visited_coordinates=json.dumps(sorted(points), separators=(",", ":")),
                         record_source=source, record_source_sha256=source_hash))

    for key, row in sorted(old_runs.items()):
        events = old_events[key]
        checked_trace(events, row["logged_callbacks"], key)
        for event in events:
            historical[check_event(key[0], event)] += 1
        if key[3] in PRIMARY:
            require(row["category"] == selected[key]["category"],
                    f"Historical category mismatch: {key}")
            add_run(key, selected[key], events, old_path + "#job_id=" + row["job_id"],
                    inputs[old_path])

    archive = manifest["return_archive"]
    with zipfile.ZipFile(root / archive["path"]) as z:
        for key, row in sorted(selected.items()):
            if key[3] not in (GEN, UNI):
                continue
            member = archive["root"] + "/" + row["record_source"] + "/evaluations.jsonl"
            data = z.read(member)
            events = [json.loads(line) for line in data.decode().splitlines()]
            add_run(key, row, events, archive["path"] + "::" + member, sha(data))
    require({run_key(r) for r in runs} == set(selected), "Incomplete final membership")
    require(len(runs) == len(selected), "Duplicate final run membership")

    coverage = []
    for config, row in sorted(inventory.items()):
        method_counts = {method: counts[method, config] for method in PRIMARY}
        case, point = config
        coverage.append(dict(case=case, model="cstr" if case.startswith("cstr_") else case,
                             model_size=case.split("_")[1] if case.startswith("cstr_") else "",
                             coordinates=json.dumps(point, separators=(",", ":")),
                             accepted=row["accepted"], status=row["status"],
                             primary_callbacks=sum(method_counts.values()),
                             primary_runs=len(run_members[config]),
                             historical_callbacks=historical[config], **method_counts))
    cases = []
    for case in sorted({c for c, _ in CONDITIONS}):
        cc = [c for c in coverage if c["case"] == case]
        cases.append(dict(case=case, inventory=len(cc),
                          primary_runs=sum(r["case"] == case for r in runs),
                          primary_callbacks=sum(c["primary_callbacks"] for c in cc),
                          primary_visited=sum(c["primary_callbacks"] > 0 for c in cc),
                          historical_visited=sum(c["historical_callbacks"] > 0 for c in cc),
                          primary_only=sum(c["primary_callbacks"] > 0 and not c["historical_callbacks"] for c in cc),
                          historical_only=sum(c["historical_callbacks"] > 0 and not c["primary_callbacks"] for c in cc)))
    methods = [dict(method=method, runs=sum(r["method"] == method for r in runs),
                    callbacks=sum(c[method] for c in coverage),
                    distinct_configurations=sum(c[method] > 0 for c in coverage))
               for method in PRIMARY]
    summary = {name: sum(c[name] for c in cases) for name in cases[0] if name != "case"}
    summary["historical_runs"] = len(old_runs)
    summary["historical_callbacks"] = sum(historical.values())
    summary["shared_visited"] = summary["primary_visited"] - summary["primary_only"]
    summary["primary_outcomes"] = dict(sorted(Counter(r["category"] for r in runs).items()))
    summary["key_definition"] = "model, size, integer coordinates; method, seed and budget are unioned"
    summary["primary_methods"] = PRIMARY
    summary["excluded_method"] = SOL
    summary["new_optimization_or_nlp_runs"] = 0
    return {"configuration_coverage.csv": coverage, "case_summary.csv": cases,
            "method_summary.csv": methods, "runs.csv": sorted(runs, key=run_key),
            "summary.json": summary}, inputs


def generate(output, root=ROOT):
    output = Path(output)
    require(not output.exists(), f"Output already exists: {output}")
    outputs, inputs = audit(root)
    output.mkdir(parents=True)
    for name, rows in outputs.items():
        if name.endswith(".json"):
            (output / name).write_text(json.dumps(rows, indent=2) + "\n")
        else:
            with (output / name).open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
    manifest = dict(input_sha256=inputs,
                    source_sha256={p: sha((Path(root)/p).read_bytes()) for p in
                                   ["review_comparison/visited_keys.py", "review_comparison/manuscript.py"]},
                    input_revision="3dee29c24e4c0eccf7fbcfdd1f72a4126ba8d9a4",
                    execution_provider_revision="38d917ef75ef6767c2a9f238d88be19bf0b89160",
                    python=platform.python_version(),
                    reproduce="python -m review_comparison.visited_keys --output /tmp/process-coverage-new",
                    outputs_sha256={n: sha((output/n).read_bytes()) for n in outputs},
                    note="Postprocessing of completed records only; historical evidence unchanged.")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return outputs["summary.json"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(generate(args.output), indent=2))
