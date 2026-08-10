"""Aggregate DSDA, RBFOpt, and BAM process case-study benchmark runs."""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import signal
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from numbers import Integral
from pathlib import Path

from benchmark import (
    normalize_int_sequence,
    normalize_methods,
    parse_int_sequence,
    parse_methods,
    resolve_required_solver_paths,
)
from case_studies.column_bam import run_column_bam
from case_studies.column_case import LOWER_BOUNDS as COLUMN_LOWER_BOUNDS
from case_studies.column_case import UPPER_BOUNDS as COLUMN_UPPER_BOUNDS
from case_studies.column_dsda import run_column_dsda
from case_studies.column_rbfopt import run_column_rbfopt
from case_studies.common import generate_lhc_starting_points
from case_studies.cstr_bam import run_cstr_bam
from case_studies.cstr_case import LOWER_BOUNDS as CSTR_LOWER_BOUNDS
from case_studies.cstr_dsda import run_cstr_dsda
from case_studies.cstr_rbfopt import run_cstr_rbfopt
from case_studies.dynamic_bam import run_dynamic_bam
from case_studies.dynamic_case import LOWER_BOUNDS as DYNAMIC_LOWER_BOUNDS
from case_studies.dynamic_case import UPPER_BOUNDS as DYNAMIC_UPPER_BOUNDS
from case_studies.dynamic_dsda import run_dynamic_dsda
from case_studies.dynamic_rbfopt import run_dynamic_rbfopt
from case_studies.small_batch_bam import run_small_batch_bam
from case_studies.small_batch_case import LOWER_BOUNDS as SMALL_BATCH_LOWER_BOUNDS
from case_studies.small_batch_case import UPPER_BOUNDS as SMALL_BATCH_UPPER_BOUNDS
from case_studies.small_batch_dsda import run_small_batch_dsda
from case_studies.small_batch_rbfopt import run_small_batch_rbfopt
from instrumentation import RESULT_FIELDS, save_results_csv


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = BASE_DIR / "results" / "case_studies"
DEFAULT_CASES = ("column", "cstr", "small_batch", "dynamic")
DEFAULT_METHODS = ("dsda", "rbfopt", "bam")
DEFAULT_SEEDS = tuple(range(10))
DEFAULT_COLUMN_SEEDS = tuple(range(1, 10))
DEFAULT_COLUMN_BUDGETS = (16,)
DEFAULT_CSTR_GRID_SIZES = (5, 10, 15, 20, 25, 30)
DEFAULT_SMALL_BATCH_BUDGETS = (10,)
DEFAULT_DYNAMIC_BUDGETS = (12, 15, 20, 30, 37, 50)
SUPPORTED_CASES = DEFAULT_CASES
CSTR_BUDGET_FORMULA = "ceil(10 * grid_size / 7)"
MANIFEST_VERSION = 3
SOFTWARE_DISTRIBUTIONS = (
    "rbfopt-test",
    "rbfopt",
    "bam-solver",
    "numpy",
    "scipy",
    "pyomo",
)
METHOD_LABELS = {
    "dsda": "DSDA",
    "rbfopt": "RBFOpt",
    "bam": "BAM",
}
RESUME_PROVENANCE_FIELDS = (
    "source_files_sha256",
    "data_files_sha256",
    "initial_design",
)
CASE_CSV_NAMES = {
    "column": "compl_enum_column_17_baron.csv",
    "small_batch": "compl_enum_small_batch_baron.csv",
    "dynamic": "dynamic",
}
CASE_BOUNDS = {
    "column": (COLUMN_LOWER_BOUNDS, COLUMN_UPPER_BOUNDS),
    "small_batch": (SMALL_BATCH_LOWER_BOUNDS, SMALL_BATCH_UPPER_BOUNDS),
    "dynamic": (DYNAMIC_LOWER_BOUNDS, DYNAMIC_UPPER_BOUNDS),
}

CASE_RUNNERS = {
    "column": {
        "dsda": run_column_dsda,
        "rbfopt": run_column_rbfopt,
        "bam": run_column_bam,
    },
    "cstr": {
        "dsda": run_cstr_dsda,
        "rbfopt": run_cstr_rbfopt,
        "bam": run_cstr_bam,
    },
    "small_batch": {
        "dsda": run_small_batch_dsda,
        "rbfopt": run_small_batch_rbfopt,
        "bam": run_small_batch_bam,
    },
    "dynamic": {
        "dsda": run_dynamic_dsda,
        "rbfopt": run_dynamic_rbfopt,
        "bam": run_dynamic_bam,
    },
}


class RunTimeoutError(TimeoutError):
    """Raised when one process-case runner exceeds its configured deadline."""


def _duplicates(values):
    seen = set()
    duplicates = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _require_unique(values, name, error_type=ValueError):
    duplicates = _duplicates(values)
    if duplicates:
        duplicate_text = ", ".join(str(value) for value in duplicates)
        raise error_type(f"{name} must not contain duplicates: {duplicate_text}")
    return values


def parse_cases(value):
    """Parse and validate a comma-separated process case-study list."""
    cases = tuple(
        case.strip().lower().replace("-", "_") for case in str(value).split(",")
    )
    cases = tuple(case for case in cases if case)
    if not cases:
        raise argparse.ArgumentTypeError("At least one case study is required")

    invalid = sorted(set(cases).difference(SUPPORTED_CASES))
    if invalid:
        invalid_text = ", ".join(invalid)
        allowed_text = ", ".join(SUPPORTED_CASES)
        raise argparse.ArgumentTypeError(
            f"Unsupported case study/studies: {invalid_text}. Choose from: {allowed_text}"
        )
    _require_unique(cases, "cases", argparse.ArgumentTypeError)
    return cases


def normalize_cases(cases):
    """Normalize case studies supplied by the CLI or Python callers."""
    if isinstance(cases, str):
        return parse_cases(cases)
    return parse_cases(",".join(str(case) for case in cases))


def parse_unique_methods(value):
    """Parse methods and reject repeated entries that would duplicate runs."""
    methods = parse_methods(value)
    _require_unique(methods, "methods", argparse.ArgumentTypeError)
    return methods


def normalize_unique_methods(methods):
    """Normalize methods and reject repeated entries from Python callers."""
    if isinstance(methods, str):
        return parse_unique_methods(methods)
    normalized = normalize_methods(methods)
    return tuple(_require_unique(normalized, "methods"))


def normalize_unique_int_sequence(values, name, minimum=None):
    """Normalize an integer sequence and validate type, domain, and uniqueness."""
    normalized = normalize_int_sequence(values, name)
    invalid_types = [
        value
        for value in normalized
        if isinstance(value, bool) or not isinstance(value, Integral)
    ]
    if invalid_types:
        invalid_text = ", ".join(repr(value) for value in invalid_types)
        raise ValueError(f"{name} must contain only integers: {invalid_text}")
    normalized = [int(value) for value in normalized]
    if minimum is not None:
        invalid_values = [value for value in normalized if value < minimum]
        if invalid_values:
            domain = "nonnegative" if minimum == 0 else "positive"
            invalid_text = ", ".join(str(value) for value in invalid_values)
            raise ValueError(
                f"{name} must contain only {domain} integers: {invalid_text}"
            )
    return list(_require_unique(normalized, name))


def parse_unique_int_sequence(value):
    """Parse a CLI integer sequence and reject repeated values."""
    normalized = parse_int_sequence(value)
    return _require_unique(
        normalized,
        "integer sequence",
        argparse.ArgumentTypeError,
    )


def scaled_cstr_budget(grid_size):
    """Return the established CSTR budget scaled from 10 evaluations at size 7."""
    return math.ceil(10 * int(grid_size) / 7)


def case_study_output_path(output, now=None):
    """Return an explicit CSV path or a timestamped process-case result path."""
    output = Path(output)
    if output.suffix.lower() == ".csv":
        return output
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S_%f")
    return output / f"process_case_studies_{timestamp}.csv"


def case_study_manifest_path(output_path):
    """Return the reproducibility-manifest path paired with a result CSV."""
    output_path = Path(output_path)
    return output_path.with_suffix(".manifest.json")


def case_study_partial_path(output_path):
    """Return the checkpoint path used while a result CSV is incomplete."""
    output_path = Path(output_path)
    return output_path.with_name(f"{output_path.stem}.partial{output_path.suffix}")


def case_study_pending_path(partial_path):
    """Return the staged CSV path used to update a checkpoint pair safely."""
    partial_path = Path(partial_path)
    return partial_path.with_name(
        f"{partial_path.stem}.pending{partial_path.suffix}"
    )


def build_run_matrix(
    cases=DEFAULT_CASES,
    seeds=DEFAULT_SEEDS,
    column_seeds=DEFAULT_COLUMN_SEEDS,
    column_budgets=DEFAULT_COLUMN_BUDGETS,
    cstr_grid_sizes=DEFAULT_CSTR_GRID_SIZES,
    small_batch_budgets=DEFAULT_SMALL_BATCH_BUDGETS,
    dynamic_budgets=DEFAULT_DYNAMIC_BUDGETS,
):
    """Build reproducible case, seed, and evaluation-budget combinations."""
    cases = normalize_cases(cases)
    seeds = normalize_unique_int_sequence(seeds, "seeds", minimum=0)
    column_seeds = normalize_unique_int_sequence(
        column_seeds,
        "column_seeds",
        minimum=0,
    )
    column_budgets = normalize_unique_int_sequence(
        column_budgets,
        "column_budgets",
        minimum=1,
    )
    cstr_grid_sizes = normalize_unique_int_sequence(
        cstr_grid_sizes,
        "cstr_grid_sizes",
        minimum=1,
    )
    small_batch_budgets = normalize_unique_int_sequence(
        small_batch_budgets,
        "small_batch_budgets",
        minimum=1,
    )
    dynamic_budgets = normalize_unique_int_sequence(
        dynamic_budgets,
        "dynamic_budgets",
        minimum=1,
    )

    matrix = []
    if "column" in cases:
        for budget in column_budgets:
            for seed in column_seeds:
                matrix.append(
                    {"case_name": "column", "seed": seed, "max_evaluations": budget}
                )

    if "cstr" in cases:
        for grid_size in cstr_grid_sizes:
            for seed in seeds:
                matrix.append(
                    {
                        "case_name": "cstr",
                        "grid_size": grid_size,
                        "seed": seed,
                        "max_evaluations": scaled_cstr_budget(grid_size),
                    }
                )

    if "small_batch" in cases:
        for budget in small_batch_budgets:
            for seed in seeds:
                matrix.append(
                    {
                        "case_name": "small_batch",
                        "seed": seed,
                        "max_evaluations": budget,
                    }
                )

    if "dynamic" in cases:
        for budget in dynamic_budgets:
            for seed in seeds:
                matrix.append(
                    {"case_name": "dynamic", "seed": seed, "max_evaluations": budget}
                )
    return matrix


def _rbfopt_defaults(case_name):
    if case_name == "small_batch":
        return "Gutmann", "sampling"
    return "MSRSM", "solver"


def _case_csv_name(row):
    case_name = row["case_name"]
    if case_name == "cstr":
        return f"compl_enum_cstr_{row['grid_size']}_baron_hull.csv"
    return CASE_CSV_NAMES[case_name]


def _normalize_n_starts(n_starts):
    if isinstance(n_starts, bool) or not isinstance(n_starts, Integral):
        raise ValueError("n_starts must be a positive integer")
    normalized = int(n_starts)
    if normalized < 1:
        raise ValueError("n_starts must be a positive integer")
    return normalized


def _planned_run_keys(matrix, methods, n_starts):
    n_starts = _normalize_n_starts(n_starts)
    planned_runs = []
    for row in matrix:
        for method in methods:
            run_key = {
                "case_name": row["case_name"],
                "method": method,
                "csv_name": _case_csv_name(row),
                "seed": int(row["seed"]),
                "n_starts": int(n_starts),
                "max_evaluations": int(row["max_evaluations"]),
            }
            if row["case_name"] == "cstr":
                run_key["grid_size"] = int(row["grid_size"])
            planned_runs.append(run_key)

    canonical_keys = [
        json.dumps(run_key, sort_keys=True, separators=(",", ":"))
        for run_key in planned_runs
    ]
    if len(canonical_keys) != len(set(canonical_keys)):
        raise ValueError("Planned process-case run keys must be unique")
    return planned_runs


def _normalize_max_run_seconds(max_run_seconds):
    if max_run_seconds is None:
        return None
    if isinstance(max_run_seconds, bool):
        raise ValueError("max_run_seconds must be a positive finite number")
    try:
        normalized = float(max_run_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_run_seconds must be a positive finite number") from exc
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError("max_run_seconds must be a positive finite number")
    if os.name != "posix" or not all(
        hasattr(signal, name) for name in ("SIGALRM", "ITIMER_REAL")
    ):
        raise RuntimeError("max_run_seconds requires POSIX SIGALRM support")
    return normalized


@contextmanager
def _runner_deadline(max_run_seconds, run_key):
    if max_run_seconds is None:
        yield
        return
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("max_run_seconds can only be used from the main thread")

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_delay, previous_interval = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()

    def raise_timeout(_signum, _frame):
        raise RunTimeoutError(
            f"Runner exceeded max_run_seconds={max_run_seconds:g}: "
            f"{json.dumps(run_key, sort_keys=True)}"
        )

    signal.signal(signal.SIGALRM, raise_timeout)
    try:
        signal.setitimer(signal.ITIMER_REAL, max_run_seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_delay > 0 or previous_interval > 0:
            elapsed = time.monotonic() - started
            restored_delay = (
                max(1e-6, previous_delay - elapsed) if previous_delay > 0 else 0.0
            )
            signal.setitimer(
                signal.ITIMER_REAL,
                restored_delay,
                previous_interval,
            )


def _validate_matrix(matrix, n_starts):
    n_starts = _normalize_n_starts(n_starts)
    too_small = sorted(
        {row["max_evaluations"] for row in matrix if row["max_evaluations"] < n_starts}
    )
    if too_small:
        values = ", ".join(str(value) for value in too_small)
        raise ValueError(
            "Every evaluation budget must be at least n_starts so the shared "
            f"initial design fits; invalid budget(s): {values}"
        )
    return n_starts


def _atomic_save_results_csv(records, output_path):
    """Save records via a same-directory temporary file and atomic replace."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f".{output_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        save_results_csv(records, temporary_path)
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_save_json(value, output_path):
    """Save JSON via a same-directory temporary file and atomic replace."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f".{output_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_path(path):
    resolved_path = Path(path).resolve()
    try:
        return resolved_path.relative_to(BASE_DIR.resolve()).as_posix()
    except ValueError:
        return str(resolved_path)


def _hash_paths(paths):
    hashes = {}
    for path in sorted({Path(path).resolve() for path in paths}):
        hashes[_portable_path(path)] = _sha256_file(path) if path.is_file() else None
    return hashes


def _git_value(*arguments):
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=BASE_DIR,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _initial_design_hashes(matrix, n_starts):
    n_starts = _normalize_n_starts(n_starts)
    designs = []
    seen_keys = set()
    for row in matrix:
        design_key = (
            row["case_name"],
            row.get("grid_size"),
            int(row["seed"]),
            int(n_starts),
        )
        if design_key in seen_keys:
            continue
        seen_keys.add(design_key)

        case_name, grid_size, seed, design_size = design_key
        if case_name == "cstr":
            lower_bounds = CSTR_LOWER_BOUNDS
            upper_bounds = [grid_size, grid_size]
        else:
            lower_bounds, upper_bounds = CASE_BOUNDS[case_name]
        points = generate_lhc_starting_points(
            n_dims=len(lower_bounds),
            n_points=design_size,
            lb=lower_bounds,
            ub=upper_bounds,
            seed=seed,
        )
        canonical_points = json.dumps(
            [list(point) for point in points],
            separators=(",", ":"),
        ).encode("utf-8")
        design = {
            "case_name": case_name,
            "seed": seed,
            "n_starts": design_size,
            "sha256": hashlib.sha256(canonical_points).hexdigest(),
        }
        if grid_size is not None:
            design["grid_size"] = grid_size
        designs.append(design)
    return designs


def _provenance(matrix, cases, methods, n_starts):
    source_paths = {
        Path(__file__),
        BASE_DIR / "benchmark.py",
        BASE_DIR / "instrumentation.py",
        BASE_DIR / "case_studies" / "common.py",
    }
    for case_name in cases:
        source_paths.add(BASE_DIR / "case_studies" / f"{case_name}_case.py")
        for method in methods:
            source_paths.add(BASE_DIR / "case_studies" / f"{case_name}_{method}.py")
    if "dsda" in methods:
        source_paths.add(BASE_DIR / "grid_dsda.py")
    if {"rbfopt", "bam"}.intersection(methods):
        source_paths.add(BASE_DIR / "case_studies" / "bam_common.py")

    data_paths = set()
    for row in matrix:
        if row["case_name"] == "dynamic":
            continue
        data_paths.add(
            BASE_DIR / "case_study_data" / row["case_name"] / _case_csv_name(row)
        )

    dirty_output = _git_value("status", "--porcelain", "--untracked-files=no")
    return {
        "git": {
            "commit": _git_value("rev-parse", "HEAD"),
            "branch": _git_value("rev-parse", "--abbrev-ref", "HEAD"),
            "tracked_worktree_dirty": bool(dirty_output)
            if dirty_output is not None
            else None,
        },
        "source_files_sha256": _hash_paths(source_paths),
        "data_files_sha256": _hash_paths(data_paths),
        "initial_design": {
            "strategy": (
                "seeded Latin hypercube sampling with deterministic "
                "rounded-lattice duplicate repair"
            ),
            "n_starts": int(n_starts),
            "same_seed_and_design_reused_across_methods": True,
            "designs": _initial_design_hashes(matrix, n_starts),
        },
    }


def _ordered_unique(values):
    return list(dict.fromkeys(values))


def _case_protocol(matrix, cases):
    protocol = {}
    for case_name in _ordered_unique(cases):
        rows = [row for row in matrix if row["case_name"] == case_name]
        parameters = {
            "seeds": _ordered_unique(row["seed"] for row in rows),
            "max_evaluation_budgets": _ordered_unique(
                row["max_evaluations"] for row in rows
            ),
        }
        if case_name == "cstr":
            parameters["grid_sizes"] = _ordered_unique(row["grid_size"] for row in rows)
            parameters["budget_scaling"] = {
                "formula": CSTR_BUDGET_FORMULA,
                "grid_size_to_max_evaluations": [
                    {
                        "grid_size": grid_size,
                        "max_evaluations": scaled_cstr_budget(grid_size),
                    }
                    for grid_size in parameters["grid_sizes"]
                ],
            }
        protocol[case_name] = parameters
    return protocol


def _software_versions():
    versions = {}
    for distribution in SOFTWARE_DISTRIBUTIONS:
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = None
    return {
        "python": platform.python_version(),
        "platform": {
            "machine": platform.machine(),
            "system": platform.system(),
            "release": platform.release(),
        },
        "distributions": versions,
    }


def _result_schema():
    return {
        "name": "unified_benchmark_result",
        "fields": list(RESULT_FIELDS),
        "structured_value_encoding": "JSON strings in CSV cells",
    }


def _executable_identity(path):
    if not path:
        return None
    executable_path = Path(path)
    try:
        is_file = executable_path.is_file()
    except OSError:
        return None
    if not is_file:
        return None
    try:
        return {
            "basename": executable_path.name,
            "sha256": _sha256_file(executable_path),
        }
    except OSError:
        return None


def _method_configuration(
    cases,
    methods,
    algorithm,
    rbf,
    global_search_method,
    diagonal,
    tie_break,
    minlp_solver_path,
    nlp_solver_path,
    bam_license_file,
    rbfopt_module,
    bam_module,
):
    configuration = {}
    if "dsda" in methods:
        configuration["dsda"] = {
            "diagonal": diagonal,
            "tie_break": tie_break,
        }
    if "rbfopt" in methods:
        solver_identities = {"minlp": None, "nlp": None}
        if rbfopt_module is None:
            solver_identities = {
                "minlp": _executable_identity(minlp_solver_path),
                "nlp": _executable_identity(nlp_solver_path),
            }
        configuration["rbfopt"] = {
            "rbf": rbf,
            "effective_case_settings": {
                case_name: {
                    "algorithm": algorithm or _rbfopt_defaults(case_name)[0],
                    "global_search_method": (
                        global_search_method or _rbfopt_defaults(case_name)[1]
                    ),
                }
                for case_name in _ordered_unique(cases)
            },
            "external_solver_executables_configured": bool(
                minlp_solver_path and nlp_solver_path
            ),
            "external_solver_executables": solver_identities,
            "module_injected": rbfopt_module is not None,
        }
    if "bam" in methods:
        configuration["bam"] = {
            "license_configured": bool(bam_license_file),
            "module_injected": bam_module is not None,
        }
    return configuration


def _build_protocol(
    *,
    matrix,
    cases,
    methods,
    n_starts,
    planned_run_keys,
    algorithm,
    rbf,
    global_search_method,
    diagonal,
    tie_break,
    minlp_solver_path,
    nlp_solver_path,
    bam_license_file,
    rbfopt_module,
    bam_module,
):
    plan_json = json.dumps(
        planned_run_keys,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "cases": list(cases),
        "methods": list(methods),
        "n_starts": int(n_starts),
        "case_parameters": _case_protocol(matrix, cases),
        "method_configuration": _method_configuration(
            cases=cases,
            methods=methods,
            algorithm=algorithm,
            rbf=rbf,
            global_search_method=global_search_method,
            diagonal=diagonal,
            tie_break=tie_break,
            minlp_solver_path=minlp_solver_path,
            nlp_solver_path=nlp_solver_path,
            bam_license_file=bam_license_file,
            rbfopt_module=rbfopt_module,
            bam_module=bam_module,
        ),
        "planned_run_keys": planned_run_keys,
        "planned_run_keys_sha256": hashlib.sha256(plan_json).hexdigest(),
    }


def _execution_attempt(
    *,
    resume_count,
    completed_rows_before_attempt,
    max_run_seconds,
    verbose,
    started_at_utc=None,
):
    """Record execution-only settings for one initial or resumed invocation."""
    return {
        "attempt": int(resume_count),
        "started_at_utc": started_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "completed_rows_before_attempt": int(completed_rows_before_attempt),
        "max_run_seconds": max_run_seconds,
        "verbose": bool(verbose),
    }


def _build_manifest(
    *,
    output_path,
    artifact_path=None,
    status="completed",
    matrix,
    planned_run_keys,
    protocol,
    records,
    started_at,
    resume_count,
    execution_context_history,
    failed_run,
    software,
    provenance,
):
    if status not in {"running", "failed", "completed"}:
        raise ValueError(f"Unsupported manifest status: {status}")
    completed_at = (
        datetime.now(timezone.utc).isoformat() if status == "completed" else None
    )
    artifact_path = Path(artifact_path or output_path)
    manifest_path = case_study_manifest_path(output_path)
    execution_context_history = [
        dict(attempt) for attempt in execution_context_history
    ]
    if not execution_context_history:
        raise ValueError("Execution context history must not be empty")
    return {
        "manifest_version": MANIFEST_VERSION,
        "schema": _result_schema(),
        "protocol": protocol,
        "run": {
            "status": status,
            "started_at_utc": started_at,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "completed_at_utc": completed_at,
            "expected_configurations": len(matrix),
            "expected_rows": len(planned_run_keys),
            "completed_rows": len(records),
            "completed_run_keys": planned_run_keys[: len(records)],
            "resume_count": resume_count,
            "execution_context": execution_context_history[-1],
            "execution_context_history": execution_context_history,
            "failed_run": failed_run,
        },
        "software": software,
        "provenance": provenance,
        "output": {
            "csv_path": _portable_path(output_path),
            "manifest_path": _portable_path(manifest_path),
            "current_csv_path": _portable_path(artifact_path),
            "csv_bytes": artifact_path.stat().st_size,
            "csv_sha256": _sha256_file(artifact_path),
        },
    }


def _save_checkpoint(
    *,
    partial_path,
    partial_manifest_path,
    manifest_context,
    status,
    records,
    failed_run,
):
    """Replace a CSV/manifest checkpoint pair through recoverable staged files."""
    pending_path = case_study_pending_path(partial_path)
    pending_manifest_path = case_study_manifest_path(pending_path)

    _atomic_save_results_csv(records, pending_path)
    manifest = _build_manifest(
        **manifest_context,
        artifact_path=pending_path,
        status=status,
        records=records,
        failed_run=failed_run,
    )
    manifest["output"]["current_csv_path"] = _portable_path(partial_path)
    _atomic_save_json(manifest, pending_manifest_path)
    os.replace(pending_path, partial_path)
    os.replace(pending_manifest_path, partial_manifest_path)
    return manifest


def _validate_record_matches_run_key(record, run_key, row_number):
    expected_values = {
        "csv_name": run_key["csv_name"],
        "method": METHOD_LABELS[run_key["method"]],
        "seed": run_key["seed"],
        "n_starts": run_key["n_starts"],
        "max_evals": run_key["max_evaluations"],
    }
    for field, expected in expected_values.items():
        if field not in record:
            raise ValueError(
                f"Result row {row_number} is missing identity field {field}"
            )
        actual = record[field]
        if field in {"seed", "n_starts", "max_evals"}:
            try:
                actual = int(actual)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Result row {row_number} has invalid {field}: {actual!r}"
                ) from exc
        if actual != expected:
            raise ValueError(
                f"Result row {row_number} does not match the planned run key: "
                f"{field}={actual!r}, expected {expected!r}"
            )


def _deserialize_result_record(record):
    deserialized = dict(record)
    for field in ("best_point", "incumbent_trajectory"):
        deserialized[field] = json.loads(record[field])
    for field in (
        "seed",
        "n_starts",
        "max_evals",
        "total_evals",
        "initial_evals",
        "adaptive_evals",
        "unique_evals",
        "solver_evalcount",
        "solver_iterations",
    ):
        deserialized[field] = int(record[field]) if record[field] != "" else None
    for field in ("best_value", "wall_time_s"):
        deserialized[field] = float(record[field]) if record[field] != "" else None
    found_optimum = record["found_optimum"]
    if found_optimum not in {"True", "False"}:
        raise ValueError(
            f"Invalid found_optimum value in checkpoint: {found_optimum!r}"
        )
    deserialized["found_optimum"] = found_optimum == "True"
    if record["solver_status"] == "":
        deserialized["solver_status"] = None
    return deserialized


def _read_checkpoint_csv(partial_path, planned_run_keys):
    with Path(partial_path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != RESULT_FIELDS:
            raise ValueError("Checkpoint CSV schema does not match RESULT_FIELDS")
        raw_records = list(reader)
    if len(raw_records) > len(planned_run_keys):
        raise ValueError("Checkpoint CSV has more rows than the planned run count")
    for row_number, (record, run_key) in enumerate(
        zip(raw_records, planned_run_keys),
        start=1,
    ):
        _validate_record_matches_run_key(record, run_key, row_number)
    return [_deserialize_result_record(record) for record in raw_records]


def _load_json(path, label):
    try:
        with Path(path).open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _validate_resume_checkpoint(
    *,
    partial_path,
    partial_manifest_path,
    expected_protocol,
    expected_software,
    expected_provenance,
    planned_run_keys,
    expected_configurations,
):
    manifest = _load_json(partial_manifest_path, "checkpoint manifest")
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError("Checkpoint manifest version does not match")
    if manifest.get("schema") != _result_schema():
        raise ValueError("Checkpoint manifest schema does not match")
    if manifest.get("protocol") != expected_protocol:
        raise ValueError("Checkpoint manifest protocol does not match this run")
    if manifest.get("software") != expected_software:
        raise ValueError("Checkpoint software versions do not match this run")
    checkpoint_provenance = manifest.get("provenance")
    if not isinstance(checkpoint_provenance, dict):
        raise ValueError("Checkpoint manifest is missing provenance")
    for field in RESUME_PROVENANCE_FIELDS:
        if checkpoint_provenance.get(field) != expected_provenance.get(field):
            raise ValueError(f"Checkpoint provenance {field} does not match this run")

    run_state = manifest.get("run")
    if not isinstance(run_state, dict):
        raise ValueError("Checkpoint manifest is missing run state")
    checkpoint_status = run_state.get("status")
    if checkpoint_status not in {"running", "failed", "completed"}:
        raise ValueError("Checkpoint manifest is not resumable")
    if run_state.get("expected_configurations") != expected_configurations:
        raise ValueError("Checkpoint expected configuration count does not match")
    if run_state.get("expected_rows") != len(planned_run_keys):
        raise ValueError("Checkpoint expected row count does not match")

    output_state = manifest.get("output")
    if not isinstance(output_state, dict):
        raise ValueError("Checkpoint manifest is missing output state")
    if output_state.get("csv_bytes") != Path(partial_path).stat().st_size:
        raise ValueError("Checkpoint CSV size does not match its manifest")
    if output_state.get("csv_sha256") != _sha256_file(partial_path):
        raise ValueError("Checkpoint CSV checksum does not match its manifest")

    records = _read_checkpoint_csv(partial_path, planned_run_keys)
    completed_rows = run_state.get("completed_rows")
    if completed_rows != len(records):
        raise ValueError("Checkpoint completed row count does not match its CSV")
    if checkpoint_status == "completed" and completed_rows != len(planned_run_keys):
        raise ValueError("Completed checkpoint does not contain every planned run")
    expected_prefix = planned_run_keys[: len(records)]
    if run_state.get("completed_run_keys") != expected_prefix:
        raise ValueError("Checkpoint completed run keys are not the planned prefix")
    started_at = run_state.get("started_at_utc")
    if not isinstance(started_at, str) or not started_at:
        raise ValueError("Checkpoint manifest has no valid start timestamp")
    resume_count = run_state.get("resume_count")
    if not isinstance(resume_count, int) or resume_count < 0:
        raise ValueError("Checkpoint manifest has an invalid resume count")
    execution_context_history = run_state.get("execution_context_history")
    if (
        not isinstance(execution_context_history, list)
        or len(execution_context_history) != resume_count + 1
        or not all(isinstance(attempt, dict) for attempt in execution_context_history)
    ):
        raise ValueError("Checkpoint manifest has invalid execution context history")
    if execution_context_history[-1].get("attempt") != resume_count:
        raise ValueError("Checkpoint execution context history is out of order")
    return records, manifest


def _load_resume_checkpoint(
    *,
    partial_path,
    partial_manifest_path,
    expected_protocol,
    expected_software,
    expected_provenance,
    planned_run_keys,
    expected_configurations,
    output_path=None,
):
    """Load the newest valid checkpoint generation and promote staged files."""
    partial_path = Path(partial_path)
    partial_manifest_path = Path(partial_manifest_path)
    pending_path = case_study_pending_path(partial_path)
    pending_manifest_path = case_study_manifest_path(pending_path)
    candidates = [
        (partial_path, partial_manifest_path, 1),
        (partial_path, pending_manifest_path, 0),
        (pending_path, pending_manifest_path, 0),
    ]
    if output_path is not None:
        candidates.append((Path(output_path), partial_manifest_path, 0))
    valid_candidates = []
    errors = []
    seen_pairs = set()

    for csv_path, manifest_path, stable_preference in candidates:
        pair = (csv_path, manifest_path)
        if pair in seen_pairs or not csv_path.is_file() or not manifest_path.is_file():
            continue
        seen_pairs.add(pair)
        try:
            records, manifest = _validate_resume_checkpoint(
                partial_path=csv_path,
                partial_manifest_path=manifest_path,
                expected_protocol=expected_protocol,
                expected_software=expected_software,
                expected_provenance=expected_provenance,
                planned_run_keys=planned_run_keys,
                expected_configurations=expected_configurations,
            )
        except (OSError, ValueError) as error:
            errors.append(error)
            continue
        valid_candidates.append(
            (
                len(records),
                stable_preference,
                csv_path,
                manifest_path,
                records,
                manifest,
            )
        )

    if not valid_candidates:
        if errors:
            raise errors[0]
        raise FileNotFoundError("No valid process-case checkpoint pair was found")

    _, _, csv_path, manifest_path, records, manifest = max(
        valid_candidates,
        key=lambda candidate: (candidate[0], candidate[1]),
    )
    if csv_path != partial_path:
        os.replace(csv_path, partial_path)
    if manifest_path != partial_manifest_path:
        os.replace(manifest_path, partial_manifest_path)
    pending_path.unlink(missing_ok=True)
    pending_manifest_path.unlink(missing_ok=True)
    return records, manifest


def _redacted_exception_message(exception, bam_license_file):
    message = str(exception)
    if bam_license_file:
        sensitive_path = str(bam_license_file)
        message = message.replace(sensitive_path, "<redacted>")
        try:
            resolved_path = str(Path(bam_license_file).resolve())
        except OSError:
            resolved_path = sensitive_path
        message = message.replace(resolved_path, "<redacted>")
    return message


def _prepare_external_dependencies(
    matrix,
    methods,
    solver_dir,
    minlp_solver_path,
    nlp_solver_path,
    global_search_method,
    bam_license_file,
    rbfopt_module,
    bam_module,
):
    if "rbfopt" in methods and rbfopt_module is None:
        needs_solver = any(
            (global_search_method or _rbfopt_defaults(row["case_name"])[1]) == "solver"
            for row in matrix
        )
        if needs_solver:
            minlp_solver_path, nlp_solver_path = resolve_required_solver_paths(
                solver_dir=solver_dir,
                minlp_solver_path=minlp_solver_path,
                nlp_solver_path=nlp_solver_path,
            )

    if "bam" in methods and bam_module is None:
        includes_small_batch = any(row["case_name"] == "small_batch" for row in matrix)
        if includes_small_batch:
            bam_license_file = bam_license_file or os.environ.get(
                "BAM_LICENSE_FILE", ""
            )
            if not bam_license_file or not Path(bam_license_file).is_file():
                raise FileNotFoundError(
                    "The three-dimensional small-batch BAM study requires a "
                    "license file. Set BAM_LICENSE_FILE, pass --bam-license-file, "
                    "or omit small_batch/BAM."
                )

    return minlp_solver_path, nlp_solver_path, bam_license_file


def run_case_study_benchmark(
    cases=DEFAULT_CASES,
    methods=DEFAULT_METHODS,
    seeds=DEFAULT_SEEDS,
    column_seeds=DEFAULT_COLUMN_SEEDS,
    column_budgets=DEFAULT_COLUMN_BUDGETS,
    cstr_grid_sizes=DEFAULT_CSTR_GRID_SIZES,
    small_batch_budgets=DEFAULT_SMALL_BATCH_BUDGETS,
    dynamic_budgets=DEFAULT_DYNAMIC_BUDGETS,
    n_starts=3,
    output=DEFAULT_RESULTS_DIR,
    solver_dir=None,
    minlp_solver_path="",
    nlp_solver_path="",
    algorithm=None,
    rbf="auto",
    global_search_method=None,
    diagonal=True,
    tie_break="first",
    verbose=False,
    rbfopt_module=None,
    bam_license_file=None,
    bam_module=None,
    runners=None,
    resume=False,
    overwrite=False,
    max_run_seconds=None,
):
    """Run or resume the matrix and save an audited CSV plus JSON manifest.

    Completed rows are atomically checkpointed to ``*.partial.csv``. Resume
    validates the manifest, protocol, source/data provenance, checksum, schema,
    and completed run-key prefix before skipping previously completed rows.
    """
    cases = normalize_cases(cases)
    methods = normalize_unique_methods(methods)
    max_run_seconds = _normalize_max_run_seconds(max_run_seconds)
    matrix = build_run_matrix(
        cases=cases,
        seeds=seeds,
        column_seeds=column_seeds,
        column_budgets=column_budgets,
        cstr_grid_sizes=cstr_grid_sizes,
        small_batch_budgets=small_batch_budgets,
        dynamic_budgets=dynamic_budgets,
    )
    n_starts = _validate_matrix(matrix, n_starts)
    planned_run_keys = _planned_run_keys(matrix, methods, n_starts)

    raw_output = Path(output)
    if resume and raw_output.suffix.lower() != ".csv":
        raise ValueError("resume requires an explicit CSV output path")
    output_path = case_study_output_path(output)
    manifest_path = case_study_manifest_path(output_path)
    partial_path = case_study_partial_path(output_path)
    partial_manifest_path = case_study_manifest_path(partial_path)
    pending_path = case_study_pending_path(partial_path)
    pending_manifest_path = case_study_manifest_path(pending_path)
    finalization_recovery_candidate = (
        resume
        and output_path.is_file()
        and not partial_path.exists()
        and partial_manifest_path.is_file()
    )
    if finalization_recovery_candidate:
        recovery_manifest = _load_json(
            partial_manifest_path,
            "finalization recovery manifest",
        )
        recovery_run = recovery_manifest.get("run")
        finalization_recovery_candidate = (
            isinstance(recovery_run, dict)
            and recovery_run.get("status") == "completed"
        )
    existing_final_paths = [
        path for path in (output_path, manifest_path) if path.exists()
    ]
    recover_without_overwrite = (
        finalization_recovery_candidate and not manifest_path.exists()
    )
    if existing_final_paths and not overwrite and not recover_without_overwrite:
        existing_text = ", ".join(str(path) for path in existing_final_paths)
        raise FileExistsError(
            f"Completed output already exists: {existing_text}. "
            "Pass overwrite=True or --overwrite to replace it after a successful run."
        )
    partial_exists = partial_path.exists()
    partial_manifest_exists = partial_manifest_path.exists()
    if resume:
        resumable_pair_exists = (
            (partial_exists and partial_manifest_exists)
            or (partial_exists and pending_manifest_path.exists())
            or (pending_path.exists() and pending_manifest_path.exists())
            or finalization_recovery_candidate
        )
        if not resumable_pair_exists:
            raise FileNotFoundError(
                "resume requires both checkpoint files or a complete staged "
                f"checkpoint pair for {partial_path}"
            )
    elif partial_exists or partial_manifest_exists or pending_manifest_path.exists():
        raise FileExistsError(
            "An incomplete process-case checkpoint already exists. "
            "Pass resume=True or --resume with the same explicit CSV output path."
        )

    minlp_solver_path, nlp_solver_path, bam_license_file = (
        _prepare_external_dependencies(
            matrix=matrix,
            methods=methods,
            solver_dir=solver_dir,
            minlp_solver_path=minlp_solver_path,
            nlp_solver_path=nlp_solver_path,
            global_search_method=global_search_method,
            bam_license_file=bam_license_file,
            rbfopt_module=rbfopt_module,
            bam_module=bam_module,
        )
    )

    runners = runners or CASE_RUNNERS
    software = _software_versions()
    provenance = _provenance(matrix, cases, methods, n_starts)
    protocol_context = {
        "matrix": matrix,
        "cases": cases,
        "methods": methods,
        "n_starts": n_starts,
        "planned_run_keys": planned_run_keys,
        "algorithm": algorithm,
        "rbf": rbf,
        "global_search_method": global_search_method,
        "diagonal": diagonal,
        "tie_break": tie_break,
        "minlp_solver_path": minlp_solver_path,
        "nlp_solver_path": nlp_solver_path,
        "bam_license_file": bam_license_file,
        "rbfopt_module": rbfopt_module,
        "bam_module": bam_module,
    }
    expected_protocol = _build_protocol(**protocol_context)

    if resume:
        records, checkpoint_manifest = _load_resume_checkpoint(
            partial_path=partial_path,
            partial_manifest_path=partial_manifest_path,
            expected_protocol=expected_protocol,
            expected_software=software,
            expected_provenance=provenance,
            planned_run_keys=planned_run_keys,
            expected_configurations=len(matrix),
            output_path=output_path,
        )
        started_at = checkpoint_manifest["run"]["started_at_utc"]
        resume_count = checkpoint_manifest["run"]["resume_count"] + 1
        execution_context_history = list(
            checkpoint_manifest["run"]["execution_context_history"]
        )
        attempt_started_at = datetime.now(timezone.utc).isoformat()
    else:
        records = []
        started_at = datetime.now(timezone.utc).isoformat()
        resume_count = 0
        execution_context_history = []
        attempt_started_at = started_at

    execution_context_history.append(
        _execution_attempt(
            resume_count=resume_count,
            completed_rows_before_attempt=len(records),
            max_run_seconds=max_run_seconds,
            verbose=verbose,
            started_at_utc=attempt_started_at,
        )
    )

    manifest_context = {
        "output_path": output_path,
        "matrix": matrix,
        "planned_run_keys": planned_run_keys,
        "protocol": expected_protocol,
        "started_at": started_at,
        "resume_count": resume_count,
        "execution_context_history": execution_context_history,
        "software": software,
        "provenance": provenance,
    }
    _save_checkpoint(
        partial_path=partial_path,
        partial_manifest_path=partial_manifest_path,
        manifest_context=manifest_context,
        status="running",
        records=records,
        failed_run=None,
    )

    run_index = 0
    for row in matrix:
        case_name = row["case_name"]
        base_kwargs = {key: value for key, value in row.items() if key != "case_name"}
        base_kwargs["n_starts"] = n_starts
        for method in methods:
            current_run_key = planned_run_keys[run_index]
            if run_index < len(records):
                run_index += 1
                continue
            kwargs = dict(base_kwargs)
            if method == "dsda":
                kwargs.update(
                    diagonal=diagonal,
                    tie_break=tie_break,
                    verbose=verbose,
                )
            elif method == "rbfopt":
                default_algorithm, default_global_search = _rbfopt_defaults(case_name)
                kwargs.update(
                    solver_dir=solver_dir,
                    minlp_solver_path=minlp_solver_path,
                    nlp_solver_path=nlp_solver_path,
                    algorithm=algorithm or default_algorithm,
                    rbf=rbf,
                    global_search_method=(
                        global_search_method or default_global_search
                    ),
                    rbfopt_module=rbfopt_module,
                    verbose=verbose,
                )
            else:
                kwargs.update(
                    bam_license_file=bam_license_file,
                    bam_module=bam_module,
                    verbose=verbose,
                )

            try:
                with _runner_deadline(max_run_seconds, current_run_key):
                    result = runners[case_name][method](**kwargs)
                result_record = result["result_record"]
                _validate_record_matches_run_key(
                    result_record,
                    current_run_key,
                    run_index + 1,
                )
                candidate_records = [*records, result_record]
                _save_checkpoint(
                    partial_path=partial_path,
                    partial_manifest_path=partial_manifest_path,
                    manifest_context=manifest_context,
                    status="running",
                    records=candidate_records,
                    failed_run=None,
                )
                records = candidate_records
            except BaseException as exception:
                failed_run = {
                    "run_key": current_run_key,
                    "exception_type": type(exception).__name__,
                    "message": _redacted_exception_message(
                        exception,
                        bam_license_file,
                    ),
                }
                try:
                    checkpoint_records, _ = _load_resume_checkpoint(
                        partial_path=partial_path,
                        partial_manifest_path=partial_manifest_path,
                        expected_protocol=expected_protocol,
                        expected_software=software,
                        expected_provenance=provenance,
                        planned_run_keys=planned_run_keys,
                        expected_configurations=len(matrix),
                        output_path=output_path,
                    )
                    _save_checkpoint(
                        partial_path=partial_path,
                        partial_manifest_path=partial_manifest_path,
                        manifest_context=manifest_context,
                        status="failed",
                        records=checkpoint_records,
                        failed_run=failed_run,
                    )
                except Exception:
                    pass
                raise
            run_index += 1

    if len(records) != len(planned_run_keys):
        raise RuntimeError(
            f"Expected {len(planned_run_keys)} result rows, but completed "
            f"{len(records)}"
        )

    manifest = _build_manifest(
        **manifest_context,
        artifact_path=partial_path,
        records=records,
        failed_run=None,
    )
    manifest["output"]["current_csv_path"] = _portable_path(output_path)
    _atomic_save_json(manifest, partial_manifest_path)
    os.replace(partial_path, output_path)
    os.replace(partial_manifest_path, manifest_path)
    pending_path.unlink(missing_ok=True)
    pending_manifest_path.unlink(missing_ok=True)
    return records, output_path


def build_parser():
    """Build the process case-study benchmark command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=parse_cases, default=DEFAULT_CASES)
    parser.add_argument(
        "--methods",
        type=parse_unique_methods,
        default=DEFAULT_METHODS,
    )
    parser.add_argument(
        "--seeds",
        type=parse_unique_int_sequence,
        default=DEFAULT_SEEDS,
    )
    parser.add_argument(
        "--column-seeds",
        type=parse_unique_int_sequence,
        default=DEFAULT_COLUMN_SEEDS,
        help="Column defaults to 1-9 because seed 0 has no feasible DSDA start.",
    )
    parser.add_argument(
        "--column-budgets",
        type=parse_unique_int_sequence,
        default=DEFAULT_COLUMN_BUDGETS,
    )
    parser.add_argument(
        "--cstr-grid-sizes",
        type=parse_unique_int_sequence,
        default=DEFAULT_CSTR_GRID_SIZES,
    )
    parser.add_argument(
        "--small-batch-budgets",
        type=parse_unique_int_sequence,
        default=DEFAULT_SMALL_BATCH_BUDGETS,
    )
    parser.add_argument(
        "--dynamic-budgets",
        type=parse_unique_int_sequence,
        default=DEFAULT_DYNAMIC_BUDGETS,
    )
    parser.add_argument("--n-starts", type=int, default=3)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Output directory or explicit CSV path.",
    )
    parser.add_argument("--solver-dir", default=None)
    parser.add_argument("--minlp-solver-path", default="")
    parser.add_argument("--nlp-solver-path", default="")
    parser.add_argument("--algorithm", default=None)
    parser.add_argument("--rbf", default="auto")
    parser.add_argument(
        "--global-search-method",
        default=None,
        help="Override case defaults (solver, except sampling for small-batch).",
    )
    parser.add_argument(
        "--bam-license-file",
        default=os.environ.get("BAM_LICENSE_FILE", ""),
    )
    parser.add_argument("--tie-break", default="first")
    parser.add_argument(
        "--max-run-seconds",
        type=float,
        default=None,
        help=(
            "Best-effort POSIX wall-clock deadline applied separately to each runner."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Strictly validate and continue an existing partial checkpoint.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow successful completion to replace an existing final output.",
    )
    parser.add_argument("--no-diagonal", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv=None, rbfopt_module=None, bam_module=None, runners=None):
    """CLI entry point for the process case-study benchmark matrix."""
    args = build_parser().parse_args(argv)
    records, output_path = run_case_study_benchmark(
        cases=args.cases,
        methods=args.methods,
        seeds=args.seeds,
        column_seeds=args.column_seeds,
        column_budgets=args.column_budgets,
        cstr_grid_sizes=args.cstr_grid_sizes,
        small_batch_budgets=args.small_batch_budgets,
        dynamic_budgets=args.dynamic_budgets,
        n_starts=args.n_starts,
        output=args.output,
        solver_dir=args.solver_dir,
        minlp_solver_path=args.minlp_solver_path,
        nlp_solver_path=args.nlp_solver_path,
        algorithm=args.algorithm,
        rbf=args.rbf,
        global_search_method=args.global_search_method,
        diagonal=not args.no_diagonal,
        tie_break=args.tie_break,
        verbose=args.verbose,
        rbfopt_module=rbfopt_module,
        bam_license_file=args.bam_license_file,
        bam_module=bam_module,
        runners=runners,
        resume=args.resume,
        overwrite=args.overwrite,
        max_run_seconds=args.max_run_seconds,
    )
    print(f"Process case-study benchmark completed: {len(records)} runs")
    print(f"Results saved in: {output_path}")
    print(f"Manifest saved in: {case_study_manifest_path(output_path)}")
    return records, output_path


if __name__ == "__main__":
    main()
