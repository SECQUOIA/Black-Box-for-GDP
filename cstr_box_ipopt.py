"""Independent IPOPT evaluations for selected CSTR sizes, covering every box coordinate."""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch
import zipfile

from cstr30_retry import formulation_fingerprint, run_child, write_json

ROOT = Path(__file__).resolve().parent
SIZES = (5, 10, 15)
SUPPORTED_SIZES = (5, 10, 15, 20, 25)
KIND = "cstr_5_10_15_box_ipopt_v1"
INITIALIZATION = "mass_balance_zero_recycle"
BUNDLE_NAME = "cstr_box_ipopt_runner"
UPSTREAM_SHA256 = {
    "gdp/cstr/gdp_reactor.py": "d4883e8911da75242fe34db7905269e7b40a49b68054e21125ef6035653933b6",
    "gdp/dsda/dsda_functions.py": "797ba7b8570b7e8b9ca8b2c6d775bf654ace77cd629b9ad54eea6027d914fc87",
    "main_cstr.py": "b26b3895196716b0424d8aecb703a75e5c1d368fb2cbc9934bb299d836bb8183",
}
FIELDS = (
    "case", "cstr_size", "point_index", "x1", "x2", "point", "logical_allowed",
    "solver", "initialization_requested", "initialization", "status", "accepted",
    "objective", "candidate_objective", "termination", "solver_status",
    "gams_solve_status", "gams_model_status", "max_primal_violation",
    "initial_primal_violation", "initial_objective", "setup_wall_s", "preprocess_wall_s",
    "feasible_initialization_wall_s", "solve_wall_s", "total_wall_s",
    "worker_process_wall_s", "worker_pid", "worker_returncode", "worker_timed_out", "message",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_sizes(sizes):
    sizes = tuple(sizes)
    if not sizes or len(set(sizes)) != len(sizes) or any(n not in SUPPORTED_SIZES for n in sizes):
        raise ValueError(f"Select distinct sizes from {SUPPORTED_SIZES}")
    return sizes


def protocol_kind(sizes):
    return "cstr_" + "_".join(map(str, validate_sizes(sizes))) + "_box_ipopt_v1"


def manifest_sizes(manifest):
    sizes = validate_sizes(manifest.get("sizes", SIZES))
    if manifest["kind"] != protocol_kind(sizes) or manifest["coordinates"] != coordinates(sizes):
        raise ValueError("Unexpected run protocol/coordinates")
    return sizes


def coordinates(sizes=SIZES):
    return [{"case": "cstr", "cstr_size": n, "point_index": (x - 1) * n + y,
             "x1": x, "x2": y, "point": [x, y], "logical_allowed": y <= x}
            for n in validate_sizes(sizes) for x in range(1, n + 1) for y in range(1, n + 1)]


def key(row):
    return f"cstr_{row['cstr_size']}_{row['x1']:02d}_{row['x2']:02d}"


def csv_text(rows, fields):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({f: json.dumps(row[f]) if f == "point" and f in row
                         else row.get(f) for f in fields})
    return out.getvalue()


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".csv.tmp")
    temp.write_text(csv_text(rows, fields))
    temp.replace(path)


def source_files():
    return [ROOT / "cstr_box_ipopt.py", ROOT / "cstr30_retry.py",
            ROOT / "run_cstr_box_ipopt_dantzig.sh", ROOT / "requirements-gdp.txt",
            ROOT / "LICENSE", ROOT / "docs/cstr_box_ipopt_dantzig.txt",
            *sorted((ROOT / "gdp_models").glob("*.py"))]


def source_hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source_files()}


def initialize_feasible(prepared):
    """CSTR30 retry's balance-based start, applied to the requested model size."""
    import pyomo.environ as pyo
    from gdp_models.evaluation import primal_violation

    if prepared.metadata["case"] != "cstr" or prepared.metadata["cstr_size"] not in SUPPORTED_SIZES:
        raise ValueError(f"Expected CSTR size in {SUPPORTED_SIZES}")
    before = formulation_fingerprint(prepared)
    started = perf_counter()
    count = prepared.point[0]

    def concentrations(volume):
        inlet, result = 0.99, []
        for _ in range(count):
            b = 1 + 2 * volume
            inlet = 2 * inlet / (b + math.sqrt(b * b - 8 * volume * inlet))
            result.append(inlet)
        return result

    lo, hi = 0.0, 10.0
    if not concentrations(lo)[-1] > 0.05 > concentrations(hi)[-1]:
        raise RuntimeError("Could not bracket the mass-balance initialization")
    for _ in range(70):
        mid = (lo + hi) / 2
        if concentrations(mid)[-1] > 0.05:
            lo = mid
        else:
            hi = mid
    volume = (lo + hi) / 2
    active, m = concentrations(volume), prepared.model
    for n in m.N:
        a = active[count - n] if n <= count else 0.99
        m.Q[n].set_value(1)
        m.QFR[n].set_value(0)
        m.V[n].set_value(volume)
        m.c[n].set_value(volume if n <= count else 0)
        m.F["A", n].set_value(a)
        m.F["B", n].set_value(1 - a if n <= count else 0.01)
        rate = -2 * a * (1 - a) if n <= count else 0
        m.rate["A", n].set_value(rate)
        m.rate["B", n].set_value(-rate)
        for component in m.I:
            m.FR[component, n].set_value(0)
    m.QR.set_value(0)
    m.QP.set_value(1)
    for component, value in (("A", 0.05), ("B", 0.95)):
        m.R[component].set_value(0)
        m.P[component].set_value(value)
    elapsed = perf_counter() - started
    violation = primal_violation(prepared)
    if formulation_fingerprint(prepared) != before or not math.isfinite(violation) or violation > 1e-8:
        raise RuntimeError("Initialization changed the formulation or failed the residual check")
    prepared.metadata.update(initialization=INITIALIZATION, initial_primal_violation=violation,
                             initial_objective=pyo.value(m.obj), initial_equal_volume=volume,
                             constraints_and_bounds_unchanged=True, formulation_sha256=before)
    prepared.timings["feasible_initialization_wall_s"] = elapsed


def worker(args):
    from gdp_models import evaluation

    row = next(r for r in coordinates(args.sizes) if key(r) == args.point_key)
    original = evaluation.prepare_nlp

    def prepare(*a, **kw):
        prepared = original(*a, **kw)
        initialize_feasible(prepared)
        return prepared

    started = perf_counter()
    try:
        with patch.object(evaluation, "prepare_nlp", prepare):
            report = evaluation.evaluate_point(
                "cstr", row["point"], cstr_size=row["cstr_size"], solver="gams_ipopt",
                initialization="default", executable=args.executable, time_limit=args.time_limit,
                feasibility_tolerance=1e-5, tee=True, artifact_dir=args.artifact_dir)
    except Exception as error:
        import traceback
        traceback.print_exc()
        report = {"accepted": False, "status": "worker_error", "objective": None,
                  "termination": "error", "message": f"{type(error).__name__}: {error}",
                  "total_wall_s": perf_counter() - started}
    report.update(row, solver="gams_ipopt", initialization_requested=INITIALIZATION,
                  worker_pid=os.getpid(), completed_utc=now())
    write_json(args.record, report)
    return 0


def run_point(directory, row, config):
    record = directory / "records" / (key(row) + ".json")
    command = [sys.executable, str(ROOT / "cstr_box_ipopt.py"), "_worker",
               "--sizes", str(row["cstr_size"]),
               "--point-key", key(row), "--record", str(record),
               "--artifact-dir", str(directory / "artifacts" / key(row)),
               "--executable", config["executable"], "--time-limit", str(config["time_limit"])]
    process = run_child(command, directory / "logs" / (key(row) + ".log"), config["worker_timeout"])
    try:
        report = json.loads(record.read_text())
        if (report.get("point") != row["point"] or report.get("cstr_size") != row["cstr_size"]
                or report.get("solver") != "gams_ipopt" or type(report.get("accepted")) is not bool):
            raise ValueError("Worker record has an incorrect identity")
        if process["worker_timed_out"] or process["worker_returncode"] != 0:
            raise ValueError("Worker timed out or exited abnormally")
    except (OSError, ValueError) as error:
        report = {**row, "solver": "gams_ipopt", "initialization_requested": INITIALIZATION,
                  "accepted": False, "objective": None,
                  "status": "worker_timeout" if process["worker_timed_out"] else "worker_error",
                  "termination": "error", "message": str(error), "completed_utc": now()}
    report.update(process)
    write_json(record, report)
    return report


def summarize(directory):
    manifest = json.loads((directory / "run.json").read_text())
    sizes = manifest_sizes(manifest)
    plan = coordinates(sizes)
    observed, expected = {}, {key(r): r for r in plan}
    for path in sorted((directory / "records").glob("*.json")):
        r = json.loads(path.read_text())
        identity = key(r)
        if (identity not in expected or identity in observed or path.stem != identity
                or any(r.get(k) != v for k, v in expected[identity].items())
                or r.get("solver") != "gams_ipopt" or type(r.get("accepted")) is not bool
                or r.get("status") == "pending"):
            raise ValueError(f"Unexpected/duplicate checkpoint: {path}")
        observed[identity] = r
    rows = [observed.get(key(r), {**r, "solver": "gams_ipopt",
                                 "initialization_requested": INITIALIZATION, "status": "pending"})
            for r in plan]
    write_csv(directory / "evaluations.csv", rows, FIELDS)
    cases = []
    for n in sizes:
        subset = [r for r in rows if r["cstr_size"] == n]
        write_csv(directory / f"cstr_{n}" / "evaluations.csv", subset, FIELDS)
        counts = Counter(r["status"] for r in subset)
        cases.append({"cstr_size": n, "expected_points": n * n,
                      "completed_points": n * n - counts["pending"], "status_counts": dict(counts),
                      "accepted_points": sum(r.get("accepted") is True for r in subset)})
    summary = {"expected_points": len(plan), "completed_points": len(observed),
               "pending_points": len(plan) - len(observed), "complete": len(observed) == len(plan),
               "accepted_points": sum(r.get("accepted") is True for r in rows),
               "status_counts": dict(Counter(r["status"] for r in rows)), "cases": cases,
               "unknown_evaluation_times": sum(r.get("total_wall_s") is None for r in observed.values()),
               "sum_known_evaluation_wall_s": sum(r["total_wall_s"] for r in observed.values()
                                                  if r.get("total_wall_s") is not None),
               "updated_utc": now()}
    write_json(directory / "summary.json", summary)
    return summary, observed


def pack(directory):
    summary, _ = summarize(directory)
    files = [p for p in sorted(directory.rglob("*")) if p.is_file() and not p.is_symlink()
             and p.name not in {"SHA256SUMS", ".batch.lock"} and not p.name.endswith(".tmp")
             and "__pycache__" not in p.parts]
    checks = directory / "SHA256SUMS"
    checks.write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(directory)}\n"
                             for p in files))
    archive = directory.with_name(directory.name + ".zip")
    temp = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in [*files, checks]:
            z.write(p, f"{directory.name}/{p.relative_to(directory)}")
    with zipfile.ZipFile(temp) as z:
        if z.testzip() is not None:
            raise RuntimeError("Invalid result ZIP")
    temp.replace(archive)
    archive.with_suffix(".zip.sha256").write_text(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n")
    print(f"RESULT_DIR={directory}\nRESULT_ZIP={archive}", flush=True)
    return summary


def run_points(directory, manifest, max_points=None):
    plan = coordinates(manifest_sizes(manifest))
    for name in ("records", "logs", "artifacts"):
        (directory / name).mkdir(exist_ok=True)
    if not (directory / "run.json").exists():
        write_json(directory / "run.json", manifest)
        write_csv(directory / "coordinates.csv", plan, list(plan[0]))
        for p in source_files():
            target = directory / "source" / p.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
    _, observed = summarize(directory)
    count = 0
    try:
        for row in plan:
            if key(row) in observed:
                continue
            if max_points is not None and count >= max_points:
                break
            try:
                report = run_point(directory, row, manifest["config"])
            except Exception as error:
                report = {**row, "solver": "gams_ipopt", "initialization_requested": INITIALIZATION,
                          "accepted": False, "status": "worker_error", "objective": None,
                          "termination": "error", "message": f"{type(error).__name__}: {error}"}
                write_json(directory / "records" / (key(row) + ".json"), report)
            count += 1
            print(f"{key(row)}: {report['status']} objective={report.get('objective')}", flush=True)
            summarize(directory)
    finally:
        summary = pack(directory)
    return summary


def bundle(output, sizes=SIZES):
    sizes = validate_sizes(sizes)
    plan = coordinates(sizes)
    output.parent.mkdir(parents=True, exist_ok=True)
    entries = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in source_files()}
    entries["coordinates.csv"] = csv_text(plan, list(plan[0])).encode()
    entries["run.sh"] = (
        '#!/usr/bin/env bash\nset -Eeuo pipefail\n'
        'cd -- "$(dirname -- "${BASH_SOURCE[0]}")"\n'
        'mode=${1:-check}\nif [[ $# -gt 0 ]]; then shift; fi\n'
        'exec bash run_cstr_box_ipopt_dantzig.sh "$mode" --sizes '
        + ' '.join(map(str, sizes)) + ' "$@"\n').encode()
    entries["bundle_protocol.json"] = (json.dumps({
        "kind": protocol_kind(sizes), "sizes": sizes, "expected_points": len(plan),
        "logical_points": sum(r["logical_allowed"] for r in plan),
        "initialization": INITIALIZATION, "launcher": "bash run.sh run",
    }, indent=2) + "\n").encode()
    entries["RUNNER_SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in entries.items()).encode()
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(f"{BUNDLE_NAME}/{name}", data)
    with zipfile.ZipFile(output) as z:
        if z.testzip() is not None:
            raise RuntimeError("Invalid runner ZIP")
    output.with_suffix(".zip.sha256").write_text(
        f"{hashlib.sha256(output.read_bytes()).hexdigest()}  {output.name}\n")
    print(f"RUNNER_ZIP={output}")


def runtime(executable, expected_version, sizes=SIZES):
    from gdp_models import batch
    from gdp_models._sources import provenance
    from gdp_models.solvers import optimizer_for
    if provenance("dsda-gdp", UPSTREAM_SHA256)["files_sha256"] != UPSTREAM_SHA256:
        raise ValueError("Upstream CSTR source differs from the audited model")
    binary = shutil.which(executable)
    if not binary:
        raise ValueError(f"GAMS executable not found: {executable}")
    binary = str(Path(binary).resolve())
    actual = tuple(optimizer_for("gams_ipopt", binary).version())
    expected = tuple(map(int, expected_version.split(".")))
    if not expected or actual[:len(expected)] != expected:
        raise ValueError(f"Expected GAMS {expected_version}, found {actual}")
    identities = {str(n): batch._runtime_identity("cstr", n, "default", "gams_ipopt", binary)
                  for n in validate_sizes(sizes)}
    # The runtime identity describes the constructor baseline; every feasible
    # worker additionally applies the declared balance-based initial values.
    for identity in identities.values():
        identity["post_preprocessing_initialization"] = INITIALIZATION
    return binary, identities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("bundle", "check", "run", "resume", "pack", "status", "_worker"))
    parser.add_argument("--sizes", nargs="+", type=int, choices=SUPPORTED_SIZES, default=SIZES)
    parser.add_argument("--executable", default=os.environ.get("GAMS_BIN", "/package/gams/52.2/gams"))
    parser.add_argument("--expected-gams-version", default="52.2")
    parser.add_argument("--time-limit", type=float, default=60)
    parser.add_argument("--worker-timeout", type=float, default=180)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--max-points", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--point-key")
    parser.add_argument("--record", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    args = parser.parse_args()
    if (not math.isfinite(args.time_limit) or args.time_limit <= 0
            or not math.isfinite(args.worker_timeout) or args.worker_timeout <= args.time_limit
            or (args.max_points is not None and args.max_points <= 0)):
        parser.error("Require positive limits, worker timeout > solve limit, and max-points > 0")
    try:
        sizes = validate_sizes(args.sizes)
        if args.mode == "bundle":
            if args.output is None:
                parser.error("bundle requires --output")
            bundle(args.output.resolve(), sizes)
            return 0
        if args.mode == "_worker":
            if args.point_key not in {key(r) for r in coordinates(sizes)} or args.record is None or args.artifact_dir is None:
                parser.error("_worker requires a valid point-key, record, and artifact-dir")
            return worker(args)
        from gdp_models import batch
        from gdp_models.dantzig import _pin_cpu
        if args.mode in {"resume", "pack", "status"}:
            if args.run_dir is None:
                parser.error(f"{args.mode} requires --run-dir")
            directory = args.run_dir.resolve()
            with batch._lock(directory):
                manifest = json.loads((directory / "run.json").read_text())
                sizes = manifest_sizes(manifest)
                if args.mode == "pack":
                    pack(directory)
                    return 0
                if args.mode == "status":
                    print(json.dumps(summarize(directory)[0], indent=2))
                    return 0
                _pin_cpu(manifest["cpu"])
                _, identities = runtime(manifest["config"]["executable"], manifest["expected_gams_version"], sizes)
                if manifest["source_hashes"] != source_hashes() or manifest["runtime"] != identities:
                    raise ValueError("Resume requires unchanged runner, source, solver and environment")
                summary = run_points(directory, manifest, args.max_points)
        else:
            cpu = _pin_cpu(args.cpu)
            binary, identities = runtime(args.executable, args.expected_gams_version, sizes)
            plan = coordinates(sizes)
            manifest = {"kind": protocol_kind(sizes), "sizes": list(sizes),
                        "created_utc": now(), "coordinates": plan,
                        "initialization": INITIALIZATION, "cpu": cpu,
                        "config": {"executable": binary, "time_limit": args.time_limit,
                                   "worker_timeout": args.worker_timeout, "feasibility_tolerance": 1e-5},
                        "expected_gams_version": args.expected_gams_version,
                        "runtime": identities, "source_hashes": source_hashes(),
                        "isolation": "fresh Python process for every coordinate; sequential",
                        "cost_policy": "single new attempt per coordinate; no prior result replacement"}
            if args.mode == "check":
                print(json.dumps({"sizes": sizes, "points": len(plan),
                                  "logical_points": sum(r["logical_allowed"] for r in plan), "cpu": cpu,
                                  "initialization": INITIALIZATION, "runtime": identities}, indent=2))
                return 0
            args.output_root.mkdir(parents=True, exist_ok=True)
            stamp = now()[:19].replace("-", "").replace(":", "").replace("T", "_")
            directory = Path(tempfile.mkdtemp(prefix=f"dantzig_cstr_box_ipopt_{stamp}_",
                                             dir=args.output_root)).resolve()
            print(f"RESULT_DIR={directory}", flush=True)
            with batch._lock(directory):
                summary = run_points(directory, manifest, args.max_points)
        print(json.dumps(summary, indent=2))
        return 1 if any(summary["status_counts"].get(s, 0) for s in
                        ("worker_error", "worker_timeout", "solver_error", "evaluation_error")) else 0
    except KeyboardInterrupt:
        print("Interrupted; completed records and pending coordinates were packaged.", file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
