"""Tests for packaged process case-study data."""

import json
from importlib import resources
from pathlib import Path

import case_study_data.column as column_data
import case_study_data.cstr as cstr_data
import case_study_data.small_batch as small_batch_data


ROOT = Path(__file__).resolve().parents[1]


def test_case_study_data_csvs_are_packaged():
    """Relocated completed-enumeration CSVs should be importable package data."""
    assert (
        resources.files(column_data) / "compl_enum_column_17_baron.csv"
    ).is_file()
    assert (
        resources.files(cstr_data) / "compl_enum_cstr_30_baron_hull.csv"
    ).is_file()
    assert (
        resources.files(small_batch_data) / "compl_enum_small_batch_baron.csv"
    ).is_file()


def test_case_study_notebooks_use_relocated_csv_paths():
    """Notebook workflows should keep pointing at relocated case-study CSVs."""
    notebook_expectations = {
        "rbfopt_test_batch.ipynb": (
            "case_study_data/small_batch/compl_enum_small_batch_baron.csv",
            "compl_enum_small_batch_baron.csv",
        ),
        "rbfopt_test_column.ipynb": (
            "case_study_data/column/compl_enum_column_17_baron.csv",
            "compl_enum_column_17_baron.csv",
        ),
        "rbfopt_test_cstr.ipynb": (
            "case_study_data/cstr/compl_enum_cstr_30_baron_hull.csv",
            "compl_enum_cstr_30_baron_hull.csv",
        ),
    }

    for notebook_name, (expected_path, old_filename) in notebook_expectations.items():
        notebook = json.loads((ROOT / notebook_name).read_text())
        source = "\n".join(
            "".join(cell.get("source", [])) for cell in notebook["cells"]
        )

        assert expected_path in source
        assert f'filename="{old_filename}"' not in source
        assert f"filename='{old_filename}'" not in source
        assert f"pd.read_csv('{old_filename}'" not in source
        assert f'pd.read_csv("{old_filename}"' not in source
