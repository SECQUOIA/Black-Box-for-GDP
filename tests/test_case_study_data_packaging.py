"""Tests for packaged process case-study data."""

from importlib import resources

import case_study_data.column as column_data
import case_study_data.cstr as cstr_data
import case_study_data.small_batch as small_batch_data


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
