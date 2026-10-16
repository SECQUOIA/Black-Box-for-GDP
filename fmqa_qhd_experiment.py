"""Pinned QHD_Data PyTorch FM + the existing budgeted CPU-SA benchmark loop."""

from collections import defaultdict
import csv
from functools import lru_cache
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys

from cpu_affinity import affinity_record, pin_cpu
from fmqa_benchmark.protocol import point_hash, problem as original_problem, verify_lookup_sources
from fmqa_benchmark.qhd_surrogate import COMMIT, cpu_settings, train, upstream, verify_sources
from overnight_benchmark.common import THREADS, csv_file, read, sha
import small_batch_full_domain as small

ROOT = Path(__file__).resolve().parent
KIND = "fmqa_qhd_pytorch_sa_v1"
RESULT_METHOD = "FMQA-SA (PyTorch QHD_Data)"
RUN_PREFIX = "fmqa_qhd_"
BUNDLE_FOLDER = "fmqa_qhd_runner"
RUNTIME_ROLES = ("fmqa",)
FROZEN_PLAN = "benchmark_protocols/fmqa_qhd_plan.json"
PROCESS_COSTS = "results/dfo_trace_nlp_20261002/analysis/point_timings.csv"
PROCESS_MANIFEST = "results/dfo_trace_nlp_20261002/analysis/manifest.json"
GRID_COSTS = "results/grid_gdp_20261009/raw/point_timings.csv"
COLUMN_EXTRA = "results/process_followup_20261012/column_8_5_historical_point.json"
SOURCE_FILES = ("fmqa_qhd_experiment.py", "fmqa_benchmark/qhd_surrogate.py",
    "fmqa_benchmark/grid_protocol.py", "small_batch_full_domain.py", small.REFERENCE, FROZEN_PLAN,
    "run_fmqa_qhd_dantzig.sh", "requirements-fmqa-qhd.txt", "docs/fmqa_qhd_dantzig.md",
    "tests/test_fmqa_qhd.py", PROCESS_COSTS, PROCESS_MANIFEST, GRID_COSTS, COLUMN_EXTRA,
    *(p.relative_to(ROOT).as_posix() for folder in ("benchmark_grids", "fmqa_benchmark/reference/grid")
      for p in sorted((ROOT / folder).glob("*")) if p.suffix in (".csv", ".json")))
PROTOCOL = {
    "upstream": "https://github.com/SECQUOIA/bbo_via_fmqa", "branch": "QHD_Data", "commit": COMMIT,
    "backend": "unmodified upstream PyTorch FMBQM, float32, rank 8, native Adam and initialization",
    "sampler": "dwave.samplers.SimulatedAnnealingSampler; 100 reads; 1000 sweeps; geometric schedule",
    "comparison": "Same budgeted loop, frozen initial points, observed-only scaling, SA/fallback streams as the NumPy benchmark",
    "initial_evaluations_in_budget": True, "n_starts": 3, "epochs": 1000, "learning_rate": .01,
    "small_batch": "Original GDP domain {1,2,3}^3; budget 10; seeds 0-9",
    "column": "Seeds 1-10; budget 16; seed 10 is the approved supplement",
    "process_jobs": 140, "grid_jobs": 1050,
    "threads": 1, "device": "CPU", "dtype": "float32", "deterministic_algorithms": True,
    "time_limit": "1800 seconds checked between fitting/sampling; 2100-second external watchdog",
    "objective_mode": "lookup; measured point costs attached separately, missing measurements explicitly reported",
    "upstream_demo_not_executed": "Its 70% initial dataset, full-table scaling, dimod SA and x<y filter differ from this comparison",
}
SCOPE, SEEDS = "small_batch", None


def configure(scope, seeds=None):
    global SCOPE, SEEDS
    if scope not in ("small_batch", "process", "grid", "all"):
        raise ValueError("Unknown QHD experiment scope")
    if seeds is not None and (not seeds or len(seeds) != len(set(seeds)) or any(s not in range(11) for s in seeds)):
        raise ValueError("Seeds must be distinct integers from 0 to 10")
    SCOPE, SEEDS = scope, seeds


def plan():
    frozen = read(ROOT / FROZEN_PLAN)
    candidates = (frozen["process"] if SCOPE in ("small_batch", "process", "all") else []) + (
        frozen["grid"] if SCOPE in ("grid", "all") else [])
    selected = [s for s in candidates if (SCOPE != "small_batch" or s["case_name"] == "small_batch")
                and (SEEDS is None or s["seed"] in SEEDS)]
    if not selected:
        raise ValueError("No jobs match this scope and seed selection")
    for spec in selected:
        if (spec["method"] != "fmqa_sa" or spec["upstream_commit"] != COMMIT
                or spec["surrogate_backend"] != "pytorch_qhd_data"
                or point_hash(spec["starting_points"]) != spec["initial_design_sha256"]):
            raise ValueError("Unexpected frozen PyTorch run or initial design")
    return selected


def problem(spec):
    return small.problem(spec) if spec["case_name"] == "small_batch" else original_problem(spec)


def worker_setup():
    with cpu_settings():
        upstream()


def runtime(config, role):
    import torch
    from dwave.samplers import SimulatedAnnealingSampler
    if role != "fmqa" or (not platform.node().startswith("dantzig") and not config["allow_other_host"]):
        raise ValueError("Use this runner on Dantzig; local checks require --allow-other-host")
    cpu = pin_cpu(config["cpu"])
    expected = dict(line.split("==") for line in (ROOT / "requirements-fmqa-qhd.txt").read_text().splitlines()
                    if line and not line.startswith("#"))
    versions = {name: importlib.metadata.version(name) for name in expected}
    if any(versions[name].split("+")[0] != value for name, value in expected.items()):
        raise ValueError(f"QHD environment differs from the pinned requirements: {versions}")
    if platform.system() == "Linux" and (torch.version.cuda is not None or "+cpu" not in versions["torch"]):
        raise ValueError("Install the pinned official CPU-only PyTorch wheel")
    with cpu_settings() as settings:
        settings = dict(settings)
    provenance = verify_sources()
    sources = verify_lookup_sources()
    if SCOPE in ("grid", "all"):
        from fmqa_benchmark.grid_protocol import verify_grid_sources
        sources.update(verify_grid_sources())
    for spec in plan():
        oracle = problem(spec)
        if any(len(p) != len(oracle["lower"]) or any(not lo <= v <= hi for v, lo, hi in
                   zip(p, oracle["lower"], oracle["upper"])) for p in spec["starting_points"]):
            raise ValueError("Frozen initial point outside selected domain")
    first = train(["00", "01", "11"], [1., .5, 0.], seed=42, epochs=5, learning_rate=.01)
    second = train(["00", "01", "11"], [1., .5, 0.], seed=42, epochs=5, learning_rate=.01)
    if dict(first.linear) != dict(second.linear) or dict(first.quadratic) != dict(second.quadratic) or first.offset != second.offset:
        raise ValueError("Seeded native PyTorch fit was not reproducible")
    sample = SimulatedAnnealingSampler().sample(first, num_reads=3, num_sweeps=20, seed=42)
    if len(sample.record) == 0:
        raise ValueError("SA could not sample the native PyTorch FMBQM")
    return {"host": platform.node(), "platform": platform.platform(), "python": platform.python_version(),
        "executable": sys.executable, "versions": versions, "affinity": affinity_record(cpu),
        "thread_environment": {k: os.environ.get(k) for k in (*THREADS, "OMP_DYNAMIC", "MKL_DYNAMIC")},
        "pytorch": settings, "upstream": provenance, "lookup_data_sha256": sources,
        "installed_packages": dict(sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions() if d.metadata["Name"]))}


def rows(path):
    with (ROOT / path).open(newline="") as stream:
        return list(csv.DictReader(stream))


@lru_cache(maxsize=1)
def measured_points():
    points = {}
    for row in rows(PROCESS_COSTS):
        key = row["case"], row["cstr_size"], tuple(json.loads(row["point"]))
        if key in points:
            raise ValueError("Duplicate process point measurement")
        points[key] = {"point_evaluation_s": float(row["nlp_evaluation_wall_s"]),
                       "point_outcome": row["outcome"], "point_source": row["source"], "point_source_sha256": row["source_sha256"]}
    for item in small.reference()["points"]:
        points["small_batch", "", tuple(item["point"])] = {
            "point_evaluation_s": item["measurement"]["total_wall_s"], "point_outcome": item["measurement"]["status"],
            "point_source": item["source_member"], "point_source_sha256": item["source_sha256"]}
    extra = read(ROOT / COLUMN_EXTRA)
    points["column", "", (8, 5)] = {"point_evaluation_s": extra["total_wall_s"], "point_outcome": extra["status"],
                                   "point_source": COLUMN_EXTRA, "point_source_sha256": sha(ROOT / COLUMN_EXTRA)}
    grid_hash = sha(ROOT / GRID_COSTS)
    for row in rows(GRID_COSTS):
        key = "grid", row["grid_name"], tuple(json.loads(row["point"]))
        if key in points or row["accepted"] != "True" or row["threads"] != "1":
            raise ValueError("Invalid Grid measurement inventory")
        points[key] = {"point_evaluation_s": float(row["point_wall_s"]), "point_outcome": "accepted",
                       "point_source": GRID_COSTS, "point_source_sha256": grid_hash}
    if any(not 0 < p["point_evaluation_s"] < math.inf for p in points.values()):
        raise ValueError("Invalid measured point cost")
    return points


def report_costs(directory, results, callbacks):
    measurements = measured_points()
    specs = {r["spec"]["job_id"]: r["spec"] for r in results}
    ledger, groups, estimates = [], defaultdict(list), []
    for event in callbacks:
        spec = specs[event["job_id"]]
        size = Path(spec["csv_name"]).stem if spec["case_name"] == "grid" else str(spec.get("grid_size") or "")
        key = spec["case_name"], size, tuple(event["point"])
        measured = measurements.get(key, {"point_evaluation_s": None, "point_outcome": "measurement_missing",
                                          "point_source": None, "point_source_sha256": None})
        row = {**event, "surrogate_backend": "pytorch_qhd_data", **measured}
        ledger.append(row)
        groups[event["job_id"]].append(row)
    for result in results:
        if result["status"] != "completed":
            continue
        spec, record = result["spec"], result["result_record"]
        events = groups[spec["job_id"]]
        missing = sum(e["point_evaluation_s"] is None for e in events)
        lookup = math.fsum(e["objective_wall_s"] for e in events)
        attached = math.fsum(e["point_evaluation_s"] for e in events if e["point_evaluation_s"] is not None)
        preparation = 0.
        if spec["case_name"] == "dynamic":
            refs = read(ROOT / PROCESS_MANIFEST)["point_reuse_audit"]["preparations"]
            if len(refs) != 1 or refs[0]["included_in_point_total_wall_s"]:
                raise ValueError("Unexpected Dynamic preparation reference")
            preparation = refs[0]["total_preparation_wall_s"]
        if len(events) != record["total_evals"] or lookup > record["wall_time_s"]:
            raise ValueError("Trace and method cost do not reconcile")
        estimates.append({"job_id": spec["job_id"], "case": spec["case_name"], "csv_name": spec["csv_name"],
            "seed": spec["seed"], "budget": spec["max_evaluations"], "evaluations": len(events),
            "infeasible_evaluations": sum(not e["lookup_feasible"] for e in events),
            "target_hit": record["found_optimum"], "recorded_method_s": record["wall_time_s"],
            "lookup_s": lookup, "attached_known_point_s": attached, "dynamic_preparation_s": preparation,
            "missing_point_costs": missing, "estimated_completion_s": None if missing else record["wall_time_s"] - lookup + attached + preparation,
            "measured_online_runtime": False})
    csv_file(directory / "evaluation_costs.csv", ledger)
    csv_file(directory / "completion_estimates.csv", estimates)
    csv_file(directory / "missing_point_costs.csv", [r for r in ledger if r["point_evaluation_s"] is None])
    summaries = []
    for name, budget in sorted({(e["csv_name"], e["budget"]) for e in estimates}):
        group = [e for e in estimates if (e["csv_name"], e["budget"]) == (name, budget)]
        hits = sum(e["target_hit"] for e in group)
        times = [e["estimated_completion_s"] for e in group]
        repeats = math.inf if not hits else 1 if hits == len(group) else math.ceil(math.log(.01) / math.log1p(-hits / len(group)))
        median = statistics.median(times) if all(t is not None for t in times) else None
        planned = sum((s["csv_name"], s["max_evaluations"]) == (name, budget) for s in plan())
        summaries.append({"csv_name": name, "budget": budget, "completed_runs": len(group), "planned_runs": planned,
            "target_hits": hits, "median_completion_s": median,
            "tts99_s": None if median is None or len(group) != planned else median * repeats,
            "tts99_infinite": median is not None and len(group) == planned and not hits})
    csv_file(directory / "pytorch_summary.csv", summaries)
    return {"backend": RESULT_METHOD, "upstream_commit": COMMIT,
            "callbacks_with_point_cost": sum(r["point_evaluation_s"] is not None for r in ledger),
            "callbacks_missing_point_cost": sum(r["point_evaluation_s"] is None for r in ledger),
            "objective_mode": "lookup; complete point-cost estimates only when all callback measurements exist"}
