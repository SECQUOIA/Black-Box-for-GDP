"""Enumerate external integer coordinates and checkpoint actual NLP evaluations."""

import argparse
from collections import Counter
import contextlib
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import platform
import shutil
import sys
from time import perf_counter
import traceback

from pyomo.version import version as pyomo_version

from ._sources import provenance
from .domains import enumeration_plan
from .evaluation import evaluate_point
from .models import MODELS, dynamic_template, initialization_info
from .preflight import SetupError, dependency_versions, model_check
from .solvers import SOLVERS, GAMS_SOLVERS, gams_smoke_check, is_gams, optimizer_for


ERROR_STATUSES = {"solver_error", "evaluation_error"}
CSV_FIELDS = [
    "point_index", "case", "cstr_size", "x1", "x2", "x3", "point", "solver", "preparation_id",
    "status", "accepted", "objective", "candidate_objective", "termination",
    "solver_interface", "gams_solver", "gams_solve_status", "gams_model_status",
    "solver_status", "max_primal_violation", "initialization", "setup_wall_s",
    "preprocess_wall_s", "solve_wall_s", "total_wall_s", "message",
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write_json(path, value):
    # A killed process can leave a .tmp file, but never a partial checkpoint.
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _runtime_identity(case, cstr_size, initialization, solver, executable):
    dependencies = dependency_versions()
    initialized_from, files = initialization_info(case, cstr_size, initialization)
    name, model_file, _ = MODELS[case]
    files = [model_file, *files]
    if case != "dynamic":
        files += ["gdp/dsda/dsda_functions.py", f"main_{case}.py"]
    binary = shutil.which(str(Path(executable).expanduser()) if executable else
                          ("gams" if is_gams(solver) else "ipopt"))
    if binary is None:
        raise FileNotFoundError(f"Solver executable not found: {executable or solver}")
    binary = str(Path(binary).resolve())
    optimizer = optimizer_for(solver, binary)
    if not optimizer.available(exception_flag=False):
        raise RuntimeError(f"Solver unavailable; check executable/license: {binary}")
    try:
        version = optimizer.version()
    except (AttributeError, NotImplementedError):
        version = None
    binary_hash = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    smoke = gams_smoke_check(solver, binary, binary_hash) if is_gams(solver) else None
    return {
        "solver_interface": "gams_shell" if is_gams(solver) else "native_ipopt",
        "gams_solver": GAMS_SOLVERS.get(solver), "solver_execution_check": smoke,
        "dependency_versions": dependencies,
        "preflight": model_check(case, cstr_size, initialization),
        "source": provenance(name, files), "initialization": initialized_from,
        "adapter_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(Path(__file__).parent.glob("*.py"))},
        "solver_executable": binary,
        "solver_executable_sha256": binary_hash,
        "solver_version": list(version) if version else None,
        "python_version": platform.python_version(), "pyomo_version": pyomo_version,
        "host": platform.node(), "platform": platform.platform(),
        "thread_environment": {name: os.environ.get(name) for name in
                               ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
    }


@contextlib.contextmanager
def _lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".batch.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"Another batch is using {directory}") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


@contextlib.contextmanager
def _diagnostics(stream):
    handlers = [(h, h.stream) for h in logging.getLogger("pyomo").handlers
                if isinstance(h, logging.StreamHandler)]
    for handler, _ in handlers:
        handler.setStream(stream)
    try:
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            yield
    finally:
        for handler, previous in handlers:
            handler.setStream(previous)


def _load_records(directory, plan, solver):
    records = {}
    for path in sorted((directory / "records").glob("*.json")):
        report = json.loads(path.read_text())
        if not isinstance(report, dict):
            raise ValueError(f"Invalid checkpoint content: {path}")
        index = report.get("point_index")
        if (type(index) is not int or not 1 <= index <= len(plan["points"])
                or path.name != f"point_{index:06d}.json" or index in records
                or report.get("point") != plan["points"][index - 1]
                or report.get("case") != plan["case"]
                or report.get("cstr_size") != plan["cstr_size"]
                or report.get("solver") != solver
                or type(report.get("accepted")) is not bool
                or not isinstance(report.get("status"), str)
                or not isinstance(report.get("total_wall_s"), (int, float))
                or not math.isfinite(report["total_wall_s"]) or report["total_wall_s"] < 0):
            raise ValueError(f"Invalid checkpoint identity/content: {path}")
        if report["accepted"] and (not isinstance(report.get("objective"), (int, float))
                                   or not math.isfinite(report["objective"])):
            raise ValueError(f"Invalid accepted objective in {path}")
        records[index] = report
    return records


def _csv_row(report):
    row = {key: report.get(key) for key in CSV_FIELDS}
    row["point"] = json.dumps(report["point"])
    row.update({f"x{i}": x for i, x in enumerate(report["point"], 1)})
    return row


def _summary(plan, records, reason, started):
    counts = Counter(r["status"] for r in records.values())
    accepted = [r for r in records.values() if r["accepted"]]
    best = min(accepted, key=lambda r: r["objective"]) if accepted else None
    complete = len(records) == plan["candidate_count"]
    errors = sum(counts[s] for s in ERROR_STATUSES)
    return {
        "case": plan["case"], "cstr_size": plan["cstr_size"], "domain": plan["domain"],
        "candidate_count": plan["candidate_count"], "completed_points": len(records),
        "remaining_points": plan["candidate_count"] - len(records),
        "accepted_points": len(accepted), "error_points": errors,
        "status_counts": dict(counts), "complete": complete,
        "status": ("completed_with_errors" if errors else "completed") if complete else reason,
        "best_point": best["point"] if best else None,
        "best_objective": best["objective"] if best else None,
        "sum_evaluation_wall_s": sum(r["total_wall_s"] for r in records.values()),
        "last_invocation_wall_s": perf_counter() - started, "updated_utc": _now(),
    }


def run_batch(case, output_dir, *, solver, cstr_size=5, domain="logical",
              initialization="auto", time_limit=60.0, feasibility_tolerance=1e-5,
              executable=None, resume=False, max_points=None, tee=False, progress=None):
    """Sequential cold-start enumeration; --resume preserves completed attempts.

    Per-point JSON files are the checkpoints. CSV is rebuilt from them on
    resume, so an interrupted CSV append never loses a completed evaluation.
    Source, solver, initialization and machine identity must match on resume.
    """
    is_gams(solver)  # Validate explicit solver/interface selection.
    if any(not math.isfinite(v) or v <= 0 for v in (time_limit, feasibility_tolerance)):
        raise ValueError("time_limit and feasibility_tolerance must be finite and positive")
    if max_points is not None and (type(max_points) is not int or max_points <= 0):
        raise ValueError("max_points must be a positive integer")
    started = perf_counter()
    plan = enumeration_plan(case, cstr_size=cstr_size, domain=domain)
    config = {"solver": solver, "initialization": initialization,
              "time_limit_s": time_limit, "feasibility_tolerance": feasibility_tolerance}
    directory = Path(output_dir)
    with _lock(directory):
        manifest_path = directory / "manifest.json"
        existing = [p for p in directory.iterdir() if p.name != ".batch.lock"]
        if existing and not resume:
            raise FileExistsError(f"Output directory is not empty: {directory}. Use --resume or a new directory.")
        if resume and not manifest_path.is_file():
            raise FileNotFoundError(f"Cannot resume without {manifest_path}")
        identity = _runtime_identity(case, cstr_size, initialization, solver, executable)
        manifest = {"schema_version": 1, "plan": plan, "config": config, "runtime": identity}
        if resume:
            previous = json.loads(manifest_path.read_text())
            if any(previous.get(k) != v for k, v in manifest.items()):
                raise ValueError("Resume requires the same points, options, sources, solver and machine. Use a new output directory.")
        else:
            _write_json(manifest_path, {**manifest, "created_utc": _now()})
        if case == "dynamic":
            path = directory / "preparation.json"
            preparations = json.loads(path.read_text()) if path.exists() else []
            preparation = dynamic_template().preparation
            if not any(p["preparation_id"] == preparation["preparation_id"] for p in preparations):
                _write_json(path, [*preparations, preparation])
        (directory / "records").mkdir(exist_ok=True)
        records = _load_records(directory, plan, solver)
        reason = "paused"
        evaluated = 0
        summary = _summary(plan, records, reason, started)
        try:
            with (directory / "evaluations.csv").open("w", newline="") as csv_stream, \
                    (directory / "run.log").open("a") as log:
                writer = csv.DictWriter(csv_stream, fieldnames=CSV_FIELDS)
                writer.writeheader()
                for index in sorted(records):
                    writer.writerow(_csv_row(records[index]))
                csv_stream.flush()
                for index, point in enumerate(plan["points"], 1):
                    if index in records:
                        continue
                    if max_points is not None and evaluated >= max_points:
                        break
                    log.write(f"\n[{_now()}] Point {index}/{plan['candidate_count']}: {point}\n")
                    log.flush()
                    point_started = perf_counter()
                    with _diagnostics(log):
                        try:
                            report = evaluate_point(
                                case, point, solver=solver, cstr_size=cstr_size,
                                initialization=initialization, time_limit=time_limit,
                                feasibility_tolerance=feasibility_tolerance,
                                executable=identity["solver_executable"], tee=tee,
                            )
                        except ImportError as error:
                            traceback.print_exc()
                            raise SetupError(f"Missing/broken dependency; stopping batch: {error}") from error
                        except SetupError:
                            raise
                        except Exception as error:
                            traceback.print_exc()
                            report = {"case": case, "point": point, "cstr_size": plan["cstr_size"],
                                      "solver": solver, "status": "evaluation_error", "accepted": False,
                                      "objective": None, "termination": "error", "message": str(error),
                                      "total_wall_s": perf_counter() - point_started}
                    report.update(point_index=index, completed_utc=_now())
                    _write_json(directory / "records" / f"point_{index:06d}.json", report)
                    records[index] = report
                    writer.writerow(_csv_row(report))
                    csv_stream.flush()
                    os.fsync(csv_stream.fileno())
                    log.flush()
                    evaluated += 1
                    summary = _summary(plan, records, reason, started)
                    _write_json(directory / "summary.json", summary)
                    if progress:
                        progress(report, summary)
        except KeyboardInterrupt:
            reason = "interrupted"
            raise
        except Exception:
            reason = "batch_error"
            raise
        finally:
            summary = _summary(plan, records, reason, started)
            _write_json(directory / "summary.json", summary)
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=MODELS, required=True)
    parser.add_argument("--cstr-size", type=int, default=5)
    parser.add_argument("--domain", choices=("logical", "box"), default="logical")
    parser.add_argument("--solver", choices=SOLVERS, required=True)
    parser.add_argument("--executable", help="Path to IPOPT or GAMS")
    parser.add_argument("--initialization", choices=("auto", "saved", "default"), default="auto")
    parser.add_argument("--time-limit", type=float, default=60.0, help="Solver limit per point, in seconds")
    parser.add_argument("--feasibility-tolerance", type=float, default=1e-5)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-points", type=int, help="Evaluate at most this many NEW points this invocation")
    parser.add_argument("--dry-run", action="store_true", help="Print all candidate coordinates; do not solve or write files")
    parser.add_argument("--tee", action="store_true", help="Include solver transcripts in run.log")
    args = parser.parse_args()

    def progress(report, summary):
        print(f"[{summary['completed_points']}/{summary['candidate_count']}] "
              f"{report['point']} {report['status']} objective={report.get('objective')} "
              f"total={report['total_wall_s']:.3f}s", file=sys.stderr, flush=True)

    try:
        if args.dry_run:
            print(json.dumps(enumeration_plan(args.case, cstr_size=args.cstr_size, domain=args.domain), indent=2))
            return 0
        if args.output_dir is None:
            parser.error("--output-dir is required unless --dry-run is used")
        with contextlib.redirect_stdout(sys.stderr):
            summary = run_batch(
                args.case, args.output_dir, solver=args.solver, cstr_size=args.cstr_size,
                domain=args.domain, initialization=args.initialization, time_limit=args.time_limit,
                feasibility_tolerance=args.feasibility_tolerance, executable=args.executable,
                resume=args.resume, max_points=args.max_points, tee=args.tee, progress=progress,
            )
    except KeyboardInterrupt:
        print("Interrupted. Reuse the same command and output directory with --resume.", file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(summary, indent=2, allow_nan=False))
    return 1 if summary["error_points"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
