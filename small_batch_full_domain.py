"""Small Batch on the original GDP domain {1,2,3}^3, with no feasibility pruning."""

from functools import lru_cache
import itertools
import math
from pathlib import Path
import time

from overnight_benchmark.common import csv_file, read, sha

ROOT = Path(__file__).resolve().parent
KIND = "small_batch_full_domain_dfo_v1"
BUNDLE_FOLDER = "small_batch_full_domain_runner"
REFERENCE = "benchmark_protocols/small_batch_full_domain.json"
SOURCE_FILES = ("small_batch_full_domain.py", REFERENCE,
                "run_small_batch_full_domain_dantzig.sh", "docs/small_batch_full_domain.md",
                "tests/test_small_batch_full_domain.py")
METHODS = ("dsda", "rbfopt", "bam", "fmqa_sa")
PENALTY = 1e6
PROTOCOL = {
    "domain": "{1,2,3}^3: original GDP unit-count choices",
    "feasible_points": 12, "preprocessing_infeasible_points": 15,
    "seeds": list(range(10)), "n_starts": 3, "total_evaluation_budget": 10,
    "initial_evaluations_in_budget": True,
    "initial_design": "Full-domain shared LHC, frozen under the original DFO SciPy; no rejection or reseeding",
    "objective_mode": "Original lookup values; known infeasible configurations from audited GDP enumeration",
    "infeasible_response": {"dsda": PENALTY, "rbfopt": PENALTY, "bam": "NaN", "fmqa_sa": "raw infinity; reported penalty 1e6"},
    "dsda_domain": "All 27 coordinate keys, no feasible-only neighbor filter; infeasible callbacks consume budget",
    "rbfopt": "MSRSM + sampling + rbf=auto",
    "trajectory": "Every actual callback, including infeasible and repeated evaluations; FMQA proposals separately saved",
    "nlp_cost": "Reuse 27 measured Dantzig GAMS/IPOPT-profile point costs; include preprocessing rejection time",
    "time_formula": "method wall time - lookup call time + measured point cost for every callback",
    "measured_online_runtime": False,
}


@lru_cache(maxsize=1)
def reference():
    from case_studies.small_batch_case import SMALL_BATCH_FEASIBLE_OBJECTIVES
    from fmqa_benchmark.protocol import point_hash
    data = read(ROOT / REFERENCE)
    if sha(ROOT / data["lookup_csv"]) != data["lookup_csv_sha256"]:
        raise ValueError("Small Batch lookup source changed")
    points = {tuple(p["point"]): p for p in data["points"]}
    if len(data["points"]) != 27 or set(points) != set(itertools.product(range(1, 4), repeat=3)):
        raise ValueError("Expected all 27 original GDP configurations")
    accepted = 0
    for key, point in points.items():
        record = point["measurement"]
        feasible = key in SMALL_BATCH_FEASIBLE_OBJECTIVES
        if (point["lookup_value"] != SMALL_BATCH_FEASIBLE_OBJECTIVES.get(key)
                or record["point"] != list(key) or record["accepted"] != feasible
                or record["solver"] != "gams_ipopt" or record["time_limit_s"] != 60
                or record["status"] != ("accepted" if feasible else "preprocessing_infeasible")
                or not 0 < record["total_wall_s"] < math.inf
                or not 0 <= record["solve_wall_s"] <= record["total_wall_s"]):
            raise ValueError(f"Invalid objective or point timing: {key}")
        if feasible:
            if (not point["lookup_value"] < PENALTY
                    or not math.isclose(record["objective"], point["lookup_value"], rel_tol=1e-5)):
                raise ValueError("NLP enumeration disagrees with lookup solution")
            accepted += 1
        elif record["solve_wall_s"] != 0:
            raise ValueError("Preprocessing rejection must not contain a solver invocation")
    if accepted != 12:
        raise ValueError("Unexpected feasible count")
    if [d["seed"] for d in data["initial_designs"]] != list(range(10)):
        raise ValueError("Expected unfiltered seeds 0-9")
    for design in data["initial_designs"]:
        starts = design["points"]
        if (len(starts) != 3 or len({tuple(p) for p in starts}) != 3
                or point_hash(starts) != design["sha256"]
                or any(tuple(p) not in points for p in starts)):
            raise ValueError("Invalid frozen full-domain initial design")
        if not any(tuple(p) in SMALL_BATCH_FEASIBLE_OBJECTIVES for p in starts):
            raise ValueError("A frozen initial design has no feasible DSDA start; do not silently reseed")
    return data


def plan():
    from process_followup_runner import FMQA_CONFIG
    settings = {"dsda": {"diagonal": True, "tie_break": "first"},
                "rbfopt": {"algorithm": "MSRSM", "global_search_method": "sampling", "rbf": "auto"},
                "bam": {}, "fmqa_sa": dict(FMQA_CONFIG)}
    return [{"case_name": "small_batch", "csv_name": "compl_enum_small_batch_baron.csv",
             "domain": "full_1_to_3", "lower_bounds": [1, 1, 1], "upper_bounds": [3, 3, 3],
             "grid_size": None, "max_evaluations": 10, "n_starts": 3, "seed": d["seed"],
             "method": method, "settings": dict(settings[method]), "starting_points": d["points"],
             "initial_design_sha256": d["sha256"],
             "job_id": f"small_batch_full_B10_seed{d['seed']}_{method}"}
            for d in reference()["initial_designs"] for method in METHODS]


def problem(spec):
    if (spec["case_name"] != "small_batch" or spec["domain"] != "full_1_to_3"
            or spec["lower_bounds"] != [1, 1, 1] or spec["upper_bounds"] != [3, 3, 3]):
        raise ValueError("This experiment is exclusively Small Batch on {1,2,3}^3")
    values = {tuple(p["point"]): p["lookup_value"] for p in reference()["points"]}

    def objective(point):
        key = tuple(int(round(v)) for v in point)
        if key not in values:
            raise ValueError(f"Callback outside declared domain: {point}")
        value = values[key]
        return math.inf if value is None else value

    return {"objective": objective, "lower": [1, 1, 1], "upper": [3, 3, 3],
            "target": min(v for v in values.values() if v is not None)}


def run_dfo(spec, config):
    from instrumentation import TrackedObjective, make_result_record
    oracle = problem(spec)
    raw_objective = oracle["objective"]

    def penalized(point):
        value = raw_objective(point)
        return value if math.isfinite(value) else PENALTY

    def nan_objective(point):
        value = raw_objective(point)
        return value if math.isfinite(value) else math.nan

    n_initial, budget = spec["n_starts"], spec["max_evaluations"]
    stop_reason, iterations, solver_evals, solver_status, solver_message = None, None, None, None, ""
    if spec["method"] == "bam":
        from case_studies.bam_common import run_bam_with_initial_design
        result = run_bam_with_initial_design(
            nan_objective, oracle["lower"], oracle["upper"], spec["starting_points"], budget,
            bam_license_file=config["bam_license"], verbose=True)
        best, point, elapsed = result["best_value"], result["best_point"], result["wall_time_s"]
        calls, unique, history = result["tracked_evals"], result["unique_evals"], result["incumbent_trajectory"]
        iterations, solver_evals = result["iterations"], result["evalcount"]
        solver_status, solver_message = result["status"], result["message"]
    else:
        tracked = TrackedObjective(penalized)
        if spec["method"] == "dsda":
            from grid_dsda import dsda_from_csv
            # Only membership is used by the existing DSDA neighbor/line search.
            # Every domain coordinate exists, with no objective values supplied.
            domain = dict.fromkeys(itertools.product(range(1, 4), repeat=3))
            started = time.perf_counter()
            initial = [(p, tracked(p)) for p in spec["starting_points"]]
            feasible = [(p, v) for p, v in initial if v < PENALTY]
            if not feasible:
                raise ValueError("No feasible initial point; the run must not be silently reseeded")
            point, best = min(feasible, key=lambda item: item[1])
            result = dsda_from_csv(
                improvement_abs_tol=None,  # Historical full-domain campaign.
                csv_path="small_batch_full_domain", grid=domain, tracked_objective=tracked,
                start_point=point, start_value=best, max_points_explored=budget - n_initial,
                diagonal=spec["settings"]["diagonal"], tie_break=spec["settings"]["tie_break"], verbose=True)
            best, point = result["best_value"], result["best_point"]
            elapsed = time.perf_counter() - started
            iterations, stop_reason = result["major_iterations"], result["stop_reason"]
        elif spec["method"] == "rbfopt":
            import numpy as np
            import rbfopt
            black_box = rbfopt.RbfoptUserBlackBox(3, np.array(oracle["lower"]), np.array(oracle["upper"]),
                                                np.array(["I"] * 3), tracked)
            settings = rbfopt.RbfoptSettings(
                max_evaluations=budget, rand_seed=spec["seed"], num_cpus=1,
                minlp_solver_path=config["bonmin"], nlp_solver_path=config["ipopt"], **spec["settings"])
            started = time.perf_counter()
            algorithm = rbfopt.RbfoptAlgorithm(settings, black_box,
                init_node_pos=np.asarray(spec["starting_points"], dtype=float),
                init_node_val=None, do_init_strategy=False)
            best, point, iterations, solver_evals, _ = algorithm.optimize()
            elapsed = time.perf_counter() - started
        else:
            raise ValueError(f"Unsupported DFO method: {spec['method']}")
        calls, unique, history = tracked.call_count, tracked.unique_evaluation_count, tracked.incumbent_trajectory
    point = [int(round(v)) for v in point]
    record = make_result_record(
        spec["csv_name"], {"dsda": "DSDA", "rbfopt": "RBFOpt", "bam": "BAM"}[spec["method"]],
        spec["seed"], n_initial, budget, best, point, calls, elapsed,
        math.isclose(best, oracle["target"], rel_tol=1e-12, abs_tol=1e-9), history,
        initial_evals=n_initial, adaptive_evals=calls - n_initial, unique_evals=unique,
        solver_evalcount=solver_evals, solver_iterations=iterations,
        solver_status=solver_status, solver_message=solver_message)
    return {"result_record": record, "stop_reason": stop_reason}


def smoke(config):
    for method in ("rbfopt", "bam"):
        spec = next(s for s in plan() if s["seed"] == 0 and s["method"] == method)
        run_dfo({**spec, "max_evaluations": 4}, config)


def report_costs(directory, results, callbacks):
    """Export point costs without running a new NLP or altering optimizer feedback."""
    points = {tuple(p["point"]): p for p in reference()["points"]}
    ledger, groups, estimates = [], {}, []
    for event in callbacks:
        ref = points[tuple(event["point"])]
        measurement = ref["measurement"]
        row = {**event, "lookup_feasible": ref["lookup_value"] is not None,
               "point_outcome": measurement["status"], "point_evaluation_s": measurement["total_wall_s"],
               "point_solver_s": measurement["solve_wall_s"],
               "point_source": ref["source_member"], "point_source_sha256": ref["source_sha256"]}
        ledger.append(row)
        groups.setdefault(event["job_id"], []).append(row)
    for result in results:
        if result["status"] != "completed":
            continue
        spec, record = result["spec"], result["result_record"]
        rows = groups[spec["job_id"]]
        lookup = math.fsum(r["objective_wall_s"] for r in rows)
        point_cost = math.fsum(r["point_evaluation_s"] for r in rows)
        if len(rows) != record["total_evals"] or record["wall_time_s"] < lookup:
            raise ValueError("Callback count or method timer does not reconcile")
        estimates.append({"job_id": spec["job_id"], "method": spec["method"], "seed": spec["seed"],
            "budget": spec["max_evaluations"], "evaluations": len(rows), "unique_evaluations": record["unique_evals"],
            "feasible_evaluations": sum(r["lookup_feasible"] for r in rows),
            "infeasible_evaluations": sum(not r["lookup_feasible"] for r in rows),
            "target_hit": record["found_optimum"], "recorded_method_s": record["wall_time_s"],
            "lookup_s": lookup, "attached_point_s": point_cost,
            "estimated_completion_s": record["wall_time_s"] - lookup + point_cost,
            "measured_online_runtime": False})
    csv_file(directory / "evaluation_costs.csv", ledger)
    csv_file(directory / "completion_estimates.csv", estimates)
    return {"objective_mode": "lookup; archived point costs joined after optimization",
            "callbacks_with_point_cost": len(ledger), "callbacks_missing_point_cost": 0,
            "feasible_callbacks": sum(r["lookup_feasible"] for r in ledger),
            "infeasible_callbacks": sum(not r["lookup_feasible"] for r in ledger),
            "nlp_cost_reference_sha256": sha(ROOT / REFERENCE)}
