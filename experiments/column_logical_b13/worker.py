"""One frozen Column search; only the recorded IPOPT table is an objective."""

import argparse
import importlib
import importlib.metadata
import os
from pathlib import Path
import platform
import sys
import time
import traceback

from common import THREADS, read, require, sha, verify_package, write

ROOT = Path(__file__).resolve().parent


def audited_oracle(core, spec, costs, directory):
    """Add diagnostics only; delegate every response to the byte-frozen oracle."""

    class AuditedOracle(core.Oracle):
        audit_budget_overrun = False

        def __call__(self, coordinates):
            if self.call_count >= self.spec["budget"]:
                self.audit_budget_overrun = True
                core.append(
                    self.directory / "callback_overrun_audit.jsonl",
                    {
                        "after_evaluations": self.call_count,
                        "coordinates": core.clean(coordinates),
                        "csv_read": False,
                        "value_returned_to_optimizer": False,
                    },
                )
            return super().__call__(coordinates)

    return AuditedOracle(spec, costs, directory)


def runtime(job, directory, core):
    expected = job["reference_runtime"]
    actual = dict(
        python=platform.python_version(),
        executable=sys.executable,
        host=platform.node(),
        platform=platform.platform(),
        versions={n: importlib.metadata.version(n) for n in expected["versions"]},
        effective_cpus=sorted(os.sched_getaffinity(0)),
        threads={k: os.environ.get(k) for k in THREADS},
        cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"),
    )
    write(directory / "runtime.json", actual)
    require(
        actual["effective_cpus"] == [2]
        and actual["threads"] == THREADS
        and actual["cuda_visible_devices"] == "",
        "CPU/thread/GPU policy differs",
    )
    for key in ("python", "versions", "host", "executable"):
        require(actual[key] == expected[key], "Historical runtime mismatch: " + key)
    method = job["spec"]["method"]
    if method != "uniform_without_replacement":
        actual.update(core.preflight(method, job["config"]))
    if method == "rbfopt":
        for name in ("bonmin", "ipopt"):
            require(
                actual[name + "_sha256"] == expected["binary_sha256"][name],
                "Surrogate executable changed",
            )
        names = [
            "rbfopt.rbfopt_algorithm",
            "rbfopt.rbfopt_settings",
            "rbfopt.rbfopt_aux_problems",
        ]
        actual["rbfopt_sources_sha256"] = {
            n: sha(importlib.import_module(n).__file__) for n in names
        }
    if method == "fmqa_sa":
        require(
            actual["qhd_source"] == expected["qhd_source"], "FMQA vendor source changed"
        )
    actual["platform_equal_to_historical"] = actual["platform"] == expected["platform"]
    write(directory / "runtime.json", actual)


def check_settings(job, directory):
    if job["spec"]["method"] == "uniform_without_replacement":
        return
    actual = read(directory / "actual_settings.json")
    require(
        actual == job["expected_settings"],
        "Actual optimizer settings differ from permitted changes",
    )
    write(
        directory / "settings_verification.json",
        dict(
            passed=True,
            historical=job["reference_settings"],
            expected=job["expected_settings"],
            actual=actual,
            allowed_changes="budget-derived counts and new BAM common initial observations only",
        ),
    )


def execute(job, directory, costs, core):
    spec = job["spec"]
    oracle = audited_oracle(core, spec, costs, directory)
    status, error, returned = "completed", None, None
    started = time.perf_counter()
    write(
        directory / "started.json",
        dict(
            pid=os.getpid(),
            monotonic=started,
            method=spec["method"],
            effective_cpus=sorted(os.sched_getaffinity(0)),
            process_nlp_calls=0,
        ),
    )
    try:
        if spec["method"] == "uniform_without_replacement":
            sys.path.insert(0, str(ROOT / "frozen/sampling"))
            from review_comparison.worker import sampling_points

            points, settings = sampling_points(job["sampling_job"])
            write(directory / "sampling_settings.json", settings)
            for point in points:
                oracle(point)
        else:
            returned = core.optimize(spec, oracle, job["config"], directory)
            if isinstance(returned, dict) and returned.get("status") == "time_limit":
                status, error = "execution_failed", "FMQA soft time limit"
            if spec["method"] == "bam" and returned.get("success") is False:
                status, error = "execution_failed", returned.get("message")
            elif spec["method"] == "bam" and oracle.call_count == spec["budget"]:
                status = "budget_completed"
    except core.BudgetStop:
        status = "budget_completed"
    except Exception as exc:
        if (
            oracle.events
            and oracle.events[-1]["callback_exit"] == "budget_stop"
            and not oracle.audit_budget_overrun
            and not getattr(oracle, "budget_overrun", False)
        ):
            status = "budget_completed"
            returned = dict(terminal_budget_exception=f"{type(exc).__name__}: {exc}")
        else:
            status, error = "execution_failed", f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
    elapsed = time.perf_counter() - started
    if (
        oracle.audit_budget_overrun
        or getattr(oracle, "budget_overrun", False)
        or len(oracle.events) > spec["budget"]
        or any(e.get("budget_overrun") for e in oracle.events)
    ):
        status, error = "execution_failed", "Callback budget overrun"
    settings_error = None
    if (directory / "actual_settings.json").exists():
        try:
            check_settings(job, directory)
        except Exception as exc:
            settings_error = str(exc)
            status, error = "execution_failed", settings_error
    write(
        directory / "result.json",
        dict(
            status=status,
            error=error,
            algorithm_result=core.clean(returned),
            recorded_search_wall_s=elapsed,
            settings_error=settings_error,
            process_nlp_calls=0,
            callback_count=oracle.call_count,
            callback_budget_overrun=oracle.audit_budget_overrun,
            evaluation_table_sha256=sha(ROOT / "inputs/column_64.csv"),
            auxiliary_solver_accounting="RBFOpt calls are journaled separately; BAM internal surrogate work remains in search overhead.",
        ),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    plan, costs = verify_package(ROOT)
    job = next(j for j in plan if j["spec"]["job_id"] == args.job_id)
    args.directory.mkdir(parents=True, exist_ok=True)
    write(args.directory / "job.json", job)
    sys.path.insert(0, str(ROOT / "frozen" / job["frozen"]))
    core = importlib.import_module("ipopt_dfo_non_cstr")
    sys.meta_path.insert(0, core.ProcessModelImportBlocker())
    runtime(job, args.directory, core)
    if args.check:
        write(
            args.directory / "passed.json",
            dict(passed=True, process_nlp_calls=0, optimizer_calls=0),
        )
    else:
        execute(job, args.directory, costs, core)


if __name__ == "__main__":
    main()
