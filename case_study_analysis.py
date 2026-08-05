"""Analysis and static figures for process case-study benchmark results.

This module consumes the unified audited CSV written by
``case_study_benchmark.py``.  Unlike ``benchmark_analysis.py``, it obtains
known optima directly from the four process case-study definitions and never
looks for metadata in ``benchmark_grids``.
"""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from benchmark_analysis import (
    METHOD_COLORS,
    METHOD_ORDER,
    configure_plot_style,
    ordered_method_names,
    runs_to_target_probability,
)
from case_studies.column_case import (
    COLUMN_CSV_NAME,
    KNOWN_BEST_VALUE as COLUMN_OPTIMUM,
)
from case_studies.cstr_case import load_cstr_case_data
from case_studies.dynamic_case import KNOWN_BEST_VALUE as DYNAMIC_OPTIMUM
from case_studies.small_batch_case import (
    KNOWN_BEST_VALUE as SMALL_BATCH_OPTIMUM,
    SMALL_BATCH_CSV_NAME,
)
from instrumentation import RESULT_FIELDS


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = BASE_DIR / "results" / "case_studies"
DEFAULT_OUTPUT_DIR = DEFAULT_RESULTS_DIR / "analysis"
DEFAULT_TARGET_PROBABILITY = 0.99

EXPECTED_RESULT_SCHEMA = {
    "name": "unified_benchmark_result",
    "fields": list(RESULT_FIELDS),
    "structured_value_encoding": "JSON strings in CSV cells",
}

CASE_ORDER = ("column", "cstr", "small_batch", "dynamic")
CASE_DISPLAY_NAMES = {
    "column": "Column",
    "cstr": "CSTR",
    "small_batch": "Small batch",
    "dynamic": "Dynamic",
}

_CSTR_NAME = re.compile(r"^compl_enum_cstr_(?P<grid_size>[1-9][0-9]*)_baron_hull\.csv$")
_REQUIRED_INTEGER_COLUMNS = ("seed", "n_starts", "max_evals", "total_evals")
_OPTIONAL_INTEGER_COLUMNS = (
    "initial_evals",
    "adaptive_evals",
    "unique_evals",
    "solver_evalcount",
    "solver_iterations",
)
_NONNEGATIVE_COLUMNS = (
    "seed",
    "n_starts",
    "max_evals",
    "total_evals",
    "wall_time_s",
    *_OPTIONAL_INTEGER_COLUMNS,
)
_RUN_ID_COLUMNS = ("csv_name", "method", "seed", "n_starts", "max_evals")
_SUMMARY_GROUP_COLUMNS = (
    "case_name",
    "problem_label",
    "csv_name",
    "cstr_grid_size",
    "target_value",
    "method",
    "n_starts",
    "max_evals",
)


def _pyplot():
    import matplotlib.pyplot as plt

    return plt


def find_latest_case_study_results_csv(results_csv=None, results_dir=None):
    """Return an explicit CSV or the newest aggregate process-study CSV."""
    if results_csv is not None:
        path = Path(results_csv)
        if not path.is_file():
            raise FileNotFoundError(f"Case-study results CSV does not exist: {path}")
        return path

    results_dir = Path(results_dir or DEFAULT_RESULTS_DIR)
    candidates = [
        path
        for path in results_dir.glob("process_case_studies_*.csv")
        if not path.name.endswith((".partial.csv", ".partial.pending.csv"))
    ]
    if not candidates:
        raise FileNotFoundError(
            "No aggregate process case-study CSV found. Run "
            "case_study_benchmark.py first or pass --results-csv explicitly."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def case_study_manifest_path(results_csv):
    """Return the completed-run manifest path paired with a results CSV."""
    return Path(results_csv).with_suffix(".manifest.json")


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_case_study_manifest(results_csv, row_count):
    """Validate a paired completed manifest or describe a legacy input.

    Aggregate files created before manifests were introduced remain readable,
    but callers receive an explicit warning through the returned audit record.
    Once a paired manifest exists, a mismatch is an integrity error rather than
    a condition that can be silently ignored.
    """
    results_csv = Path(results_csv)
    manifest_path = case_study_manifest_path(results_csv)
    if not manifest_path.is_file():
        return {
            "verified": False,
            "manifest_path": manifest_path,
            "warning": (
                "No paired manifest was found; treating this as a legacy, "
                "unverified case-study CSV."
            ),
        }

    try:
        with manifest_path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Case-study manifest is not valid JSON: {manifest_path}"
        ) from error
    if not isinstance(manifest, dict):
        raise ValueError("Case-study manifest must contain a JSON object")
    if manifest.get("schema") != EXPECTED_RESULT_SCHEMA:
        raise ValueError("Case-study manifest schema does not match RESULT_FIELDS")

    run_state = manifest.get("run")
    if not isinstance(run_state, dict):
        raise ValueError("Case-study manifest is missing run metadata")
    if run_state.get("status") != "completed":
        raise ValueError("Case-study manifest status must be completed")
    for field in ("expected_rows", "completed_rows"):
        if run_state.get(field) != int(row_count):
            raise ValueError(
                f"Case-study manifest {field} does not match CSV row count"
            )

    output_state = manifest.get("output")
    if not isinstance(output_state, dict):
        raise ValueError("Case-study manifest is missing output metadata")
    if output_state.get("csv_bytes") != results_csv.stat().st_size:
        raise ValueError("Case-study manifest csv_bytes does not match the CSV")
    if output_state.get("csv_sha256") != _sha256_file(results_csv):
        raise ValueError("Case-study manifest csv_sha256 does not match the CSV")

    return {
        "verified": True,
        "manifest_path": manifest_path,
        "warning": None,
    }


def infer_case_study(csv_name):
    """Infer a process case and its known optimum from a result ``csv_name``.

    Returns a new metadata dictionary for Column, CSTR, Small batch, or
    Dynamic.  A CSTR filename also determines the packaged grid size and its
    corresponding known optimum.
    """
    csv_name = str(csv_name)
    if csv_name == COLUMN_CSV_NAME:
        metadata = {
            "case_name": "column",
            "problem_label": CASE_DISPLAY_NAMES["column"],
            "cstr_grid_size": math.nan,
            "target_value": float(COLUMN_OPTIMUM),
        }
    elif csv_name == SMALL_BATCH_CSV_NAME:
        metadata = {
            "case_name": "small_batch",
            "problem_label": CASE_DISPLAY_NAMES["small_batch"],
            "cstr_grid_size": math.nan,
            "target_value": float(SMALL_BATCH_OPTIMUM),
        }
    elif csv_name == "dynamic":
        metadata = {
            "case_name": "dynamic",
            "problem_label": CASE_DISPLAY_NAMES["dynamic"],
            "cstr_grid_size": math.nan,
            "target_value": float(DYNAMIC_OPTIMUM),
        }
    else:
        cstr_match = _CSTR_NAME.fullmatch(csv_name)
        if cstr_match is None:
            raise ValueError(f"Unsupported process case-study csv_name: {csv_name!r}")
        grid_size = int(cstr_match.group("grid_size"))
        try:
            case_data = load_cstr_case_data(grid_size)
        except FileNotFoundError as error:
            raise ValueError(
                f"No packaged CSTR metadata is available for grid size {grid_size}"
            ) from error
        metadata = {
            "case_name": "cstr",
            "problem_label": f"CSTR {grid_size}x{grid_size}",
            "cstr_grid_size": grid_size,
            "target_value": float(case_data["known_best_value"]),
        }

    return metadata.copy()


def _parse_json_sequence(value, column, row_number, track_legacy_constants=False):
    legacy_constants = []

    def parse_legacy_constant(token):
        legacy_constants.append(token)
        return {
            "NaN": math.nan,
            "Infinity": math.inf,
            "-Infinity": -math.inf,
        }[token]

    if isinstance(value, (list, tuple)):
        parsed = list(value)
    else:
        if pd.isna(value):
            raise ValueError(f"{column} is missing in CSV row {row_number}")
        try:
            parsed = json.loads(str(value), parse_constant=parse_legacy_constant)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"{column} is not valid JSON in CSV row {row_number}"
            ) from error
    if not isinstance(parsed, list):
        raise ValueError(f"{column} must contain a JSON list in CSV row {row_number}")
    if track_legacy_constants:
        return parsed, len(legacy_constants)
    return parsed


def _parse_bool(value, row_number):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float)) and not pd.isna(value):
        if float(value) in (0.0, 1.0):
            return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    raise ValueError(f"found_optimum must be a boolean value in CSV row {row_number}")


def _parse_integer_column(frame, column, allow_missing):
    try:
        values = pd.to_numeric(frame[column], errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError(f"{column} must contain integer values") from error
    if not allow_missing and values.isna().any():
        raise ValueError(f"{column} must not contain missing values")
    finite = values.dropna().to_numpy(dtype=float)
    if finite.size and not np.all(np.isfinite(finite)):
        raise ValueError(f"{column} must contain finite integer values")
    if finite.size and not np.allclose(finite, np.round(finite)):
        raise ValueError(f"{column} must contain integer values")
    return values.astype(float if allow_missing else int)


def _numeric_trajectory(trajectory, row_number):
    values = []
    for value in trajectory:
        if value is None:
            values.append(math.nan)
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "incumbent_trajectory must contain only numeric values or null "
                f"in CSV row {row_number}"
            ) from error
        values.append(numeric)
    return values


def _validate_trajectory(
    trajectory,
    legacy_constant_count,
    total_evals,
    best_value,
    row_number,
):
    if len(trajectory) != total_evals:
        raise ValueError(
            "incumbent_trajectory length must equal total_evals in CSV row "
            f"{row_number}"
        )

    values = _numeric_trajectory(trajectory, row_number)
    finite_values = [value for value in values if math.isfinite(value)]
    if not finite_values:
        legacy_all_nonfinite = (
            legacy_constant_count == len(values) and legacy_constant_count > 0
        )
        if not legacy_all_nonfinite:
            raise ValueError(
                "A finite best_value with no finite incumbent trace is allowed "
                "only for an explicit legacy all-nonfinite trajectory in CSV row "
                f"{row_number}"
            )
        return True

    previous = None
    seen_finite = False
    for value in values:
        if not math.isfinite(value):
            if seen_finite:
                raise ValueError(
                    "incumbent_trajectory cannot become nonfinite after a finite "
                    f"incumbent in CSV row {row_number}"
                )
            continue
        if (
            previous is not None
            and value > previous
            and not math.isclose(
                value,
                previous,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        ):
            raise ValueError(
                "incumbent_trajectory must be monotonically nonincreasing in "
                f"CSV row {row_number}"
            )
        previous = value
        seen_finite = True

    if not math.isclose(
        finite_values[-1],
        best_value,
        rel_tol=1e-10,
        abs_tol=1e-12,
    ):
        raise ValueError(
            f"The terminal incumbent must match best_value in CSV row {row_number}"
        )
    return False


def attach_case_study_metadata(results_df):
    """Attach case names and known optima without benchmark-grid metadata."""
    if "csv_name" not in results_df:
        raise ValueError("Case-study results are missing csv_name")
    metadata_rows = []
    for csv_name in pd.unique(results_df["csv_name"]):
        metadata_rows.append({"csv_name": csv_name, **infer_case_study(csv_name)})
    metadata = pd.DataFrame(metadata_rows)
    metadata_columns = [
        "case_name",
        "problem_label",
        "cstr_grid_size",
        "target_value",
    ]
    return results_df.drop(columns=metadata_columns, errors="ignore").merge(
        metadata,
        on="csv_name",
        how="left",
        validate="many_to_one",
    )


def load_case_study_results(results_csv):
    """Load, validate, and annotate an audited process-case benchmark CSV."""
    results_csv = Path(results_csv)
    frame = pd.read_csv(results_csv)
    input_validation = validate_case_study_manifest(results_csv, len(frame))
    missing = set(RESULT_FIELDS).difference(frame.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(
            f"Case-study results CSV is missing audited columns: {missing_text}"
        )
    if frame.empty:
        raise ValueError("Case-study results CSV contains no runs")

    frame = frame.loc[:, RESULT_FIELDS].copy()
    frame["csv_name"] = frame["csv_name"].astype(str)
    frame["method"] = frame["method"].astype(str).str.strip()
    if (frame["method"] == "").any():
        raise ValueError("method must not be empty")

    for column in _REQUIRED_INTEGER_COLUMNS:
        frame[column] = _parse_integer_column(frame, column, allow_missing=False)
    for column in _OPTIONAL_INTEGER_COLUMNS:
        frame[column] = _parse_integer_column(frame, column, allow_missing=True)
    for column in ("initial_evals", "adaptive_evals", "unique_evals"):
        if frame[column].isna().any():
            raise ValueError(f"{column} must not contain missing values")
    for column in ("best_value", "wall_time_s"):
        try:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        except (TypeError, ValueError) as error:
            raise ValueError(f"{column} must contain numeric values") from error
    if not np.isfinite(frame["best_value"].to_numpy(dtype=float)).all():
        raise ValueError("best_value must be finite")

    frame["found_optimum"] = [
        _parse_bool(value, row_number)
        for row_number, value in enumerate(frame["found_optimum"], start=2)
    ]
    frame["best_point"] = [
        _parse_json_sequence(value, "best_point", row_number)
        for row_number, value in enumerate(frame["best_point"], start=2)
    ]
    trajectories = []
    legacy_constant_counts = []
    for row_number, value in enumerate(frame["incumbent_trajectory"], start=2):
        trajectory, legacy_constant_count = _parse_json_sequence(
            value,
            "incumbent_trajectory",
            row_number,
            track_legacy_constants=True,
        )
        trajectories.append(trajectory)
        legacy_constant_counts.append(legacy_constant_count)
    frame["incumbent_trajectory"] = trajectories

    for column in _NONNEGATIVE_COLUMNS:
        if (frame[column].dropna() < 0).any():
            raise ValueError(f"{column} must be nonnegative")
    if (frame["n_starts"] < 1).any():
        raise ValueError("n_starts must be at least 1")
    if (frame["max_evals"] < frame["n_starts"]).any():
        raise ValueError("max_evals must be greater than or equal to n_starts")
    if (frame["total_evals"] > frame["max_evals"]).any():
        raise ValueError("total_evals must not exceed max_evals")
    if not np.isfinite(frame["wall_time_s"].to_numpy(dtype=float)).all():
        raise ValueError("wall_time_s must be finite")
    if not (frame["initial_evals"] == frame["n_starts"]).all():
        raise ValueError("initial_evals must equal n_starts")
    if not (
        frame["initial_evals"] + frame["adaptive_evals"] == frame["total_evals"]
    ).all():
        raise ValueError("initial_evals + adaptive_evals must equal total_evals")
    if (frame["unique_evals"] > frame["total_evals"]).any():
        raise ValueError("unique_evals must not exceed total_evals")

    frame["legacy_terminal_trace_fallback"] = [
        _validate_trajectory(
            trajectory=trajectory,
            legacy_constant_count=legacy_constant_count,
            total_evals=int(total_evals),
            best_value=float(best_value),
            row_number=row_number,
        )
        for row_number, (
            trajectory,
            legacy_constant_count,
            total_evals,
            best_value,
        ) in enumerate(
            zip(
                frame["incumbent_trajectory"],
                legacy_constant_counts,
                frame["total_evals"],
                frame["best_value"],
                strict=True,
            ),
            start=2,
        )
    ]

    duplicate_runs = frame.duplicated(list(_RUN_ID_COLUMNS), keep=False)
    if duplicate_runs.any():
        duplicate = frame.loc[duplicate_runs, list(_RUN_ID_COLUMNS)].iloc[0]
        run_id = ", ".join(
            f"{column}={duplicate[column]!r}" for column in _RUN_ID_COLUMNS
        )
        raise ValueError(f"Duplicate case-study run identifier: {run_id}")
    annotated = attach_case_study_metadata(frame)
    annotated.attrs["input_validation"] = input_validation
    return annotated


def normalized_optimality_gap(best_value, target_value):
    """Return ``100 * (best_value - target_value) / abs(target_value)``.

    A unit denominator is used only for a zero-valued target.  Positive values
    indicate a worse minimization result; a negative value exposes a result
    below the recorded known optimum rather than silently clipping it.
    """
    best_value = float(best_value)
    target_value = float(target_value)
    denominator = abs(target_value) if target_value != 0.0 else 1.0
    return 100.0 * (best_value - target_value) / denominator


def annotate_optimality_gaps(results_df):
    """Return process-case results with a normalized optimality-gap column."""
    data = results_df.copy()
    if "target_value" not in data:
        data = attach_case_study_metadata(data)
    data["normalized_optimality_gap_pct"] = [
        normalized_optimality_gap(best_value, target_value)
        for best_value, target_value in zip(
            data["best_value"], data["target_value"], strict=True
        )
    ]
    return data


def _sort_case_study_frame(frame):
    if frame.empty:
        return frame.reset_index(drop=True)
    sorted_frame = frame.copy()
    case_rank = {name: rank for rank, name in enumerate(CASE_ORDER)}
    observed_methods = ordered_method_names(sorted_frame["method"], METHOD_ORDER)
    method_rank = {name: rank for rank, name in enumerate(observed_methods)}
    sorted_frame["_case_rank"] = sorted_frame["case_name"].map(case_rank)
    sorted_frame["_method_rank"] = sorted_frame["method"].map(method_rank)
    sort_columns = [
        "_case_rank",
        "cstr_grid_size",
        "max_evals",
        "_method_rank",
    ]
    if "eval_number" in sorted_frame:
        sort_columns.append("eval_number")
    return (
        sorted_frame.sort_values(sort_columns, na_position="first")
        .drop(columns=["_case_rank", "_method_rank"])
        .reset_index(drop=True)
    )


def summarize_case_study_results(
    results_df,
    target_probability=DEFAULT_TARGET_PROBABILITY,
):
    """Compute per-case, method, initialization, and budget audit metrics.

    TTS99 uses the empirical exact-optimum hit rate and the median wall time of
    all runs in a group.  Zero-hit groups retain infinite ``runs_99`` and
    ``tts99_s`` values.  Solver iterations are summarized only over rows where
    a solver reported them; their meaning remains method-specific.
    """
    target_probability = float(target_probability)
    if not 0.0 < target_probability < 1.0:
        raise ValueError("target_probability must be between 0 and 1")
    data = annotate_optimality_gaps(results_df)
    required = set(_SUMMARY_GROUP_COLUMNS).union(
        {
            "seed",
            "found_optimum",
            "best_value",
            "normalized_optimality_gap_pct",
            "wall_time_s",
            "total_evals",
            "initial_evals",
            "adaptive_evals",
            "unique_evals",
            "solver_iterations",
            "legacy_terminal_trace_fallback",
        }
    )
    missing = required.difference(data.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Case-study summary input is missing columns: {missing_text}")
    if (data["wall_time_s"] < 0).any():
        raise ValueError("wall_time_s must be nonnegative")
    data["terminal_trace_fallback"] = data["legacy_terminal_trace_fallback"].astype(
        bool
    )

    summary = (
        data.groupby(list(_SUMMARY_GROUP_COLUMNS), as_index=False, dropna=False)
        .agg(
            n_runs=("seed", "size"),
            n_seeds=("seed", "nunique"),
            hits=("found_optimum", "sum"),
            hit_rate=("found_optimum", "mean"),
            median_objective=("best_value", "median"),
            best_objective=("best_value", "min"),
            median_normalized_gap_pct=(
                "normalized_optimality_gap_pct",
                "median",
            ),
            best_normalized_gap_pct=("normalized_optimality_gap_pct", "min"),
            median_wall_time_s=("wall_time_s", "median"),
            median_total_evals=("total_evals", "median"),
            median_initial_evals=("initial_evals", "median"),
            median_adaptive_evals=("adaptive_evals", "median"),
            median_unique_evals=("unique_evals", "median"),
            solver_iteration_runs=("solver_iterations", "count"),
            median_solver_iterations=("solver_iterations", "median"),
            terminal_trace_fallback_runs=("terminal_trace_fallback", "sum"),
        )
        .reset_index(drop=True)
    )
    for column in (
        "n_runs",
        "n_seeds",
        "hits",
        "solver_iteration_runs",
        "terminal_trace_fallback_runs",
    ):
        summary[column] = summary[column].astype(int)
    summary["runs_99"] = summary["hit_rate"].apply(
        lambda hit_rate: runs_to_target_probability(
            hit_rate,
            target_probability=target_probability,
        )
    )
    summary["tts99_s"] = summary["runs_99"] * summary["median_wall_time_s"]
    summary.loc[summary["hit_rate"] == 0.0, "tts99_s"] = math.inf
    summary["target_probability"] = target_probability
    return _sort_case_study_frame(summary)


def _finite_trajectory_values(trajectory):
    values = []
    for value in trajectory:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            numeric_value = math.nan
        values.append(numeric_value)
    return values


def _robust_quantile(values, probability):
    """Return a linear quantile without creating NaN from infinities."""
    ordered = np.sort(np.asarray(list(values), dtype=float))
    ordered = ordered[~np.isnan(ordered)]
    if not len(ordered):
        return math.nan
    position = (len(ordered) - 1) * float(probability)
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    lower = float(ordered[lower_index])
    upper = float(ordered[upper_index])
    if lower_index == upper_index or lower == upper:
        return lower
    if not math.isfinite(lower) or not math.isfinite(upper):
        return upper if math.isinf(upper) else lower
    fraction = position - lower_index
    return lower + fraction * (upper - lower)


def evaluation_convergence_summary(results_df):
    """Summarize failure-aware normalized gap by evaluation allowance.

    Every run contributes at every allowance through its configured budget.
    Before a run has a finite incumbent it contributes ``+inf`` rather than
    disappearing from the denominator. Runs that terminate early carry their
    terminal incumbent forward, but trajectory entries beyond ``total_evals``
    are never consumed. Explicit legacy all-nonfinite traces use their audited
    final value only at the terminal evaluation and are counted once there.
    """
    data = annotate_optimality_gaps(results_df)
    required = {
        "case_name",
        "problem_label",
        "csv_name",
        "cstr_grid_size",
        "target_value",
        "method",
        "seed",
        "n_starts",
        "max_evals",
        "total_evals",
        "best_value",
        "incumbent_trajectory",
        "legacy_terminal_trace_fallback",
    }
    missing = required.difference(data.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(
            f"Case-study convergence input is missing columns: {missing_text}"
        )

    rows = []
    for run in data.itertuples(index=False):
        if not isinstance(run.incumbent_trajectory, (list, tuple)):
            raise ValueError(
                "incumbent_trajectory must be a sequence for "
                f"case={run.case_name}, method={run.method}, seed={run.seed}"
            )
        trajectory = _finite_trajectory_values(run.incumbent_trajectory)
        terminal_trace_fallback = bool(run.legacy_terminal_trace_fallback)
        budget = int(run.max_evals)
        total_evals = int(run.total_evals)
        if len(trajectory) != total_evals:
            raise ValueError(
                "incumbent_trajectory length must equal total_evals for "
                f"case={run.case_name}, method={run.method}, seed={run.seed}"
            )
        final_value = float(run.best_value)
        running_best = math.nan

        for eval_number in range(1, budget + 1):
            fallback_applied = False
            if eval_number <= total_evals:
                candidate = trajectory[eval_number - 1]
                if math.isfinite(candidate):
                    running_best = candidate
            if terminal_trace_fallback and eval_number == total_evals:
                running_best = final_value
                fallback_applied = True
            has_finite_incumbent = math.isfinite(running_best)
            incumbent = running_best if has_finite_incumbent else math.inf
            rows.append(
                {
                    "case_name": run.case_name,
                    "problem_label": run.problem_label,
                    "csv_name": run.csv_name,
                    "cstr_grid_size": run.cstr_grid_size,
                    "target_value": run.target_value,
                    "method": run.method,
                    "seed": run.seed,
                    "n_starts": run.n_starts,
                    "max_evals": budget,
                    "eval_number": eval_number,
                    "incumbent": incumbent,
                    "normalized_optimality_gap_pct": normalized_optimality_gap(
                        incumbent,
                        run.target_value,
                    ),
                    "has_finite_incumbent": has_finite_incumbent,
                    "terminal_trace_fallback_applied": fallback_applied,
                }
            )

    run_level = pd.DataFrame(rows)
    group_columns = [
        "case_name",
        "problem_label",
        "csv_name",
        "cstr_grid_size",
        "target_value",
        "method",
        "n_starts",
        "max_evals",
        "eval_number",
    ]
    convergence = (
        run_level.groupby(group_columns, as_index=False, dropna=False)
        .agg(
            n_total_runs_at_eval=("seed", "size"),
            n_finite_incumbent_runs_at_eval=("has_finite_incumbent", "sum"),
            n_terminal_fallback_runs_at_eval=(
                "terminal_trace_fallback_applied",
                "sum",
            ),
            median_incumbent=(
                "incumbent",
                lambda values: _robust_quantile(values, 0.5),
            ),
            median_normalized_gap_pct=(
                "normalized_optimality_gap_pct",
                lambda values: _robust_quantile(values, 0.5),
            ),
            q25_normalized_gap_pct=(
                "normalized_optimality_gap_pct",
                lambda values: _robust_quantile(values, 0.25),
            ),
            q75_normalized_gap_pct=(
                "normalized_optimality_gap_pct",
                lambda values: _robust_quantile(values, 0.75),
            ),
        )
        .reset_index(drop=True)
    )
    for column in (
        "n_total_runs_at_eval",
        "n_finite_incumbent_runs_at_eval",
        "n_terminal_fallback_runs_at_eval",
    ):
        convergence[column] = convergence[column].astype(int)
    convergence["n_runs_at_eval"] = convergence["n_total_runs_at_eval"]
    convergence["n_censored_runs_at_eval"] = (
        convergence["n_total_runs_at_eval"]
        - convergence["n_finite_incumbent_runs_at_eval"]
    )
    convergence["finite_incumbent_rate"] = (
        convergence["n_finite_incumbent_runs_at_eval"]
        / convergence["n_total_runs_at_eval"]
    )
    return _sort_case_study_frame(convergence)


def _configuration_rows(frame):
    columns = [
        "case_name",
        "problem_label",
        "csv_name",
        "cstr_grid_size",
        "n_starts",
        "max_evals",
    ]
    return _sort_case_study_frame(
        frame.loc[:, [*columns, "method"]].drop_duplicates(columns).assign(method="")
    ).drop(columns="method")


def _configuration_label(row, show_n_starts):
    label = f"{row.problem_label}\nB={int(row.max_evals)}"
    if show_n_starts:
        label += f", starts={int(row.n_starts)}"
    return label


def plot_case_study_overview(summary_df, method_order=METHOD_ORDER):
    """Plot reproducible overview metrics for every case configuration.

    The reported solver-iteration panel is deliberately labeled as
    method-specific: DSDA, RBFOpt, and BAM do not define an iteration in the
    same way, so those bars document solver telemetry but are not directly
    comparable measures of black-box work.
    """
    if summary_df.empty:
        raise ValueError("Case-study summary is empty")
    plt = _pyplot()
    configurations = _configuration_rows(summary_df)
    config_keys = [
        (row.csv_name, row.n_starts, row.max_evals)
        for row in configurations.itertuples(index=False)
    ]
    multiple_starts = summary_df["n_starts"].nunique() > 1
    labels = [
        _configuration_label(row, multiple_starts)
        for row in configurations.itertuples(index=False)
    ]
    methods = ordered_method_names(summary_df["method"], method_order)
    metrics = (
        ("hit_rate", "Exact-optimum hit rate (%)", 100.0, False),
        ("median_normalized_gap_pct", "Median optimality gap (%)", 1.0, True),
        ("median_wall_time_s", "Median wall time (s)", 1.0, True),
        ("tts99_s", "TTS99 (s)", 1.0, True),
        ("median_total_evals", "Median total evaluations", 1.0, False),
        ("median_unique_evals", "Median unique evaluations", 1.0, False),
        ("median_adaptive_evals", "Median adaptive evaluations", 1.0, False),
        (
            "median_solver_iterations",
            "Median reported solver iterations*",
            1.0,
            False,
        ),
    )
    required = {metric for metric, _, _, _ in metrics}.union(
        {"csv_name", "method", "n_starts", "max_evals"}
    )
    missing = required.difference(summary_df.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Overview summary is missing columns: {missing_text}")

    width = max(14.0, 0.95 * len(configurations))
    fig, axes = plt.subplots(
        len(metrics),
        1,
        figsize=(width, 2.6 * len(metrics)),
        sharex=True,
        squeeze=False,
    )
    x_positions = np.arange(len(configurations), dtype=float)
    bar_width = min(0.25, 0.8 / max(1, len(methods)))
    indexed = summary_df.set_index(["csv_name", "n_starts", "max_evals", "method"])

    for axis, (metric, ylabel, scale, use_symlog) in zip(
        axes.ravel(), metrics, strict=True
    ):
        finite_plotted_values = []
        infinite_markers = []
        for method_index, method in enumerate(methods):
            offset = (method_index - (len(methods) - 1) / 2.0) * bar_width
            raw_values = []
            for csv_name, n_starts, max_evals in config_keys:
                key = (csv_name, n_starts, max_evals, method)
                raw_values.append(
                    float(indexed.loc[key, metric])
                    if key in indexed.index
                    else math.nan
                )
            values = np.asarray(raw_values, dtype=float) * scale
            finite = np.isfinite(values)
            finite_plotted_values.extend(values[finite].tolist())
            axis.bar(
                x_positions + offset,
                np.where(finite, values, math.nan),
                width=bar_width,
                label=method,
                color=METHOD_COLORS.get(method),
                alpha=0.85,
            )
            for x_value, is_infinite in zip(
                x_positions + offset, np.isinf(values), strict=True
            ):
                if is_infinite:
                    infinite_markers.append((x_value, method))

        if infinite_markers:
            finite_max = max(finite_plotted_values, default=1.0)
            marker_height = max(1.0, finite_max * 1.15)
            for x_value, method in infinite_markers:
                axis.scatter(
                    [x_value],
                    [marker_height],
                    marker="^",
                    color=METHOD_COLORS.get(method, "red"),
                    edgecolor="black",
                    linewidth=0.5,
                    zorder=3,
                )
                axis.annotate(
                    "inf",
                    (x_value, marker_height),
                    xytext=(0, 4),
                    textcoords="offset points",
                    ha="center",
                    fontsize=7,
                )
            axis.set_ylim(top=marker_height * 1.25)
        if use_symlog:
            axis.set_yscale("symlog", linthresh=1e-3)
        axis.set_ylabel(ylabel)
        axis.grid(axis="x", visible=False)
        if metric == "hit_rate":
            axis.set_ylim(0.0, 105.0)

    for axis in axes.ravel()[:-1]:
        axis.tick_params(axis="x", labelbottom=False)
    axes.ravel()[-1].set_xticks(
        x_positions,
        labels=labels,
        rotation=45,
        ha="right",
    )

    handles, legend_labels = axes.ravel()[0].get_legend_handles_labels()
    if handles:
        fig.legend(
            handles,
            legend_labels,
            loc="upper center",
            ncol=len(legend_labels),
            bbox_to_anchor=(0.5, 0.995),
        )
    fig.suptitle("Process case-study benchmark overview", y=0.96)
    fig.text(
        0.5,
        0.01,
        "* Iteration definitions are method-specific and not directly "
        "comparable; a missing bar means that method reported no iteration count.",
        ha="center",
        va="bottom",
        fontsize=8,
    )
    fig.tight_layout(rect=(0.0, 0.035, 1.0, 0.96))
    return fig


def plot_evaluation_convergence(convergence_df, method_order=METHOD_ORDER):
    """Plot failure-aware median normalized gap for each setup."""
    if convergence_df.empty:
        raise ValueError("Case-study convergence summary is empty")
    required = {
        "problem_label",
        "csv_name",
        "method",
        "n_starts",
        "max_evals",
        "eval_number",
        "median_normalized_gap_pct",
        "q25_normalized_gap_pct",
        "q75_normalized_gap_pct",
        "n_total_runs_at_eval",
        "n_finite_incumbent_runs_at_eval",
        "finite_incumbent_rate",
        "n_terminal_fallback_runs_at_eval",
    }
    missing = required.difference(convergence_df.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Convergence summary is missing columns: {missing_text}")

    plt = _pyplot()
    configurations = _configuration_rows(convergence_df)
    n_columns = min(3, len(configurations))
    n_rows = math.ceil(len(configurations) / n_columns)
    fig, axes = plt.subplots(
        n_rows,
        n_columns,
        figsize=(4.6 * n_columns, 3.4 * n_rows),
        squeeze=False,
    )
    methods = ordered_method_names(convergence_df["method"], method_order)

    for axis, configuration in zip(
        axes.ravel(), configurations.itertuples(index=False), strict=False
    ):
        selected = convergence_df[
            (convergence_df["csv_name"] == configuration.csv_name)
            & (convergence_df["n_starts"] == configuration.n_starts)
            & (convergence_df["max_evals"] == configuration.max_evals)
        ]
        infinite_median_markers = []
        censored_finite_markers = []
        for method_index, method in enumerate(methods):
            method_data = selected[selected["method"] == method]
            if method_data.empty:
                continue
            x_values = method_data["eval_number"].to_numpy(dtype=float)
            medians = method_data["median_normalized_gap_pct"].to_numpy(dtype=float)
            lower = method_data["q25_normalized_gap_pct"].to_numpy(dtype=float)
            upper = method_data["q75_normalized_gap_pct"].to_numpy(dtype=float)
            color = METHOD_COLORS.get(method)
            finite_medians = np.isfinite(medians)
            axis.plot(
                x_values,
                np.where(finite_medians, medians, math.nan),
                label=method,
                color=color,
                linewidth=1.8,
                marker="o",
                markersize=2.5,
            )
            finite_band = np.isfinite(lower) & np.isfinite(upper)
            axis.fill_between(
                x_values,
                lower,
                upper,
                where=finite_band,
                color=color,
                alpha=0.15,
            )
            marker_offset = 0.06 * (method_index - (len(methods) - 1) / 2.0)
            for x_value in x_values[np.isinf(medians)]:
                infinite_median_markers.append((x_value + marker_offset, method))
            partially_censored = (
                method_data["finite_incumbent_rate"].to_numpy(dtype=float) < 1.0
            )
            for x_value, y_value in zip(
                x_values[partially_censored & finite_medians],
                medians[partially_censored & finite_medians],
                strict=True,
            ):
                censored_finite_markers.append((x_value, y_value, method))

        finite_panel_values = selected[
            [
                "median_normalized_gap_pct",
                "q25_normalized_gap_pct",
                "q75_normalized_gap_pct",
            ]
        ].to_numpy(dtype=float)
        finite_panel_values = finite_panel_values[np.isfinite(finite_panel_values)]
        marker_height = max(
            1.0,
            float(finite_panel_values.max()) * 1.15
            if finite_panel_values.size
            else 1.0,
        )
        for x_value, method in infinite_median_markers:
            axis.scatter(
                [x_value],
                [marker_height],
                marker="^",
                s=30,
                color=METHOD_COLORS.get(method),
                edgecolor="black",
                linewidth=0.5,
                zorder=4,
            )
        for x_value, y_value, method in censored_finite_markers:
            axis.scatter(
                [x_value],
                [y_value],
                marker="o",
                s=34,
                facecolor="none",
                edgecolor=METHOD_COLORS.get(method),
                linewidth=1.0,
                zorder=4,
            )

        panel_notes = []
        if infinite_median_markers:
            panel_notes.append("triangle = inf median")
        if censored_finite_markers:
            panel_notes.append("ring = some runs censored")
        fallback_count = int(selected["n_terminal_fallback_runs_at_eval"].sum())
        if fallback_count:
            fallback_rows = selected[selected["n_terminal_fallback_runs_at_eval"] > 0]
            axis.scatter(
                fallback_rows["eval_number"],
                fallback_rows["median_normalized_gap_pct"],
                marker="X",
                s=35,
                facecolor="none",
                edgecolor="black",
                linewidth=0.8,
                zorder=4,
            )
            panel_notes.append(f"terminal-only trace fallback: {fallback_count}")
        if panel_notes:
            axis.text(
                0.98,
                0.03,
                "\n".join(panel_notes),
                transform=axis.transAxes,
                ha="right",
                va="bottom",
                fontsize=7,
                bbox={
                    "facecolor": "white",
                    "edgecolor": "none",
                    "alpha": 0.85,
                    "pad": 1.5,
                },
            )
        axis.axhline(0.0, color="black", linestyle="--", linewidth=0.8)
        axis.set_yscale("symlog", linthresh=1e-3)
        if infinite_median_markers:
            axis.set_ylim(top=marker_height * 1.3)
        budget = int(configuration.max_evals)
        if budget == 1:
            axis.set_xlim(0.5, 1.5)
        else:
            axis.set_xlim(0.75, budget + 0.25)
        axis.set_xlabel("black-box evaluation allowance")
        axis.set_ylabel("normalized gap (%)")
        axis.set_title(
            f"{configuration.problem_label}, budget={int(configuration.max_evals)}"
        )

    for axis in axes.ravel()[len(configurations) :]:
        axis.set_visible(False)

    handles_by_label = {}
    for axis in axes.ravel()[: len(configurations)]:
        handles, labels = axis.get_legend_handles_labels()
        handles_by_label.update(zip(labels, handles, strict=True))
    legend_labels = [method for method in methods if method in handles_by_label]
    if legend_labels:
        fig.legend(
            [handles_by_label[label] for label in legend_labels],
            legend_labels,
            loc="upper center",
            ncol=len(legend_labels),
            bbox_to_anchor=(0.5, 0.94),
        )
    fig.suptitle(
        "Evaluation-allowance convergence (median and interquartile band)",
        y=0.995,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.86))
    return fig


def create_case_study_analysis_outputs(
    results_csv=None,
    results_dir=None,
    output_dir=DEFAULT_OUTPUT_DIR,
    target_probability=DEFAULT_TARGET_PROBABILITY,
    dpi=300,
):
    """Load one audited CSV and save summary tables plus static PNG figures."""
    results_path = find_latest_case_study_results_csv(results_csv, results_dir)
    results = load_case_study_results(results_path)
    summary = summarize_case_study_results(results, target_probability)
    convergence = evaluation_convergence_summary(results)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "case_study_summary.csv"
    convergence_path = output_dir / "evaluation_convergence_summary.csv"
    summary.to_csv(summary_path, index=False)
    convergence.to_csv(convergence_path, index=False)

    configure_plot_style()
    plt = _pyplot()
    figure_factories = (
        ("case_study_overview.png", lambda: plot_case_study_overview(summary)),
        (
            "evaluation_convergence.png",
            lambda: plot_evaluation_convergence(convergence),
        ),
    )
    figure_paths = []
    for filename, factory in figure_factories:
        figure = factory()
        path = output_dir / filename
        figure.savefig(path, dpi=int(dpi), bbox_inches="tight")
        plt.close(figure)
        figure_paths.append(path)

    return {
        "results_path": results_path,
        "output_dir": output_dir,
        "input_validation": results.attrs["input_validation"],
        "input_warning": results.attrs["input_validation"]["warning"],
        "results": results,
        "summary": summary,
        "convergence_summary": convergence,
        "table_paths": [summary_path, convergence_path],
        "figure_paths": figure_paths,
        "terminal_trace_fallback_runs": int(
            summary["terminal_trace_fallback_runs"].sum()
        ),
    }


def build_parser():
    """Build the process case-study analysis command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-csv",
        type=Path,
        default=None,
        help="Explicit aggregate case-study CSV (otherwise use the newest one).",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Directory searched when --results-csv is omitted.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--target-probability",
        type=float,
        default=DEFAULT_TARGET_PROBABILITY,
        help="Success probability used for runs_99 and TTS99 (default: 0.99).",
    )
    parser.add_argument("--dpi", type=int, default=300)
    return parser


def main(argv=None):
    """CLI entry point for process case-study summaries and static figures."""
    args = build_parser().parse_args(argv)
    outputs = create_case_study_analysis_outputs(
        results_csv=args.results_csv,
        results_dir=args.results_dir,
        output_dir=args.output_dir,
        target_probability=args.target_probability,
        dpi=args.dpi,
    )
    print(f"Analyzed process case-study results: {outputs['results_path']}")
    if outputs["input_warning"]:
        print(f"Warning: {outputs['input_warning']}")
    if outputs["terminal_trace_fallback_runs"]:
        print(
            "Warning: "
            f"{outputs['terminal_trace_fallback_runs']} run(s) had no finite "
            "incumbent trace; convergence includes an explicitly counted "
            "terminal-only best-value fallback."
        )
    for path in [*outputs["table_paths"], *outputs["figure_paths"]]:
        print(f"Saved: {path}")
    return outputs


if __name__ == "__main__":
    main()
