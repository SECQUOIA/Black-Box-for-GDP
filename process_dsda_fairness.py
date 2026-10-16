"""DSDA-only frozen process rerun. No Grid runs, NLP solves, or other DFO methods."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parent
REFERENCE = "benchmark_protocols/process_dsda_fairness_reference.json"
KIND = "process_dsda_budget_fairness_v1"
THREADS = (
    "OMP_NUM_THREADS",
    "OMP_THREAD_LIMIT",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)
PINS = {"numpy": "2.4.6", "scipy": "1.17.1"}
RECORDED_PACKAGES = (*PINS, "pandas")
ENVIRONMENT_POLICY = (
    "Pin NumPy/SciPy; record pandas without an exact pin. The process DSDA "
    "path supplies domain dictionaries and never calls pandas CSV/dataframe APIs. "
    "Required tests forbid those APIs on every configured process run."
)


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def save(p, data):
    from evaluation_trace import safe_json

    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(safe_json(data), indent=2, allow_nan=False) + "\n")
    tmp.replace(p)


def sources():
    names = [
        "process_dsda_fairness.py",
        "process_dsda_fairness_analysis.py",
        "process_dsda_fairness_recovery.py",
        "run_process_dsda_fairness_dantzig.sh",
        "docs/process_dsda_fairness_dantzig.txt",
        "docs/process_dsda_fairness_report.txt",
        "grid_dsda.py",
        "instrumentation.py",
        "evaluation_trace.py",
        "cpu_affinity.py",
        "small_batch_full_domain.py",
        REFERENCE,
        "benchmark_protocols/small_batch_full_domain.json",
        "fmqa_benchmark/__init__.py",
        "fmqa_benchmark/protocol.py",
        "overnight_benchmark/__init__.py",
        "overnight_benchmark/common.py",
        "case_studies/__init__.py",
        "case_studies/common.py",
        "case_studies/dsda_domain.py",
        "tests/test_process_dsda_fairness.py",
        "tests/test_process_dsda_fairness_analysis.py",
        "scripts/prepare_process_dsda_fairness.py",
    ]
    for c in ("column", "cstr", "dynamic", "small_batch"):
        names += [
            f"case_studies/{c}_dsda.py",
            f"case_studies/{c}_case.py",
            f"tests/test_{c}_dsda_case.py",
        ]
    names += [
        str(p.relative_to(ROOT))
        for p in (ROOT / "case_study_data").rglob("*")
        if p.suffix in (".py", ".csv")
    ]
    return sorted(set(names))


def hashes():
    return {s: sha(ROOT / s) for s in sources()}


@contextmanager
def exclusive_run(directory):
    """Reject concurrent resume/pack; never manipulate another process."""
    import fcntl

    with (Path(directory) / ".controller.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "This run has an active controller; leave it running"
            ) from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def git_state(path):
    data = {"path": str(path)}
    for key, args in {
        "head": ["rev-parse", "HEAD"],
        "branch": ["branch", "--show-current"],
        "working_tree": ["status", "--short"],
    }.items():
        p = subprocess.run(
            ["git", "-C", str(path), *args], capture_output=True, text=True
        )
        data[key] = p.stdout.strip() if p.returncode == 0 else None
    return data


def verify_plan(ref):
    from case_studies.dsda_domain import validate_design

    specs = ref["plan"]
    expected = set()
    for n, b in zip((5, 10, 15, 20, 25, 30), (8, 15, 22, 29, 36, 43)):
        expected.update(("cstr", n, b, s) for s in range(10))
    expected.update(
        ("dynamic", None, b, s) for b in (12, 15, 20, 30, 37, 50) for s in range(10)
    )
    expected.update(("column", None, 16, s) for s in range(1, 11))
    expected.update(("small_batch", None, 10, s) for s in range(10))
    actual = {
        (s["case_name"], s.get("grid_size"), s["max_evaluations"], s["seed"])
        for s in specs
    }
    if actual != expected or len(specs) != 140:
        raise ValueError("Expected exactly 140 publication DSDA runs")
    for s in specs:
        if (
            s["method"] != "dsda"
            or s["n_starts"] != 3
            or s["settings"] != {"diagonal": True, "tie_break": "first"}
        ):
            raise ValueError("Changed algorithm/settings")
        n = s.get("grid_size")
        lo, hi = {
            "column": ([7, 1], [15, 9]),
            "cstr": ([1, 1], [n, n]),
            "dynamic": ([1, 2], [9, 9]),
            "small_batch": ([1] * 3, [3] * 3),
        }[s["case_name"]]
        if (s["lower_bounds"], s["upper_bounds"]) != (lo, hi):
            raise ValueError("Changed publication bounds")
        validate_design(s["starting_points"], lo, hi, 3, s["max_evaluations"])
        if (
            hashlib.sha256(
                json.dumps(s["starting_points"], separators=(",", ":")).encode()
            ).hexdigest()
            != s["initial_design_sha256"]
        ):
            raise ValueError("Changed initial design")
    others = [r for r in ref["selected_runs"] if r["method"] != "dsda"]
    if (
        len(others) != 420
        or hashlib.sha256(json.dumps(others, sort_keys=True).encode()).hexdigest()
        != ref["non_dsda_sha256"]
    ):
        raise ValueError("Non-DSDA selection changed")
    return specs


def runtime(cpu, development):
    from cpu_affinity import pin_cpu, affinity_record

    if not development and (
        platform.system() != "Linux" or not socket.getfqdn().startswith("dantzig")
    ):
        raise RuntimeError(
            "Publication measurements must run on Dantzig; use --development for local smoke only"
        )
    affinity = affinity_record(pin_cpu(cpu))
    versions = {k: importlib.metadata.version(k) for k in RECORDED_PACKAGES}
    if any(versions[k] != expected for k, expected in PINS.items()):
        raise RuntimeError(
            f"Use existing compatible DFO environment: expected {PINS}, got {versions}"
        )
    if any(os.environ.get(k) != "1" for k in THREADS):
        raise RuntimeError(
            "Single-thread variables must all be 1; use the shell wrapper"
        )
    return {
        "utc": now(),
        "host": socket.getfqdn(),
        "platform": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "versions": versions,
        "environment_policy": ENVIRONMENT_POLICY,
        "affinity": affinity,
        "thread_environment": {k: os.environ[k] for k in THREADS},
        "development_only": development,
        "repository_state": git_state(os.environ.get("DSDA_REPOSITORY", ROOT)),
    }


def raw_problem(spec):
    if spec["case_name"] == "small_batch":
        from small_batch_full_domain import problem
    else:
        from fmqa_benchmark.protocol import problem
    return problem(spec)


def invoke(spec):
    if spec["case_name"] == "small_batch":
        from small_batch_full_domain import run_dfo

        return run_dfo(spec, {})
    module = importlib.import_module("case_studies." + spec["case_name"] + "_dsda")
    kwargs = {
        "seed": spec["seed"],
        "n_starts": 3,
        "max_evaluations": spec["max_evaluations"],
        "starting_points": spec["starting_points"],
        "verbose": True,
        **spec["settings"],
    }
    if spec["case_name"] == "cstr":
        kwargs["grid_size"] = spec["grid_size"]
    return getattr(module, "run_" + spec["case_name"] + "_dsda")(**kwargs)


def check_events(spec, events, record):
    from evaluation_trace import finite_value, validate_events

    validate_events(events, record)
    if (
        not 3 <= len(events) <= spec["max_evaluations"]
        or [e["point"] for e in events[:3]] != spec["starting_points"]
    ):
        raise ValueError("Budget or frozen ordered initial design mismatch")
    oracle = raw_problem(spec)["objective"]
    best = None
    seen = set()
    last = 0.0
    first = None
    for i, e in enumerate(events, 1):
        p = tuple(e["point"])
        if len(p) != len(spec["lower_bounds"]) or any(
            type(v) is not int or not lo <= v <= hi
            for v, lo, hi in zip(p, spec["lower_bounds"], spec["upper_bounds"])
        ):
            raise ValueError("Callback outside declared box")
        raw = oracle(p)
        value = raw if math.isfinite(raw) or spec["case_name"] == "cstr" else 1e6
        if (e["value"], e["value_kind"]) != finite_value(value):
            raise ValueError("Changed lookup response")
        if best is None or math.isnan(best) or value < best:
            best = value
        if (e["incumbent"], e["incumbent_kind"]) != finite_value(best):
            raise ValueError("Invalid incumbent")
        if e["repeated_point"] != (p in seen):
            raise ValueError("Wrong repeat flag")
        if not last <= e["started_elapsed_s"] <= e["completed_elapsed_s"]:
            raise ValueError("Invalid callback clocks")
        if (
            not 0
            <= e["objective_wall_s"]
            <= e["completed_elapsed_s"] - e["started_elapsed_s"] + 1e-9
        ):
            raise ValueError("Invalid lookup duration")
        last = e["completed_elapsed_s"]
        seen.add(p)
        e["raw_value"], e["raw_value_kind"] = finite_value(raw)
        e["lookup_successful"] = math.isfinite(raw)
        e["raw_response_note"] = (
            "Common lookup response; unsuccessful does not prove mathematical infeasibility"
        )
        hit = math.isfinite(raw) and abs(raw - spec["target_value"]) <= 1e-5 * max(
            1, abs(spec["target_value"])
        )
        if hit and first is None:
            first = i
    if list(record["best_point"]) not in [
        e["point"] for e in events if e["lookup_successful"]
    ]:
        raise ValueError("Final incumbent not observed valid")
    if oracle(record["best_point"]) != record["best_value"]:
        raise ValueError("Final best disagrees with its lookup response")
    # Initial ranking is strict/stable; the unchanged DSDA engine subsequently
    # updates best_seen only for value < best_seen - tol. The tracker above
    # intentionally records every strict minimum, including sub-tolerance ones.
    initial = [e for e in events[:3] if e["lookup_successful"]]
    expected = min(initial, key=lambda e: e["value"])
    for event in events[3:]:
        if event["lookup_successful"] and event["value"] < expected["value"] - 1e-12:
            expected = event
    if (list(record["best_point"]), record["best_value"]) != (
        expected["point"], expected["value"]
    ):
        raise ValueError("Final best disagrees with DSDA tolerance-aware callbacks")
    if record["unique_evals"] != len(seen) or record["initial_evals"] != 3:
        raise ValueError("Wrong callback counts")
    return {
        "target_hit": first is not None,
        "first_target_callback": first,
        "unsuccessful_evaluations": sum(not e["lookup_successful"] for e in events),
    }


def diagnostic(spec, measured):
    """Replay after the measured clock: membership-only candidates, no cost claims."""
    from unittest.mock import patch
    from evaluation_trace import ACTIVE_TRACE, finite_value
    import grid_dsda

    records = []
    events = []
    engine_results = []
    original = grid_dsda.dsda_from_csv

    class Observer:
        timer = staticmethod(time.perf_counter)

        def record(self, point, value, incumbent, *args):
            events.append(
                {"point": [int(v) for v in point], "value": finite_value(value)}
            )
            records.append(
                {
                    "event": "callback",
                    "evaluation_index": len(events),
                    "point": events[-1]["point"],
                }
            )

    class Domain(dict):
        def __contains__(self, p):
            inside = super().__contains__(p)
            name = sys._getframe(1).f_code.co_name
            phase = (
                "neighbor_search"
                if name == "get_neighbors"
                else "start_membership"
                if len(events) == 3
                and not engine_results
                and not any(r.get("search_phase") == "neighbor_search" for r in records)
                else "line_search"
            )
            records.append(
                {
                    "event": "candidate",
                    "point": list(p),
                    "search_phase": phase,
                    "in_bounds": inside,
                    "callbacks_so_far": len(events),
                    "decision": "in_bounds_candidate" if inside else "out_of_bounds",
                }
            )
            return inside

        def __getitem__(self, p):
            raise AssertionError("DSDA read a domain value")

        def get(self, *args):
            raise AssertionError("DSDA read a domain value")

    def wrapped(*args, **kwargs):
        kwargs["grid"] = Domain(kwargs["grid"])
        out = original(*args, **kwargs)
        engine_results.append(out)
        return out

    observer = Observer()
    token = ACTIVE_TRACE.set(observer)
    try:
        module = (
            grid_dsda
            if spec["case_name"] == "small_batch"
            else importlib.import_module("case_studies." + spec["case_name"] + "_dsda")
        )
        with patch.object(module, "dsda_from_csv", wrapped):
            invoke(spec)
    finally:
        ACTIVE_TRACE.reset(token)
    if events != [
        {"point": e["point"], "value": (e["value"], e["value_kind"])} for e in measured
    ]:
        raise ValueError("Diagnostic replay differs from measured path")
    phases = ["initial"] * 3
    if engine_results:
        phases += [p[2] for p in engine_results[0]["explored_points"][1:]]
    if len(phases) != len(measured):
        raise ValueError("Search phase alignment failed")
    for e, phase in zip(measured, phases):
        e["search_phase"] = phase
    # Inspect outcomes only AFTER execution; annotations never enter search.
    oracle = raw_problem(spec)["objective"]
    for r in records:
        if r["event"] == "candidate" and r["in_bounds"]:
            r["would_be_excluded_by_old_finite_map"] = spec[
                "case_name"
            ] != "small_batch" and not math.isfinite(oracle(r["point"]))
    return {
        "timing_excluded": True,
        "replay_matches_measured_callbacks": True,
        "records": records,
        "engine_result": engine_results[0] if engine_results else None,
    }


def worker(directory, identifier):
    from evaluation_trace import EvaluationTrace

    directory = Path(directory)
    run = read(directory / "run.json")
    if run["source_files_sha256"] != hashes():
        raise ValueError("Source changed since freezing run")
    spec = next(s for s in run["plan"] if s["job_id"] == identifier)
    job = directory / "jobs" / identifier
    job.mkdir(parents=True, exist_ok=False)
    save(job / "spec.json", spec)
    outer = time.perf_counter()
    result = {"spec": spec, "status": "error"}
    try:
        # Match historical tracing: October 2 flush; October 12 supplement fsync.
        class Trace(EvaluationTrace):
            def write(self, event):
                super().write(event)
                if spec["case_name"] == "small_batch" or (
                    spec["case_name"] == "column" and spec["seed"] == 10
                ):
                    os.fsync(self.handle.fileno())

        with Trace(job / "lookup.csv", spec) as trace:
            out = invoke(spec)
            search_elapsed = trace.timer() - trace.origin
            record = out["result_record"]
            # Preserve the actual return and measured clocks even if subsequent
            # audit checks fail. These writes occur after the method timer ends.
            result.update(result_record=record, search_wall_s=search_elapsed)
            save(job / "optimizer_return.json", {
                "result_record": record,
                "search_wall_s": search_elapsed,
                "stop_reason": out.get("stop_reason"),
            })
            checks = check_events(spec, trace.events, record)
            artifact = trace.complete(record)
        method = record["wall_time_s"]
        lookup = math.fsum(e["objective_wall_s"] for e in trace.events)
        if not 0 <= lookup <= method <= search_elapsed:
            raise ValueError("Clock scopes do not reconcile")
        result.update(
            status="completed",
            result_record=record,
            trace=artifact,
            search_wall_s=search_elapsed,
            lookup_wall_s=lookup,
            stop_reason=out.get("stop_reason") or "no_improving_neighbor",
            raw_stop_reason=out.get("stop_reason"),
            **checks,
        )
        measured_outer = time.perf_counter() - outer
        diag = diagnostic(spec, trace.events)
        save(job / "diagnostic_candidates.json", diag)
        save(job / "callbacks.json", trace.events)
        result["measured_worker_wall_s"] = measured_outer
        result["clock_scope"] = (
            "Historical method clock and callback flush policy; diagnostic replay/validation/export excluded from method time"
        )
    except BaseException as error:
        result.update(
            status="error",
            exception_type=type(error).__name__,
            exception=str(error),
            traceback=traceback.format_exc(),
        )
    result["worker_total_with_diagnostics_s"] = time.perf_counter() - outer
    save(job / "result.json", result)
    save(
        job / "terminal.json",
        {
            "files_sha256": {
                str(p.relative_to(job)): sha(p)
                for p in sorted(job.rglob("*"))
                if p.is_file() and p.name != "terminal.json"
            }
        },
    )
    if result["status"] != "completed":
        raise RuntimeError(result["exception"])


def valid_job(job):
    seal = read(job / "terminal.json")["files_sha256"]
    actual = {
        str(p.relative_to(job))
        for p in job.rglob("*")
        if p.is_file() and p.name != "terminal.json"
    }
    if set(seal) != actual or any(sha(job / k) != v for k, v in seal.items()):
        raise ValueError(f"Job checksum mismatch: {job}")
    return read(job / "result.json")


def pack(directory):
    directory = Path(directory)
    files = [
        p
        for p in sorted(directory.rglob("*"))
        if p.is_file() and p.name != "SHA256SUMS"
    ]
    (directory / "SHA256SUMS").write_text(
        "".join(f"{sha(p)}  {p.relative_to(directory).as_posix()}\n" for p in files)
    )
    output = directory.parent / (directory.name + "_" + str(time.time_ns()) + ".zip")
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.rglob("*")):
            if p.is_file():
                z.write(p, str(Path(directory.name) / p.relative_to(directory)))
    output.with_suffix(".zip.sha256").write_text(
        sha(output) + "  " + output.name + "\n"
    )
    save(
        directory.parent / "latest_result.json",
        {"run_dir": str(directory), "result_zip": str(output), "sha256": sha(output)},
    )
    print("RESULT_ZIP=" + str(output), flush=True)
    return output


def execute_locked(directory):
    run = read(directory / "run.json")
    if hashes() != run["source_files_sha256"]:
        raise ValueError("Source/plan changed")
    failed = False
    try:
        print("START required DSDA tests (no NLP/other-method runs)", flush=True)
        with (directory / "tests.log").open("w") as log:
            tested = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests",
                    "-p",
                    "test_process_dsda_fairness*.py",
                    "-v",
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        if tested.returncode:
            raise RuntimeError(
                "Required tests failed; see tests.log. No benchmark runs launched."
            )
        print("PASS required DSDA tests", flush=True)
        for spec in run["plan"]:
            ident = spec["job_id"]
            job = directory / "jobs" / ident
            if job.exists():
                if valid_job(job)["status"] == "completed":
                    continue
                raise RuntimeError(
                    "Existing failed job; preserve it and start a new run, or inspect before retrying"
                )
            print("START " + ident, flush=True)
            logpath = directory / "logs" / (ident + ".log")
            logpath.parent.mkdir(exist_ok=True)
            with logpath.open("w") as log:
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "process_dsda_fairness.py"),
                        "worker",
                        "--run-dir",
                        str(directory),
                        "--job",
                        ident,
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=120,
                )
            ok = completed.returncode == 0 and valid_job(job)["status"] == "completed"
            print(
                "DONE " + ident + " status=" + ("completed" if ok else "error"),
                flush=True,
            )
            failed |= not ok
        from process_dsda_fairness_analysis import analyze

        summary = analyze(directory)
        print(json.dumps(summary), flush=True)
        if failed:
            raise RuntimeError("Some DSDA jobs failed; see per-job logs")
    except BaseException as error:
        save(
            directory / "interruption.json",
            {"utc": now(), "error": str(error), "traceback": traceback.format_exc()},
        )
        raise
    finally:
        pack(directory)


def execute(directory):
    with exclusive_run(directory):
        execute_locked(directory)


def bundle(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    inventory = hashes()
    ref = read(ROOT / REFERENCE)
    verify_plan(ref)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for name in inventory:
            z.write(ROOT / name, "process_dsda_fairness/" + name)
        metadata = {
            "kind": KIND,
            "created_utc": now(),
            "source_files_sha256": inventory,
            "planned_runs": 140,
            "requirements": PINS,
            "environment_policy": ENVIRONMENT_POLICY,
            "head": ref["head"],
            "build_repository_state": git_state(ROOT),
        }
        z.writestr(
            "process_dsda_fairness/bundle.json", json.dumps(metadata, indent=2) + "\n"
        )
    output.with_suffix(".zip.sha256").write_text(
        sha(output) + "  " + output.name + "\n"
    )
    print("BUNDLE_ZIP=" + str(output))
    print("SHA256=" + sha(output))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "mode",
        choices=["bundle", "run", "recover", "resume", "worker", "analyze", "pack", "status"],
    )
    p.add_argument("--output", type=Path)
    p.add_argument("--output-root", type=Path, default=ROOT / "runs")
    p.add_argument("--run-dir", type=Path)
    p.add_argument("--parent-zip", type=Path)
    p.add_argument("--job")
    p.add_argument("--cpu", type=int)
    p.add_argument("--development", action="store_true")
    p.add_argument("--smoke", action="store_true")
    a = p.parse_args()
    if a.mode == "bundle":
        return bundle(a.output)
    if a.mode == "recover":
        from process_dsda_fairness_recovery import recover

        return recover(a.parent_zip, a.output_root, a.cpu, a.development)
    if a.mode == "worker":
        return worker(a.run_dir, a.job)
    if a.mode == "pack":
        with exclusive_run(a.run_dir):
            return pack(a.run_dir)
    if a.mode == "status":
        run = read(a.run_dir / "run.json")
        done = [
            valid_job(d)
            for d in (a.run_dir / "jobs").glob("*")
            if (d / "terminal.json").exists()
        ]
        print(
            json.dumps(
                {
                    "planned": len(run["plan"]),
                    "completed": sum(r["status"] == "completed" for r in done),
                    "errors": sum(r["status"] != "completed" for r in done),
                },
                indent=2,
            )
        )
        return
    if a.mode == "analyze":
        from process_dsda_fairness_analysis import analyze

        with exclusive_run(a.run_dir):
            print(json.dumps(analyze(a.run_dir), indent=2))
        return
    if a.mode == "resume":
        run = read(a.run_dir / "run.json")
        current = runtime(a.cpu, run["development_only"])
        if (
            current["host"] != run["runtime"]["host"]
            or current["affinity"]["effective_cpus"]
            != run["runtime"]["affinity"]["effective_cpus"]
        ):
            raise ValueError("Resume host/CPU differs from original")
        return execute(a.run_dir)
    ref = read(ROOT / REFERENCE)
    plan = verify_plan(ref)
    if (ROOT / "bundle.json").exists() and read(ROOT / "bundle.json")[
        "source_files_sha256"
    ] != hashes():
        raise ValueError("Bundle content changed")
    if a.smoke:
        plan = [
            next(s for s in plan if s["case_name"] == c)
            for c in ("column", "cstr", "dynamic", "small_batch")
        ]
    a.output_root.mkdir(parents=True, exist_ok=True)
    directory = Path(
        tempfile.mkdtemp(
            prefix="process_dsda_budget_fairness_20261014_", dir=a.output_root
        )
    ).resolve()
    print("RUN_DIR=" + str(directory), flush=True)
    save(a.output_root / "latest_run.json", {"run_dir": str(directory)})
    try:
        rt = runtime(a.cpu, a.development)
        print("ENVIRONMENT=" + json.dumps(rt["versions"], sort_keys=True), flush=True)
        run = {
            "kind": KIND,
            "created_utc": now(),
            "development_only": a.development,
            "smoke_only": a.smoke,
            "plan": plan,
            "runtime": rt,
            "source_files_sha256": hashes(),
            "reference_sha256": sha(ROOT / REFERENCE),
            "build_metadata": read(ROOT / "bundle.json")
            if (ROOT / "bundle.json").exists()
            else git_state(ROOT),
            "policy": "DSDA lookup only; diagnostic replay excluded from measurement; no official selection overwrite",
        }
        save(directory / "run.json", run)
        for name in sources():
            dest = directory / "source" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
    except BaseException as error:
        save(
            directory / "preflight_error.json",
            {"error": str(error), "traceback": traceback.format_exc()},
        )
        pack(directory)
        raise
    execute(directory)


if __name__ == "__main__":
    main()
