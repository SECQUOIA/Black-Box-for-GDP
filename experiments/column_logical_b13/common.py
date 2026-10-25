"""Frozen-reference validation and timing for the independent Column follow-up."""

import csv
import hashlib
import json
import math
from pathlib import Path

METHODS = ("dsda", "rbfopt", "bam", "fmqa_sa", "uniform_without_replacement")
THREADS = dict.fromkeys(
    (
        "OMP_NUM_THREADS",
        "OMP_THREAD_LIMIT",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ),
    "1",
)
THREADS.update(OMP_DYNAMIC="FALSE", MKL_DYNAMIC="FALSE")
LOWER, UPPER, BUDGET = [8, 1], [15, 8], 13
POINTS = {(x, y) for x in range(8, 16) for y in range(1, 9)}


def require(test, message):
    if not test:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def rows(path):
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def csvwrite(path, data, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(k for r in data for k in r))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for r in data:
            writer.writerow(
                {
                    k: json.dumps(v, allow_nan=False)
                    if isinstance(v, (list, dict))
                    else v
                    for k, v in r.items()
                    if k in fields
                }
            )


def events(path):
    return (
        [json.loads(line) for line in Path(path).read_text().splitlines()]
        if Path(path).exists()
        else []
    )


def hit(value, target):
    return (
        value is not None
        and math.isfinite(value)
        and abs(value - target) <= 1e-5 * max(1, abs(target))
    )


def table(path):
    data = rows(path)
    result = {tuple(json.loads(r["point"])): r for r in data}
    require(len(data) == len(result), "Duplicate evaluation coordinates")
    return result


def validate_plan(plan):
    require(len(plan) == 50, "Expected exactly 50 Column jobs")
    require(
        {(j["spec"]["method"], j["spec"]["seed"]) for j in plan}
        == {(m, s) for m in METHODS for s in range(10)},
        "Missing or duplicate method/seed",
    )
    require(len({j["spec"]["job_id"] for j in plan}) == 50, "Duplicate job identifier")
    for seed in range(10):
        group = [j for j in plan if j["spec"]["seed"] == seed]
        starts = group[0]["spec"]["starts"]
        require(
            len(starts) == 3
            and len(set(map(tuple, starts))) == 3
            and all(tuple(p) in POINTS for p in starts),
            "Invalid initial design",
        )
        for job in group:
            spec = job["spec"]
            require(
                spec["starts"] == starts
                and spec["lower"] == LOWER
                and spec["upper"] == UPPER
                and spec["case"] == "column"
                and spec["budget"] == BUDGET,
                "Scope/design changed",
            )
            require(
                job["hard_seconds"] == 2100 and job["cpu"] == 2, "CPU/watchdog changed"
            )
            if spec["method"] == "rbfopt":
                require(
                    spec["settings"]["global_search_method"] == "genetic",
                    "Incorrect RBFOpt variant",
                )


def verify_package(root):
    manifest = read(root / "manifest.json")
    for name, checksum in manifest["files_sha256"].items():
        path = (root / name).resolve()
        require(
            path.is_relative_to(root.resolve()) and sha(path) == checksum,
            "Package hash mismatch: " + name,
        )
    plan = read(root / "plan.json")
    validate_plan(plan)
    costs = table(root / "inputs/column_64.csv")
    require(set(costs) == POINTS and len(costs) == 64, "Incomplete 64-coordinate input")
    require(
        sum(r["accepted"] == "True" for r in costs.values()) == 29,
        "Acceptance inventory changed",
    )
    require(
        all(
            math.isfinite(float(r["total_wall_s"])) and float(r["total_wall_s"]) > 0
            for r in costs.values()
        ),
        "Missing/invalid measured cost",
    )
    return plan, costs


def measure(spec, ev, result, costs, target, primary="final_best_absolute"):
    """Same measured-search-minus-lookup accounting, charging repeated callbacks."""
    charged = [
        e for e in ev if e["index"] <= spec["budget"] and not e.get("budget_overrun")
    ]
    accepted = [e for e in charged if e["accepted"]]
    best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
    any_hit = any(hit(e["raw_objective"], target) for e in accepted)
    final_hit = bool(best and hit(best["raw_objective"], target))
    status = result.get("status", "not_run")
    protocol_error = (
        len(ev) > spec["budget"]
        or any(e.get("budget_overrun") for e in ev)
        or [e["point"] for e in ev[:3]] != spec["starts"][: min(3, len(ev))]
        or [e["index"] for e in ev] != list(range(1, len(ev) + 1))
    )
    failed = (
        status not in ("completed", "budget_completed")
        or best is None
        or protocol_error
    )
    target_hit = (
        final_hit if primary == "final_best_absolute" else any_hit
    ) and not failed
    ledger, missing = [], []
    for e in charged:
        r = costs.get(tuple(e["point"]))
        require(r is not None, "Unmeasured coordinate in a full evaluation table")
        require(
            e["accepted"] == (r["accepted"] == "True"),
            "Acceptance/cost record mismatch",
        )
        if e["accepted"]:
            require(
                e["raw_objective"] == float(r["objective"]),
                "Objective/cost attempt mismatch",
            )
        cost = float(r["total_wall_s"]) if r.get("total_wall_s") else None
        if cost is None:
            missing.append(e["point"])
        else:
            require(math.isfinite(cost) and cost >= 0, "Invalid evaluation cost")
        ledger.append(
            {
                **e,
                "point_cost_s": cost,
                "evaluation_record_sha256": r.get("record_sha256"),
                "repeated_point": any(p["point"] == e["point"] for p in ledger),
            }
        )
    wall = result.get("recorded_search_wall_s", result.get("dfo_wall_s"))
    lookup = sum(e["lookup_wall_s"] for e in ev)
    retained = wall - lookup if wall is not None else None
    total = sum(e["point_cost_s"] for e in ledger) if not missing else None
    objective = best["raw_objective"] if best else None
    return dict(
        status=status,
        category="execution_failed"
        if failed
        else "target_reached"
        if target_hit
        else "target_not_reached",
        target_hit=target_hit,
        target=target,
        target_rule=primary,
        any_target_hit=any_hit and not failed,
        final_best_target_hit=final_hit and not failed,
        best_objective=objective,
        best_point=best["point"] if best else None,
        callbacks=len(charged),
        first_hit=next(
            (e["index"] for e in accepted if hit(e["raw_objective"], target)), None
        )
        if target_hit
        else None,
        shared_starts_complete=[e["point"] for e in ev[:3]] == spec["starts"],
        protocol_error=protocol_error,
        search_s=wall,
        lookup_s=lookup,
        retained_search_s=retained,
        point_cost_s=total,
        completion_s=retained + total
        if retained is not None and total is not None
        else None,
        missing_cost_points=missing,
        better_than_reference_but_final_miss=bool(
            objective is not None and objective < target and not final_hit
        ),
    ), ledger
