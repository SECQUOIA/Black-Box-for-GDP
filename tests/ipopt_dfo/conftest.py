"""Only later CSTR archives are optional; committed original inputs must validate."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def isolate_worker_import_guard(monkeypatch):
    # Workers normally exit in their own process. In-process tests must not
    # leave their process-model import blocker installed in subsequent tests.
    monkeypatch.setattr(sys, 'meta_path', list(sys.meta_path))


def pytest_collection_modifyitems(items):
    small = ROOT / 'results/cstr_box_ipopt/dantzig_cstr_box_ipopt_20261015_155116_eqpg0g41.zip'
    large = ROOT / 'results/archives/dantzig_cstr_box_ipopt_20261015_162507_3bnp0xm3.zip'
    for item in items:
        if item.path.name != 'test_ipopt_dfo_cstr.py':
            continue
        required = []
        if item.originalname in {
            'test_model_procedure_duplicate_and_acceptance_validation',
            'test_n10_rejection_keeps_candidate_status_and_matching_cost',
        }:
            required = [small]
        elif item.originalname in {
            'test_measured_n20_exclusion_does_not_fill_missing_breakdown',
            'test_incomplete_size_stays_not_run_while_ready_size_proceeds',
        }:
            required = [large]
        elif item.originalname == 'test_input_reports_keep_minima_and_all_failures':
            required = [small, large]
        elif item.originalname == 'test_frozen_sources_and_no_executable_process_models':
            size = int(item.callspec.params['case'].split('_')[1])
            required = [small] if size < 20 else [large] if size < 30 else []
        if any(not path.exists() for path in required):
            item.add_marker(pytest.mark.skip(reason=
                'This case needs later size-specific CSTR archives supplied by final result PR #37'))
