"""Execute exactly one validated Grid D-SDA job using stored CSV responses."""

import argparse
from contextlib import redirect_stdout
import importlib
import json
import os
from pathlib import Path
import random
import time
import traceback

from protocol import first_hit, hit, read, validate_job, verify_grid, write
from runtime import BLOCKED, THREADS, install_no_solver_guard

os.environ.update(THREADS)
ROOT = Path(__file__).resolve().parent


def execute(job, out, common_stop=True):
    validate_job(job)
    s = job["spec"]
    verify_grid(ROOT / "inputs/grids" / f"{s['case']}.csv", s)
    import numpy as np
    import grid_dsda as dsda

    importlib.import_module("scipy")
    install_no_solver_guard()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    random.seed(s["seed"])
    np.random.seed(s["seed"])
    original = dsda.TrackedObjective
    events = []

    class Recording(original):
        def __call__(self, p):
            v = super().__call__(p)
            events.append(
                dict(
                    index=self.call_count,
                    point=list(p),
                    raw_objective=v,
                    accepted=True,
                    lookup_wall_s=self.wall_times[-1],
                    phase="initial" if self.call_count <= 3 else "adaptive",
                )
            )
            return v

    dsda.TrackedObjective = Recording
    algorithm = None
    status = "completed"
    error = None
    start = time.perf_counter()
    try:
        with (out / "search.log").open("w") as f, redirect_stdout(f):
            options = {"target_stop": hit} if common_stop else {}
            algorithm = dsda.run_dsda_from_best_starting_points(
                ROOT / "inputs/grids" / f"{s['case']}.csv",
                s["starts"],
                target_value=job["target"],
                verbose=True,
                max_points_explored=s["budget"],
                improvement_abs_tol=1e-5,
                **s["settings"],
                **options,
            )
    except Exception as exc:
        status = "missing_lookup" if isinstance(exc, KeyError) else "execution_failed"
        error = traceback.format_exc()
    finally:
        dsda.TrackedObjective = original
    elapsed = time.perf_counter() - start
    best = min(events, key=lambda e: e["raw_objective"]) if events else None
    success = bool(
        best and hit(best["raw_objective"], job["target"]) and status == "completed"
    )
    paths = [r["path"] for r in algorithm["runs"]] if algorithm else []
    reason = (
        algorithm["stop_reason"] or "all_ranked_starts_exhausted"
        if algorithm
        else status
    )
    result = dict(
        spec=s,
        target=job["target"],
        improvement_abs_tol=1e-5,
        target_stop_rule="adopted_analysis.hit" if common_stop else "legacy",
        status=status,
        error=error,
        category="execution_failed"
        if status != "completed"
        else "target_reached"
        if success
        else "target_not_reached",
        hit=success,
        best_objective=best["raw_objective"] if best else None,
        best_point=best["point"] if best else None,
        evaluations=len(events),
        first_hit=first_hit(events, job["target"]),
        termination=reason,
        termination_callback=len(events),
        last_callback=events[-1]["point"] if events else None,
        path=paths,
        endpoint=paths[-1][-1] if paths else None,
        algorithm_result=algorithm,
        search_s=elapsed,
        lookup_s=sum(e["lookup_wall_s"] for e in events),
        solver_calls=0,
        process_nlp_calls=0,
        blocked_solver_or_process_attempts=list(BLOCKED),
        effective_cpus=sorted(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else None,
    )
    with (out / "callbacks.jsonl").open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    write(out / "result.json", result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    matches = [
        j for j in read(ROOT / "inputs/jobs.json") if j["spec"]["job_id"] == a.job
    ]
    if len(matches) != 1:
        raise ValueError("Missing or duplicate Grid job identifier")
    result = execute(matches[0], a.output)
    raise SystemExit(0 if result["status"] == "completed" else 1)
