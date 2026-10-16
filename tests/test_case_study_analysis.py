"""Tests for process case-study analysis and static result artifacts."""

import hashlib
import json
import math
import os

import matplotlib
import pandas as pd
import pytest

matplotlib.use("Agg")

import case_study_analysis
from case_studies.column_case import COLUMN_CSV_NAME, KNOWN_BEST_VALUE
from case_studies.cstr_case import cstr_csv_name, load_cstr_case_data
from case_studies.small_batch_case import SMALL_BATCH_CSV_NAME
from instrumentation import make_result_record, save_results_csv


def _record(
    csv_name,
    method,
    seed,
    best_value,
    trajectory,
    *,
    found_optimum=False,
    wall_time_s=1.0,
    max_evals=4,
    total_evals=3,
    solver_iterations=None,
):
    return make_result_record(
        csv_name=csv_name,
        method=method,
        seed=seed,
        n_starts=1,
        max_evals=max_evals,
        best_value=best_value,
        best_point=[1, 1],
        total_evals=total_evals,
        wall_time_s=wall_time_s,
        found_optimum=found_optimum,
        incumbent_trajectory=trajectory,
        initial_evals=1,
        adaptive_evals=total_evals - 1,
        unique_evals=total_evals,
        solver_evalcount=total_evals,
        solver_iterations=solver_iterations,
        solver_status=0,
        solver_message="test run",
    )


def _write_completed_manifest(results_path, row_count):
    manifest = {
        "manifest_version": 1,
        "schema": case_study_analysis.EXPECTED_RESULT_SCHEMA,
        "run": {
            "status": "completed",
            "expected_rows": row_count,
            "completed_rows": row_count,
        },
        "output": {
            "csv_bytes": results_path.stat().st_size,
            "csv_sha256": hashlib.sha256(results_path.read_bytes()).hexdigest(),
        },
    }
    manifest_path = case_study_analysis.case_study_manifest_path(results_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _set_nested(mapping, path, value):
    target = mapping
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def _summary_records():
    target = KNOWN_BEST_VALUE
    return [
        _record(
            COLUMN_CSV_NAME,
            "DSDA",
            0,
            target,
            [target * 1.2, target, target],
            found_optimum=True,
            wall_time_s=1.0,
        ),
        _record(
            COLUMN_CSV_NAME,
            "DSDA",
            1,
            target * 1.2,
            [target * 1.3, target * 1.2, target * 1.2],
            wall_time_s=3.0,
        ),
        _record(
            COLUMN_CSV_NAME,
            "RBFOpt",
            0,
            target * 1.1,
            [target * 1.3, target * 1.2, target * 1.1],
            wall_time_s=2.0,
            solver_iterations=8,
        ),
        _record(
            COLUMN_CSV_NAME,
            "RBFOpt",
            1,
            target * 1.3,
            [target * 1.5, target * 1.4, target * 1.3],
            wall_time_s=4.0,
            solver_iterations=10,
        ),
    ]


def test_infer_case_study_maps_all_four_process_cases_and_cstr_grid():
    column = case_study_analysis.infer_case_study(COLUMN_CSV_NAME)
    cstr = case_study_analysis.infer_case_study(cstr_csv_name(5))
    small_batch = case_study_analysis.infer_case_study(SMALL_BATCH_CSV_NAME)
    dynamic = case_study_analysis.infer_case_study("dynamic")

    assert column["case_name"] == "column"
    assert column["target_value"] == KNOWN_BEST_VALUE
    assert cstr["case_name"] == "cstr"
    assert cstr["cstr_grid_size"] == 5
    assert cstr["target_value"] == load_cstr_case_data(5)["known_best_value"]
    assert small_batch["case_name"] == "small_batch"
    assert dynamic["case_name"] == "dynamic"

    with pytest.raises(ValueError, match="Unsupported process case-study"):
        case_study_analysis.infer_case_study("unknown.csv")


def test_load_case_study_results_parses_audited_csv_without_grid_metadata(tmp_path):
    records = [
        _record(
            COLUMN_CSV_NAME,
            "DSDA",
            0,
            KNOWN_BEST_VALUE,
            [math.inf, KNOWN_BEST_VALUE],
            found_optimum=True,
            total_evals=2,
        ),
        _record(
            cstr_csv_name(5),
            "RBFOpt",
            0,
            load_cstr_case_data(5)["known_best_value"],
            [math.inf, load_cstr_case_data(5)["known_best_value"]],
            found_optimum=True,
            total_evals=2,
        ),
        _record(
            SMALL_BATCH_CSV_NAME,
            "BAM",
            0,
            case_study_analysis.SMALL_BATCH_OPTIMUM,
            [math.nan, case_study_analysis.SMALL_BATCH_OPTIMUM],
            found_optimum=True,
            total_evals=2,
        ),
        _record(
            "dynamic",
            "DSDA",
            0,
            case_study_analysis.DYNAMIC_OPTIMUM,
            [case_study_analysis.DYNAMIC_OPTIMUM],
            found_optimum=True,
            total_evals=1,
        ),
    ]
    results_path = tmp_path / "process_cases.csv"
    save_results_csv(records, results_path)
    serialized = pd.read_csv(results_path)
    serialized.loc[0, "incumbent_trajectory"] = f"[Infinity, {KNOWN_BEST_VALUE}]"
    serialized.to_csv(results_path, index=False)

    results = case_study_analysis.load_case_study_results(results_path)

    assert set(results["case_name"]) == {
        "column",
        "cstr",
        "small_batch",
        "dynamic",
    }
    assert results.loc[0, "best_point"] == [1, 1]
    assert math.isinf(results.loc[0, "incumbent_trajectory"][0])
    assert results.loc[2, "incumbent_trajectory"][0] is None
    assert results.loc[1, "problem_label"] == "CSTR 5x5"
    assert not results.attrs["input_validation"]["verified"]
    assert "legacy, unverified" in results.attrs["input_validation"]["warning"]


def test_latest_results_ignores_incomplete_checkpoints(tmp_path):
    completed = tmp_path / "process_case_studies_20260802_120000.csv"
    partial = tmp_path / "process_case_studies_20260802_130000.partial.csv"
    pending = tmp_path / "process_case_studies_20260802_130000.partial.pending.csv"
    completed.write_text("completed\n", encoding="utf-8")
    partial.write_text("partial\n", encoding="utf-8")
    pending.write_text("pending\n", encoding="utf-8")

    assert (
        case_study_analysis.find_latest_case_study_results_csv(results_dir=tmp_path)
        == completed
    )


def test_load_case_study_results_requires_audit_columns_and_unique_runs(tmp_path):
    results_path = tmp_path / "process_cases.csv"
    save_results_csv([_summary_records()[0]], results_path)
    incomplete = pd.read_csv(results_path).drop(columns="unique_evals")
    incomplete.to_csv(results_path, index=False)

    with pytest.raises(ValueError, match="missing audited columns: unique_evals"):
        case_study_analysis.load_case_study_results(results_path)

    save_results_csv([_summary_records()[0]] * 2, results_path)
    with pytest.raises(ValueError, match="Duplicate case-study run identifier"):
        case_study_analysis.load_case_study_results(results_path)


def test_latest_results_selection_excludes_newer_partial_checkpoint(tmp_path):
    completed = tmp_path / "process_case_studies_20260802.csv"
    partial = tmp_path / "process_case_studies_20260802.partial.csv"
    pending = tmp_path / "process_case_studies_20260802.partial.pending.csv"
    completed.write_text("completed\n", encoding="utf-8")
    partial.write_text("partial\n", encoding="utf-8")
    pending.write_text("pending\n", encoding="utf-8")
    os.utime(completed, (1, 1))
    os.utime(partial, (2, 2))
    os.utime(pending, (3, 3))

    selected = case_study_analysis.find_latest_case_study_results_csv(
        results_dir=tmp_path
    )

    assert selected == completed


def test_load_case_study_results_validates_completed_manifest(tmp_path):
    results_path = tmp_path / "process_cases.csv"
    save_results_csv([_summary_records()[0]], results_path)
    manifest_path = _write_completed_manifest(results_path, row_count=1)

    results = case_study_analysis.load_case_study_results(results_path)

    assert results.attrs["input_validation"] == {
        "verified": True,
        "manifest_path": manifest_path,
        "warning": None,
    }


@pytest.mark.parametrize(
    ("field_path", "invalid_value", "message"),
    [
        (("schema",), {}, "schema does not match"),
        (("run", "status"), "failed", "status must be completed"),
        (("run", "expected_rows"), 2, "expected_rows"),
        (("run", "completed_rows"), 2, "completed_rows"),
        (("output", "csv_bytes"), -1, "csv_bytes"),
        (("output", "csv_sha256"), "0" * 64, "csv_sha256"),
    ],
)
def test_load_case_study_results_rejects_manifest_mismatches(
    tmp_path,
    field_path,
    invalid_value,
    message,
):
    results_path = tmp_path / "process_cases.csv"
    save_results_csv([_summary_records()[0]], results_path)
    manifest_path = _write_completed_manifest(results_path, row_count=1)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _set_nested(manifest, field_path, invalid_value)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        case_study_analysis.load_case_study_results(results_path)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {"incumbent_trajectory": json.dumps([KNOWN_BEST_VALUE] * 2)},
            "length must equal total_evals",
        ),
        ({"initial_evals": 2}, "initial_evals must equal n_starts"),
        (
            {"adaptive_evals": 1},
            r"initial_evals \+ adaptive_evals must equal total_evals",
        ),
        ({"unique_evals": 4}, "unique_evals must not exceed total_evals"),
        ({"best_value": math.nan}, "best_value must be finite"),
        (
            {
                "incumbent_trajectory": json.dumps(
                    [
                        KNOWN_BEST_VALUE * 1.2,
                        KNOWN_BEST_VALUE * 1.3,
                        KNOWN_BEST_VALUE,
                    ]
                )
            },
            "monotonically nonincreasing",
        ),
        (
            {
                "incumbent_trajectory": json.dumps(
                    [
                        KNOWN_BEST_VALUE * 1.2,
                        KNOWN_BEST_VALUE * 1.1,
                        KNOWN_BEST_VALUE * 1.05,
                    ]
                )
            },
            "terminal incumbent must match best_value",
        ),
    ],
)
def test_load_case_study_results_enforces_audit_invariants(
    tmp_path,
    updates,
    message,
):
    results_path = tmp_path / "process_cases.csv"
    record = _record(
        COLUMN_CSV_NAME,
        "DSDA",
        0,
        KNOWN_BEST_VALUE,
        [KNOWN_BEST_VALUE * 1.2, KNOWN_BEST_VALUE * 1.1, KNOWN_BEST_VALUE],
    )
    save_results_csv([record], results_path)
    serialized = pd.read_csv(results_path)
    for column, value in updates.items():
        serialized.loc[0, column] = value
    serialized.to_csv(results_path, index=False)

    with pytest.raises(ValueError, match=message):
        case_study_analysis.load_case_study_results(results_path)


def test_only_explicit_legacy_all_nonfinite_trace_uses_terminal_fallback(tmp_path):
    results_path = tmp_path / "process_cases.csv"
    record = _record(
        COLUMN_CSV_NAME,
        "BAM",
        0,
        KNOWN_BEST_VALUE * 1.1,
        [math.nan, math.nan, math.nan],
    )
    save_results_csv([record], results_path)

    with pytest.raises(ValueError, match="explicit legacy all-nonfinite"):
        case_study_analysis.load_case_study_results(results_path)

    serialized = pd.read_csv(results_path)
    serialized.loc[0, "incumbent_trajectory"] = "[NaN, NaN, NaN]"
    serialized.to_csv(results_path, index=False)
    results = case_study_analysis.load_case_study_results(results_path)

    assert results.loc[0, "legacy_terminal_trace_fallback"]


def test_convergence_uses_constant_denominator_and_failure_aware_quantiles(tmp_path):
    target = KNOWN_BEST_VALUE
    records = [
        _record(
            COLUMN_CSV_NAME,
            "DSDA",
            0,
            target,
            [math.inf, target * 1.2, target],
            found_optimum=True,
        ),
        _record(
            COLUMN_CSV_NAME,
            "DSDA",
            1,
            target * 1.1,
            [target * 1.3, target * 1.2, target * 1.1],
        ),
    ]
    results_path = tmp_path / "process_cases.csv"
    save_results_csv(records, results_path)
    results = case_study_analysis.load_case_study_results(results_path)

    convergence = case_study_analysis.evaluation_convergence_summary(results).set_index(
        "eval_number"
    )

    assert set(convergence["n_total_runs_at_eval"]) == {2}
    assert convergence.loc[1, "n_finite_incumbent_runs_at_eval"] == 1
    assert convergence.loc[1, "finite_incumbent_rate"] == 0.5
    assert math.isinf(convergence.loc[1, "median_normalized_gap_pct"])
    assert not math.isnan(convergence.loc[1, "q25_normalized_gap_pct"])
    assert convergence.loc[2, "median_normalized_gap_pct"] == pytest.approx(20.0)
    assert convergence.loc[4, "median_normalized_gap_pct"] == pytest.approx(5.0)


def test_summary_reports_gaps_audit_medians_and_zero_hit_infinity(tmp_path):
    results_path = tmp_path / "process_cases.csv"
    save_results_csv(_summary_records(), results_path)
    results = case_study_analysis.load_case_study_results(results_path)

    summary = case_study_analysis.summarize_case_study_results(results)
    dsda = summary[summary["method"] == "DSDA"].iloc[0]
    rbfopt = summary[summary["method"] == "RBFOpt"].iloc[0]

    assert dsda["n_runs"] == 2
    assert dsda["n_seeds"] == 2
    assert dsda["hits"] == 1
    assert dsda["hit_rate"] == 0.5
    assert dsda["median_objective"] == pytest.approx(KNOWN_BEST_VALUE * 1.1)
    assert dsda["best_objective"] == KNOWN_BEST_VALUE
    assert dsda["median_normalized_gap_pct"] == pytest.approx(10.0)
    assert dsda["best_normalized_gap_pct"] == pytest.approx(0.0)
    assert dsda["median_wall_time_s"] == 2.0
    assert dsda["median_total_evals"] == 3.0
    assert dsda["median_initial_evals"] == 1.0
    assert dsda["median_adaptive_evals"] == 2.0
    assert dsda["median_unique_evals"] == 3.0
    assert dsda["runs_99"] == 7
    assert dsda["tts99_s"] == 14.0

    assert rbfopt["hit_rate"] == 0.0
    assert math.isinf(rbfopt["runs_99"])
    assert math.isinf(rbfopt["tts99_s"])
    assert rbfopt["solver_iteration_runs"] == 2
    assert rbfopt["median_solver_iterations"] == 9.0
    assert rbfopt["terminal_trace_fallback_runs"] == 0


def test_convergence_ignores_leading_nonfinite_and_marks_terminal_fallback(tmp_path):
    target = KNOWN_BEST_VALUE
    records = [
        _record(
            COLUMN_CSV_NAME,
            "DSDA",
            0,
            target,
            [math.inf, target * 1.2, target],
            found_optimum=True,
        ),
        _record(
            COLUMN_CSV_NAME,
            "BAM",
            0,
            target * 1.1,
            [math.nan, math.nan, math.nan],
        ),
    ]
    results_path = tmp_path / "process_cases.csv"
    save_results_csv(records, results_path)
    serialized = pd.read_csv(results_path)
    serialized.loc[serialized["method"] == "BAM", "incumbent_trajectory"] = (
        "[NaN, NaN, NaN]"
    )
    serialized.to_csv(results_path, index=False)
    results = case_study_analysis.load_case_study_results(results_path)

    convergence = case_study_analysis.evaluation_convergence_summary(results)
    dsda = convergence[convergence["method"] == "DSDA"].set_index("eval_number")
    bam = convergence[convergence["method"] == "BAM"].set_index("eval_number")

    assert list(dsda.index) == [1, 2, 3, 4]
    assert math.isinf(dsda.loc[1, "median_normalized_gap_pct"])
    assert dsda.loc[1, "n_total_runs_at_eval"] == 1
    assert dsda.loc[1, "n_finite_incumbent_runs_at_eval"] == 0
    assert dsda.loc[1, "finite_incumbent_rate"] == 0.0
    assert dsda.loc[2, "median_normalized_gap_pct"] == pytest.approx(20.0)
    assert dsda.loc[3, "median_normalized_gap_pct"] == pytest.approx(0.0)
    assert dsda.loc[4, "median_normalized_gap_pct"] == pytest.approx(0.0)
    assert list(bam.index) == [1, 2, 3, 4]
    assert math.isinf(bam.loc[1, "median_normalized_gap_pct"])
    assert math.isinf(bam.loc[2, "median_normalized_gap_pct"])
    assert bam.loc[3, "median_normalized_gap_pct"] == pytest.approx(10.0)
    assert bam.loc[3, "n_terminal_fallback_runs_at_eval"] == 1
    assert bam["n_terminal_fallback_runs_at_eval"].sum() == 1
    assert bam.loc[4, "median_normalized_gap_pct"] == pytest.approx(10.0)

    figure = case_study_analysis.plot_evaluation_convergence(convergence)
    plot_text = " ".join(text.get_text() for axis in figure.axes for text in axis.texts)
    assert "triangle = inf median" in plot_text
    assert "terminal-only trace fallback: 1" in plot_text
    case_study_analysis._pyplot().close(figure)


def test_overview_labels_solver_iterations_as_method_specific(tmp_path):
    results_path = tmp_path / "process_cases.csv"
    save_results_csv(_summary_records(), results_path)
    results = case_study_analysis.load_case_study_results(results_path)
    summary = case_study_analysis.summarize_case_study_results(results)

    figure = case_study_analysis.plot_case_study_overview(summary)

    assert "Median reported solver iterations*" in {
        axis.get_ylabel() for axis in figure.axes
    }
    figure_notes = " ".join(text.get_text() for text in figure.texts)
    assert "method-specific and not directly comparable" in figure_notes
    assert figure.axes[1].get_ylim()[0] == 0.0
    case_study_analysis._pyplot().close(figure)


def test_gap_plots_keep_zero_visible_without_negative_axis_space(tmp_path):
    results_path = tmp_path / "process_cases.csv"
    save_results_csv(_summary_records(), results_path)
    results = case_study_analysis.load_case_study_results(results_path)
    convergence = case_study_analysis.evaluation_convergence_summary(results)
    figure = case_study_analysis.plot_evaluation_convergence(convergence)
    for axis in figure.axes:
        if axis.get_visible():
            assert axis.get_ylim()[0] == 0.0
            assert axis.get_yscale() == "symlog"
    case_study_analysis._pyplot().close(figure)
    convergence.loc[0, "q25_normalized_gap_pct"] = -1.0
    with pytest.raises(ValueError, match="Negative optimality gaps"):
        case_study_analysis.plot_evaluation_convergence(convergence)
    summary = case_study_analysis.summarize_case_study_results(results)
    summary.loc[0, "median_normalized_gap_pct"] = -1.0
    with pytest.raises(ValueError, match="Negative optimality gaps"):
        case_study_analysis.plot_case_study_overview(summary)


def test_default_sized_overview_keeps_configuration_labels_readable(tmp_path):
    results_path = tmp_path / "process_cases.csv"
    save_results_csv(_summary_records(), results_path)
    results = case_study_analysis.load_case_study_results(results_path)
    base_summary = case_study_analysis.summarize_case_study_results(results)
    summaries = []
    for configuration in range(14):
        summaries.append(
            base_summary.assign(
                case_name="dynamic",
                problem_label=f"Case {configuration + 1}",
                csv_name=f"case_{configuration + 1}",
                cstr_grid_size=math.nan,
                max_evals=configuration + 4,
            )
        )
    summary = pd.concat(summaries, ignore_index=True)

    figure = case_study_analysis.plot_case_study_overview(summary)
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    labels = [
        label
        for label in figure.axes[-1].get_xticklabels()
        if label.get_visible() and label.get_text()
    ]
    bounds = sorted(
        (label.get_window_extent(renderer=renderer) for label in labels),
        key=lambda box: box.x0,
    )

    assert len(figure.axes) == 8
    assert len(labels) == 14
    assert all(left.x1 <= right.x0 for left, right in zip(bounds, bounds[1:]))
    assert not any(label.get_visible() for label in figure.axes[0].get_xticklabels())
    case_study_analysis._pyplot().close(figure)


def test_cli_saves_reproducible_summary_csvs_and_static_pngs(tmp_path, capsys):
    results_path = tmp_path / "process_case_studies_20260802.csv"
    output_dir = tmp_path / "analysis"
    save_results_csv(_summary_records(), results_path)

    outputs = case_study_analysis.main(
        [
            "--results-csv",
            str(results_path),
            "--output-dir",
            str(output_dir),
            "--dpi",
            "72",
        ]
    )

    assert outputs["results_path"] == results_path
    assert "legacy, unverified" in outputs["input_warning"]
    assert "Warning: No paired manifest was found" in capsys.readouterr().out
    assert {path.name for path in outputs["table_paths"]} == {
        "case_study_summary.csv",
        "evaluation_convergence_summary.csv",
    }
    assert {path.name for path in outputs["figure_paths"]} == {
        "case_study_overview.png",
        "evaluation_convergence.png",
    }
    for path in [*outputs["table_paths"], *outputs["figure_paths"]]:
        assert path.is_file()
        assert path.stat().st_size > 0
