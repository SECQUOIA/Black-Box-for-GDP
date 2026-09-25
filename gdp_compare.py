"""Dantzig: GDPopt RIC/GLOA (IPOPT) versus Big-M/Hull (BARON), 30 min/job."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
from time import monotonic
import zipfile

from cpu_affinity import affinity_record, pin_cpu


ROOT = Path(__file__).resolve().parent
MCPP_COMMIT = "c8ae9800d02b09bee0012aed593de92c9cf10fa7"
KIND = "full_gdp_method_comparison"
METHODS = ("ric", "gloa", "bigm", "hull")
CASES = ("cstr", "column", "dynamic", "small_batch")
CSTR_SIZES = (5, 10, 15, 20, 25, 30)
THREAD_ENV = {name: "1" for name in (
    "OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "GOTO_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS", "NUMEXPR_MAX_THREADS")}


def environment():
    # Must run before importing Pyomo/NumPy/MC++.
    os.environ.update(THREAD_ENV, OMP_DYNAMIC="FALSE", MKL_DYNAMIC="FALSE", MPLBACKEND="Agg")
    os.environ.setdefault("PYOMO_CONFIG_DIR", str(ROOT / ".pyomo-gdp-comparison"))


def save(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def planned_instances(config):
    """Expand each CSTR size into its own GDP; retain old archive identifiers."""
    instances = []
    for case in config["cases"]:
        if case == "cstr":
            # Only old manifests omit cstr_sizes; new runs always record it.
            legacy = "cstr_sizes" not in config
            for size in config.get("cstr_sizes", (30,)):
                instances.append({"instance_id": "cstr" if legacy else f"cstr_{size}",
                                  "case": case, "cstr_size": size})
        else:
            instances.append({"instance_id": case, "case": case, "cstr_size": None})
    return instances


def model_identity(template):
    metadata = template.metadata
    return {"case": metadata["case"], "cstr_size": metadata.get("cstr_size"),
            "instance_id": metadata.get("instance_id", metadata["case"])}


def result_key(record):
    return record.get("instance_id", record["case"]), record["method"]


def source_files():
    return [ROOT / "gdp_compare.py", ROOT / "cpu_affinity.py", *sorted((ROOT / "gdp_models").glob("*.py")),
            ROOT / "requirements-gdp.txt", ROOT / "requirements-gdp-comparison.txt",
            ROOT / "docs/gdp_comparison.md", ROOT / "docs/dantzig_cpu_rerun.md", ROOT / "LICENSE",
            *(p for p in (ROOT / "run_gdp_comparison_dantzig.sh",) if p.is_file())]


def setup_mcpp():
    base = Path(os.environ["PYOMO_CONFIG_DIR"])
    target = base / "src/mcpp"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--no-checkout", "https://github.com/omega-icl/mcpp.git", str(target)], check=True)
    if not (target / ".git").is_dir():
        raise ValueError(f"Existing MC++ directory is not a Git checkout: {target}")
    dirty = subprocess.check_output(["git", "-C", str(target), "status", "--porcelain"], text=True)
    # An initial --no-checkout clone appears deleted until the first checkout.
    head = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
    if dirty and any(target.glob("src/mc/*.hpp")) and head != MCPP_COMMIT:
        raise ValueError("MC++ checkout has local changes; refusing to replace them")
    subprocess.run(["git", "-C", str(target), "checkout", "--detach", MCPP_COMMIT], check=True)
    os.environ["MCPP_ROOT"] = str(target)
    os.environ["CXXFLAGS"] = (os.environ.get("CXXFLAGS", "") + " -std=c++17").strip()
    from pyomo.contrib.mcpp.build import build_mcpp
    build_mcpp()
    print(f"MC++ ready: {MCPP_COMMIT}; PYOMO_CONFIG_DIR={base}")


def check(config, directory):
    from pyomo.common.fileutils import find_library
    from pyomo.contrib.mcpp.pyomo_mcpp import mcpp_available, McCormick
    import pyomo.environ as pyo
    from gdp_models import comparison as impl
    from gdp_models.preflight import dependency_versions

    config["executable"] = str(Path(config["executable"]).resolve())
    impl.CONTEXT = impl.SolveContext(config["executable"], directory, monotonic() + 30)
    version = list(impl.TimedGAMS().version())
    expected = [int(n) for n in config["expected_gams_version"].split(".")]
    if version[:len(expected)] != expected:
        raise ValueError(f"Expected GAMS {expected}, found {version}")
    mcpp = None
    if "gloa" in config["methods"]:
        if not mcpp_available():
            raise RuntimeError("GLOA requires MC++; run the comparison setup command first")
        m = pyo.ConcreteModel()
        m.x = pyo.Var(bounds=(0, 2), initialize=1)
        relaxation = McCormick(m.x**2)
        if relaxation.lower() > 0 or relaxation.upper() < 4:
            raise RuntimeError("MC++ arithmetic smoke test failed")
        library = Path(find_library("mcppInterface"))
        mcpp = {"library": str(library), "sha256": sha(library),
                "expected_source_commit": MCPP_COMMIT}
    solvers = (["ipopt", "cplex"] if set(config["methods"]) & {"ric", "gloa"} else [])
    if set(config["methods"]) & {"bigm", "hull"}:
        solvers.append("baron")
    solver_checks = impl.smoke_solvers(config["executable"], directory / "solver_checks", solvers)
    templates = {spec["instance_id"]: impl.build_template(
        spec["case"], cstr_size=spec["cstr_size"] or 30, instance_id=spec["instance_id"])
        for spec in planned_instances(config)}
    transformation_checks = []
    for instance_id, template in templates.items():
        for method in config["methods"]:
            if method not in {"bigm", "hull"}:
                continue
            model = template.model.clone()
            impl.reformulate(model, method)
            with tempfile.TemporaryDirectory(prefix="gdp-transform-check-") as tmp:
                model.write(str(Path(tmp) / "model.gms"), format="gams",
                            io_options={"solver": "baron", "mtype": "minlp"})
            transformation_checks.append({**model_identity(template), "method": method, "gams_written": True})
    identity = {"gams_version": version, "gams_executable_sha256": sha(Path(config["executable"])),
                "dependencies": dependency_versions(), "python_version": sys.version,
                "mcpp": mcpp, "solver_checks": solver_checks,
                "transformation_checks": transformation_checks,
                "templates": {instance_id: t.metadata for instance_id, t in templates.items()}}
    return templates, identity


def worker(template, method, path, config, deadline):
    os.setsid()
    with (path / "run.log").open("w", buffering=1) as log:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        try:
            from gdp_models.comparison import solve_method
            solve_method(template, method, path, config, deadline)
        except BaseException as error:
            import traceback
            traceback.print_exc()
            current = path / "result.json"
            record = json.loads(current.read_text()) if current.exists() else {}
            record.update(**model_identity(template), method=method,
                          status="worker_error", message=f"{type(error).__name__}: {error}",
                          global_optimality_certified=False)
            save(current, record)
            raise


def terminate_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    process.join(3)
    # Clean up surviving solver descendants even if Python already exited.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.join(3)


def run_job(template, method, directory, config, target=worker):
    directory.mkdir(parents=True)
    before = monotonic()
    process = multiprocessing.get_context("fork").Process(
        target=target, args=(template, method, directory, config, before + config["time_limit"]))
    sys.stdout.flush()
    sys.stderr.flush()
    process.start()
    timed_out = False
    try:
        process.join(max(0, config["time_limit"] - (monotonic() - before)))
        if process.is_alive():
            timed_out = True
            terminate_group(process)
    except BaseException:
        terminate_group(process)
        result_path = directory / "result.json"
        try:
            record = json.loads(result_path.read_text())
        except (OSError, ValueError):
            record = {**model_identity(template), "method": method,
                      "has_feasible_solution": False, "objective": None}
        record.update(status="interrupted", termination="userInterrupt", global_optimality_certified=False,
                      **model_identity(template),
                      worker_pid=process.pid, worker_returncode=process.exitcode,
                      worker_wall_s=monotonic() - before)
        save(result_path, record)
        raise
    result_path = directory / "result.json"
    try:
        record = json.loads(result_path.read_text())
    except (OSError, ValueError):
        record = {**model_identity(template), "method": method,
                  "status": "worker_error", "has_feasible_solution": False,
                  "objective": None, "global_optimality_certified": False,
                  "message": "Worker did not return a readable result"}
    if timed_out:
        record.update(status="hard_time_limit", termination="maxTimeLimit", global_optimality_certified=False)
    elif process.exitcode != 0:
        record.update(status="worker_error", global_optimality_certified=False)
    record.update(**model_identity(template), worker_pid=process.pid, worker_returncode=process.exitcode,
                  worker_wall_s=monotonic() - before, hard_time_limit_reached=timed_out)
    save(result_path, record)
    return record


def summarize(directory):
    manifest = json.loads((directory / "run.json").read_text())
    records = [json.loads(p.read_text()) for p in sorted((directory / "jobs").glob("*/*/result.json"))]
    keys = {result_key(r) for r in records}
    specs = {s["instance_id"]: s for s in planned_instances(manifest["config"])}
    expected = {(key, m) for key in specs for m in manifest["config"]["methods"]}
    if len(keys) != len(records) or not keys <= expected:
        raise ValueError("Unexpected/duplicate comparison result")
    for record in records:
        spec = specs[result_key(record)[0]]
        if record["case"] != spec["case"] or (
                "cstr_sizes" in manifest["config"] and record.get("cstr_size") != spec["cstr_size"]):
            raise ValueError("Comparison result does not match the planned model size")
    completed = {result_key(r) for r in records if r.get("status") != "running"}
    summary = {"completed_jobs": len(completed), "planned_jobs": len(expected), "complete": completed == expected,
               "feasible_jobs": sum(bool(r.get("has_feasible_solution")) for r in records),
               "globally_certified_jobs": sum(bool(r.get("global_optimality_certified")) for r in records),
               "pending_jobs": [list(k) for k in sorted(expected - completed)], "results": records}
    save(directory / "summary.json", summary)
    fields = ("instance_id", "case", "cstr_size", "method", "status", "termination", "objective", "has_feasible_solution",
              "global_optimality_certified", "global_bound_valid", "reported_lower_bound",
              "reported_upper_bound", "max_primal_violation", "template_wall_s",
              "reformulation_wall_s", "solve_wall_s", "method_wall_s", "worker_wall_s", "solver_calls", "message")
    with (directory / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    return summary


def pack(directory):
    directory = Path(directory).resolve()
    if json.loads((directory / "run.json").read_text())["kind"] != KIND:
        raise ValueError("Not a full GDP comparison run")
    summary = summarize(directory)
    paths = sorted(p for p in directory.rglob("*") if p.is_file() and not p.is_symlink()
                   and p.name != "SHA256SUMS" and not p.name.endswith(".tmp")
                   and not any(part.startswith("gams-") for part in p.relative_to(directory).parts))
    checks = directory / "SHA256SUMS"
    checks.write_text("".join(f"{sha(p)}  {p.relative_to(directory).as_posix()}\n" for p in paths))
    output = directory.with_name(directory.name + ".zip")
    temporary = output.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for p in [*paths, checks]:
            archive.write(p, f"{directory.name}/{p.relative_to(directory).as_posix()}")
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Corrupt comparison result ZIP")
    temporary.replace(output)
    output.with_suffix(".zip.sha256").write_text(f"{sha(output)}  {output.name}\n")
    print(f"RESULT_ZIP={output}", flush=True)
    return summary


def bundle(output):
    files = source_files()
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, "gdp_comparison_runner/" + path.relative_to(ROOT).as_posix())
        archive.writestr("gdp_comparison_runner/COMPARISON_RUNNER_SHA256SUMS", "".join(
            f"{sha(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in files))
    print(f"RUNNER_ZIP={output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("setup", "check", "run", "pack", "bundle"))
    parser.add_argument("--cases", default=",".join(CASES))
    parser.add_argument("--cstr-sizes", "--cstr-grid-sizes", default=",".join(map(str, CSTR_SIZES)),
                        help="CSTR reactor counts, default: 5,10,15,20,25,30")
    parser.add_argument("--methods", default=",".join(METHODS))
    parser.add_argument("--time-limit", type=int, default=1800, help="Total seconds per case/method worker")
    parser.add_argument("--cpu", type=int, help="Linux logical CPU ID; default: first allowed CPU")
    parser.add_argument("--relative-gap", type=float, default=1e-5)
    parser.add_argument("--baron-column-hull-lbtt", type=int, choices=(0, 1), default=0,
                        help="Column/Hull linear range reduction: 0 avoids a reproduced false infeasibility; 1 is BARON's default")
    parser.add_argument("--executable", default=os.environ.get("GAMS_BIN", "/package/gams/52.2/gams"))
    parser.add_argument("--expected-gams-version", default=os.environ.get("GDP_GAMS_VERSION", "52.2"))
    parser.add_argument("--output-root", type=Path, default=ROOT / "results")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    environment()
    if args.time_limit <= 0 or not 0 < args.relative_gap < 1:
        parser.error("Time limit must be positive and relative gap must lie in (0,1)")
    cases, methods = args.cases.split(","), args.methods.split(",")
    try:
        cstr_sizes = [int(size) for size in args.cstr_sizes.split(",")]
    except ValueError:
        parser.error("CSTR sizes must be comma-separated positive integers")
    if any(size <= 0 for size in cstr_sizes) or len(set(cstr_sizes)) != len(cstr_sizes):
        parser.error("CSTR sizes must be distinct positive integers")
    if (not set(cases) <= set(CASES) or len(set(cases)) != len(cases) or
            not set(methods) <= set(METHODS) or len(set(methods)) != len(methods)):
        parser.error("Choose distinct supported cases/methods")
    try:
        if args.mode == "setup":
            setup_mcpp()
            return 0
        if args.mode == "bundle":
            if args.output is None:
                parser.error("bundle requires --output")
            bundle(args.output)
            return 0
        if args.mode == "pack":
            if args.run_dir is None:
                parser.error("pack requires --run-dir")
            pack(args.run_dir)
            return 0
        if "fork" not in multiprocessing.get_all_start_methods():
            raise RuntimeError("This runner requires Linux/macOS process isolation via fork")
        executable = shutil.which(args.executable)
        if executable is None:
            raise ValueError("GAMS executable not found; set GAMS_BIN or --executable")
        config = {"cases": cases, "cstr_sizes": cstr_sizes, "methods": methods, "time_limit": args.time_limit,
                  "relative_gap": args.relative_gap, "executable": executable,
                  "baron_column_hull_lbtt": args.baron_column_hull_lbtt,
                  "expected_gams_version": args.expected_gams_version}
        cpu = pin_cpu(args.cpu)
        affinity = affinity_record(cpu)
        print(f"CPU_AFFINITY={json.dumps(affinity)}", flush=True)
        args.output_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        directory = Path(tempfile.mkdtemp(prefix=f"dantzig_gdp_compare_{stamp}_", dir=args.output_root)).resolve()
        print(f"RESULT_DIR={directory}", flush=True)
        protocol = {"kind": KIND, "config": config, "cpu": cpu, "cpu_affinity": affinity, "thread_environment": THREAD_ENV,
                    "host": os.uname().nodename, "created_utc": datetime.now(timezone.utc).isoformat(),
                    "source_sha256": {p.relative_to(ROOT).as_posix(): sha(p) for p in source_files()},
                    "time_policy": "1800s default per method worker; shared templates/preflight separate; up to 6s termination cleanup"}
        save(directory / "run.json", protocol)
        for source in source_files():
            dest = directory / "source" / source.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        try:
            started = monotonic()
            templates, identity = check(config, directory)
            protocol.update(preflight_wall_s=monotonic() - started, runtime=identity, preflight_status="passed")
            save(directory / "run.json", protocol)
            print("PREFLIGHT=passed (selected solvers, models and reformulations)", flush=True)
            if args.mode == "run":
                for instance_id, template in templates.items():
                    for method in methods:
                        print(f"START {instance_id}/{method}, limit={args.time_limit}s", flush=True)
                        result = run_job(template, method, directory / "jobs" / instance_id / method, config)
                        summarize(directory)
                        print(f"DONE {instance_id}/{method}: {result['status']}, objective={result.get('objective')}, "
                              f"feasible={result.get('has_feasible_solution', False)}", flush=True)
        except Exception as error:
            protocol["error"] = f"{type(error).__name__}: {error}"
            save(directory / "run.json", protocol)
            raise
        finally:
            summary = pack(directory)
        print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
        return 1 if any(r.get("status") in {"error", "worker_error"} for r in summary["results"]) else 0
    except KeyboardInterrupt:
        print("Interrupted; completed jobs and saved incumbents have been packaged.", file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
