"""One isolated algorithm run or point measurement, with durable event records."""

from pathlib import Path
import time
import traceback

from .common import now, read, save


def measured_point(spec, config, directory):
    from gdp_models.evaluation import evaluate_point
    return evaluate_point(
        spec["case_name"], spec["point"], cstr_size=spec.get("grid_size") or 5,
        solver=config["solver"], initialization=config["initialization"],
        time_limit=config["nlp_seconds"], feasibility_tolerance=1e-5,
        executable=config["gams"], artifact_dir=directory,
        baron_lp_solver="clp" if config["solver"] == "baron" else None)


def lookup(spec, config, directory):
    from case_study_benchmark import CASE_RUNNERS
    from case_studies.common import generate_lhc_starting_points
    from evaluation_trace import EvaluationTrace
    from fmqa_benchmark.protocol import problem
    oracle = problem(spec)
    starts = generate_lhc_starting_points(len(oracle["lower"]), spec["n_starts"],
                                         oracle["lower"], oracle["upper"], spec["seed"])
    if [list(p) for p in starts] != spec["starting_points"]:
        raise RuntimeError("Generated LHC design differs from frozen Dantzig coordinates")
    kwargs = dict(seed=spec["seed"], n_starts=spec["n_starts"],
                  max_evaluations=spec["max_evaluations"], verbose=True)
    if spec["case_name"] == "cstr":
        kwargs["grid_size"] = spec["grid_size"]
    if spec["method"] == "rbfopt":
        kwargs.update(minlp_solver_path=config["bonmin"], nlp_solver_path=config["ipopt"])
    if spec["method"] == "bam":
        kwargs["bam_license_file"] = config["bam_license"]
    save(directory / "clock.json", {"started_monotonic_s": time.monotonic(), "started_utc": now()})
    with EvaluationTrace(directory / "lookup.csv", spec) as trace:
        result = CASE_RUNNERS[spec["case_name"]][spec["method"]](**kwargs)
        completion = trace.timer() - trace.origin
        artifact = trace.complete(result["result_record"])
    return {"spec": spec, "mode": "lookup", "status": "completed",
            "result_record": result["result_record"], "trace": artifact,
            "wall_time_s": completion, "target": oracle["target"], "completed_utc": now()}


def point(spec, config, directory):
    from gdp_models.models import dynamic_template
    from gdp_models.preflight import model_check
    # The archived enumeration batches also ran model_check before starting
    # point timers. Match that source/import-cache state while preserving a
    # fresh model and identical variable initialization for the actual point.
    setup_started = time.monotonic()
    model_check(spec["case_name"], spec.get("grid_size") or 5, config["initialization"])
    setup_seconds = time.monotonic() - setup_started
    save(directory / "measurement_setup.json", {"wall_s": setup_seconds,
         "included_in_point_cost": False, "policy": "model_check before timer, as in original enumeration batch"})
    origin = time.monotonic()
    save(directory / "clock.json", {"started_monotonic_s": origin, "started_utc": now()})
    preparation = None
    if spec["case_name"] == "dynamic":
        preparation = dynamic_template().preparation
    started = time.monotonic()
    save(directory / "active_evaluation.json", {"point": spec["point"],
                                                "started_monotonic_s": started})
    record = measured_point(spec, config, directory / "solver")
    duration = time.monotonic() - started
    (directory / "active_evaluation.json").unlink()
    return {"spec": spec, "mode": "points", "status": "completed", "record": record,
            "evaluation_wall_s": duration, "preparation": preparation,
            "premeasurement_setup_wall_s": setup_seconds,
            "wall_time_s": time.monotonic() - origin, "completed_utc": now()}


def main(run_dir, mode, job_id):
    directory = Path(run_dir) / mode / job_id
    spec = read(directory / "spec.json")
    config = read(Path(run_dir) / "run.json")["config"]
    try:
        result = {"lookup": lookup, "points": point}[mode](spec, config, directory)
    except Exception as error:
        from gdp_models.preflight import SetupError
        traceback.print_exc()
        result = {"spec": spec, "mode": mode, "status": "setup_error" if isinstance(error, SetupError) else "error",
                  "error_type": type(error).__name__, "error": str(error), "completed_utc": now()}
    save(directory / "result.json", result)
    return 2 if result["status"] in {"error", "setup_error"} else 0
