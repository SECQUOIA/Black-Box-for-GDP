"""Isolated, seven-point CSTR30 IPOPT rerun for Dantzig; never merge in place."""

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from time import perf_counter
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parent
POINTS = ((5, 1), (5, 3), (6, 2), (6, 4), (23, 2), (26, 2), (29, 3))
PARENT_RUN = "dantzig_gdp_gams_20260922_050038_p4q8hy54"
PARENT_SHA256 = "e406b8fae2a90191835eb7332d483c719ebb1675d14d3b0e6d3bf5f7789a197b"
KIND = "cstr30_seven_point_isolated_retry"
CSV_FIELDS = (
    "case", "cstr_size", "point", "original_point_index", "solver", "initialization",
    "accepted", "status", "termination", "objective", "candidate_objective",
    "max_primal_violation", "initial_primal_violation", "setup_wall_s",
    "preprocess_wall_s", "feasible_initialization_wall_s", "solve_wall_s",
    "total_wall_s", "worker_process_wall_s", "worker_pid", "worker_returncode",
    "gams_solve_status", "gams_model_status", "message",
)


def write_json(path, data):
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def point_name(point):
    return f"point_{point[0]:02d}_{point[1]:02d}"


def source_files():
    modules = ("__init__", "_sources", "models", "evaluation", "solvers", "preflight",
               "batch", "domains")
    return [ROOT / "cstr30_retry.py",
            *(p for p in (ROOT / "run_cstr30_retry_dantzig.sh",) if p.is_file()),
            ROOT / "requirements-gdp.txt", ROOT / "LICENSE", ROOT / "docs/cstr30_retry.md",
            *(ROOT / "gdp_models" / f"{name}.py" for name in modules)]


def hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source_files()}


def formulation_fingerprint(prepared):
    import pyomo.environ as pyo

    def number(value):
        return None if value is None else float(value)

    payload = {
        "objective": str(prepared.model.obj.expr),
        "constraints": [(c.name, str(c.expr), c.active) for c in prepared.constraints],
        "variables": [(v.name, number(v.lb), number(v.ub), v.fixed,
                       number(v.value) if v.fixed else None)
                      for v in prepared.model.component_data_objects(pyo.Var)],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def initialize_feasible(prepared):
    """Use actual balances only; no lookup objectives or previously solved values."""
    import pyomo.environ as pyo
    from gdp_models.evaluation import primal_violation

    if prepared.metadata["case"] != "cstr" or prepared.metadata["cstr_size"] != 30:
        raise ValueError("This initialization is restricted to the CSTR30 retry")
    before = formulation_fingerprint(prepared)
    started = perf_counter()
    count = prepared.point[0]

    def concentrations(volume):
        inlet = 0.99
        result = []
        for _ in range(count):
            b = 1 + 2 * volume
            inlet = 2 * inlet / (b + math.sqrt(b * b - 8 * volume * inlet))
            result.append(inlet)
        return result

    lo, hi = 0.0, 10.0
    if not concentrations(lo)[-1] > 0.05 > concentrations(hi)[-1]:
        raise RuntimeError("Mass-balance initialization could not bracket the volume")
    for _ in range(70):
        mid = (lo + hi) / 2
        if concentrations(mid)[-1] > 0.05:
            lo = mid
        else:
            hi = mid
    volume = (lo + hi) / 2
    active = concentrations(volume)
    m = prepared.model
    for n in m.N:
        a = active[count - n] if n <= count else 0.99
        m.Q[n].set_value(1)
        m.QFR[n].set_value(0)
        m.V[n].set_value(volume)
        m.c[n].set_value(volume if n <= count else 0)
        m.F['A', n].set_value(a)
        m.F['B', n].set_value(1 - a if n <= count else 0.01)
        rate = -2 * a * (1 - a) if n <= count else 0
        m.rate['A', n].set_value(rate)
        m.rate['B', n].set_value(-rate)
        for component in m.I:
            m.FR[component, n].set_value(0)
    m.QR.set_value(0)
    m.QP.set_value(1)
    for component, value in [('A', 0.05), ('B', 0.95)]:
        m.R[component].set_value(0)
        m.P[component].set_value(value)
    elapsed = perf_counter() - started
    violation = primal_violation(prepared)
    if formulation_fingerprint(prepared) != before or not math.isfinite(violation) or violation > 1e-8:
        raise RuntimeError("Feasible initialization changed the formulation or failed residual validation")
    prepared.metadata.update(
        initialization="mass_balance_zero_recycle", initial_primal_violation=violation,
        initial_objective=pyo.value(m.obj), initial_equal_volume=volume,
        constraints_and_bounds_unchanged=True, formulation_sha256=before,
    )
    prepared.timings["feasible_initialization_wall_s"] = elapsed


def worker(args):
    """One fresh process, one point, one solver call."""
    from gdp_models import evaluation

    point = parse_point(args.point)
    started = perf_counter()
    original = evaluation.prepare_nlp

    def prepare(*a, **kw):
        prepared = original(*a, **kw)
        initialize_feasible(prepared)
        return prepared

    try:
        with patch.object(evaluation, "prepare_nlp", prepare):
            report = evaluation.evaluate_point(
                "cstr", point, cstr_size=30, initialization="default", solver="gams_ipopt",
                executable=args.executable, time_limit=args.time_limit, tee=True)
    except Exception as error:
        import traceback
        traceback.print_exc()
        report = {"accepted": False, "status": "worker_error", "objective": None,
                  "termination": "error", "message": f"{type(error).__name__}: {error}",
                  "total_wall_s": perf_counter() - started}
    report.update(case="cstr", cstr_size=30, point=list(point), solver="gams_ipopt",
                  original_point_index=point[0] * (point[0] - 1) // 2 + point[1],
                  initialization_requested="mass_balance_zero_recycle", worker_pid=os.getpid())
    write_json(args.record, report)
    return 0


def _signal_process_group(process, signum):
    """Retry Darwin's transient EPERM while an owned group becomes reapable."""
    for attempt in range(3):
        try:
            os.killpg(process.pid, signum)
            return
        except PermissionError:
            if sys.platform != "darwin" or attempt == 2:
                raise
            # Darwin can find a group but exclude its exiting/zombie members
            # from signal delivery, returning EPERM instead of ESRCH.
            # Reap our worker and retry the same group, including descendants;
            # its leader's exit alone is not proof the whole group is gone.
            process.poll()
            time.sleep(0.01)


def stop_process(process, grace=3):
    """Clean up the session run_child owns, even if its leader already exited."""
    interrupted = False
    try:
        try:
            _signal_process_group(process, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + grace
        while True:
            process.poll()  # Reap the worker without mistaking its exit for group exit.
            try:
                _signal_process_group(process, 0)
            except ProcessLookupError:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.05, remaining))
    except KeyboardInterrupt:
        interrupted = True
    finally:
        # Keep the original session ID: getpgid(worker.pid) can fail after its
        # exit. A second interrupt must not skip the group kill or worker reap.
        while True:
            try:
                try:
                    _signal_process_group(process, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                break
            except KeyboardInterrupt:
                interrupted = True
    if interrupted:
        raise KeyboardInterrupt


def run_child(command, log_path, timeout):
    with log_path.open("w") as log:
        started = perf_counter()
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop_process(process)
            code = process.returncode
        except BaseException:
            stop_process(process)
            raise
    return {"worker_pid": process.pid, "worker_returncode": code,
            "worker_timed_out": timed_out, "worker_process_wall_s": perf_counter() - started}


def run_point(directory, point, config):
    record = directory / "records" / (point_name(point) + ".json")
    command = [sys.executable, str(ROOT / "cstr30_retry.py"), "_worker",
               "--point", ",".join(map(str, point)), "--record", str(record),
               "--executable", config["executable"], "--time-limit", str(config["time_limit"])]
    process = run_child(command, directory / "logs" / (point_name(point) + ".log"),
                        config["worker_timeout"])
    try:
        report = json.loads(record.read_text())
        if report.get("point") != list(point) or report.get("solver") != "gams_ipopt":
            raise ValueError("Worker returned a different point or solver")
        if process["worker_timed_out"] or process["worker_returncode"] != 0:
            raise ValueError("Worker timed out or exited abnormally")
    except (OSError, ValueError) as error:
        report = {"case": "cstr", "cstr_size": 30, "point": list(point), "solver": "gams_ipopt",
                  "original_point_index": point[0] * (point[0] - 1) // 2 + point[1],
                  "accepted": False, "objective": None,
                  "status": "worker_timeout" if process["worker_timed_out"] else "worker_error",
                  "termination": "error", "message": str(error)}
    report.update(process)
    write_json(record, report)
    return report


def summarize(directory):
    manifest = json.loads((directory / "run.json").read_text())
    if manifest["kind"] != KIND:
        raise ValueError("Not a seven-point CSTR30 retry run")
    records = [json.loads(p.read_text()) for p in sorted((directory / "records").glob("*.json"))]
    expected = {tuple(p) for p in manifest["points"]}
    observed = {tuple(r["point"]) for r in records}
    if len(observed) != len(records) or not observed <= expected:
        raise ValueError("Unexpected or duplicate point records")
    summary = {"selected_points": len(expected), "completed_points": len(records),
               "accepted_points": sum(bool(r["accepted"]) for r in records),
               "complete": observed == expected,
               "all_accepted": observed == expected and all(r["accepted"] for r in records),
               "pending_points": [list(p) for p in sorted(expected - observed)],
               "nonaccepted_points": [r["point"] for r in records if not r["accepted"]],
               "sum_completed_evaluation_wall_s": sum(r.get("total_wall_s", 0) for r in records),
               "sum_worker_process_wall_s": sum(r.get("worker_process_wall_s", 0) for r in records)}
    write_json(directory / "summary.json", summary)
    with (directory / "evaluations.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow({k: json.dumps(record[k]) if k == "point" else record.get(k)
                             for k in CSV_FIELDS})
    return summary


def archive_results(directory):
    summary = summarize(directory)
    files = [p for p in sorted(directory.rglob("*")) if p.is_file() and not p.is_symlink()
             and p.name != "SHA256SUMS" and not p.name.endswith(".tmp")]
    checks = directory / "SHA256SUMS"
    checks.write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(directory)}\n"
                             for p in files))
    archive = directory.with_name(directory.name + ".zip")
    temporary = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in [*files, checks]:
            z.write(path, f"{directory.name}/{path.relative_to(directory)}")
    with zipfile.ZipFile(temporary) as z:
        if z.testzip() is not None:
            raise RuntimeError("Result ZIP verification failed")
    temporary.replace(archive)
    archive.with_suffix(".zip.sha256").write_text(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n")
    print(f"RESULT_DIR={directory}\nRESULT_ZIP={archive}", flush=True)
    return summary


def run_points(directory, manifest):
    for name in ("records", "logs"):
        (directory / name).mkdir()
    write_json(directory / "run.json", manifest)
    for path in source_files():
        destination = directory / "source" / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    try:
        for point in manifest["points"]:
            try:
                report = run_point(directory, point, manifest["config"])
            except Exception as error:
                report = {"case": "cstr", "cstr_size": 30, "point": point,
                          "solver": "gams_ipopt", "accepted": False, "objective": None,
                          "status": "worker_error", "message": f"{type(error).__name__}: {error}"}
                write_json(directory / "records" / (point_name(point) + ".json"), report)
            print(f"{tuple(point)}: {report['status']}, objective={report.get('objective')}", flush=True)
            summarize(directory)
    finally:
        summary = archive_results(directory)
    return summary


def parse_point(value):
    try:
        point = tuple(int(x) for x in value.split(","))
    except ValueError as error:
        raise ValueError("Point must be two integers, e.g. 5,3") from error
    if point not in POINTS:
        raise ValueError(f"Choose one of the seven retry points: {POINTS}")
    return point


def bundle(output):
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for path in source_files():
            z.write(path, "cstr30_retry_runner/" + path.relative_to(ROOT).as_posix())
        z.writestr("cstr30_retry_runner/RETRY_RUNNER_SHA256SUMS",
                   "".join(f"{digest}  {name}\n" for name, digest in hashes().items()))
    print(f"RUNNER_ZIP={output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "check", "pack", "bundle", "_worker"))
    parser.add_argument("--point", help="Only this one of the seven points, e.g. 5,3")
    parser.add_argument("--executable", default=os.environ.get("GAMS_BIN"))
    parser.add_argument("--expected-gams-version", default=os.environ.get("GDP_GAMS_VERSION", "52.2"))
    parser.add_argument("--time-limit", type=float, default=60)
    parser.add_argument("--worker-timeout", type=float, default=180)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.time_limit) or args.time_limit <= 0:
        parser.error("time-limit must be finite and positive")
    if not math.isfinite(args.worker_timeout) or args.worker_timeout <= args.time_limit:
        parser.error("worker-timeout must be finite and greater than time-limit")
    try:
        if args.mode == "bundle":
            if args.output is None:
                parser.error("bundle requires --output")
            bundle(args.output)
            return 0
        if args.mode == "_worker":
            if args.point is None or args.record is None:
                parser.error("_worker requires --point and --record")
            return worker(args)
        if args.mode == "pack":
            if args.run_dir is None:
                parser.error("pack requires --run-dir")
            archive_results(args.run_dir.resolve())
            return 0
        from gdp_models import batch
        from gdp_models.solvers import gams_smoke_check, optimizer_for

        points = [parse_point(args.point)] if args.point else POINTS
        binary = shutil.which(args.executable or "gams")
        if binary is None:
            raise ValueError("GAMS executable not found; set GAMS_BIN")
        binary = str(Path(binary).resolve())
        cpu = None
        if hasattr(os, "sched_getaffinity"):
            cpu = min(os.sched_getaffinity(0))
            os.sched_setaffinity(0, {cpu})
        # Require the intended GAMS version before calling the optimizer.
        actual = tuple(optimizer_for("gams_ipopt", binary).version())
        expected = tuple(int(n) for n in args.expected_gams_version.split("."))
        if not expected or actual[:len(expected)] != expected:
            raise ValueError(f"Expected GAMS {args.expected_gams_version}, found {actual}; set GAMS_BIN")
        gams_smoke_check("gams_ipopt", binary, hashlib.sha256(Path(binary).read_bytes()).hexdigest())
        runtime = batch._runtime_identity("cstr", 30, "default", "gams_ipopt", binary)
        if args.mode == "check":
            print(json.dumps({"points": points, "cpu": cpu, "runtime": runtime}, indent=2))
            return 0
        args.output_root.mkdir(parents=True, exist_ok=True)
        stamp = batch._now()[:19].replace("-", "").replace(":", "").replace("T", "_")
        directory = Path(tempfile.mkdtemp(prefix=f"dantzig_cstr30_retry_{stamp}_",
                                         dir=args.output_root)).resolve()
        manifest = {
            "kind": KIND, "created_utc": batch._now(), "points": [list(p) for p in points],
            "parent_run": PARENT_RUN, "parent_zip_sha256": PARENT_SHA256,
            "merge_key": ["case", "cstr_size", "point", "solver"],
            "initialization": "mass_balance_zero_recycle", "cpu": cpu,
            "config": {"executable": binary, "time_limit": args.time_limit,
                       "worker_timeout": args.worker_timeout},
            "runtime": runtime, "runner_sha256": hashes(),
            "isolation": "fresh Python process for every point; sequential",
            "cost_policy": "new attempts only; preserve prior Dantzig attempts when merging",
        }
        print(f"RESULT_DIR={directory}", flush=True)
        summary = run_points(directory, manifest)
        print(json.dumps(summary, indent=2))
        return 0 if summary["all_accepted"] else 1
    except KeyboardInterrupt:
        print("Interrupted; completed point records were packaged.", file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
