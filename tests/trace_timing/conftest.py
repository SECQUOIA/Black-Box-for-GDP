"""Explicit prerequisites for historical replay tests in a source-only PR."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def pytest_collection_modifyitems(items):
    for item in items:
        name = item.path.name
        reason = None
        if name == "test_cstr30_structural_rejections.py" and "bundle" in item.fixturenames:
            if not (ROOT / "results/archives/ipopt_dfo_cstr_20261015_174637_r1dzn5tk.zip").exists():
                reason = "Structural overlay replay requires immutable Benchmark archives, excluded from this PR"
        if name == "test_cstr_box_ipopt.py" and item.originalname in {
            "test_audited_upstream_hashes_match_local_models",
            "test_feasible_start_preserves_model_and_satisfies_original_constraints",
            "test_logically_impossible_point_is_measured_without_solver",
            "test_bundle_contains_verified_sources_and_selected_plan",
        } and importlib.util.find_spec("gdp_models") is None:
            reason = "Process model integration is supplied by issue #27"
        if name == "test_nlp_cost_analysis.py" and importlib.util.find_spec("gdp_models") is None:
            reason = "Cost reconstruction uses process domain mapping from issue #27"
        if name == "test_cstr_box_ipopt.py" and item.originalname == "test_partial_run_exports_pending_and_failed_coordinates_and_resumes" and importlib.util.find_spec("gdp_models") is None:
            reason = "Checkpoint formatting uses the process batch interface from issue #27"
        if name == "test_enumerate_process_ipopt.py":
            if item.originalname not in {"test_plans_cover_every_dfo_coordinate", "test_failure_limit_and_exception_states_stay_distinct"} and importlib.util.find_spec("gdp_models") is None:
                reason = "Evaluation integration requires issue #27"
            if item.originalname in {"test_original_model_and_reference_hashes_match", "test_resume_never_repeats_completed_points_and_compares_new_values"} and not (ROOT / "results/ipopt_dfo_non_cstr_20261015_172428_o671edu_/inputs").exists():
                reason = "Historical reference comparison requires frozen Benchmark input tables"
        if reason:
            item.add_marker(pytest.mark.skip(reason=reason))
