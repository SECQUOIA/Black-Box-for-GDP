"""Immutable-data audit regressions; all optimizer imports are prohibited."""

import copy
import importlib.abc
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pr56_return_analysis", ROOT / "scripts/analyze_pr56_dantzig_return.py"
)
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)
EVIDENCE = ROOT / "results/pr56_dantzig_return_20261031/evidence"


class OptimizerBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {
            "PyNomad",
            "soogo",
            "pyomo",
            "pyscipopt",
            "cyipopt",
            "rbfopt",
            "gams",
            "pymoo",
        }:
            raise AssertionError(
                f"Analysis attempted an optimizer/model import: {fullname}"
            )


@pytest.fixture(scope="module")
def analyzed():
    blocker = OptimizerBlocker()
    sys.meta_path.insert(0, blocker)
    try:
        return A.analyze(EVIDENCE / "RETURN.zip", EVIDENCE)
    finally:
        sys.meta_path.remove(blocker)


def test_all_returned_records_are_independently_audited(analyzed):
    summary, audit, tables = analyzed
    assert audit["validation_passed"]
    assert audit["internal_members_verified"] == 11229
    assert audit["sealed_members_verified"] == 263
    assert audit["mi_results"] == 2380 and audit["dsda_results"] == 420
    assert audit["preflight_passed"] == 12 and audit["preflight_skipped"] == 0
    assert len(tables["individual_new_runs"]) == 2380
    assert summary["methods"]["miso"]["hits"] == 798
    assert summary["methods"]["nomad"]["hits"] == 618


def test_restart_changes_are_eleven_jobs_and_zero_new_hits(analyzed):
    summary, _, tables = analyzed
    dsda = summary["dsda"]
    assert dsda["replay_matched"] == 140
    assert dsda["changed_variant_comparisons"] == 22
    assert dsda["changed_unique_jobs"] == 11 and dsda["changed_hits"] == 0
    assert all(row["hits"] == 74 for row in dsda["variant_summaries"])
    assert all(
        row["improvement"] > 0 and not row["single_hit"] and not row["restart_hit"]
        for row in tables["dsda_changes"]
    )


def test_native_retry_counts_and_missing_times_remain_visible(analyzed):
    summary, _, tables = analyzed
    nomad = summary["methods"]["nomad"]
    assert nomad["statuses"] == {
        "completed": 1046,
        "completed_after_verified_rerun": 123,
        "crashed_identical_reruns": 21,
    }
    assert nomad["native_attempts"] == 1368 and nomad["native_crash_attempts"] == 199
    assert nomad["missing_times"] == 21
    crashed = tables["nomad_terminal_crashes"]
    assert len(crashed) == 21 and sum(r["hit"] for r in crashed) == 16
    assert all(
        r["completion_s"] is None and r["retained_search_s"] is None for r in crashed
    )
    assert (
        sum(
            r["terminal_crash_as_failure_hits"]
            for r in tables["nomad_crash_sensitivity"]
        )
        == 602
    )


def test_primary_rbfopt_is_genetic_not_solver_control(analyzed):
    _, _, tables = analyzed
    old = tables["historical_primary_runs"]
    controls = tables["historical_control_runs"]
    assert len(old) == 5950 and len(controls) == 2240
    assert all(r["method"] != "rbfopt_msrsm_solver" for r in old)
    assert (
        sum(
            r["hit"]
            for r in old
            if r["method"] == "rbfopt_msrsm_genetic" and r["scope"] == "process"
        )
        == 114
    )
    assert any(r["case"] == "column" and r["budget"] == 16 for r in controls)


def test_process_seed_pairs_and_multiplicity_are_explicit(analyzed):
    _, _, tables = analyzed
    assert len(tables["process_pairs"]) == 700
    assert len(tables["process_paired_tests"]) == 70
    assert all(
        r["pairs"] == 10 and r["p_holm_70"] >= r["p_exact"]
        for r in tables["process_paired_tests"]
    )
    assert not any(r["p_holm_70"] < 0.05 for r in tables["process_paired_tests"])


def test_expanded_process_cohort_excludes_retries_and_restart_diagnostic(analyzed):
    summary, _, tables = analyzed
    cohort = summary["combined_primary_process"]
    assert cohort["runs"] == 980
    assert cohort["historical_callbacks"] == 16041
    assert cohort["historical_distinct_configurations"] == 2024
    assert cohort["combined_callbacks"] == 21777
    assert cohort["combined_distinct_configurations"] == 2106
    assert cohort["nomad_callbacks"] == 2336 and cohort["miso_callbacks"] == 3400
    assert len(tables["combined_configuration_coverage"]) == 2438


def test_frozen_source_or_return_bytes_cannot_be_silently_changed(tmp_path):
    fake = tmp_path / "changed.zip"
    fake.write_bytes(b"changed artifact")
    with pytest.raises(A.AuditError, match="SHA256 mismatch"):
        A.Evidence(fake, EVIDENCE)


def fixture():
    job = {
        "spec": {"budget": 4, "starts": [[0], [1], [2]], "lower": [0], "upper": [2]},
        "target": 0.0,
        "baseline": {"prep_s": "0"},
    }
    events = [
        dict(
            index=i + 1,
            point=[i],
            accepted=True,
            raw_objective=float(i),
            method_value=float(i),
            lookup_wall_s=0.1,
            point_cost_s=1.0,
            nlp_solve=True,
            origin="shared_start",
        )
        for i in range(3)
    ]
    responses = {(i,): (True, float(i), 1.0, True) for i in range(3)}
    return job, events, responses


@pytest.mark.parametrize(
    "mutation", ["coordinate", "order", "budget", "penalty", "point_cost"]
)
def test_corrupted_callback_accounting_is_rejected(mutation):
    job, events, responses = fixture()
    if mutation == "coordinate":
        events[-1]["point"] = [3]
    elif mutation == "order":
        events[0], events[1] = events[1], events[0]
    elif mutation == "budget":
        job["spec"]["budget"] = 2
    elif mutation == "penalty":
        events[0]["method_value"] = 1e6
    else:
        events[0]["point_cost_s"] = 0
    with pytest.raises(A.AuditError):
        A.audit_events(job, events, responses, "fixture", True)


def test_verified_retry_uses_retry_lookup_time():
    job, original, _ = fixture()
    retry = copy.deepcopy(original)
    for event in retry:
        event["lookup_wall_s"] = 0.01
    metrics = A.recompute(
        job, {"search_s": 2.0}, original, retry, [1.0, 1.0, 1.0], [True] * 3, True
    )
    assert metrics["retained_search_s"] == pytest.approx(1.97)
    assert metrics["completion_s"] == pytest.approx(4.97)


def test_repeated_crash_scores_path_but_does_not_invent_time():
    job, events, _ = fixture()
    metrics = A.recompute(
        job, {"search_s": None}, events, events, [1.0, 1.0, 1.0], [True] * 3, True
    )
    assert metrics["hit"] and metrics["first_hit"] == 1
    assert metrics["completion_s"] is None and metrics["retained_search_s"] is None


def test_inclusive_quartiles_do_not_treat_missing_as_zero():
    assert A.quantile([None, 10, 20], 0.25) == 12.5
    assert A.quantile([None, None], 0.5) is None


def test_exact_tests_and_holm_known_values():
    assert A.exact_mcnemar(0, 0) == 1
    assert A.exact_mcnemar(6, 0) == 0.03125
    assert A.exact_mcnemar(3, 1) == 0.625
    assert A.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
