"""Audit native solver evidence and select only the requested replacement runs."""

import math

import pytest

from scripts.import_small_batch_full_domain import ROOT, audit, verify_archive
from scripts.import_small_batch_rbfopt_solver import FILES
import small_batch_rbfopt_solver as experiment


def test_solver_archive_reconciles_seals_sources_callbacks_and_native_calls(tmp_path):
    archive = ROOT / "results/archives/small_batch_rbfopt_solver_20261013_172454_czzqkizx.zip"
    count = verify_archive(archive, tmp_path)
    result = audit(tmp_path, count, experiment=experiment, files=FILES)
    assert count == 180 and result["executed_source_files_verified"] == 101
    assert result["callback_counts"] == {"rbfopt": 100}
    assert result["methods"][0]["target_hits"] == 5
    assert result["methods"][0]["infeasible_evaluations"] == 35
    assert result["methods"][0]["repeated_evaluations"] == 0
    traces = [run["auxiliary_solver_trace"] for run in result["runs"]]
    assert sum(trace["calls_by_solver"]["bonmin"] for trace in traces) == 72
    assert sum(trace["exceptions"] + trace["nonoptimal_calls"] for trace in traces) == 0
    assert result["methods"][0]["tts99_s"] == pytest.approx(42.10879001439753)
    calls = tmp_path / "auxiliary_solver_calls.csv"
    calls.write_text(calls.read_text().replace("optimal", "infeasible", 1))
    with pytest.raises(ValueError, match="Aggregate CSV differs"):
        audit(tmp_path, count, experiment=experiment, files=FILES)


def test_publication_replaces_only_small_batch_rbfopt_and_preserves_cost_coverage():
    from scripts.plot_dantzig_cost_breakdown import SOLVER_BATCH, full_batch_runs, load_runs, read_csv
    from scripts.plot_dantzig_performance import PANELS, performance_tables
    historical, _ = full_batch_runs()
    current, _, _, _, manifest = load_runs(PANELS)
    # The two unaffected methods still use the original full-domain runs verbatim.
    for row in historical:
        if row["method"] in {"dsda", "bam"}:
            assert next(r for r in current if r["job_id"] == row["job_id"]) == row
    batch = [r for r in current if r["case"] == "small_batch" and r["method"] == "rbfopt"]
    expected = experiment.plan()
    assert len(batch) == 10 and {r["job_id"] for r in batch} == {s["job_id"] for s in expected}
    assert not {r["job_id"] for r in historical if r["method"] == "rbfopt"} & {r["job_id"] for r in current}
    events = read_csv(SOLVER_BATCH / "evaluation_costs.csv")
    assert len(events) == 100
    for row in batch:
        group = [event for event in events if event["job_id"] == row["job_id"]]
        assert len(group) == 10
        cost = row["recorded_dfo_s"] + math.fsum(float(e["point_evaluation_s"]) - float(e["objective_wall_s"])
                                               for e in group)
        assert row["estimated_total_s"] == pytest.approx(cost, rel=1e-12)
    profiles, summaries = performance_tables(current)
    result = next(r for r in summaries if r["case"] == "small_batch" and r["method"] == "rbfopt")
    assert result["target_hits"] == 5 and result["runs_99"] == 7
    assert result["median_completion_s"] == pytest.approx(6.015541430628218)
    assert result["tts99_s"] == pytest.approx(42.10879001439753)
    assert sum(math.isinf(r["profile_completion_s"]) for r in profiles
               if r["case"] == "small_batch" and r["method"] == "rbfopt") == 5
    assert len(manifest["followup_selection"]["superseded_small_batch_rbfopt_job_ids"]) == 10
