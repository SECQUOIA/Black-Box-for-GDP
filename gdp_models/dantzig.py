"""Run the process-case enumeration matrix and package portable result folders."""

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from . import batch
from ._sources import PINS, source_root
from .domains import enumeration_plan
from .preflight import SetupError
from .solvers import SOLVERS, is_gams


ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = {"dsda-gdp": "https://github.com/SECQUOIA/dsda-gdp.git",
                "ld-sda-dynamic": "https://github.com/SECQUOIA/LD-SDA-Dynamic.git"}
KIND = "gdp_external_integer_enumeration"


def setup_sources():
    """Works both in this Git repository and the standalone runner ZIP."""
    base = Path(os.environ.get("RBFOPT_GDP_SOURCES", ROOT / "external"))
    base.mkdir(parents=True, exist_ok=True)
    for name, url in REPOSITORIES.items():
        path = base / name
        if path.exists() and not (path / ".git").exists():
            if any(path.iterdir()):
                raise ValueError(f"Refusing to overwrite nonempty source directory: {path}")
        if not (path / ".git").exists():
            subprocess.run(["git", "clone", url, str(path)], check=True)
        revision = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        if revision != PINS[name]:
            dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True)
            if dirty:
                raise ValueError(f"Source checkout has local changes; cannot change its revision: {path}")
            subprocess.run(["git", "-C", str(path), "checkout", "--detach", PINS[name]], check=True)
        source_root.cache_clear()
        source_root(name)
        print(f"Source ready: {name} @ {PINS[name]}", flush=True)


def make_jobs(cases, sizes, domain, solvers=None):
    jobs = []
    if len(set(cases)) != len(cases) or len(set(sizes)) != len(sizes):
        raise ValueError("Duplicate cases or CSTR sizes")
    for case in cases:
        for size in sizes if case == "cstr" else [5]:
            plan = enumeration_plan(case, cstr_size=size, domain=domain)
            jobs.append({"name": f"cstr_{size}" if case == "cstr" else case,
                         "case": case, "cstr_size": size,
                         "candidate_count": plan["candidate_count"]})
    if not jobs:
        raise ValueError("Select at least one case (and a size for CSTR)")
    if solvers is not None:
        if not solvers or len(set(solvers)) != len(solvers):
            raise ValueError("Choose a nonempty list of distinct solvers")
        if len({is_gams(solver) for solver in solvers}) != 1:
            raise ValueError("Do not mix native and GAMS executables; use gams_ipopt,ipopth,conopt")
        jobs = [{**job, "name": f"{solver}/{job['name']}", "solver": solver}
                for solver in solvers for job in jobs]
    return jobs


def runner_files():
    return [*sorted((ROOT / "gdp_models").glob("*.py")),
            *(p for p in (ROOT / "run_gdp_dantzig.sh", ROOT / "run_gdp_gams_dantzig.sh")
              if p.is_file()),
            ROOT / "requirements-gdp.txt", ROOT / "LICENSE"]


def runner_hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in runner_files()}


def _pin_cpu(cpu):
    if not hasattr(os, "sched_getaffinity"):
        if cpu is not None:
            raise ValueError("CPU affinity selection is supported on Linux only")
        return None
    allowed = os.sched_getaffinity(0)
    selected = min(allowed) if cpu is None else cpu
    if selected not in allowed:
        raise ValueError(f"CPU {selected} is outside this process's allowed CPU set")
    os.sched_setaffinity(0, {selected})
    return selected


def _identities(jobs, config):
    return {j["name"]: batch._runtime_identity(
        j["case"], j["cstr_size"], config["initialization"],
        j.get("solver", config["solver"]), config["executable"],
    ) for j in jobs}


def check_gams_version(jobs, identities, expected):
    if expected is None:
        return
    try:
        prefix = tuple(int(part) for part in expected.split("."))
        if not prefix or any(n < 0 for n in prefix):
            raise ValueError
    except ValueError as error:
        raise ValueError("Expected GAMS version must be a dotted number, e.g. 52.2") from error
    for job in jobs:
        identity = identities[job["name"]]
        actual = tuple(identity.get("solver_version") or ())
        if identity.get("solver_interface") != "gams_shell" or actual[:len(prefix)] != prefix:
            raise SetupError(f"Expected GAMS {expected}; {job['name']} uses version {actual}. Set GAMS_BIN to the intended GAMS executable.")


def summarize(directory, protocol, failures, reason):
    rows = []
    for job in protocol["jobs"]:
        path = directory / job["name"] / "summary.json"
        summary = json.loads(path.read_text()) if path.is_file() else {}
        row = {"case": job["name"], "solver": job.get("solver", protocol["config"]["solver"]),
               "candidate_count": job["candidate_count"],
               "completed_points": summary.get("completed_points", 0),
               "accepted_points": summary.get("accepted_points", 0),
               "error_points": summary.get("error_points", 0),
               "status": "batch_error" if job["name"] in failures else summary.get("status", "pending"),
               "best_point": summary.get("best_point"), "best_objective": summary.get("best_objective"),
               "sum_evaluation_wall_s": summary.get("sum_evaluation_wall_s", 0),
               "message": failures.get(job["name"], "")}
        rows.append(row)
    complete = all(r["completed_points"] == r["candidate_count"] for r in rows) and not failures
    errors = sum(r["error_points"] for r in rows) + len(failures)
    summary = {"status": ("completed_with_errors" if errors else "completed") if complete else reason,
               "complete": complete, "candidate_count": sum(r["candidate_count"] for r in rows),
               "completed_points": sum(r["completed_points"] for r in rows),
               "accepted_points": sum(r["accepted_points"] for r in rows),
               "error_count": errors, "cases": rows, "updated_utc": batch._now()}
    batch._write_json(directory / "summary.json", summary)
    temporary = directory / "summary.csv.tmp"
    with temporary.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "best_point": json.dumps(row["best_point"])})
    temporary.replace(directory / "summary.csv")
    return summary


def archive_results(directory):
    """Caller holds the run lock. Exclude temporary files and symlinks."""
    directory = Path(directory).resolve()
    protocol = json.loads((directory / "run.json").read_text())
    if protocol.get("kind") != KIND:
        raise ValueError("Not a GDP enumeration result directory")
    files = [p for p in sorted(directory.rglob("*"))
             if p.is_file() and not p.is_symlink() and p.name != "SHA256SUMS"
             and p.name != ".batch.lock" and not p.name.endswith(".tmp")
             and not any(part in {"__pycache__", "matplotlib-cache"} for part in p.relative_to(directory).parts)]
    checksums = directory / "SHA256SUMS"
    checksums.write_text("".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(directory).as_posix()}\n" for p in files
    ))
    archive_path = directory.with_name(directory.name + ".zip")
    temporary = archive_path.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [*files, checksums]:
            archive.write(path, f"{directory.name}/{path.relative_to(directory).as_posix()}")
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP verification failed")
    temporary.replace(archive_path)
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive_path.name}\n")
    print(f"RESULT_DIR={directory}\nRESULT_ZIP={archive_path}", flush=True)
    return archive_path


def execute_matrix(directory, protocol, *, resume=False, max_points=None):
    failures = {}
    reason = "paused"
    with batch._lock(directory):
        if resume:
            current = json.loads((directory / "run.json").read_text())
            if current != protocol or runner_hashes() != protocol["runner_sha256"]:
                raise ValueError("Runner changed since this run; use the original source snapshot to resume")
            if _identities(protocol["jobs"], protocol["config"]) != protocol["runtime"]:
                raise ValueError("Model sources, solver or environment changed; use a new run directory")
        else:
            batch._write_json(directory / "run.json", protocol)
            for path in runner_files():
                destination = directory / "source" / path.relative_to(ROOT)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        try:
            summarize(directory, protocol, failures, reason)
            for job in protocol["jobs"]:
                case_dir = directory / job["name"]
                print(f"\n=== {job['name']}: {job['candidate_count']} integer candidates ===", flush=True)

                def progress(report, summary):
                    print(f"{job['name']} [{summary['completed_points']}/{summary['candidate_count']}] "
                          f"{report['point']} {report['status']} objective={report.get('objective')}", flush=True)

                try:
                    batch.run_batch(
                        job["case"], case_dir, cstr_size=job["cstr_size"],
                        resume=(case_dir / "manifest.json").is_file(), max_points=max_points,
                        progress=progress, tee=True,
                        **{**protocol["config"], "solver": job.get("solver", protocol["config"]["solver"])},
                    )
                except SetupError as error:
                    failures[job["name"]] = f"{type(error).__name__}: {error}"
                    print(f"Setup failed; stopping matrix: {error}", file=sys.stderr, flush=True)
                    break
                except Exception as error:
                    failures[job["name"]] = f"{type(error).__name__}: {error}"
                    print(f"Case failed: {failures[job['name']]}", file=sys.stderr, flush=True)
                summarize(directory, protocol, failures, reason)
            if failures:
                reason = "batch_error"
        except KeyboardInterrupt:
            reason = "interrupted"
            raise
        finally:
            summary = summarize(directory, protocol, failures, reason)
            archive_results(directory)
    return summary


def bundle_runner(output):
    """Ship only the runner; setup fetches original sources from their owners."""
    files = [*runner_files(), ROOT / "docs/gdp_dantzig.md"]
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
        archive.writestr("GDP_RUNNER_SHA256SUMS", "".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n" for p in files
        ))
    print(f"RUNNER_ZIP={output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("setup", "check", "run", "resume", "pack", "bundle"))
    parser.add_argument("--cases", default="column,cstr,small_batch,dynamic")
    parser.add_argument("--cstr-sizes", default="30")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--solver", choices=SOLVERS, default="ipopt")
    selection.add_argument("--solvers", help="Sequential comparison, e.g. gams_ipopt,ipopth,conopt")
    parser.add_argument("--executable")
    parser.add_argument("--expected-gams-version", help="Require this GAMS version prefix, e.g. 52.2")
    parser.add_argument("--domain", choices=("logical", "box"), default="logical")
    parser.add_argument("--initialization", choices=("auto", "saved", "default"), default="auto")
    parser.add_argument("--time-limit", type=float, default=60)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output", type=Path, help="Standalone source ZIP path (bundle only)")
    parser.add_argument("--max-points", type=int, help="New points per case for a short validation run")
    parser.add_argument("--cpu", type=int, help="Allowed Linux CPU to use (default: first allowed CPU)")
    args = parser.parse_args()
    if not math.isfinite(args.time_limit) or args.time_limit <= 0:
        parser.error("--time-limit must be finite and positive")
    if args.max_points is not None and args.max_points <= 0:
        parser.error("--max-points must be positive")
    try:
        if args.mode == "setup":
            setup_sources()
            print("Setup complete. Next: python -m gdp_models.dantzig check")
            return 0
        if args.mode == "bundle":
            if args.output is None:
                parser.error("bundle requires --output")
            bundle_runner(args.output)
            return 0
        if args.mode in {"resume", "pack"}:
            if args.run_dir is None:
                parser.error(f"{args.mode} requires --run-dir")
            directory = args.run_dir.resolve()
            protocol = json.loads((directory / "run.json").read_text())
            if protocol.get("kind") != KIND:
                raise ValueError("Not a GDP enumeration run")
            if args.mode == "pack":
                with batch._lock(directory):
                    previous = directory / "summary.json"
                    previous = json.loads(previous.read_text()) if previous.is_file() else {}
                    failures = {r["case"]: r["message"] for r in previous.get("cases", [])
                                if r["status"] == "batch_error"}
                    summarize(directory, protocol, failures, "partial")
                    archive_results(directory)
                return 0
            _pin_cpu(protocol["cpu"])
            summary = execute_matrix(directory, protocol, resume=True, max_points=args.max_points)
        else:
            cpu = _pin_cpu(args.cpu)
            selected = args.solvers.split(",") if args.solvers else None
            solver = selected[0] if selected else args.solver
            jobs = make_jobs(args.cases.split(","), [int(n) for n in args.cstr_sizes.split(",")], args.domain, selected)
            executable = args.executable or os.environ.get("GAMS_BIN" if is_gams(solver) else "IPOPT_BIN")
            if executable is None and is_gams(solver) and os.environ.get("GAMS_DIR"):
                executable = str(Path(os.environ["GAMS_DIR"]) / "gams")
            if executable is None and solver == "ipopt" and (ROOT / ".venv-dantzig/bin/ipopt").is_file():
                executable = str(ROOT / ".venv-dantzig/bin/ipopt")
            config = {"solver": solver, "executable": executable, "domain": args.domain,
                      "initialization": args.initialization, "time_limit": args.time_limit}
            identities = _identities(jobs, config)
            check_gams_version(jobs, identities, args.expected_gams_version)
            config["executable"] = next(iter(identities.values()))["solver_executable"]
            protocol = {"kind": KIND, "created_utc": batch._now(), "cpu": cpu,
                        "jobs": jobs, "config": config, "runtime": identities,
                        "expected_gams_version": args.expected_gams_version,
                        "runner_sha256": runner_hashes()}
            print(json.dumps({"jobs": jobs, "total_candidates": sum(j["candidate_count"] for j in jobs),
                              "solvers": selected or [solver], "executable": config["executable"], "cpu": cpu,
                              "solver_execution_checks": {
                                  j.get("solver", solver): identities[j["name"]].get("solver_execution_check")
                                  for j in jobs},
                              "preflight": {name: identity["preflight"] for name, identity in identities.items()},
                              "dependency_versions": next(iter(identities.values()))["dependency_versions"]}, indent=2))
            if args.mode == "check":
                return 0
            args.output_root.mkdir(parents=True, exist_ok=True)
            stamp = batch._now()[:19].replace("-", "").replace(":", "").replace("T", "_")
            label = "dantzig_gdp_gams" if selected and is_gams(solver) else "dantzig_gdp"
            directory = Path(tempfile.mkdtemp(prefix=f"{label}_{stamp}_", dir=args.output_root)).resolve()
            print(f"RESULT_DIR={directory}", flush=True)
            summary = execute_matrix(directory, protocol, max_points=args.max_points)
        print(json.dumps(summary, indent=2))
        return 1 if summary["error_count"] else 0
    except KeyboardInterrupt:
        print("Interrupted. Resume with: python -m gdp_models.dantzig resume --run-dir RESULT_DIR", file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
