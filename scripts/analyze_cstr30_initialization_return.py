"""Audit the first-attempt CSTR30 initialization return without optimization."""
import argparse
from collections import Counter
from contextlib import ExitStack
import csv
import json
import hashlib
import logging
import math
import os
from pathlib import Path, PurePosixPath
import platform
import statistics
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "cstr30_init_20261025_060540_98uz54ol.zip"
SHA256 = "0cfec308ee68512f9e46bd2dc78f9839dad987fd5843cc3e829d5d71ee9ccdfb"
METHODS = ("dsda", "rbfopt", "bam", "fmqa_sa", "uniform_without_replacement")
REPORTED = ("README.txt", "evaluations.csv", "coordinate_comparison.csv", "paired_runs.csv",
            "method_summary.csv", "all_cstr_summary.csv", "retained_other_cstr_runs.csv",
            "rbfopt_coordinates.csv", "summary.json", "validation.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def events(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def csvwrite(path, data):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]), lineterminator="\n")
        writer.writeheader()
        for row in data:
            writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k,v in row.items()})


def close(a, b, tolerance=1e-10):
    return a is not None and b is not None and math.isfinite(a) and math.isfinite(b) and abs(a-b) <= tolerance


def target_hit(value, target):
    return value is not None and math.isfinite(value) and abs(value-target) <= 1e-5 * max(1, abs(target))


def extract_verified(path, destination):
    require(sha(path) == SHA256, "Return archive identity mismatch")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate ZIP member")
        require(archive.testzip() is None, "ZIP CRC failure")
        prefix = ARCHIVE.removesuffix(".zip") + "/"
        require(all(n.startswith(prefix) and ".." not in PurePosixPath(n).parts for n in names), "Unsafe archive member")
        checksums = dict((name, digest) for digest, name in
                         (line.split("  ", 1) for line in archive.read(prefix + "SHA256SUMS").decode().splitlines()))
        require(set(checksums) == {n[len(prefix):] for n in names if not n.endswith("/")} - {"SHA256SUMS"}, "Incomplete checksum coverage")
        for name, digest in checksums.items():
            data = archive.read(prefix + name)
            require(hashlib.sha256(data).hexdigest() == digest, f"Internal checksum mismatch: {name}")
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return len(checksums)


def audit_inputs(directory):
    manifest = read(directory / "manifest.json")
    package = directory / "reproduction"
    inventory = read(package / "inventory.json")
    require(sha(package / "inventory.json") == read(directory / "run.json")["bundle_inventory_sha256"], "Package inventory changed")
    for name, digest in inventory.items():
        require(sha(package / name) == digest, f"Reproduction source/input changed: {name}")
    for name, digest in manifest["output_hashes"].items():
        require(sha(directory / name) == digest, f"Server output hash changed: {name}")
    original = {}
    with ExitStack() as stack:
        archives = {}
        for key, spec in manifest["archives"].items():
            path = ROOT / spec["path"]
            require(sha(path) == spec["sha256"], f"Historical archive identity mismatch: {key}")
            archives[spec["path"]] = (stack.enter_context(zipfile.ZipFile(path)), spec["root"])
            original[spec["path"]] = spec["sha256"]
        compared = 0
        for row in rows(package / "baseline/runs.csv"):
            archive, prefix = archives[row["source_archive"]]
            for local in (package / "baseline/jobs" / row["job_id"]).iterdir():
                if local.is_file():
                    require(local.read_bytes() == archive.read(prefix + row["source_member"] + local.name),
                            f"Selected historical job bytes changed: {local.name}")
                    compared += 1
        old_nlp, prefix = archives[manifest["archives"]["nlp"]["path"]]
        for record in (package / "baseline/nlp/records").glob("*.json"):
            require(record.read_bytes() == old_nlp.read(prefix + "gams_ipopt/cstr_30/records/" + record.name), "Original NLP attempt changed")
    expected = read(package / "expected_environment.json")
    actual = read(directory / "preflight/nlp/actual_environment.json")
    baseline = expected["manifest"]["runtime"]
    for key in ("host", "python_version", "dependency_versions", "solver_executable_sha256", "solver_version", "source"):
        require(actual[key] == baseline[key], f"Historical NLP environment mismatch: {key}")
    for key in ("solver_options", "solver_option_file", "ipopt_version_line"):
        require(actual[key] == expected[key], f"NLP option/version mismatch: {key}")
    require(all(actual['thread_environment'][k] == v for k,v in baseline['thread_environment'].items()),
            'Historical NLP thread settings differ')
    require(actual == manifest["actual_environment"], "Run/preflight environment mismatch")
    return {"package_inventory_files_verified": len(inventory), "output_hashes_verified": len(manifest["output_hashes"]),
            "historical_job_files_compared": compared, "historical_archive_sha256": original,
            "baseline_revision": manifest["baseline_revision"], "execution_source_revision": manifest["execution_source_revision"],
            "package_inventory_sha256": sha(package / "inventory.json"), "actual_environment": actual,
            "old_platform": baseline["platform"], "new_platform": actual["platform"]}


def replay_report(directory, output):
    with tempfile.TemporaryDirectory(prefix="cstr30-replay-") as temp:
        replay = Path(temp)
        for name in ("reproduction", "points", "searches", "preflight"):
            (replay / name).symlink_to(directory / name, target_is_directory=True)
        completed = subprocess.run([sys.executable, str(directory / "reproduction/analyze.py"), str(replay)],
                                   capture_output=True, text=True, timeout=120)
        require(completed.returncode == 0, "Archived report replay failed: " + completed.stderr)
        verified = {}
        for name in (*REPORTED, "callbacks.csv"):
            identical = (replay / name).read_bytes() == (directory / name).read_bytes()
            differences = []
            if not identical:
                require(name.endswith('.json'), f"Report does not reproduce: {name}")
                def compare(a, b, key=''):
                    if a == b:
                        return
                    if isinstance(a, dict) and isinstance(b, dict):
                        require(a.keys() == b.keys(), f"Report keys differ: {key}")
                        for k in a:
                            compare(a[k],b[k],key+'/'+k)
                    elif isinstance(a, list) and isinstance(b, list):
                        require(len(a) == len(b), f"Report lengths differ: {key}")
                        for i,(x,y) in enumerate(zip(a,b)):
                            compare(x,y,key+'/'+str(i))
                    else:
                        require(isinstance(a,(int,float)) and isinstance(b,(int,float)) and close(a,b,1e-8),
                                f"Report differs beyond numeric replay tolerance: {key}")
                        differences.append(dict(field=key,returned=a,replayed=b,absolute_difference=abs(a-b)))
                compare(read(directory/name),read(replay/name))
            verified[name] = dict(byte_identical=identical,returned_sha256=sha(directory/name),
                                 replayed_sha256=sha(replay/name),numeric_differences=differences)
        (output / "returned").mkdir(exist_ok=True)
        for name in REPORTED:
            (output / "returned" / name).write_bytes((directory / name).read_bytes())
    return verified


def audit_coordinates(directory):
    expected = read(directory / "reproduction/expected_environment.json")
    old = {tuple(json.loads(r["point"])): r for r in rows(directory / "reproduction/baseline/cost_table_cstr_30.csv")}
    raw = [read(p) for p in sorted((directory / "points").glob("*/first_attempt.json"))]
    require(len(raw) == 900 and {tuple(r["point"]) for r in raw} == {(i,j) for i in range(1,31) for j in range(1,31)}, "Missing or duplicate coordinates")
    require(len(list((directory / "points").iterdir())) == 900, "Unexpected point attempts")
    coordinates = []
    for record in raw:
        point = tuple(record["point"])
        job = directory / "points" / f"{point[0]:02d}_{point[1]:02d}"
        require(record["attempt"] == 1 and record["cstr_size"] == 30, "Repeated attempt or wrong CSTR size")
        require(record["process"] == read(job / "process.json"), "Worker identity mismatch")
        require({k:v for k,v in record.items() if k != "process"} == read(job / "record.json"), "First attempt changed")
        require(math.isfinite(record["total_wall_s"]) and record["total_wall_s"] >= 0, "Missing/invalid timing")
        logical = point[1] <= point[0]
        log = job / "artifacts/solver.log"
        invocations = log.read_text().count("This is Ipopt version ") if log.exists() else 0
        require(invocations == record["ipopt_invocations_in_solver_log"], "IPOPT log invocation mismatch")
        require(record["nlp_calls"] == int((job / "nlp_call_started.json").exists()) == int(logical), "Incorrect NLP call gate")
        if not logical:
            require(record["status"] == "preprocessing_infeasible" and not record["accepted"] and not invocations, "Structural rejection called NLP")
        else:
            require(record["formulation_before"] == record["formulation_after"] == record["formulation_sha256"], "Changed algebra/bounds")
            require(record["solver_options"] == expected["solver_options"] and record["solver_option_file"] == expected["solver_option_file"], "Point solver options differ")
            with zipfile.ZipFile(job / "artifacts/gams_files.zip") as artifacts:
                require(artifacts.testzip() is None, "Nested GAMS artifact CRC failure")
                require(artifacts.read("ipopt.opt").decode().splitlines() == expected["solver_option_file"], "Actual option file differs")
                if record["accepted"]:
                    require(invocations == 1 and expected["ipopt_version_line"] in log.read_text(), "Missing actual solver/version evidence")
                    stats = {}
                    for line in artifacts.read("resultsstat.dat").decode().splitlines()[1:]:
                        parts = line.split()
                        if len(parts) < 2:
                            continue
                        try:
                            value = float(parts[1])
                        except ValueError:
                            value = math.nan
                        stats[parts[0]] = value if math.isfinite(value) else None
                    require(stats == record["gams_statistics"], "GAMS statuses/times not from saved attempt")
                    require(record["gams_solve_status"] == 1 and record["gams_model_status"] in (1,2)
                            and record["solver_status"] not in ("error", "aborted")
                            and record["max_primal_violation"] <= 1e-5, "Acceptance rule differs")
        previous = old[point]
        common = record["accepted"] and previous["accepted"] == "True"
        coordinates.append({"point": list(point), "logical_allowed": logical,
            "old_accepted": previous["accepted"] == "True", "new_accepted": record["accepted"],
            "old_termination": previous["termination"], "new_termination": record["termination"],
            "new_status": record["status"], "old_objective": float(previous["objective"]) if previous["objective"] else None,
            "new_objective": record["objective"],
            "objective_delta_if_both_accepted": record["objective"]-float(previous["objective"]) if common else None,
            "old_max_primal_violation": float(previous["max_primal_violation"]) if previous["max_primal_violation"] else None,
            "new_max_primal_violation": record["max_primal_violation"], "new_residual_state": record["residual_state"],
            "old_total_s": float(previous["total_wall_s"]), "new_total_s": record["total_wall_s"],
            "old_solve_s": float(previous["solve_wall_s"]) if previous.get("solve_wall_s") else 0.,
            "new_solve_s": record["solve_wall_s"], "interface_attempts": record["nlp_calls"],
            "confirmed_cstr_ipopt_invocations": invocations, "record_sha256": sha(job / "first_attempt.json")})
    return coordinates


def recompute_search(ev, result, costs, budget, target):
    require(len(ev) <= budget and [e["index"] for e in ev] == list(range(1,len(ev)+1)), "Callback budget/index violation")
    require(not any(e.get("budget_overrun") for e in ev), "Budget overrun")
    for e in ev:
        row = costs[tuple(e["point"])]
        require(e["accepted"] == (row["accepted"] == "True"), "Callback acceptance/table mismatch")
        if e["accepted"]:
            require(e["raw_objective"] == float(row["objective"]), "Callback objective/table mismatch")
    best = min((e["raw_objective"] for e in ev if e["accepted"]), default=None)
    successful_execution = result["status"] in ("completed", "budget_completed") and best is not None
    search = result.get("recorded_search_wall_s", result.get("dfo_wall_s"))
    lookup = sum(e["lookup_wall_s"] for e in ev)
    cost = sum(float(costs[tuple(e["point"])]["total_wall_s"]) for e in ev)
    require(search is not None and search >= lookup >= 0, "Invalid search clock")
    return dict(best=best, hit=successful_execution and target_hit(best, target),
                any_hit=successful_execution and any(target_hit(e["raw_objective"],target) for e in ev if e["accepted"]),
                search_s=search, lookup_s=lookup, cost_s=cost, completion_s=search-lookup+cost,
                callbacks=len(ev), failed=not successful_execution)


def audit_searches(directory):
    package = directory / "reproduction"
    plan = read(package / "plan.json")
    require(len(plan) == 50 and {(j["spec"]["method"],j["spec"]["budget"],j["spec"]["seed"]) for j in plan}
            == {(m,43,s) for m in METHODS for s in range(10)}, "Search design changed")
    require({p.name for p in (directory / "searches").iterdir()} == {j['spec']['job_id'] for j in plan}, "Extra or missing searches")
    costs = {tuple(json.loads(r["point"])):r for r in rows(directory / "evaluations.csv")}
    original = rows(package / "baseline/runs.csv")
    require(len(original) == 300 and len({r["job_id"] for r in original}) == 300, "Historical six-size records incomplete")
    historical_targets = {r['job_id']:float(r['target']) for r in original}
    previous = {}
    for r in original:
        job = package / "baseline/jobs" / r["job_id"]
        table = {tuple(json.loads(e["point"])):e for e in rows(package / "baseline" / f"cost_table_{r['case']}.csv")}
        computed = recompute_search(events(job / "callbacks.jsonl"), read(job / "result.json"), table, int(r["budget"]),float(r["target"]))
        require(computed["hit"] == (r["target_hit"] == "True") and close(computed["completion_s"],float(r["completion_s"]),1e-8), "Historical accounting differs")
        previous[r["job_id"]] = {**computed, "case":r["case"], "method":r["method"]}
    paired = {r["job_id"]:r for r in rows(directory / "paired_runs.csv")}
    output = []
    starts = {}
    for job in plan:
        spec = job["spec"]
        name, method, seed = spec["job_id"], spec["method"], spec["seed"]
        require(job['target'] == historical_targets[name], 'Reference target changed')
        path = directory / "searches" / name
        require(read(path / "job.json") == job, "Executed job differs from plan")
        result = read(path / "effective_result.json")
        require({k:v for k,v in result.items() if k != "process"} == read(path / "result.json"), "Effective result changed")
        require(result["process_nlp_calls"] == 0 and result["evaluation_table_sha256"] == sha(directory / "evaluations.csv"), "Search uses wrong oracle")
        ev = events(path / "callbacks.jsonl")
        old = events(package / job["baseline_directory"] / "callbacks.jsonl")
        require([e["point"] for e in ev[:3]] == [e["point"] for e in old[:3]] == spec["starts"], "Initial triple/order differs")
        require(starts.setdefault(seed,spec["starts"]) == spec["starts"], "Methods did not share starts")
        runtime = read(path / "runtime.json")
        for key in ("python", "host", "versions"):
            require(runtime[key] == job["reference_runtime"][key], f"Search environment differs: {key}")
        if method != "uniform_without_replacement":
            actual, expected = read(path / "actual_settings.json"), job["reference_settings"]
            if method == "bam":
                actual = {**actual,"options":{k:v for k,v in actual["options"].items() if k != "f_evaluated"}}
                expected = {**expected,"options":{k:v for k,v in expected["options"].items() if k != "f_evaluated"}}
            require(actual == expected and read(path / "settings_check.json")["identical"], "Algorithm settings differ")
        if method in ("dsda","rbfopt"):
            require(spec["unaccepted_response"] == 1e6, "Wrong penalty baseline")
            require(all(e["method_value"] == 1e6 and e["unaccepted_response"] == 1e6 for e in ev if not e["accepted"]), "Unaccepted response differs")
        if method == "rbfopt":
            require(spec["settings"]["global_search_method"] == "genetic" and read(path / "effective_rbfopt_settings.json")["global_search_method"] == "genetic", "Wrong RBFOpt candidate search")
            for key in ("bonmin_sha256", "ipopt_sha256", "rbfopt_sources_sha256"):
                require(runtime[key] == job["reference_runtime"][key], "RBFOpt source/auxiliary solver differs")
        computed = recompute_search(ev,result,costs,43,job["target"])
        require(computed["hit"] == (paired[name]["new_target_hit"] == "True")
                and close(computed["completion_s"],float(paired[name]["new_completion_s"]),1e-8), "New accounting differs")
        for e in ev:
            c = costs[tuple(e["point"])]
            require(e["source_row"]["record_sha256"] == c["record_sha256"] and e["source_row"] == c, "Objective/status/cost mixed between attempts")
        prefix = next((i for i,(a,b) in enumerate(zip(old,ev)) if a['point'] != b['point']), min(len(old),len(ev)))
        changed = [b["point"] for a,b in zip(old[:prefix],ev[:prefix]) if a["accepted"] != b["accepted"]]
        deltas = [abs(a["raw_objective"]-b["raw_objective"]) for a,b in zip(old[:prefix],ev[:prefix]) if a["accepted"] and b["accepted"]]
        output.append({"job_id":name, "method":method, "seed":seed, "budget":43, "target":job["target"],
            "old_hit":previous[name]["hit"], "new_hit":computed["hit"], "new_any_hit":computed["any_hit"],
            "old_best":previous[name]["best"], "new_best":computed["best"],
            "old_callbacks":len(old), "new_callbacks":len(ev), "identical_coordinate_sequence":[e['point'] for e in old] == [e['point'] for e in ev],
            "first_different_or_missing_callback":prefix+1 if prefix < max(len(old),len(ev)) else None,
            "acceptance_changes_in_common_prefix":changed, "max_objective_difference_in_common_prefix":max(deltas,default=0),
            "old_next_point":old[prefix]['point'] if prefix < len(old) else None,
            "new_next_point":ev[prefix]['point'] if prefix < len(ev) else None,
            "failed_point_27_10_visits":sum(e["point"] == [27,10] for e in ev),
            "old_completion_s":previous[name]["completion_s"], "new_completion_s":computed["completion_s"],
            "new_search_s":computed["search_s"], "new_lookup_s":computed["lookup_s"], "new_point_cost_s":computed["cost_s"],
            "new_failed":computed["failed"]})
    methods = []
    for method in METHODS:
        chosen = [r for r in output if r['method'] == method]
        others = [r for r in previous.values() if r['method'] == method and r['case'] != 'cstr_30']
        require(len(chosen) == 10 and len(others) == 50, "Wrong denominator")
        methods.append(dict(method=method, runs=10, old_hits=sum(r['old_hit'] for r in chosen), new_hits=sum(r['new_hit'] for r in chosen),
            both=sum(r['old_hit'] and r['new_hit'] for r in chosen), new_only=sum(not r['old_hit'] and r['new_hit'] for r in chosen),
            old_only=sum(r['old_hit'] and not r['new_hit'] for r in chosen), neither=sum(not r['old_hit'] and not r['new_hit'] for r in chosen),
            all_cstr_old_hits=sum(r['hit'] for r in previous.values() if r['method'] == method),
            all_cstr_new_hits=sum(r['hit'] for r in others)+sum(r['new_hit'] for r in chosen), all_cstr_runs=60,
            old_completion_s=sum(r['old_completion_s'] for r in chosen),new_completion_s=sum(r['new_completion_s'] for r in chosen),
            changed_coordinate_sequences=sum(not r['identical_coordinate_sequence'] for r in chosen)))
    return output, methods


def check_vector(prepared, values):
    import pyomo.environ as pyo
    variables = list(prepared.model.component_data_objects(pyo.Var))
    require(set(values) <= {v.name for v in variables}, "Unknown saved variable")
    max_bound, max_constraint = 0., 0.
    for v in variables:
        require(v.name in values or not v.fixed, f"Missing fixed variable: {v.name}")
        if v.name not in values:
            v.set_value(None)
            continue
        value = values[v.name]
        require(value is not None and math.isfinite(value), "Nonfinite saved variable")
        if v.fixed:
            require(close(value,pyo.value(v),1e-10), f"Fixed variable changed: {v.name}")
        v.set_value(value,skip_validation=True)
        max_bound = max(max_bound, pyo.value(v.lb)-value if v.has_lb() else 0., value-pyo.value(v.ub) if v.has_ub() else 0.)
        if v.is_integer():
            max_bound = max(max_bound,abs(value-round(value)))
    for c in prepared.constraints:
        value = pyo.value(c.body,exception=False)
        require(value is not None and math.isfinite(value), f"Undefined original constraint: {c.name}")
        max_constraint = max(max_constraint,pyo.value(c.lower)-value if c.has_lb() else 0., value-pyo.value(c.upper) if c.has_ub() else 0.)
    return dict(objective=float(pyo.value(prepared.model.obj)),max_constraint_violation=max_constraint,
                max_bound_violation=max_bound,variables_checked=len(values))


def audit_models(directory, sources):
    require(not any(n == 'gdp_models' or n.startswith('gdp_models.') for n in sys.modules), "Use a fresh process for frozen model audit")
    os.environ['RBFOPT_GDP_SOURCES'] = str(sources)
    sys.path.insert(0,str(directory / 'reproduction/frozen/nlp'))
    import pyomo.environ as pyo
    import pyomo
    from pyomo.common.errors import InfeasibleConstraintException
    from gdp_models.models import prepare_nlp
    from gdp_models._sources import provenance
    from cstr_box_ipopt import initialize_feasible, formulation_fingerprint
    expected = read(directory / 'reproduction/expected_environment.json')['manifest']['runtime']['source']
    require(pyomo.__version__ == '6.10.0', 'Model audit requires Pyomo 6.10.0')
    require(provenance('dsda-gdp',list(expected['files_sha256'])) == expected,'Local upstream model source mismatch')
    checked = []
    with patch.object(type(pyo.SolverFactory),'__call__',side_effect=AssertionError('Optimization forbidden in return audit')):
        for first in sorted((directory / 'points').glob('*/first_attempt.json')):
            record = read(first)
            point = record['point']
            try:
                prepared = prepare_nlp('cstr',point,cstr_size=30,initialization='default')
            except InfeasibleConstraintException:
                require(point[1] > point[0] and not record['initialization_applied'], 'Unexpected structural rejection')
                checked.append(dict(point=point,structural_rejection=True,formulation_unchanged=None,
                                    initial_verified=False,returned_solution_verified=False,final_state=None))
                continue
            before = formulation_fingerprint(prepared)
            initialize_feasible(prepared)
            after = formulation_fingerprint(prepared)
            require(before == after == record['formulation_before'] == record['formulation_after'],'Formulation fingerprint mismatch')
            initial = read(first.parent / 'initial_values.json')
            for v in prepared.model.component_data_objects(pyo.Var):
                if v.name in initial:
                    require(close(v.value,initial[v.name],1e-12),f'Initialization value differs: {point}/{v.name}')
            initial_check = check_vector(prepared,initial)
            require(max(initial_check['max_bound_violation'],initial_check['max_constraint_violation']) <= 1e-8,'Invalid initial point')
            final = read(first.parent / 'final_values.json')
            state = check_vector(prepared,final['values'])
            require(close(state['max_constraint_violation'],record['max_constraint_violation'],1e-12)
                    and close(state['max_bound_violation'],record['max_bound_violation'],1e-12),'Residual discrepancy')
            if record['accepted']:
                require(final['accepted'] and close(state['objective'],record['objective'],1e-10)
                        and max(state['max_bound_violation'],state['max_constraint_violation']) <= 1e-5,'Invalid accepted vector')
            else:
                require(not final['accepted'] and final['objective'] is None,'Unavailable candidate promoted to solution')
            checked.append(dict(point=point,structural_rejection=False,formulation_unchanged=True,initial_verified=True,
                                returned_solution_verified=record['accepted'],final_state=state))
            if point[1] == point[0]:
                print(f"MODEL CHECK row {point[0]}/30",flush=True)
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,default=ROOT / 'results/archives' / ARCHIVE)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--sources',type=Path,default=ROOT / 'external')
    parser.add_argument('--skip-models',action='store_true',help='Only replay/accounting; do not claim model validation.')
    args = parser.parse_args()
    logging.getLogger('pyomo').setLevel(logging.ERROR)
    args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cstr30-return-audit-') as temp:
        directory = Path(temp)
        checksum_count = extract_verified(args.archive,directory)
        inputs = audit_inputs(directory)
        replay = replay_report(directory,args.output)
        coordinates = audit_coordinates(directory)
        runs, methods = audit_searches(directory)
        model_checks = None if args.skip_models else audit_models(directory,args.sources.resolve())
        csvwrite(args.output / 'coordinates.csv',coordinates)
        csvwrite(args.output / 'acceptance_changes.csv',[r for r in coordinates if r['old_accepted'] != r['new_accepted']])
        csvwrite(args.output / 'paired_search_audit.csv',runs)
        csvwrite(args.output / 'methods.csv',methods)
        write(args.output / 'model_checks.json',model_checks)
        logical = [r for r in coordinates if r['logical_allowed']]
        common = [r for r in coordinates if r['old_accepted'] and r['new_accepted']]
        summary = dict(coordinates=len(coordinates),logical=len(logical),structural=len(coordinates)-len(logical),
            interface_attempts=sum(r['interface_attempts'] for r in coordinates),
            confirmed_cstr_ipopt_invocations=sum(r['confirmed_cstr_ipopt_invocations'] for r in coordinates),
            separate_preflight_ipopt_invocations=read(directory / 'preflight/nlp/actual_environment.json')['smoke_nlp_calls'],
            failed_before_cstr_ipopt=[r['point'] for r in logical if r['confirmed_cstr_ipopt_invocations']==0],
            old_accepted=sum(r['old_accepted'] for r in coordinates),new_accepted=sum(r['new_accepted'] for r in coordinates),
            old_termination_counts=dict(Counter(r['old_termination'] for r in coordinates)),
            new_status_counts=dict(Counter(r['new_status'] for r in coordinates)),
            both_accepted=len(common),newly_accepted=sum(not r['old_accepted'] and r['new_accepted'] for r in coordinates),
            newly_rejected=sum(r['old_accepted'] and not r['new_accepted'] for r in coordinates),
            maximum_absolute_objective_change_common=max(abs(r['objective_delta_if_both_accepted']) for r in common),
            all_common_changes_below_1e_minus_5=all(abs(r['objective_delta_if_both_accepted'])<1e-5 for r in common),
            old_evaluation_total_s=sum(r['old_total_s'] for r in coordinates),new_evaluation_total_s=sum(r['new_total_s'] for r in coordinates),
            old_evaluation_median_s=statistics.median(r['old_total_s'] for r in coordinates),
            new_evaluation_median_s=statistics.median(r['new_total_s'] for r in coordinates),
            old_solve_wall_s_sum=sum(r['old_solve_s'] for r in coordinates),new_solve_wall_s_sum=sum(r['new_solve_s'] for r in coordinates),
            timing_by_structure={kind:{era+'_total_s':sum(r[era+'_total_s'] for r in coordinates if r['logical_allowed']==allowed)
                                      for era in ('old','new')} for kind,allowed in [('logical',True),('structural',False)]},
            total_search_attempts=len(runs),new_search_execution_failures=sum(r['new_failed'] for r in runs),
            common_initial_triples_verified=True,all_search_settings_verified=True,
            failed_point_search_visits=sum(r['failed_point_27_10_visits'] for r in runs),
            cstr30_old_hits=sum(m['old_hits'] for m in methods),cstr30_new_hits=sum(m['new_hits'] for m in methods),
            all_cstr_old_hits=sum(m['all_cstr_old_hits'] for m in methods),all_cstr_new_hits=sum(m['all_cstr_new_hits'] for m in methods),
            all_cstr_runs=sum(m['all_cstr_runs'] for m in methods),fixed_target=runs[0]['target'],
            new_minimum=min(r['new_objective'] for r in coordinates if r['new_accepted']),
            reference_coordinate=next(r for r in coordinates if r['point']==[30,30]),
            measured_search_s=sum(r['new_search_s'] for r in runs),new_search_completion_estimate_s=sum(r['new_completion_s'] for r in runs),
            old_search_completion_estimate_s=sum(r['old_completion_s'] for r in runs),
            new_optimization_calls_during_analysis=0,model_audit_completed=model_checks is not None)
        if model_checks is not None:
            returned = [r['final_state'] for r in model_checks if r['returned_solution_verified']]
            summary['returned_solution_vectors_verified'] = len(returned)
            summary['maximum_returned_constraint_violation'] = max(r['max_constraint_violation'] for r in returned)
            summary['maximum_returned_bound_violation'] = max(r['max_bound_violation'] for r in returned)
        write(args.output / 'audit_summary.json',summary)
        manifest=dict(archive=str(args.archive.relative_to(ROOT)) if args.archive.is_relative_to(ROOT) else args.archive.name,
            archive_sha256=SHA256,archive_bytes=args.archive.stat().st_size,outer_checksum='locally computed; server sidecar not provided',
            internal_checksum_entries=checksum_count,**inputs,reproduced_report_files=replay,
            analysis_python=platform.python_version(),analysis_platform=platform.platform(),
            analysis_source_sha256=sha(Path(__file__)),model_audit_completed=model_checks is not None,
            call_count_note='Returned nlp_calls counts solve_gams entry attempts; actual CSTR IPOPT invocations are independently counted from solver logs and GAMS model/stat artifacts.')
        write(args.output / 'audit_manifest.json',manifest)
        print(json.dumps({k:summary[k] for k in ('interface_attempts','confirmed_cstr_ipopt_invocations','old_accepted','new_accepted','cstr30_old_hits','cstr30_new_hits','all_cstr_old_hits','all_cstr_new_hits')},indent=2))


if __name__ == '__main__':
    main()
