"""Tests for the aggregate process case-study benchmark runner."""

import csv
import hashlib
import json
import signal
import time
from datetime import datetime
from pathlib import Path

import pytest

import case_study_benchmark
from instrumentation import RESULT_FIELDS, make_result_record


METHOD_NAMES = {
    "dsda": "DSDA",
    "rbfopt": "RBFOpt",
    "bam": "BAM",
}


def _fake_runner(method, calls, case_name="cstr"):
    def run(**kwargs):
        calls.append((method, kwargs))
        row = {"case_name": case_name, **kwargs}
        return {
            "result_record": make_result_record(
                csv_name=case_study_benchmark._case_csv_name(row),
                method=METHOD_NAMES[method],
                seed=kwargs["seed"],
                n_starts=kwargs["n_starts"],
                max_evals=kwargs["max_evaluations"],
                best_value=1.0,
                best_point=[1, 1],
                total_evals=kwargs["max_evaluations"],
                wall_time_s=0.1,
                found_optimum=True,
                incumbent_trajectory=[1.0],
                initial_evals=kwargs["n_starts"],
                adaptive_evals=kwargs["max_evaluations"] - kwargs["n_starts"],
                unique_evals=kwargs["max_evaluations"],
            )
        }

    return run


def test_default_matrix_matches_the_documented_process_study():
    matrix = case_study_benchmark.build_run_matrix()
    planned_runs = case_study_benchmark._planned_run_keys(
        matrix,
        case_study_benchmark.DEFAULT_METHODS,
        n_starts=3,
    )

    assert len(matrix) == 139
    assert len(planned_runs) == 417
    assert len({json.dumps(run, sort_keys=True) for run in planned_runs}) == 417
    assert sum(row["case_name"] == "column" for row in matrix) == 9
    assert sum(row["case_name"] == "cstr" for row in matrix) == 60
    assert sum(row["case_name"] == "small_batch" for row in matrix) == 10
    assert sum(row["case_name"] == "dynamic" for row in matrix) == 60

    column_rows = [row for row in matrix if row["case_name"] == "column"]
    assert {row["seed"] for row in column_rows} == set(range(1, 10))
    assert {row["max_evaluations"] for row in column_rows} == {16}

    cstr_budgets = {
        row["grid_size"]: row["max_evaluations"]
        for row in matrix
        if row["case_name"] == "cstr"
    }
    assert cstr_budgets == {5: 8, 10: 15, 15: 22, 20: 29, 25: 36, 30: 43}
    assert {
        row["max_evaluations"] for row in matrix if row["case_name"] == "dynamic"
    } == {12, 15, 20, 30, 37, 50}


def test_run_case_study_benchmark_combines_all_methods_in_one_csv(tmp_path):
    calls = []
    runners = {
        "cstr": {
            method: _fake_runner(method, calls) for method in ("dsda", "rbfopt", "bam")
        }
    }
    rbfopt_module = object()
    bam_module = object()
    output_path = tmp_path / "process_cases.csv"

    records, saved_path = case_study_benchmark.run_case_study_benchmark(
        cases=("cstr",),
        methods=("dsda", "rbfopt", "bam"),
        seeds=(2,),
        cstr_grid_sizes=(5,),
        n_starts=3,
        output=output_path,
        rbfopt_module=rbfopt_module,
        bam_module=bam_module,
        runners=runners,
    )

    assert saved_path == output_path
    assert [record["method"] for record in records] == ["DSDA", "RBFOpt", "BAM"]
    assert all(record["max_evals"] == 8 for record in records)

    calls_by_method = {method: kwargs for method, kwargs in calls}
    assert calls_by_method["dsda"]["grid_size"] == 5
    assert calls_by_method["dsda"]["diagonal"] is True
    assert calls_by_method["rbfopt"]["algorithm"] == "MSRSM"
    assert calls_by_method["rbfopt"]["global_search_method"] == "solver"
    assert calls_by_method["rbfopt"]["rbfopt_module"] is rbfopt_module
    assert calls_by_method["rbfopt"]["verbose"] is False
    assert calls_by_method["bam"]["bam_module"] is bam_module

    with output_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert tuple(reader.fieldnames) == RESULT_FIELDS
    assert [row["method"] for row in rows] == ["DSDA", "RBFOpt", "BAM"]

    manifest_path = case_study_benchmark.case_study_manifest_path(output_path)
    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert manifest["manifest_version"] == 2
    assert manifest["schema"]["fields"] == list(RESULT_FIELDS)
    assert manifest["protocol"]["cases"] == ["cstr"]
    assert manifest["protocol"]["methods"] == ["dsda", "rbfopt", "bam"]
    assert manifest["protocol"]["n_starts"] == 3
    assert manifest["protocol"]["method_configuration"]["rbfopt"]["verbose"] is False
    assert manifest["protocol"]["case_parameters"]["cstr"] == {
        "seeds": [2],
        "max_evaluation_budgets": [8],
        "grid_sizes": [5],
        "budget_scaling": {
            "formula": "ceil(10 * grid_size / 7)",
            "grid_size_to_max_evaluations": [{"grid_size": 5, "max_evaluations": 8}],
        },
    }
    assert manifest["run"]["expected_configurations"] == 1
    assert manifest["run"]["expected_rows"] == 3
    assert manifest["run"]["completed_rows"] == 3
    assert manifest["run"]["status"] == "completed"
    assert manifest["output"]["csv_path"] == str(output_path.resolve())
    assert manifest["output"]["current_csv_path"] == str(output_path.resolve())
    assert (
        manifest["output"]["csv_sha256"]
        == hashlib.sha256(output_path.read_bytes()).hexdigest()
    )
    assert manifest["provenance"]["initial_design"]["designs"] == [
        {
            "case_name": "cstr",
            "grid_size": 5,
            "n_starts": 3,
            "seed": 2,
            "sha256": manifest["provenance"]["initial_design"]["designs"][0]["sha256"],
        }
    ]
    assert len(manifest["provenance"]["initial_design"]["designs"][0]["sha256"]) == 64
    assert manifest["provenance"]["initial_design"]["strategy"] == (
        "seeded Latin hypercube sampling with deterministic "
        "rounded-lattice duplicate repair"
    )
    assert any(
        path.endswith("compl_enum_cstr_5_baron_hull.csv")
        for path in manifest["provenance"]["data_files_sha256"]
    )
    source_hashes = manifest["provenance"]["source_files_sha256"]
    assert "grid_dsda.py" in source_hashes
    assert "case_studies/bam_common.py" in source_hashes
    partial_path = case_study_benchmark.case_study_partial_path(output_path)
    assert not partial_path.exists()
    assert not case_study_benchmark.case_study_manifest_path(partial_path).exists()


def test_small_batch_keeps_its_rbfopt_sampling_defaults(tmp_path):
    calls = []
    runners = {
        "small_batch": {"rbfopt": _fake_runner("rbfopt", calls, "small_batch")},
    }

    output_path = tmp_path / "small_batch.csv"
    case_study_benchmark.run_case_study_benchmark(
        cases=("small_batch",),
        methods=("rbfopt",),
        seeds=(0,),
        small_batch_budgets=(10,),
        output=output_path,
        rbfopt_module=object(),
        runners=runners,
    )

    _, kwargs = calls[0]
    assert kwargs["algorithm"] == "Gutmann"
    assert kwargs["global_search_method"] == "sampling"
    manifest = json.loads(
        case_study_benchmark.case_study_manifest_path(output_path).read_text(
            encoding="utf-8"
        )
    )
    assert (
        "case_studies/bam_common.py"
        in manifest["provenance"]["source_files_sha256"]
    )


def test_real_small_batch_bam_requires_a_license_before_starting(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("BAM_LICENSE_FILE", raising=False)
    with pytest.raises(FileNotFoundError, match="small-batch BAM study"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("small_batch",),
            methods=("bam",),
            seeds=(0,),
            small_batch_budgets=(10,),
            output=tmp_path / "small_batch.csv",
            bam_license_file="",
        )


def test_manifest_does_not_serialize_bam_license_path(tmp_path):
    calls = []
    runners = {
        "small_batch": {"bam": _fake_runner("bam", calls, "small_batch")},
    }
    output_path = tmp_path / "small_batch.csv"
    sensitive_license_path = tmp_path / "do-not-record-this-license.lic"

    case_study_benchmark.run_case_study_benchmark(
        cases=("small_batch",),
        methods=("bam",),
        seeds=(0,),
        small_batch_budgets=(10,),
        output=output_path,
        bam_license_file=sensitive_license_path,
        bam_module=object(),
        runners=runners,
    )

    manifest_text = case_study_benchmark.case_study_manifest_path(
        output_path
    ).read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert str(sensitive_license_path) not in manifest_text
    assert "do-not-record-this-license" not in manifest_text
    assert manifest["protocol"]["method_configuration"]["bam"] == {
        "license_configured": True,
        "module_injected": True,
        "verbose": False,
    }


def test_failed_run_keeps_checkpoint_and_prior_output_untouched(tmp_path):
    calls = []
    successful_runner = _fake_runner("dsda", calls)

    def fail_on_second_run(**kwargs):
        if kwargs["seed"] == 1:
            raise RuntimeError("simulated solver failure")
        return successful_runner(**kwargs)

    runners = {"cstr": {"dsda": fail_on_second_run}}
    output_path = tmp_path / "process_cases.csv"
    output_path.write_text("previous completed result\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="simulated solver failure"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0, 1),
            cstr_grid_sizes=(5,),
            output=output_path,
            runners=runners,
            overwrite=True,
        )

    assert output_path.read_text(encoding="utf-8") == "previous completed result\n"
    partial_path = case_study_benchmark.case_study_partial_path(output_path)
    with partial_path.open(newline="") as handle:
        checkpoint_rows = list(csv.DictReader(handle))
    assert len(checkpoint_rows) == 1
    assert checkpoint_rows[0]["seed"] == "0"
    assert not case_study_benchmark.case_study_manifest_path(output_path).exists()
    partial_manifest_path = case_study_benchmark.case_study_manifest_path(partial_path)
    with partial_manifest_path.open(encoding="utf-8") as handle:
        partial_manifest = json.load(handle)
    assert partial_manifest["run"]["status"] == "failed"
    assert partial_manifest["run"]["expected_rows"] == 2
    assert partial_manifest["run"]["completed_rows"] == 1
    assert partial_manifest["output"]["current_csv_path"] == str(partial_path.resolve())
    assert partial_manifest["run"]["failed_run"]["run_key"]["seed"] == 1
    assert partial_manifest["run"]["failed_run"]["exception_type"] == "RuntimeError"
    assert partial_manifest["run"]["failed_run"]["message"] == (
        "simulated solver failure"
    )

    with pytest.raises(FileExistsError, match="Completed output already exists"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0,),
            cstr_grid_sizes=(5,),
            output=output_path,
            runners=runners,
        )


def test_case_study_output_path_uses_a_descriptive_timestamp():
    now = datetime(2026, 8, 2, 12, 34, 56, 123456)

    path = case_study_benchmark.case_study_output_path("results", now=now)

    assert path.name == "process_case_studies_20260802_123456_123456.csv"


def test_parse_cases_accepts_hyphenated_small_batch_and_rejects_unknown():
    assert case_study_benchmark.parse_cases("column,small-batch") == (
        "column",
        "small_batch",
    )
    with pytest.raises(
        case_study_benchmark.argparse.ArgumentTypeError,
        match="Unsupported case study",
    ):
        case_study_benchmark.parse_cases("unknown")


def _create_one_row_checkpoint(tmp_path, filename="resume.csv"):
    calls = []
    successful_runner = _fake_runner("dsda", calls)

    def fail_on_second_run(**kwargs):
        if kwargs["seed"] == 1:
            raise RuntimeError("second run failed")
        return successful_runner(**kwargs)

    output_path = tmp_path / filename
    with pytest.raises(RuntimeError, match="second run failed"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0, 1),
            cstr_grid_sizes=(5,),
            output=output_path,
            runners={"cstr": {"dsda": fail_on_second_run}},
        )
    return output_path


def test_row_one_failure_retains_zero_row_failed_checkpoint(tmp_path):
    output_path = tmp_path / "row_one.csv"
    partial_path = case_study_benchmark.case_study_partial_path(output_path)
    partial_manifest_path = case_study_benchmark.case_study_manifest_path(partial_path)

    def fail_first_run(**_kwargs):
        assert partial_path.exists()
        with partial_path.open(newline="") as handle:
            assert list(csv.DictReader(handle)) == []
        running_manifest = json.loads(partial_manifest_path.read_text(encoding="utf-8"))
        assert running_manifest["run"]["status"] == "running"
        assert running_manifest["run"]["completed_rows"] == 0
        raise RuntimeError("failed immediately")

    with pytest.raises(RuntimeError, match="failed immediately"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0,),
            cstr_grid_sizes=(5,),
            output=output_path,
            runners={"cstr": {"dsda": fail_first_run}},
        )

    failed_manifest = json.loads(partial_manifest_path.read_text(encoding="utf-8"))
    assert failed_manifest["run"]["status"] == "failed"
    assert failed_manifest["run"]["completed_rows"] == 0
    assert failed_manifest["run"]["failed_run"] == {
        "run_key": failed_manifest["protocol"]["planned_run_keys"][0],
        "exception_type": "RuntimeError",
        "message": "failed immediately",
    }
    assert not output_path.exists()


def test_resume_validates_and_skips_completed_prefix(tmp_path):
    output_path = _create_one_row_checkpoint(tmp_path)
    resume_calls = []

    records, saved_path = case_study_benchmark.run_case_study_benchmark(
        cases=("cstr",),
        methods=("dsda",),
        seeds=(0, 1),
        cstr_grid_sizes=(5,),
        output=output_path,
        runners={"cstr": {"dsda": _fake_runner("dsda", resume_calls)}},
        resume=True,
    )

    assert saved_path == output_path
    assert [kwargs["seed"] for _, kwargs in resume_calls] == [1]
    assert [record["seed"] for record in records] == [0, 1]
    assert records[0]["best_point"] == [1, 1]
    manifest = json.loads(
        case_study_benchmark.case_study_manifest_path(output_path).read_text(
            encoding="utf-8"
        )
    )
    assert manifest["run"]["status"] == "completed"
    assert manifest["run"]["resume_count"] == 1
    assert (
        manifest["run"]["completed_run_keys"]
        == manifest["protocol"]["planned_run_keys"]
    )
    partial_path = case_study_benchmark.case_study_partial_path(output_path)
    assert not partial_path.exists()
    assert not case_study_benchmark.case_study_manifest_path(partial_path).exists()


def test_interrupt_after_staged_csv_write_keeps_checkpoint_resumable(
    tmp_path,
    monkeypatch,
):
    output_path = tmp_path / "interrupted_staging.csv"
    real_save = case_study_benchmark._atomic_save_results_csv
    save_count = 0

    def interrupt_after_save(records, path):
        nonlocal save_count
        real_save(records, path)
        save_count += 1
        if save_count == 2:
            raise KeyboardInterrupt("interrupted after staged CSV write")

    monkeypatch.setattr(
        case_study_benchmark,
        "_atomic_save_results_csv",
        interrupt_after_save,
    )
    with pytest.raises(KeyboardInterrupt, match="staged CSV"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0,),
            cstr_grid_sizes=(5,),
            output=output_path,
            runners={"cstr": {"dsda": _fake_runner("dsda", [])}},
        )

    monkeypatch.setattr(
        case_study_benchmark,
        "_atomic_save_results_csv",
        real_save,
    )
    resume_calls = []
    records, _ = case_study_benchmark.run_case_study_benchmark(
        cases=("cstr",),
        methods=("dsda",),
        seeds=(0,),
        cstr_grid_sizes=(5,),
        output=output_path,
        runners={"cstr": {"dsda": _fake_runner("dsda", resume_calls)}},
        resume=True,
    )

    assert len(records) == 1
    assert [kwargs["seed"] for _, kwargs in resume_calls] == [0]


def test_resume_recovers_interruption_between_checkpoint_pair_promotions(
    tmp_path,
    monkeypatch,
):
    output_path = tmp_path / "interrupted_promotion.csv"
    partial_path = case_study_benchmark.case_study_partial_path(output_path)
    partial_manifest_path = case_study_benchmark.case_study_manifest_path(partial_path)
    pending_path = case_study_benchmark.case_study_pending_path(partial_path)
    pending_manifest_path = case_study_benchmark.case_study_manifest_path(pending_path)
    real_replace = case_study_benchmark.os.replace
    promotion_count = 0

    def interrupt_manifest_promotion(source, destination):
        nonlocal promotion_count
        if Path(source) == pending_manifest_path and Path(
            destination
        ) == partial_manifest_path:
            promotion_count += 1
            if promotion_count == 2:
                raise KeyboardInterrupt("interrupted between pair promotions")
        return real_replace(source, destination)

    monkeypatch.setattr(
        case_study_benchmark.os,
        "replace",
        interrupt_manifest_promotion,
    )
    with pytest.raises(KeyboardInterrupt, match="between pair promotions"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0,),
            cstr_grid_sizes=(5,),
            output=output_path,
            runners={"cstr": {"dsda": _fake_runner("dsda", [])}},
        )

    monkeypatch.setattr(case_study_benchmark.os, "replace", real_replace)
    resume_calls = []
    records, _ = case_study_benchmark.run_case_study_benchmark(
        cases=("cstr",),
        methods=("dsda",),
        seeds=(0,),
        cstr_grid_sizes=(5,),
        output=output_path,
        runners={"cstr": {"dsda": _fake_runner("dsda", resume_calls)}},
        resume=True,
    )

    assert len(records) == 1
    assert resume_calls == []


@pytest.mark.parametrize("existing_final", (False, True))
def test_resume_recovers_interruption_between_final_pair_promotions(
    tmp_path,
    monkeypatch,
    existing_final,
):
    output_path = tmp_path / "interrupted_finalization.csv"
    partial_path = case_study_benchmark.case_study_partial_path(output_path)
    partial_manifest_path = case_study_benchmark.case_study_manifest_path(partial_path)
    manifest_path = case_study_benchmark.case_study_manifest_path(output_path)
    real_replace = case_study_benchmark.os.replace
    if existing_final:
        output_path.write_text("previous result\n", encoding="utf-8")
        manifest_path.write_text("{}\n", encoding="utf-8")

    def interrupt_manifest_promotion(source, destination):
        if Path(source) == partial_manifest_path and Path(destination) == manifest_path:
            raise KeyboardInterrupt("interrupted between final pair promotions")
        return real_replace(source, destination)

    monkeypatch.setattr(
        case_study_benchmark.os,
        "replace",
        interrupt_manifest_promotion,
    )
    with pytest.raises(KeyboardInterrupt, match="between final pair promotions"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0,),
            cstr_grid_sizes=(5,),
            output=output_path,
            runners={"cstr": {"dsda": _fake_runner("dsda", [])}},
            overwrite=existing_final,
        )

    assert output_path.is_file()
    assert manifest_path.exists() is existing_final
    assert not partial_path.exists()
    assert partial_manifest_path.is_file()

    monkeypatch.setattr(case_study_benchmark.os, "replace", real_replace)
    resume_calls = []
    records, saved_path = case_study_benchmark.run_case_study_benchmark(
        cases=("cstr",),
        methods=("dsda",),
        seeds=(0,),
        cstr_grid_sizes=(5,),
        output=output_path,
        runners={"cstr": {"dsda": _fake_runner("dsda", resume_calls)}},
        resume=True,
        overwrite=existing_final,
    )

    assert len(records) == 1
    assert saved_path == output_path
    assert resume_calls == []
    assert output_path.is_file()
    assert manifest_path.is_file()
    completed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert completed_manifest["run"]["status"] == "completed"
    assert not partial_path.exists()
    assert not partial_manifest_path.exists()


def test_resume_rejects_protocol_mismatch(tmp_path):
    output_path = _create_one_row_checkpoint(tmp_path, "protocol.csv")

    with pytest.raises(ValueError, match="protocol does not match"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0, 2),
            cstr_grid_sizes=(5,),
            output=output_path,
            runners={"cstr": {"dsda": _fake_runner("dsda", [])}},
            resume=True,
        )


def test_resume_requires_both_partial_csv_and_manifest(tmp_path):
    output_path = tmp_path / "missing_manifest.csv"
    partial_path = case_study_benchmark.case_study_partial_path(output_path)
    case_study_benchmark._atomic_save_results_csv([], partial_path)

    with pytest.raises(FileNotFoundError, match="requires both checkpoint files"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0,),
            cstr_grid_sizes=(5,),
            output=output_path,
            runners={"cstr": {"dsda": _fake_runner("dsda", [])}},
            resume=True,
        )


def test_resume_rejects_schema_and_completed_prefix_tampering(tmp_path):
    schema_output = _create_one_row_checkpoint(tmp_path, "schema.csv")
    schema_partial = case_study_benchmark.case_study_partial_path(schema_output)
    schema_manifest_path = case_study_benchmark.case_study_manifest_path(schema_partial)
    schema_manifest = json.loads(schema_manifest_path.read_text(encoding="utf-8"))
    schema_manifest["schema"]["fields"] = schema_manifest["schema"]["fields"][:-1]
    schema_manifest_path.write_text(json.dumps(schema_manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="schema does not match"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0, 1),
            cstr_grid_sizes=(5,),
            output=schema_output,
            runners={"cstr": {"dsda": _fake_runner("dsda", [])}},
            resume=True,
        )

    prefix_output = _create_one_row_checkpoint(tmp_path, "prefix.csv")
    prefix_partial = case_study_benchmark.case_study_partial_path(prefix_output)
    prefix_manifest_path = case_study_benchmark.case_study_manifest_path(prefix_partial)
    prefix_manifest = json.loads(prefix_manifest_path.read_text(encoding="utf-8"))
    prefix_manifest["run"]["completed_run_keys"] = [
        prefix_manifest["protocol"]["planned_run_keys"][1]
    ]
    prefix_manifest_path.write_text(json.dumps(prefix_manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="not the planned prefix"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0, 1),
            cstr_grid_sizes=(5,),
            output=prefix_output,
            runners={"cstr": {"dsda": _fake_runner("dsda", [])}},
            resume=True,
        )


def test_resume_rejects_checkpoint_csv_tampering(tmp_path):
    output_path = _create_one_row_checkpoint(tmp_path, "tampered.csv")
    partial_path = case_study_benchmark.case_study_partial_path(output_path)
    original_bytes = partial_path.read_bytes()
    tampered_bytes = original_bytes.replace(b",1.0,", b",2.0,", 1)
    assert tampered_bytes != original_bytes
    assert len(tampered_bytes) == len(original_bytes)
    partial_path.write_bytes(tampered_bytes)

    with pytest.raises(ValueError, match="checksum does not match"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0, 1),
            cstr_grid_sizes=(5,),
            output=output_path,
            runners={"cstr": {"dsda": _fake_runner("dsda", [])}},
            resume=True,
        )


def test_existing_final_output_requires_explicit_overwrite(tmp_path):
    output_path = tmp_path / "protected.csv"
    output_path.write_text("old result\n", encoding="utf-8")
    calls = []
    runners = {"cstr": {"dsda": _fake_runner("dsda", calls)}}

    with pytest.raises(FileExistsError, match="Pass overwrite=True"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0,),
            cstr_grid_sizes=(5,),
            output=output_path,
            runners=runners,
        )
    assert calls == []
    assert output_path.read_text(encoding="utf-8") == "old result\n"

    case_study_benchmark.run_case_study_benchmark(
        cases=("cstr",),
        methods=("dsda",),
        seeds=(0,),
        cstr_grid_sizes=(5,),
        output=output_path,
        runners=runners,
        overwrite=True,
    )
    assert output_path.read_text(encoding="utf-8").startswith("csv_name,method,")


@pytest.mark.parametrize(
    "parameter_name",
    (
        "seeds",
        "column_seeds",
        "column_budgets",
        "cstr_grid_sizes",
        "small_batch_budgets",
        "dynamic_budgets",
    ),
)
def test_duplicate_integer_inputs_are_rejected(parameter_name):
    with pytest.raises(
        ValueError, match=f"{parameter_name} must not contain duplicates"
    ):
        case_study_benchmark.build_run_matrix(**{parameter_name: (1, 1)})


def test_duplicate_cases_methods_and_planned_keys_are_rejected(tmp_path):
    with pytest.raises(
        case_study_benchmark.argparse.ArgumentTypeError,
        match="cases must not contain duplicates",
    ):
        case_study_benchmark.parse_cases("cstr,cstr")
    with pytest.raises(
        case_study_benchmark.argparse.ArgumentTypeError,
        match="methods must not contain duplicates",
    ):
        case_study_benchmark.parse_unique_methods("dsda,dsda")
    duplicate_row = {
        "case_name": "cstr",
        "grid_size": 5,
        "seed": 0,
        "max_evaluations": 8,
    }
    with pytest.raises(ValueError, match="run keys must be unique"):
        case_study_benchmark._planned_run_keys(
            [duplicate_row, duplicate_row],
            ("dsda",),
            n_starts=3,
        )


@pytest.mark.parametrize("n_starts", (True, 3.0, 3.5, "3", 0, -1))
def test_n_starts_must_be_a_positive_integer(n_starts, tmp_path):
    with pytest.raises(ValueError, match="n_starts must be a positive integer"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0,),
            cstr_grid_sizes=(5,),
            n_starts=n_starts,
            output=tmp_path / "invalid_n_starts.csv",
            runners={"cstr": {"dsda": _fake_runner("dsda", [])}},
        )


@pytest.mark.parametrize("invalid_value", (True, 1.0, 1.5, "1"))
def test_integer_iterables_reject_bool_and_non_integral_values(invalid_value):
    with pytest.raises(ValueError, match="seeds must contain only integers"):
        case_study_benchmark.build_run_matrix(seeds=(invalid_value,))


@pytest.mark.parametrize("parameter_name", ("seeds", "column_seeds"))
def test_seed_inputs_must_be_nonnegative(parameter_name):
    with pytest.raises(ValueError, match="must contain only nonnegative integers"):
        case_study_benchmark.build_run_matrix(**{parameter_name: (-1,)})


@pytest.mark.parametrize(
    "parameter_name",
    (
        "column_budgets",
        "cstr_grid_sizes",
        "small_batch_budgets",
        "dynamic_budgets",
    ),
)
def test_budget_and_grid_inputs_must_be_positive(parameter_name):
    with pytest.raises(ValueError, match="must contain only positive integers"):
        case_study_benchmark.build_run_matrix(**{parameter_name: (0,)})


def test_configured_solver_provenance_uses_only_basename_and_hash(tmp_path):
    minlp_path = tmp_path / "bonmin"
    nlp_path = tmp_path / "ipopt"
    minlp_path.write_bytes(b"minlp executable")
    nlp_path.write_bytes(b"nlp executable")

    configuration = case_study_benchmark._method_configuration(
        cases=("cstr",),
        methods=("rbfopt",),
        algorithm=None,
        rbf="auto",
        global_search_method=None,
        diagonal=True,
        tie_break="first",
        verbose=True,
        minlp_solver_path=minlp_path,
        nlp_solver_path=nlp_path,
        bam_license_file=None,
        rbfopt_module=None,
        bam_module=None,
    )["rbfopt"]

    assert configuration["verbose"] is True
    assert configuration["external_solver_executables"] == {
        "minlp": {
            "basename": "bonmin",
            "sha256": hashlib.sha256(b"minlp executable").hexdigest(),
        },
        "nlp": {
            "basename": "ipopt",
            "sha256": hashlib.sha256(b"nlp executable").hexdigest(),
        },
    }
    assert str(tmp_path) not in json.dumps(configuration)
    with pytest.raises(ValueError, match="methods must not contain duplicates"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda", "dsda"),
            seeds=(0,),
            cstr_grid_sizes=(5,),
            output=tmp_path / "duplicates.csv",
            runners={"cstr": {"dsda": _fake_runner("dsda", [])}},
        )


@pytest.mark.skipif(
    not hasattr(signal, "setitimer"),
    reason="POSIX interval timers are required",
)
def test_max_run_seconds_times_out_and_restores_signal_state(tmp_path):
    output_path = tmp_path / "timeout.csv"
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def slow_runner(**_kwargs):
        time.sleep(0.2)

    with pytest.raises(case_study_benchmark.RunTimeoutError):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0,),
            cstr_grid_sizes=(5,),
            output=output_path,
            runners={"cstr": {"dsda": slow_runner}},
            max_run_seconds=0.02,
        )

    assert signal.getsignal(signal.SIGALRM) == previous_handler
    if previous_timer == (0.0, 0.0):
        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    partial_path = case_study_benchmark.case_study_partial_path(output_path)
    failed_manifest = json.loads(
        case_study_benchmark.case_study_manifest_path(partial_path).read_text(
            encoding="utf-8"
        )
    )
    assert failed_manifest["protocol"]["max_run_seconds"] == 0.02
    assert failed_manifest["run"]["completed_rows"] == 0
    assert failed_manifest["run"]["failed_run"]["exception_type"] == ("RunTimeoutError")


@pytest.mark.parametrize("value", (0, -1, float("inf"), float("nan"), True))
def test_max_run_seconds_must_be_positive_and_finite(value, tmp_path):
    with pytest.raises(ValueError, match="positive finite"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("cstr",),
            methods=("dsda",),
            seeds=(0,),
            cstr_grid_sizes=(5,),
            output=tmp_path / "invalid_timeout.csv",
            runners={"cstr": {"dsda": _fake_runner("dsda", [])}},
            max_run_seconds=value,
        )


def test_failed_manifest_redacts_bam_license_path(tmp_path):
    output_path = tmp_path / "redacted.csv"
    sensitive_path = tmp_path / "secret-license.lic"

    def fail_with_license_path(**_kwargs):
        raise RuntimeError(f"BAM rejected {sensitive_path.resolve()}")

    with pytest.raises(RuntimeError, match="BAM rejected"):
        case_study_benchmark.run_case_study_benchmark(
            cases=("small_batch",),
            methods=("bam",),
            seeds=(0,),
            small_batch_budgets=(10,),
            output=output_path,
            bam_license_file=sensitive_path,
            bam_module=object(),
            runners={"small_batch": {"bam": fail_with_license_path}},
        )

    partial_path = case_study_benchmark.case_study_partial_path(output_path)
    manifest_text = case_study_benchmark.case_study_manifest_path(
        partial_path
    ).read_text(encoding="utf-8")
    assert str(sensitive_path.resolve()) not in manifest_text
    assert "<redacted>" in manifest_text


def test_manifest_paths_are_repo_relative_when_possible():
    repo_result = case_study_benchmark.BASE_DIR / "results" / "portable.csv"

    assert case_study_benchmark._portable_path(repo_result) == ("results/portable.csv")
