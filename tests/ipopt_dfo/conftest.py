"""Explicit prerequisites for historical replay tests in a source-only PR."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def pytest_collection_modifyitems(items):
    for item in items:
        name = item.path.name
        reason = None
        if name in {"test_ipopt_dfo_cstr.py", "test_ipopt_dfo_non_cstr.py"}:
            if "frozen" in item.fixturenames or item.originalname == "test_bam_only_bundle_keeps_every_seed_and_preflights_only_bam":
                required = [ROOT / "evaluation_trace.py", ROOT / "cpu_affinity.py",
                            ROOT / "fmqa_benchmark/optimizer.py",
                            ROOT / "results/dantzig_review/gams_cstr_audit_20260922/dantzig_gdp_gams_20260922_050038_p4q8hy54"]
                if name == "test_ipopt_dfo_cstr.py":
                    required += [ROOT / "results/cstr_box_ipopt/dantzig_cstr_box_ipopt_20261015_155116_eqpg0g41.zip",
                                 ROOT / "results/archives/dantzig_cstr_box_ipopt_20261015_162507_3bnp0xm3.zip"]
                if any(not p.exists() for p in required):
                    reason = "Historical bundle replay requires #27/#29, separate FMQA integration, and frozen Benchmark inputs"
            if item.originalname == "test_cpu_selection_excludes_non_cstr_and_physical_sibling" and not (ROOT / "cpu_affinity.py").exists():
                reason = "CPU adapter is supplied by issue #27"
        if reason:
            item.add_marker(pytest.mark.skip(reason=reason))
